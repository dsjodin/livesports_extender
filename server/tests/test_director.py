from typing import Any

import pytest

from app.engine.director import GOAL_HOLD_MS, POSTGAME_HOLD_MS, Scene, SceneDirector
from app.engine.events import NormalizedEvent

T = 1_760_000_000_000


def ev(typ: str, key: str = "e1", period: int | str = 1, side: str | None = "home") -> Any:
    return NormalizedEvent(
        key=key, type=typ, raw_type=typ, period=period, side=side, first_seen_ms=T, received_ms=T
    )


def names(scenes: list[Scene]) -> list[tuple[str, int, Any]]:
    return [(s.name, s.since_ms - T, s.data.get("overlay")) for s in scenes]


def test_game_flow() -> None:
    d = SceneDirector(T)
    assert names(d.set_game(True, T)) == [("pregame", 0, None)]
    assert names(d.on_event(ev("period_start"), T + 10)) == [("live", 10, None)]
    goal = d.on_event(ev("goal", "e7"), T + 100)
    assert names(goal) == [("goal", 100, None)]
    assert goal[0].data == {"event_key": "e7", "side": "home"} and goal[0].hold_ms == GOAL_HOLD_MS
    assert d.next_timer_ms() == T + 100 + GOAL_HOLD_MS
    assert names(d.advance(T + 100 + GOAL_HOLD_MS)) == [("live", 100 + GOAL_HOLD_MS, None)]
    assert names(d.on_event(ev("period_end"), T + 50_000)) == [("intermission", 50_000, None)]
    assert names(d.on_event(ev("period_start", period=2), T + 60_000)) == [("live", 60_000, None)]
    assert names(d.on_event(ev("game_end"), T + 70_000)) == [("postgame", 70_000, None)]
    assert names(d.advance(T + 70_000 + POSTGAME_HOLD_MS)) == [
        ("idle", 70_000 + POSTGAME_HOLD_MS, None)
    ]


def test_new_goal_restarts_the_hold() -> None:
    d = SceneDirector(T)
    d.on_event(ev("period_start"), T)
    d.on_event(ev("goal", "e1"), T + 1000)
    scenes = d.on_event(ev("goal", "e2", side="away"), T + 11_000)
    assert names(scenes) == [("goal", 11_000, None)] and scenes[0].data["side"] == "away"
    assert d.advance(T + 1000 + GOAL_HOLD_MS) == []
    assert names(d.advance(T + 11_000 + GOAL_HOLD_MS)) == [("live", 11_000 + GOAL_HOLD_MS, None)]


def test_overlays() -> None:
    d = SceneDirector(T)
    d.on_event(ev("period_start"), T)
    assert names(d.on_event(ev("penalty", "e5"), T + 1000)) == [("live", 1000, "penalty")]
    assert names(d.advance(T + 9000)) == [("live", 9000, None)]
    assert names(d.on_event(ev("timeout", "e6"), T + 20_000)) == [("live", 20_000, "timeout")]
    # a penalty during a goal scene does not interrupt it
    d.on_event(ev("goal", "e7"), T + 30_000)
    assert d.on_event(ev("penalty", "e8"), T + 31_000) == []
    # a disallowed goal does
    assert names(d.on_event(ev("goal_disallowed", "e7-x"), T + 32_000)) == [
        ("live", 32_000, "goal_disallowed")
    ]


def test_shootout_goal_is_not_a_goal_scene() -> None:
    d = SceneDirector(T)
    d.on_event(ev("period_start", period="shootout"), T)
    assert d.on_event(ev("goal", period="shootout"), T + 1000) == []


def test_override() -> None:
    d = SceneDirector(T)
    d.on_event(ev("period_start"), T)
    over = d.set_override("intermission", 60_000, T + 1000)
    assert names(over) == [("intermission", 1000, None)] and over[0].override
    assert d.on_event(ev("goal", "e7"), T + 50_000) == []  # override wins
    assert names(d.advance(T + 61_000)) == [("goal", 61_000, None)]  # goal hold still running
    d.set_override("postgame", None, T + 70_000)
    assert names(d.clear_override(T + 80_000)) == [("live", 80_000, None)]
    with pytest.raises(ValueError):
        d.set_override("party", None, T)


def test_reset_and_no_game() -> None:
    d = SceneDirector(T)
    d.set_game(True, T)
    d.on_event(ev("period_start"), T + 1)
    assert names(d.reset(True, T + 2)) == [("pregame", 2, None)]
    assert names(d.set_game(False, T + 3)) == [("idle", 3, None)]
