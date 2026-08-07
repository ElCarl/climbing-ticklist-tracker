"""Bake challenge YAMLs into a static offline-first site under docs/."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageDraw

from gen.model import Challenge, load_challenge

REPO = Path(__file__).resolve().parents[1]
TOPO_MAX_WIDTH = 1600
TOPO_QUALITY = 72


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(REPO / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _process_topos(challenge, out_dir: Path) -> dict[str, str]:
    """Compress topo images to JPEG; return source filename -> emitted relative path."""
    emitted: dict[str, str] = {}
    src_dir = challenge.directory / "topos"
    items = challenge.climbs if challenge.type == "enchainment" else challenge.routes
    for route in items:
        if not route.topo or route.topo in emitted:
            continue
        src = src_dir / route.topo
        if not src.exists():
            raise FileNotFoundError(f"{challenge.slug}: missing topo {src}")
        with Image.open(src) as im:
            im = im.convert("RGB")
            if im.width > TOPO_MAX_WIDTH:
                im = im.resize(
                    (TOPO_MAX_WIDTH, round(im.height * TOPO_MAX_WIDTH / im.width)))
            digest = hashlib.sha256(src.read_bytes()).hexdigest()[:10]
            rel = f"topos/topo-{digest}.jpg"
            dest = out_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            im.save(dest, "JPEG", quality=TOPO_QUALITY, optimize=True)
        emitted[route.topo] = rel
    return emitted


def _challenge_json(challenge: Challenge) -> str:
    data = {
        "slug": challenge.slug,
        "name": challenge.name,
        "targetHours": challenge.target_hours,
        "routes": [
            {
                "slug": r.slug,
                "number": r.number,
                "name": r.name,
                "grade": r.grade,
                "stars": r.stars,
                "heightM": r.height_m,
                "sector": r.sector,
                "leader": challenge.leader_for(r.number),
            }
            for r in challenge.routes
        ],
    }
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def _planned_leaders(stage, leaders: list[str]) -> list[str]:
    """Alternating leads starting from first_lead."""
    start = leaders.index(stage.first_lead)
    return [leaders[(start + i) % len(leaders)] for i in range(len(stage.pitches))]


def _stage_json(stage, challenge, branch=None) -> dict:
    d = {
        "id": stage.id, "kind": stage.kind, "name": stage.name,
        "branch": branch,
    }
    if stage.kind == "climb":
        planned = _planned_leaders(stage, challenge.leaders)
        d.update(estimateMin=stage.estimate_min, distKm=stage.distance_km,
                 pitches=[{"i": p.index, "grade": p.grade, "lengthM": p.length_m,
                           "plannedLeader": planned[p.index - 1]}
                          for p in stage.pitches])
    else:
        d.update(estimateMin=stage.estimate_min, distKm=stage.distance_km)
    return d


def _enchainment_json(c) -> str:
    stages, decisions = [], []
    for s in c.stages:
        if s.kind == "decision":
            decisions.append({"id": s.id, "name": s.name,
                              "options": [o.name for o in s.options]})
            for i, o in enumerate(s.options):
                for inner in o.stages:
                    stages.append(_stage_json(inner, c, {"decision": s.id, "option": i}))
        else:
            stages.append(_stage_json(s, c))
    data = {
        "slug": c.slug, "name": c.name, "type": "enchainment",
        "targetHours": c.target_hours, "leaders": c.leaders,
        "stages": stages, "decisions": decisions,
    }
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def _profile_polylines(c) -> list[dict]:
    """One elevation polyline per decision path, ready for the SVG template."""
    paths = []
    for choice, stages in c.paths():
        x, y = 0.0, float(c.start_elev_m)
        pts = [(x, y)]
        for s in stages:
            x += s.distance_km
            if s.end_elev_m is not None:
                y = float(s.end_elev_m)
            elif s.kind == "climb":
                y += s.height_m
            else:
                y += s.ascent_m - s.descent_m
            pts.append((x, y))
        paths.append({"choice": choice, "pts": pts,
                      "stage_ids": [s.id for s in stages]})

    all_pts = [p for path in paths for p in path["pts"]]
    xmax = max(p[0] for p in all_pts) or 1
    ymin = min(p[1] for p in all_pts)
    ymax = max(p[1] for p in all_pts)
    yspan = (ymax - ymin) or 1
    W, H, M = 600, 140, 10
    for path in paths:
        path["svg_points"] = " ".join(
            f"{M + px / xmax * (W - 2 * M):.1f},"
            f"{H - M - (py - ymin) / yspan * (H - 2 * M):.1f}"
            for px, py in path["pts"])
        path["choice_json"] = json.dumps(path["choice"]).replace("</", "<\\/")
        path["ids_json"] = json.dumps(path["stage_ids"]).replace("</", "<\\/")
    return paths


def _icon(px: int, dest: Path) -> None:
    im = Image.new("RGB", (px, px), (18, 66, 44))
    d = ImageDraw.Draw(im)
    w = px / 10
    points = [(px * 0.24, px * 0.52), (px * 0.42, px * 0.70), (px * 0.78, px * 0.30)]
    d.line(points, fill=(240, 245, 242), width=round(w), joint="curve")
    im.save(dest, "PNG")


def _write_sw(out_dir: Path) -> None:
    files = sorted(
        p for p in out_dir.rglob("*")
        if p.is_file() and p.name != "sw.js" and not p.name.startswith(".")
    )
    urls = ["./"] + [f"./{p.relative_to(out_dir).as_posix()}" for p in files]
    urls += [f"./{p.relative_to(out_dir).as_posix()}/"
             for p in out_dir.iterdir() if p.is_dir()]
    h = hashlib.sha256()
    for p in files:
        h.update(p.read_bytes())
    version = f"ticklist-v{h.hexdigest()[:12]}"
    sw = f"""const CACHE = {json.dumps(version)};
const PRECACHE = {json.dumps(sorted(set(urls)))};

self.addEventListener('install', e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
}});

self.addEventListener('activate', e => {{
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
}});

self.addEventListener('fetch', e => {{
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request, {{ignoreSearch: true}}).then(hit =>
      hit || fetch(e.request).then(resp => {{
        if (resp.ok && new URL(e.request.url).origin === location.origin) {{
          const copy = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }}
        return resp;
      }})
    )
  );
}});
"""
    (out_dir / "sw.js").write_text(sw)


def build_site(challenges_dir: Path, out_dir: Path) -> list[Challenge]:
    challenges_dir, out_dir = Path(challenges_dir), Path(out_dir)
    env = _env()
    out_dir.mkdir(parents=True, exist_ok=True)

    challenges = []
    for yaml_path in sorted(challenges_dir.glob("*/challenge.yaml")):
        challenge = load_challenge(yaml_path)
        page_dir = out_dir / challenge.slug
        page_dir.mkdir(parents=True, exist_ok=True)
        topo_map = _process_topos(challenge, page_dir)
        if challenge.type == "enchainment":
            html = env.get_template("enchainment.html.j2").render(
                c=challenge,
                topo_map=topo_map,
                challenge_json=_enchainment_json(challenge),
                profiles=_profile_polylines(challenge),
                planned_leaders=lambda s: _planned_leaders(s, challenge.leaders),
            )
        else:
            html = env.get_template("challenge.html.j2").render(
                c=challenge,
                topo_map=topo_map,
                challenge_json=_challenge_json(challenge),
            )
        (page_dir / "index.html").write_text(html)
        challenges.append(challenge)

    for name in ["app.js", "enchain.js", "style.css"]:
        shutil.copyfile(REPO / "static" / name, out_dir / name)
    _icon(192, out_dir / "icon-192.png")
    _icon(512, out_dir / "icon-512.png")
    manifest = {
        "name": "Ticklist",
        "short_name": "Ticklist",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#12422c",
        "theme_color": "#12422c",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (out_dir / "index.html").write_text(
        env.get_template("index.html.j2").render(challenges=challenges))
    (out_dir / ".nojekyll").write_text("")
    _write_sw(out_dir)
    return challenges


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenges", type=Path, default=REPO / "challenges")
    parser.add_argument("--out", type=Path, default=REPO / "docs")
    args = parser.parse_args()
    built = build_site(args.challenges, args.out)
    for c in built:
        if c.type == "enchainment":
            print(f"built {c.slug}: {len(c.stages)} stages, {len(c.climbs)} climbs")
        else:
            print(f"built {c.slug}: {len(c.routes)} routes")


if __name__ == "__main__":
    main()
