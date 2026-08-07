"""Load and validate a challenge YAML into plain dataclasses.

Two challenge types: "ticklist" (flat route list, e.g. a gritstone circuit)
and "enchainment" (typed stage sequence: climb/walk/scramble/decision).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from gen.estimates import naismith_langmuir


class ChallengeError(Exception):
    pass


def slugify(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


@dataclass
class Route:
    number: int
    name: str
    grade: str
    stars: int
    height_m: int
    ukc: str
    sector: str
    description: str = ""
    descent: str = ""
    to_next: str = ""
    topo: str | None = None
    slug: str = field(init=False)

    def __post_init__(self):
        self.slug = slugify(self.name)


@dataclass
class Sector:
    name: str
    routes: list[Route]


@dataclass
class Block:
    start: int
    leader: str


@dataclass
class Challenge:
    type = "ticklist"
    name: str
    slug: str
    target_hours: float
    notes: str
    ukc_ticklist: str
    leaders: list[str]
    blocks: list[Block]
    sectors: list[Sector]
    directory: Path

    @property
    def routes(self) -> list[Route]:
        return [r for s in self.sectors for r in s.routes]

    def leader_for(self, number: int) -> str:
        leader = self.blocks[0].leader
        for b in self.blocks:
            if b.start <= number:
                leader = b.leader
        return leader

    def changeover_before(self, number: int) -> bool:
        return any(b.start == number for b in self.blocks[1:])


# --- Enchainment stages ---

@dataclass
class Pitch:
    index: int
    grade: str
    length_m: int
    note: str = ""


@dataclass
class ClimbStage:
    kind = "climb"
    id: str
    name: str
    grade: str
    stars: int
    height_m: int
    ukc: str
    sector: str
    pitches: list[Pitch]
    first_lead: str
    estimate_min: int
    description: str = ""
    escape: str = ""
    topo: str | None = None
    end_elev_m: int | None = None
    distance_km: float = 0.05  # nominal horizontal distance for the profile


@dataclass
class WalkStage:
    kind = "walk"
    id: str
    name: str
    distance_km: float
    ascent_m: int
    descent_m: int
    terrain: str
    estimate_min: int
    bearing: str = ""
    escape: str = ""
    note: str = ""
    end_elev_m: int | None = None
    grade: str = ""  # scramble grade when kind == "scramble"


@dataclass
class ScrambleStage(WalkStage):
    kind = "scramble"


@dataclass
class DecisionOption:
    name: str
    stages: list


@dataclass
class DecisionStage:
    kind = "decision"
    id: str
    name: str
    options: list[DecisionOption]
    note: str = ""


@dataclass
class Enchainment:
    type = "enchainment"
    name: str
    slug: str
    target_hours: float
    notes: str
    leaders: list[str]
    start_elev_m: int
    stages: list
    directory: Path

    def all_stages(self):
        """Every stage including those inside decision branches."""
        out = []
        for s in self.stages:
            out.append(s)
            if s.kind == "decision":
                for o in s.options:
                    out.extend(o.stages)
        return out

    def paths(self):
        """(choice-dict, flat stage list) per combination of decision options."""
        paths = [({}, [])]
        for s in self.stages:
            if s.kind != "decision":
                for _, stages in paths:
                    stages.append(s)
            else:
                paths = [
                    ({**choice, s.id: i}, stages + list(o.stages))
                    for choice, stages in paths
                    for i, o in enumerate(s.options)
                ]
        return paths

    @property
    def climbs(self):
        return [s for s in self.all_stages() if s.kind == "climb"]


def _load_stage(sdata: dict, ids: set[str], index: int, leaders: list[str],
                depth: int = 0):
    (kind, body), = sdata.items()
    name = body["name"]
    sid = f"s{index:02d}-{slugify(name)}"
    if sid in ids:
        raise ChallengeError(f"duplicate stage id: {sid}")
    ids.add(sid)

    if kind == "decision":
        if depth > 0:
            raise ChallengeError(f"{name}: nested decisions are not supported")
        options = []
        for oi, o in enumerate(body["options"]):
            stages = []
            for i, inner in enumerate(o["stages"]):
                stages.append(_load_stage(inner, ids, index * 100 + oi * 10 + i + 1,
                                          leaders, depth + 1))
            options.append(DecisionOption(name=o["name"], stages=stages))
        if len(options) < 2:
            raise ChallengeError(f"{name}: a decision needs at least 2 options")
        return DecisionStage(id=sid, name=name, options=options,
                             note=body.get("note", ""))

    if kind == "climb":
        pitches = [
            Pitch(index=i + 1, grade=str(p.get("grade", "")),
                  length_m=int(p.get("length_m", 0)), note=p.get("note", ""))
            for i, p in enumerate(body.get("pitches", []))
        ]
        if not pitches:
            raise ChallengeError(f"{name}: climb stages need a pitches list")
        first_lead = body.get("first_lead") or leaders[0]
        if first_lead not in leaders:
            raise ChallengeError(f"{name}: unknown first_lead {first_lead}")
        estimate = int(body.get("estimate_min") or (len(pitches) * 25 + 15))
        return ClimbStage(
            id=sid, name=name, grade=body["grade"], stars=int(body.get("stars", 0)),
            height_m=int(body["height_m"]), ukc=body.get("ukc", ""),
            sector=body.get("sector", ""), pitches=pitches, first_lead=first_lead,
            estimate_min=estimate, description=body.get("description") or "",
            escape=body.get("escape") or "", topo=body.get("topo"),
            end_elev_m=body.get("end_elev_m"),
        )

    if kind in ("walk", "scramble"):
        cls = ScrambleStage if kind == "scramble" else WalkStage
        terrain = body.get("terrain", "scramble" if kind == "scramble" else "path")
        distance = float(body["distance_km"])
        ascent = int(body.get("ascent_m", 0))
        descent = int(body.get("descent_m", 0))
        estimate = int(body.get("estimate_min")
                       or naismith_langmuir(distance, ascent, descent, terrain))
        return cls(
            id=sid, name=name, distance_km=distance, ascent_m=ascent,
            descent_m=descent, terrain=terrain, estimate_min=estimate,
            bearing=body.get("bearing") or "", escape=body.get("escape") or "",
            note=body.get("note") or "", end_elev_m=body.get("end_elev_m"),
            grade=body.get("grade", ""),
        )

    raise ChallengeError(f"unknown stage kind: {kind}")


def _load_enchainment(data: dict, path: Path) -> Enchainment:
    leaders = data.get("leaders") or []
    if len(leaders) < 1:
        raise ChallengeError("enchainment needs a leaders list")
    ids: set[str] = set()
    stages = [_load_stage(s, ids, i + 1, leaders)
              for i, s in enumerate(data.get("stages", []))]
    if not stages:
        raise ChallengeError("enchainment has no stages")
    return Enchainment(
        name=data["name"],
        slug=data["slug"],
        target_hours=float(data.get("target_hours", 12)),
        notes=data.get("notes", "").strip(),
        leaders=leaders,
        start_elev_m=int(data.get("start_elev_m", 0)),
        stages=stages,
        directory=path.parent,
    )


def load_challenge(path: Path) -> Challenge | Enchainment:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    if data.get("type") == "enchainment":
        return _load_enchainment(data, path)

    sectors: list[Sector] = []
    number = 0
    names_seen: set[str] = set()
    for sdata in data.get("sectors", []):
        routes = []
        for rdata in sdata.get("routes", []):
            number += 1
            name = rdata["name"]
            if name in names_seen:
                raise ChallengeError(f"duplicate route name: {name}")
            names_seen.add(name)
            stars = int(rdata["stars"])
            if not 0 <= stars <= 3:
                raise ChallengeError(f"{name}: stars must be 0-3, got {stars}")
            routes.append(
                Route(
                    number=number,
                    name=name,
                    grade=rdata["grade"],
                    stars=stars,
                    height_m=int(rdata["height_m"]),
                    ukc=rdata["ukc"],
                    sector=sdata["name"],
                    description=rdata.get("description") or "",
                    descent=rdata.get("descent") or "",
                    to_next=rdata.get("to_next") or "",
                    topo=rdata.get("topo"),
                )
            )
        sectors.append(Sector(name=sdata["name"], routes=routes))

    leaders = data.get("leaders") or []
    blocks = [Block(start=int(b["from"]), leader=b["leader"]) for b in data.get("blocks", [])]
    if not blocks or blocks[0].start != 1:
        raise ChallengeError("first block must start from route 1")
    if [b.start for b in blocks] != sorted({b.start for b in blocks}):
        raise ChallengeError("block starts must be ascending and unique")
    for b in blocks:
        if b.leader not in leaders:
            raise ChallengeError(f"block leader not in leaders list: {b.leader}")
        if not 1 <= b.start <= number:
            raise ChallengeError(f"block start out of range: {b.start}")

    return Challenge(
        name=data["name"],
        slug=data["slug"],
        target_hours=float(data.get("target_hours", 10)),
        notes=data.get("notes", "").strip(),
        ukc_ticklist=data.get("ukc_ticklist", ""),
        leaders=leaders,
        blocks=blocks,
        sectors=sectors,
        directory=path.parent,
    )
