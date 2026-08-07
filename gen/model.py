"""Load and validate a challenge YAML into plain dataclasses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


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


def load_challenge(path: Path) -> Challenge:
    path = Path(path)
    data = yaml.safe_load(path.read_text())

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
