import json
import re
from pathlib import Path

import pytest

from gen.estimates import naismith_langmuir
from gen.model import ChallengeError, load_challenge
from gen.build import build_site

REPO = Path(__file__).resolve().parents[1]
LLANBERIS = REPO / "challenges" / "llanberis-enchainment" / "challenge.yaml"


def test_naismith_flat_path():
    # 4 km path, 400 m ascent: 4*12 + 40 = 88
    assert naismith_langmuir(4, 400, 0, "path") == 88


def test_naismith_scramble_multiplier():
    # 0.5 km scramble, 200 m ascent: 0.5*12*1.6 + 20 = 29.6 -> 30
    assert naismith_langmuir(0.5, 200, 0, "scramble") == 30


def test_naismith_gentle_descent_subtracts_but_clamps():
    # path descent reduces time (Langmuir) but is floored at 7.5 km/h equivalent
    assert naismith_langmuir(2, 0, 0, "path") == 24
    assert naismith_langmuir(2, 0, 300, "path") == 16  # 24-10=14, floor 2km*8=16


def test_naismith_steep_descent_adds():
    assert naismith_langmuir(2, 0, 300, "rough") > naismith_langmuir(2, 0, 0, "rough")


@pytest.fixture(scope="module")
def ench():
    return load_challenge(LLANBERIS)


def test_enchainment_loads(ench):
    assert ench.type == "enchainment"
    kinds = [s.kind for s in ench.stages]
    assert kinds.count("climb") >= 4
    assert "walk" in kinds and "scramble" in kinds and "decision" in kinds


def test_main_wall_pitches(ench):
    main_wall = next(s for s in ench.stages if s.kind == "climb" and s.name == "Main Wall")
    assert len(main_wall.pitches) == 6
    assert main_wall.grade == "HS 4b"


def test_decision_options(ench):
    decision = next(s for s in ench.stages if s.kind == "decision")
    assert len(decision.options) == 2
    assert all(len(o.stages) >= 1 for o in decision.options)


def test_stage_ids_unique_including_branches(ench):
    ids = [s.id for s in ench.all_stages()]
    assert len(ids) == len(set(ids))


def test_walk_estimates_computed_or_overridden(ench):
    for s in ench.all_stages():
        if s.kind in ("walk", "scramble"):
            assert s.estimate_min > 0


def test_paths_enumerated(ench):
    paths = ench.paths()
    assert len(paths) == 2  # one decision, two options
    for choice, stages in paths:
        assert all(s.kind != "decision" for s in stages)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("docs")
    build_site(REPO / "challenges", out)
    return out


def test_enchainment_page_built(site):
    html = (site / "llanberis-enchainment" / "index.html").read_text()
    for name in ["Direct Route", "Slow Ledge Climb", "Main Wall",
                 "Fallen Block Crack", "Reade's Route"]:
        assert name in html
    data = json.loads(re.search(
        r'<script id="challenge-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert data["type"] == "enchainment"
    assert len(data["stages"]) > 5


def test_pitch_rows_rendered(site):
    html = (site / "llanberis-enchainment" / "index.html").read_text()
    main_wall = re.search(r'data-stage="[^"]*main-wall".*?</article>', html, re.S).group(0)
    assert main_wall.count('class="pitch"') == 6
    assert main_wall.count('data-leader=') == 12  # two leader buttons per pitch


def test_decision_rendered_with_branch_stages_tagged(site):
    html = (site / "llanberis-enchainment" / "index.html").read_text()
    assert 'class="stage decision"' in html
    assert html.count("data-branch=") >= 2


def test_escape_routes_rendered(site):
    html = (site / "llanberis-enchainment" / "index.html").read_text()
    assert html.count('class="escape"') >= 3


def test_elevation_profile_svg(site):
    html = (site / "llanberis-enchainment" / "index.html").read_text()
    assert html.count('class="profile-path"') == 2  # one per decision path


def test_index_lists_both_challenges(site):
    html = (site / "index.html").read_text()
    assert 'href="stanage-vs/"' in html
    assert 'href="llanberis-enchainment/"' in html


def test_no_nested_decisions_rejected(tmp_path):
    import yaml
    inner = {"decision": {"name": "inner", "options": [
        {"name": "x", "stages": [{"walk": {"name": "w", "distance_km": 1,
                                            "ascent_m": 0, "descent_m": 0}}]}]}}
    data = {
        "name": "Bad", "slug": "bad", "type": "enchainment", "target_hours": 5,
        "leaders": ["A", "B"], "start_elev_m": 100,
        "stages": [{"decision": {"name": "outer", "options": [
            {"name": "a", "stages": [inner]}]}}],
    }
    p = tmp_path / "challenge.yaml"
    p.write_text(yaml.safe_dump(data))
    with pytest.raises(ChallengeError, match="nested"):
        load_challenge(p)
