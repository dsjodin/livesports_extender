"""Smoke test: every fixture file exists and parses."""

import pytest
from conftest import FIXTURES, load_fixture

GAMES = ["bdhvuc5tex", "m01wkdm2u1", "et9erhx0si"]
EVENING = ["pmch0rrshr", "ux4bplsxbh", "wffn21lxeb", "yklkh1aqmw"]  # with et9erhx0si
EXPECTED = [
    "filter.json",
    "schedule_2026.json",
    "site_settings.json",
    "standings_qa98unlbd6.json",
    *(
        f"{prefix}_{game}.json"
        for game in GAMES
        for prefix in ("game_info", "pbp", "boxscore", "team_stats")
    ),
    *(f"{prefix}_{game}.json" for game in EVENING for prefix in ("game_info", "pbp")),
    # Phase 8 pregame slides: scoring leaders, last season (head-to-head)
    *(f"leaders_{kind}_{team}.json" for kind in ("points", "goals") for team in ("fhc", "ske")),
    "filter_2025.json",
    "schedule_2025_regular.json",
    "schedule_2025_playoff.json",
]


def test_fixture_set_is_complete() -> None:
    assert sorted(p.name for p in FIXTURES.glob("*.json")) == sorted(EXPECTED)
    assert (FIXTURES / "README.md").is_file()


@pytest.mark.parametrize("name", EXPECTED)
def test_fixture_loads(name: str) -> None:
    data = load_fixture(name)
    assert data, name


def test_fixture_shapes() -> None:
    assert load_fixture("filter.json")["defaultSsgtFilter"]["season"]
    assert len(load_fixture("schedule_2026.json")["gameInfo"]) > 300
    assert load_fixture("site_settings.json")["teamsInSite"]
    assert len(load_fixture("standings_qa98unlbd6.json")["leagueStandings"]) == 14
    for game in GAMES:
        assert load_fixture(f"game_info_{game}.json")["gameInfo"]["gameUuid"] == game
        pbp = load_fixture(f"pbp_{game}.json")
        assert isinstance(pbp, list) and {e["gameUuid"] for e in pbp} == {game}
        assert "stats" in load_fixture(f"boxscore_{game}.json")
