"""Phase 2 acceptance on the runtime with a fake clock and hand-made snapshots."""

import asyncio
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


async def test_first_snapshot_catches_up_silently(setup: Any) -> None:
    """Starting (or seeking) mid-game: what the TV already showed is the starting state,
    not a burst of old goals; later events still play at their time."""
    rt, hub, clock = setup
    on_ice = T + 10 * S
    await at(clock, rt, on_ice + 130 * S)  # TV showed the goal at on_ice + 80 s
    feed(rt, clock, [goal(8, on_ice + 60 * S, 2, 0), goal(7, on_ice, 1, 0), period(T)])
    assert not [m for m in hub.of("event") if m["event"]["key"] == "e7"]
    assert not [m for m in hub.of("scene") if m["scene"]["name"] == "goal"]
    state = hub.of("state")[-1]["state"]
    assert state["score"] == {"home": 1, "away": 0}
    assert state["scene"]["name"] == "live"
    assert [r["key"] for r in state["recent"]] == ["period-1-start", "e7"]
    # e8 is shown on TV at on_ice + 140 s: it is still played, with its goal scene
    await at(clock, rt, on_ice + 140 * S)
    [event] = [m for m in hub.of("event") if m["event"]["key"] == "e8"]
    assert event["play_at_ms"] == on_ice + 140 * S and not event["event"]["late"]
    assert rt.applied["scene"]["name"] == "goal"


def period_n(n: int, started_ms: int) -> dict[str, Any]:
    return period(started_ms) | {"period": n}


async def test_sync_presses_at_period_starts_propose_the_tv_delay(setup: Any) -> None:
    """Phase 4 acceptance: fake TV 75 s behind, system offset 60 s, three presses at the
    TV's period starts propose 75 ± 0.5 s; after accepting, events play 75 s after the ice."""
    rt, hub, clock = setup
    rt.set_offset("iptv", 60)
    starts = [T + 10 * S, T + 40 * 60 * S, T + 80 * 60 * S]
    for n, start in enumerate(starts, start=1):
        await at(clock, rt, start + 25 * S)  # the feed shows a period start ~25 s late
        feed(rt, clock, [period_n(k, s) for k, s in enumerate(starts[:n], start=1)])
        await at(clock, rt, start + 75 * S + 300)  # seen on TV, pressed after 0.3 s
        rt.calibrate("period_start", None)
    cal = rt.calibration()
    assert [s["status"] for s in cal["samples"]] == ["matched"] * 3
    assert abs(cal["proposal_s"] - 75) <= 0.5
    rt.accept_calibration()
    assert rt.config.offset_s == cal["proposal_s"]
    on_ice = starts[2] + 300 * S
    await at(clock, rt, on_ice + 30 * S)
    feed(
        rt,
        clock,
        [goal(7, on_ice, 1, 0) | {"period": 3}, *[period_n(k, s) for k, s in enumerate(starts, 1)]],
    )
    await at(clock, rt, on_ice + 75 * S)
    [event] = [m for m in hub.of("event") if m["event"]["key"] == "e7"]
    assert event["play_at_ms"] == on_ice + 75 * S


async def test_sync_press_before_the_feed_has_the_goal(setup: Any) -> None:
    rt, _hub, clock = setup
    on_ice = T + 10 * S
    await at(clock, rt, on_ice + 41 * S)
    press = rt.calibrate("goal", "home")
    assert press["status"] == "pending"
    await at(clock, rt, on_ice + 60 * S)
    feed(rt, clock, [goal(7, on_ice, 1, 0), period(T)])
    [sample] = rt.calibration()["samples"]
    assert sample["status"] == "matched" and sample["sample_s"] == 40.7


async def test_goal_button_with_a_late_feed_goal_links_without_a_second_celebration(
    setup: Any,
) -> None:
    """Phase 4 acceptance: TV 40 s behind, the goal reaches the feed 48 s after the ice.
    MÅL! celebrates at once; the feed goal links to it: no second goal scene."""
    rt, hub, clock = setup
    rt.set_offset("iptv", 40)
    await at(clock, rt, T + 5 * S)
    feed(rt, clock, [period(T)])
    on_ice = T + 100 * S
    await at(clock, rt, on_ice + 40 * S + 300)
    press = rt.manual_goal("home")
    await at(clock, rt, clock.now_ms() + 300)
    scenes = [m["scene"] for m in hub.of("scene") if m["scene"]["name"] == "goal"]
    assert len(scenes) == 1 and scenes[0]["data"]["event_key"] == press["key"]
    assert rt.applied["score"] == {"home": 0, "away": 0}  # the feed has no goal yet
    await at(clock, rt, on_ice + 48 * S)
    feed(rt, clock, [goal(7, on_ice, 1, 0), period(T)])
    await at(clock, rt, on_ice + 50 * S)
    goal_scenes = [m["scene"] for m in hub.of("scene") if m["scene"]["name"] == "goal"]
    assert len(goal_scenes) == 2  # the same scene, now carrying the feed goal
    assert goal_scenes[1]["data"] == {"event_key": "e7", "side": "home", "linked_from": "manual-1"}
    assert goal_scenes[1]["since_ms"] == on_ice + 48 * S + 1500
    assert rt.applied["score"] == {"home": 1, "away": 0}
    [status] = rt.manual_status()
    assert status["status"] == "linked" and status["scorer"]["last"] == "Peterson"
    goal_sample = [s for s in rt.calibration()["samples"] if s["source"] == "goal_button"]
    assert goal_sample[0]["sample_s"] == 40.0
    await at(clock, rt, on_ice + 70 * S)
    assert rt.applied["scene"]["name"] == "live"  # the hold ran from the press


async def test_goal_button_links_to_a_goal_already_waiting_and_expires(setup: Any) -> None:
    rt, hub, clock = setup
    on_ice = T + 10 * S
    await at(clock, rt, on_ice + 20 * S)
    feed(rt, clock, [goal(7, on_ice, 1, 0), period(T)])  # plays at on_ice + 80 s
    await at(clock, rt, on_ice + 70 * S)
    rt.manual_goal("home")  # the TV is ahead of the screens
    rt.manual_goal("away")  # nothing behind this one
    assert [p["status"] for p in rt.manual_status()] == ["linked", "waiting"]
    await at(clock, rt, on_ice + 90 * S)
    # the away press took over the scene, so the linked home goal only fills the state
    assert len([m for m in hub.of("scene") if m["scene"]["name"] == "goal"]) == 2
    assert rt.applied["score"] == {"home": 1, "away": 0}
    await at(clock, rt, on_ice + 70 * S + 181 * S)
    assert [p["status"] for p in rt.manual_status()] == ["linked", "unconfirmed"]


async def test_test_goal_plays_at_once(setup: Any) -> None:
    rt, hub, clock = setup
    press = rt.manual_goal("home", test=True)
    [event] = [m for m in hub.of("event") if m["event"]["key"] == press["key"]]
    assert event["event"]["test"] and event["play_at_ms"] == clock.now_ms() + 300
    await at(clock, rt, clock.now_ms() + 300)
    assert rt.applied["scene"]["name"] == "goal"
    assert rt.manual_status()[0]["status"] == "test"


class TodaysGames:
    def __init__(self, games: list[dict[str, Any]]) -> None:
        self.games = games

    async def upcoming(self, days: int) -> list[dict[str, Any]]:
        return self.games


def scheduled(uuid: str, home: str, away: str, state: str = "pre-game") -> dict[str, Any]:
    return {"uuid": uuid, "state": state, "home": {"uuid": home}, "away": {"uuid": away}}


async def test_follow_my_team(tmp_path: Path) -> None:
    clock = FakeClock(T)
    settings = Settings(
        web_dir=tmp_path, config_dir=tmp_path, data_dir=tmp_path, fixtures_dir=FIXTURES
    )
    store = StateStore(tmp_path / "state.json")
    store.config.my_team_uuid = "ore"
    games = TodaysGames([scheduled("g1", "fhc", "lhc"), scheduled("g2", "ore", "bif")])
    rt = Runtime(clock, settings, store, Collector(), schedule=games)  # type: ignore[arg-type]
    started: list[tuple[str, str | None]] = []

    async def fake_source(mode: str, uuid: str | None = None, *_: Any) -> None:
        started.append((mode, uuid))
        rt.config.source.mode, rt.config.source.uuid = mode, uuid  # type: ignore[assignment]

    rt.set_source = fake_source  # type: ignore[method-assign]
    assert await rt.follow_my_team() is None  # off by default
    await rt.set_follow(True)
    assert started == [("live", "g2")] and rt.config.my_side is None
    assert await rt.follow_my_team() is None  # already followed today
    rt.config.source.mode = "replay"  # type: ignore[assignment]
    rt._source_task = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
    assert await rt.follow_my_team() is None  # never interrupts a replay
    games.games = [scheduled("g2", "ore", "bif", "post-game")]
    rt._source_task = None
    rt.config.source.mode = "none"  # type: ignore[assignment]
    assert await rt.follow_my_team() is None  # my team's game is over
