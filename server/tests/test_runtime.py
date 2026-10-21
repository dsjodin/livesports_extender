"""Phase 2 acceptance on the runtime with a fake clock and hand-made snapshots."""

from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES, load_fixture

from app.clock import FakeClock
from app.config import Settings, StateStore
from app.feed.snapshot import Snapshot
from app.feedtime import format_local, format_local_z
from app.runtime import Runtime

T = 1_800_000_000_000
S = 1000
INFO = load_fixture("game_info_bdhvuc5tex.json")


class Collector:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def broadcast(self, message: dict[str, Any], *, raw: bool = False) -> None:
        if not raw:
            self.messages.append(message)

    def of(self, t: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["t"] == t]


def period(started_ms: int) -> dict[str, Any]:
    return {
        "type": "period",
        "period": 1,
        "started": True,
        "finished": False,
        "startedAt": format_local_z(started_ms),
        "gameUuid": "bdhvuc5tex",
    }


def goal(
    event_id: int,
    at_ms: int,
    home: int,
    away: int,
    scorer: str = "Peterson",
    side: str = "home",
    **extra: Any,
) -> dict[str, Any]:
    item = {
        "eventId": event_id,
        "type": "goal",
        "period": 1,
        "time": "04:33",
        "revision": 2,
        "gameState": "Ongoing",
        "gameUuid": "bdhvuc5tex",
        "realWorldTime": format_local(at_ms),
        "eventTeam": {"place": side, "teamCode": "FHC" if side == "home" else "LHC"},
        "player": {
            "playerId": "1",
            "firstName": "Jacob",
            "familyName": scorer,
            "jerseyToday": "40",
        },
        "homeGoals": home,
        "awayGoals": away,
        "goalStatus": "EQ",
        "goalSection": 3,
        "locationX": 50,
        "locationY": 0,
        "attendance": 12044,
    }
    item.update(extra)
    return item


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Runtime, Collector, FakeClock]:
    clock = FakeClock(T, auto_advance=False)
    settings = Settings(
        web_dir=tmp_path, config_dir=tmp_path, data_dir=tmp_path, fixtures_dir=FIXTURES
    )
    store = StateStore(tmp_path / "state.json")
    store.config.profiles["iptv"] = 80.0
    hub = Collector()
    rt = Runtime(clock, settings, store, hub)
    rt.select_game("bdhvuc5tex", "home")
    return rt, hub, clock


async def at(clock: FakeClock, rt: Runtime, ms: int) -> None:
    await clock.advance(ms - clock.now_ms())
    rt.pump(ms)


def feed(rt: Runtime, clock: FakeClock, pbp: list[dict[str, Any]], age: int | None = None) -> None:
    rt.on_snapshot(Snapshot.at(clock.now_ms(), INFO, pbp, age_s=age))


async def test_play_at_formula_and_late_flag(setup: Any) -> None:
    rt, hub, clock = setup
    on_ice = T + 10 * S
    await at(clock, rt, on_ice + 48 * S)  # the goal reaches us 48 s after it happened
    feed(rt, clock, [goal(7, on_ice, 1, 0), period(T)], age=4)
    for offset_s in (80, 40):
        rt.set_offset("iptv", offset_s)
    # offset changed to 40 before release: now too late for the TV → plays at arrival + lead
    [event] = [m for m in hub.of("event") if m["event"]["key"] == "e7"]
    received = on_ice + 48 * S
    assert event["play_at_ms"] == max(on_ice + 40 * S, received + 1500) == received + 1500
    assert event["event"]["late"] and event["event"]["late_by_ms"] == 48 * S + 1500 - 40 * S
    assert event["event"]["first_seen_ms"] == received - 4 * S


async def test_in_time_goal_and_no_early_state(setup: Any) -> None:
    rt, hub, clock = setup
    on_ice = T + 10 * S
    await at(clock, rt, on_ice + 48 * S)
    feed(rt, clock, [goal(7, on_ice, 1, 0), period(T)])
    assert hub.of("event") == [m for m in hub.of("event") if m["event"]["type"] != "goal"]
    play_at = on_ice + 80 * S
    await at(clock, rt, play_at - 1500)  # handed out lead_ms early
    [event] = [m for m in hub.of("event") if m["event"]["key"] == "e7"]
    assert event["play_at_ms"] == play_at and not event["event"]["late"]
    patch = [m for m in hub.of("state_patch") if "score" in m["patch"]][-1]
    assert patch["play_at_ms"] == play_at and patch["patch"]["score"] == {"home": 1, "away": 0}
    # not applied yet: a client connecting now gets 0–0 plus the pending patch
    assert rt.applied["score"] == {"home": 0, "away": 0}
    first, *pending = rt.full_state_messages()
    assert first["state"]["score"] == {"home": 0, "away": 0}
    assert any(m["t"] == "state_patch" and "score" in m["patch"] for m in pending)
    await at(clock, rt, play_at)
    assert rt.applied["score"] == {"home": 1, "away": 0}
    goal_scene = [m for m in hub.of("scene") if m["scene"]["name"] == "goal"]
    assert goal_scene[0]["play_at_ms"] == play_at
    await at(clock, rt, play_at + 20 * S)
    assert rt.applied["scene"]["name"] == "live"


async def test_goal_removed_before_play_at_is_never_broadcast(setup: Any) -> None:
    rt, hub, clock = setup
    on_ice = T + 10 * S
    await at(clock, rt, on_ice + 20 * S)
    feed(rt, clock, [goal(7, on_ice, 1, 0), period(T)])
    await at(clock, rt, on_ice + 30 * S)
    feed(rt, clock, [period(T)])
    await at(clock, rt, on_ice + 200 * S)
    assert not [m for m in hub.of("event") if m["event"]["type"] in ("goal", "goal_disallowed")]
    assert rt.applied["score"] == {"home": 0, "away": 0}


async def test_scorer_correction_after_release(setup: Any) -> None:
    rt, hub, clock = setup
    on_ice = T + 10 * S
    await at(clock, rt, on_ice + 20 * S)
    feed(rt, clock, [goal(7, on_ice, 1, 0), period(T)])
    await at(clock, rt, on_ice + 81 * S)
    feed(rt, clock, [goal(7, on_ice, 1, 0, scorer="Fagemo", revision=3), period(T)])
    [update] = hub.of("event_update")
    assert update["event"]["player"]["last"] == "Fagemo"
    assert update["play_at_ms"] == on_ice + 81 * S + 1500
    await at(clock, rt, on_ice + 83 * S)
    assert rt.applied["goals"][0]["player"]["last"] == "Fagemo"


async def test_goal_removed_after_release(setup: Any) -> None:
    rt, hub, clock = setup
    on_ice = T + 10 * S
    await at(clock, rt, on_ice + 20 * S)
    feed(rt, clock, [goal(7, on_ice, 1, 0), period(T)])
    await at(clock, rt, on_ice + 81 * S)
    assert rt.applied["score"] == {"home": 1, "away": 0}
    feed(rt, clock, [period(T)])
    feed(rt, clock, [period(T)])  # seeing it gone twice changes nothing
    [disallowed] = [m for m in hub.of("event") if m["event"]["type"] == "goal_disallowed"]
    assert disallowed["event"]["data"] == {"original_key": "e7", "score": {"home": 0, "away": 0}}
    await at(clock, rt, on_ice + 83 * S)
    assert rt.applied["score"] == {"home": 0, "away": 0}
    assert rt.applied["scene"]["data"].get("overlay") == "goal_disallowed"


async def test_offset_change_replans_pending_only(setup: Any) -> None:
    rt, hub, clock = setup
    await at(clock, rt, T + 30 * S)
    feed(rt, clock, [goal(7, T + 10 * S, 1, 0), period(T)])
    await at(clock, rt, T + 90 * S)  # e7 released (play_at T+90 s)
    feed(rt, clock, [goal(8, T + 60 * S, 2, 0), goal(7, T + 10 * S, 1, 0), period(T)])
    rt.set_offset("iptv", 100)
    await at(clock, rt, T + 200 * S)
    plays = {m["event"]["key"]: m["play_at_ms"] for m in hub.of("event")}
    assert plays["e7"] == T + 90 * S  # untouched
    assert plays["e8"] == T + 160 * S  # re-planned with 100 s
    assert rt.store.config.profiles["iptv"] == 100
    assert hub.of("config")[-1]["config"]["offset_ms"] == 100 * S


async def test_events_are_broadcast_in_play_order(setup: Any) -> None:
    rt, hub, clock = setup
    await at(clock, rt, T + 60 * S)
    feed(
        rt,
        clock,
        [
            goal(9, T + 40 * S, 2, 1),
            goal(8, T + 20 * S, 1, 1, side="away"),
            goal(7, T + 10 * S, 1, 0),
            period(T),
        ],
    )
    await at(clock, rt, T + 200 * S)
    timed = [m["play_at_ms"] for m in hub.messages if "play_at_ms" in m]
    assert timed == sorted(timed)
    assert [m["event"]["key"] for m in hub.of("event")] == ["period-1-start", "e7", "e8", "e9"]


async def test_my_side_follows_my_team(setup: Any) -> None:
    rt, _, clock = setup
    rt.select_game("bdhvuc5tex", None)
    assert rt.config.my_team_uuid == "82eb-82ebmgaJ8"  # Örebro by default
    feed(rt, clock, [period(T)])
    assert rt.my_side is None  # Örebro does not play in FHC–LHC
    rt.set_my_team("41c4-41c4BiYZU")  # Linköping
    assert rt.my_side == "away" and rt.status()["my_side"] == "away"
    await at(clock, rt, clock.now_ms() + 2000)
    assert rt.applied["game"]["my_side"] == "away"
    rt.select_game("bdhvuc5tex", "home")  # an explicit side wins
    assert rt.my_side == "home"
