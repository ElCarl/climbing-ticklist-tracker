from pathlib import Path

import pytest

from gen.model import ChallengeError, load_challenge, slugify

REPO = Path(__file__).resolve().parents[1]
STANAGE = REPO / "challenges" / "stanage-vs" / "challenge.yaml"


@pytest.fixture(scope="module")
def stanage():
    return load_challenge(STANAGE)


def test_loads_36_routes_in_3_sectors(stanage):
    assert stanage.slug == "stanage-vs"
    assert [s.name for s in stanage.sectors] == [
        "Stanage Popular",
        "Stanage Plantation",
        "Stanage North",
    ]
    assert len(stanage.routes) == 36


def test_route_numbering_and_spot_checks(stanage):
    r1 = stanage.routes[0]
    assert (r1.number, r1.name, r1.grade, r1.stars) == (1, "Heather Wall", "VS 4c", 2)
    r22 = stanage.routes[21]
    assert (r22.name, r22.grade, r22.stars) == ("Paradise Wall", "HS 4b", 3)
    r36 = stanage.routes[35]
    assert (r36.number, r36.name, r36.sector) == (36, "Crab Crawl Arete", "Stanage North")


def test_ukc_links_absolute_and_unique(stanage):
    links = [r.ukc for r in stanage.routes]
    assert all(u.startswith("https://www.ukclimbing.com/") for u in links)
    assert len(set(links)) == 36


def test_route_slugs_unique(stanage):
    slugs = [r.slug for r in stanage.routes]
    assert len(set(slugs)) == 36


def test_leader_blocks(stanage):
    first = stanage.blocks[0]
    assert first.start == 1
    # every route resolves to a leader, changeovers land where blocks start
    leaders = [stanage.leader_for(r.number) for r in stanage.routes]
    assert all(leaders)
    changeover_at = [b.start for b in stanage.blocks[1:]]
    for n in range(2, 37):
        assert stanage.changeover_before(n) == (n in changeover_at)
    assert not stanage.changeover_before(1)


def test_totals(stanage):
    assert sum(r.height_m for r in stanage.routes) == 538
    assert sum(r.stars for r in stanage.routes) == 76


def test_slugify():
    assert slugify("Hargreaves' Original") == "hargreaves-original"
    assert slugify("Step-ladder Crack") == "step-ladder-crack"


def _minimal(tmp_path, **overrides):
    import yaml

    data = {
        "name": "Test",
        "slug": "test",
        "target_hours": 5,
        "leaders": ["A"],
        "blocks": [{"from": 1, "leader": "A"}],
        "sectors": [
            {
                "name": "S",
                "routes": [
                    {
                        "name": "R1",
                        "grade": "VS 4c",
                        "stars": 1,
                        "height_m": 10,
                        "ukc": "https://www.ukclimbing.com/x",
                    }
                ],
            }
        ],
    }
    data.update(overrides)
    p = tmp_path / "challenge.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_rejects_bad_stars(tmp_path):
    p = _minimal(
        tmp_path,
        sectors=[
            {
                "name": "S",
                "routes": [
                    {"name": "R1", "grade": "VS", "stars": 4, "height_m": 10,
                     "ukc": "https://www.ukclimbing.com/x"}
                ],
            }
        ],
    )
    with pytest.raises(ChallengeError, match="stars"):
        load_challenge(p)


def test_rejects_blocks_not_starting_at_1(tmp_path):
    p = _minimal(tmp_path, blocks=[{"from": 2, "leader": "A"}])
    with pytest.raises(ChallengeError, match="block"):
        load_challenge(p)


def test_rejects_duplicate_route_names(tmp_path):
    route = {"name": "R1", "grade": "VS", "stars": 1, "height_m": 10,
             "ukc": "https://www.ukclimbing.com/x"}
    p = _minimal(tmp_path, sectors=[{"name": "S", "routes": [route, dict(route)]}])
    with pytest.raises(ChallengeError, match="duplicate"):
        load_challenge(p)


def test_rejects_unknown_block_leader(tmp_path):
    p = _minimal(tmp_path, blocks=[{"from": 1, "leader": "Nobody"}])
    with pytest.raises(ChallengeError, match="leader"):
        load_challenge(p)
