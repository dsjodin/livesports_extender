"""Live checks against shl.se: the real API still looks like our fixtures.

These run by default (project decision, 2026-10-20). Deselect with -m "not live".
"""

import pytest
from conftest import LiveShl, load_fixture
from test_fixtures import GAMES

import shl_http as shl

pytestmark = pytest.mark.live


def test_filter(live_shl: LiveShl) -> None:
    live = live_shl.get(shl.filter_url())
    assert live.keys() == load_fixture("filter.json").keys()
    default = live["defaultSsgtFilter"]
    assert default["series"] in {s["uuid"] for s in live["series"]}
    assert default["season"] in {s["uuid"] for s in live["season"]}


def test_schedule(live_shl: LiveShl) -> None:
    filt = load_fixture("filter.json")
    default = filt["defaultSsgtFilter"]
    live = live_shl.get(shl.schedule_url(default["season"], default["series"], default["gameType"]))
    games = live["gameInfo"]
    fixture_game = load_fixture("schedule_2026.json")["gameInfo"][0]
    assert len(games) > 300
    for game in games:
        assert fixture_game.keys() <= game.keys()
        assert game["homeTeamInfo"]["uuid"] and game["awayTeamInfo"]["uuid"]
        assert isinstance(game["state"], str) and game["state"]


def test_site_settings(live_shl: LiveShl) -> None:
    live = live_shl.get(shl.site_settings_url())
    assert {"teamsInSite", "allTeamsInSite"} <= live.keys()


def test_standings(live_shl: LiveShl) -> None:
    ssgt = load_fixture("filter.json")["ssgtUuid"]
    live = live_shl.get(shl.standings_url(ssgt))
    fixture = load_fixture(f"standings_{ssgt}.json")
    assert live.keys() == fixture.keys()
    assert len(live["leagueStandings"]) == len(fixture["leagueStandings"])
    assert live["leagueStandings"][0].keys() == fixture["leagueStandings"][0].keys()


@pytest.mark.parametrize("game", GAMES)
def test_finished_game_matches_fixture(live_shl: LiveShl, game: str) -> None:
    info = live_shl.get(shl.game_info_url(game))
    fixture_info = load_fixture(f"game_info_{game}.json")
    assert info["gameInfo"]["state"] == fixture_info["gameInfo"]["state"] == "post_game"
    for side in ("homeTeam", "awayTeam"):
        assert info[side]["score"] == fixture_info[side]["score"]
        assert info[side]["uuid"] == fixture_info[side]["uuid"]

    pbp = live_shl.get(shl.pbp_url(game))
    fixture_pbp = load_fixture(f"pbp_{game}.json")
    assert {e.get("eventId") for e in pbp} == {e.get("eventId") for e in fixture_pbp}
    goals = [
        (e["period"], e["time"], e["homeGoals"], e["awayGoals"]) for e in pbp if e["type"] == "goal"
    ]
    fixture_goals = [
        (e["period"], e["time"], e["homeGoals"], e["awayGoals"])
        for e in fixture_pbp
        if e["type"] == "goal"
    ]
    assert goals == fixture_goals

    box = live_shl.get(shl.boxscore_url(game))
    assert box.keys() == load_fixture(f"boxscore_{game}.json").keys()
