import json
import re
from pathlib import Path

import pytest
import yaml
from PIL import Image

from gen.build import build_site

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("docs")
    build_site(REPO / "challenges", out)
    return out


def test_expected_files_exist(site):
    for rel in [
        "index.html",
        "manifest.json",
        "sw.js",
        "app.js",
        "style.css",
        "icon-192.png",
        "icon-512.png",
        "stanage-vs/index.html",
    ]:
        assert (site / rel).exists(), rel


def test_challenge_page_contents(site):
    html = (site / "stanage-vs" / "index.html").read_text()
    for name in ["Heather Wall", "Crab Crawl Arete", "Paradise Wall"]:
        assert name in html
    assert html.count("ukclimbing.com/logbook/crags/") == 36
    assert 'id="challenge-data"' in html
    data = json.loads(re.search(
        r'<script id="challenge-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert len(data["routes"]) == 36
    assert data["targetHours"] == 10


def test_voted_difficulty_chips_rendered(site):
    html = (site / "stanage-vs" / "index.html").read_text()
    assert html.count('class="voted') == 36
    assert "+0.33" in html  # Fern Crack
    assert "−0.59" in html or "-0.59" in html  # Paradise Wall


def test_every_route_has_explicit_clear_button(site):
    html = (site / "stanage-vs" / "index.html").read_text()
    assert html.count('class="clear"') == 36


def test_page_has_clear_all_button(site):
    html = (site / "stanage-vs" / "index.html").read_text()
    assert html.count('id="clear-all"') == 1


def test_transition_rows_follow_route_cards(site):
    html = (site / "stanage-vs" / "index.html").read_text()
    # descent text for route N sits between card N and card N+1
    card1 = html.index('data-route="heather-wall"')
    card2 = html.index('data-route="gargoyle-buttress"')
    transition = html.index('data-transition-after="heather-wall"')
    assert card1 < transition < card2


def test_index_links_challenge(site):
    html = (site / "index.html").read_text()
    assert 'href="stanage-vs/"' in html
    assert "Stanage VS Challenge" in html


def test_sw_precaches_pages_and_assets(site):
    sw = (site / "sw.js").read_text()
    for rel in ["./stanage-vs/", "./app.js", "./style.css", "./manifest.json"]:
        assert rel in sw
    assert re.search(r"ticklist-v[0-9a-f]{8,}", sw)


def test_icons_are_valid_png(site):
    for name, px in [("icon-192.png", 192), ("icon-512.png", 512)]:
        with Image.open(site / name) as im:
            assert im.size == (px, px)


def _challenge_with_shared_topo(tmp_path):
    cdir = tmp_path / "challenges" / "mini"
    (cdir / "topos").mkdir(parents=True)
    Image.new("RGB", (800, 600), (120, 130, 140)).save(cdir / "topos" / "buttress.png")
    routes = [
        {"name": f"R{i}", "grade": "VS 4c", "stars": 1, "height_m": 10,
         "ukc": f"https://www.ukclimbing.com/r{i}", "topo": "buttress.png",
         "descent": f"Descent note {i}"}
        for i in (1, 2)
    ]
    data = {
        "name": "Mini", "slug": "mini", "target_hours": 2, "leaders": ["A"],
        "blocks": [{"from": 1, "leader": "A"}],
        "sectors": [{"name": "S", "routes": routes}],
    }
    (cdir / "challenge.yaml").write_text(yaml.safe_dump(data))
    return tmp_path / "challenges"


def test_shared_topo_emitted_once_referenced_twice(tmp_path):
    out = tmp_path / "docs"
    build_site(_challenge_with_shared_topo(tmp_path), out)
    assets = list((out / "mini" / "topos").glob("*.jpg"))
    assert len(assets) == 1
    html = (out / "mini" / "index.html").read_text()
    assert html.count(f'topos/{assets[0].name}') == 2


def test_descent_rendered_in_transition(tmp_path):
    out = tmp_path / "docs"
    build_site(_challenge_with_shared_topo(tmp_path), out)
    html = (out / "mini" / "index.html").read_text()
    assert "Descent note 1" in html
