import asyncio

import pytest
from conftest import load_fixture, replay_to_end

from app.engine.events import NormalizedEvent
from app.engine.tvstate import GameMeta, build, diff

SCENE = {"name": "live", "since_ms": 0, "hold_ms": None, "data": {}, "override": False}


@pytest.fixture(scope="module")
def events() -> list[NormalizedEvent]:
    normalizer, _ = asyncio.run(replay_to_end("bdhvuc5tex"))
    return list(normalizer.events.values())


def meta() -> GameMeta:
    return GameMeta.from_game_info(load_fixture("game_info_bdhvuc5tex.json"), 12044, "home")


def test_full_game(events: list[NormalizedEvent]) -> None:
    tv = build(events, meta(), SCENE)
    assert tv["score"] == {"home": 2, "away": 1} and tv["phase"] == "postgame" and tv["ended"]
    assert tv["game"] == {
        "uuid": "bdhvuc5tex",
        "arena": "Scandinavium",
        "attendance": 12044,
        "start_ms": 1757769300000,
        "my_side": "home",
    }
    assert tv["teams"]["home"]["code"] == "FHC" and tv["teams"]["home"]["short"] == "Frölunda"
    assert tv["teams"]["away"]["uuid"] == "41c4-41c4BiYZU"
    home, away = tv["stats"]["home"], tv["stats"]["away"]
    assert home["shots_by_period"] == [15, 11, 5] and away["shots_by_period"] == [4, 10, 15]
    assert (home["shots_wide"], home["shots_blocked"]) == (9, 15)
    assert home["pp"] == {"goals": 1, "chances": 3} and away["pp"] == {"goals": 1, "chances": 2}
    # goalie saves equal the boxscore (Johansson 28 of 29, Myrenberg 29 of 31)
    assert (home["goalie"]["saves"], home["goalie"]["shots_against"]) == (28, 29)
    assert (away["goalie"]["saves"], away["goalie"]["shots_against"]) == (29, 31)
    assert [g["time"] for g in tv["goals"]] == ["04:33", "00:24", "09:07"]
    assert len(tv["penalties"]) == 5 and tv["penalties_active"] == []
    dots = tv["shots"]["home"] + tv["shots"]["away"]
    assert len(dots) == 118 - 2  # two outliers outside 0..300 dm skipped
    assert sum(d["goal"] for d in dots) == 3
    assert tv["scene"] == SCENE


def test_partial_state_uses_only_given_events(events: list[NormalizedEvent]) -> None:
    upto = [
        e
        for e in events
        if isinstance(e.period, int) and e.period <= 2 and (e.game_seconds or 0) <= 1235
    ]
    upto = [e for e in upto if e.type != "period_end" or e.period == 1]
    tv = build(upto, meta(), SCENE)
    assert tv["score"] == {"home": 1, "away": 1}
    assert tv["phase"] == "live" and tv["period"] == 2 and tv["period_running"]
    assert tv["last_game_time"] == "00:24"  # latest event seen: the 1–1 goal


def test_active_penalty(events: list[NormalizedEvent]) -> None:
    upto = [e for e in events if e.period == 1 and (e.game_seconds or 0) <= 1120]
    tv = build(upto, meta(), SCENE)
    [pen] = tv["penalties_active"]
    assert pen["number"] == "46" and pen["offence_text"] == "Tripping"
    assert pen["started"] == "P1 18:35" and pen["expires_game_seconds"] == 1235
    assert tv["strength"]["label"] == "4v5" and tv["strength"]["pp_side"] == "away"


def test_no_spoilers_from_game_info() -> None:
    """The final game-info says 2–1; with nothing released the TV still shows 0–0."""
    tv = build([], meta(), SCENE)
    assert tv["score"] == {"home": 0, "away": 0} and tv["phase"] == "pregame"
    assert build([], GameMeta(), SCENE, selected=False)["phase"] == "idle"


def test_diff() -> None:
    old = {"rev": 1, "score": {"home": 0, "away": 0}, "period": 1}
    new = {"rev": 2, "score": {"home": 1, "away": 0}, "period": 1}
    assert diff(old, new) == {"score": {"home": 1, "away": 0}}
