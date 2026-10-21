import asyncio
import copy
import itertools
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import FIXTURES, load_fixture

from app.clock import FakeClock
from app.engine.normalizer import Normalizer
from app.feed.client import ShlClient
from app.feed.polllog import PollLog
from app.feed.snapshot import Snapshot
from app.feed.sources import LiveSource, OtherLiveSource, RecordingSource, ReplaySource
from app.feedtime import format_local, format_naive_utc, format_utc_z, parse_local_ms

GAME = "bdhvuc5tex"


def replay(clock: FakeClock, **kwargs: Any) -> ReplaySource:
    return ReplaySource.from_fixtures(FIXTURES, GAME, clock, **kwargs)


async def collect(source: Any, limit: int | None = None) -> list[Snapshot]:
    out: list[Snapshot] = []
    async for snapshot in source:
        out.append(snapshot)
        if limit is not None and len(out) >= limit:
            break
    return out


def raw(pbp: list[dict[str, Any]] | None, event_id: int) -> dict[str, Any] | None:
    return next((e for e in pbp or [] if e.get("eventId") == event_id), None)


async def test_replay_cadence_and_end() -> None:
    clock = FakeClock()
    snaps = await collect(replay(clock, speed=50))
    gaps = {b.received_ms - a.received_ms for a, b in itertools.pairwise(snaps)}
    assert gaps == {40}  # 2 s of feed time at 50x
    feed_gaps = {b.feed_ms - a.feed_ms for a, b in itertools.pairwise(snaps)}
    assert feed_gaps == {2000}
    final = snaps[-1]
    assert len([e for e in final.pbp or [] if "eventId" in e]) == 128
    assert final.game_info and final.game_info["gameInfo"]["state"] == "post_game"
    assert final.game_info["homeTeam"]["score"] == 2


async def test_replay_states_follow_the_live_feed() -> None:
    snaps = await collect(replay(FakeClock(), speed=50))
    states = []
    for s in snaps:
        pbp_state = next((e["gameState"] for e in s.pbp or [] if "gameState" in e), None)
        pair = (s.game_info["gameInfo"]["state"], pbp_state) if s.game_info else None
        if not states or states[-1] != pair:
            states.append(pair)
    assert states == [
        ("pre_game", None),
        ("pre_game", "Ongoing"),
        ("pre_game", "Intermission"),
        ("pre_game", "Ongoing"),
        ("pre_game", "Intermission"),
        ("pre_game", "Ongoing"),
        ("pre_game", "GameEnded"),
        ("post_game", "GameEnded"),
    ]
    assert snaps[0].pbp == []
    pre = snaps[0].game_info or {}
    assert pre["homeTeam"]["score"] == "" and pre["awayTeam"]["score"] == ""


async def test_running_period_looks_like_the_live_feed() -> None:
    snaps = await collect(replay(FakeClock(), speed=50))
    running = next(s for s in snaps if any(e.get("type") == "period" for e in s.pbp or []))
    period = next(e for e in running.pbp or [] if e.get("type") == "period")
    assert period["started"] is True and period["finished"] is False
    assert "finishedAt" not in period


async def test_events_appear_after_their_lag_with_shifted_timestamps() -> None:
    clock = FakeClock()
    source = replay(clock, speed=10, lag_s={"goal": 48})
    original = raw(load_fixture(f"pbp_{GAME}.json"), 96) or {}  # P3 09:07 goal
    rwt = parse_local_ms(original["realWorldTime"]) or 0
    first = None
    async for snapshot in source:
        if raw(snapshot.pbp, 96):
            first = snapshot
            break
    assert first is not None and first.feed_ms is not None
    assert rwt + 48_000 <= first.feed_ms < rwt + 48_000 + 2000
    shifted = raw(first.pbp, 96) or {}
    assert shifted["realWorldTime"] == format_local(source.to_clock(rwt))
    # On the clock's timeline the goal is seen lag / speed after its on-ice moment.
    event_ms = parse_local_ms(shifted["realWorldTime"]) or 0
    assert 4800 <= first.received_ms - event_ms < 4800 + 200


async def test_zero_lag() -> None:
    clock = FakeClock()
    source = replay(clock, speed=50, lag_s=0)
    original = raw(load_fixture(f"pbp_{GAME}.json"), 96) or {}
    rwt = parse_local_ms(original["realWorldTime"]) or 0
    async for snapshot in source:
        if raw(snapshot.pbp, 96):
            assert snapshot.feed_ms is not None and rwt <= snapshot.feed_ms < rwt + 2000
            break


async def test_seek_period_and_goal() -> None:
    clock = FakeClock()
    source = replay(clock, speed=50)
    normalizer = Normalizer()
    seen: list[Snapshot] = []
    async for snapshot in source:
        changes = normalizer.apply(snapshot)
        seen.append(snapshot)
        if len(seen) == 3:
            assert source.seek_period(3)
        if len(seen) == 4:
            assert snapshot.epoch == 1
            assert changes[0].kind == "reset"
            p3 = next(
                p
                for p in load_fixture(f"pbp_{GAME}.json")
                if p.get("period") == 3 and p.get("type") == "period"
            )
            target = (parse_local_ms(p3["startedAt"]) or 0) - 10_000
            assert snapshot.feed_ms == target + 2000  # one poll after the seek
            assert source.seek_before_next_goal(10)
        if len(seen) == 5:
            goal = raw(load_fixture(f"pbp_{GAME}.json"), 96) or {}
            target = (parse_local_ms(goal["realWorldTime"]) or 0) - 10_000
            assert snapshot.feed_ms == target + 2000
            assert snapshot.epoch == 2
            break
    assert not source.seek_period(7)


async def test_pause_play_and_speed() -> None:
    clock = FakeClock()
    source = replay(clock, speed=10)
    snaps: list[Snapshot] = []

    async def resume_later() -> None:
        await clock.sleep(60)
        source.play()

    async for snapshot in source:
        snaps.append(snapshot)
        if len(snaps) == 2:
            source.pause()
            asyncio.get_running_loop().create_task(resume_later())
        if len(snaps) == 3:
            source.set_speed(50)
        if len(snaps) == 5:
            break
    assert snaps[2].received_ms - snaps[1].received_ms >= 60_000  # paused a minute
    assert snaps[2].feed_ms == snaps[1].feed_ms  # feed time did not move
    assert snaps[4].received_ms - snaps[3].received_ms == 40  # 50x after set_speed
    with pytest.raises(ValueError):
        source.set_speed(0)


def write_recording(path: Path, start: int) -> None:
    event = {
        "eventId": 1,
        "type": "shot",
        "period": 1,
        "time": "00:30",
        "realWorldTime": format_local(start - 20_000),
        "updatedTime": format_naive_utc(start - 10_000),
        "gameState": "Ongoing",
    }
    info = load_fixture(f"game_info_{GAME}.json")
    rows = [
        {
            "received_ms": start - 3600_000,
            "endpoint": "game-info",
            "status": 200,
            "sha1": "i",
            "body": info,
        },
        {
            "received_ms": start - 1000,
            "endpoint": "play-by-play",
            "status": 200,
            "sha1": "p0",
            "age": 1,
            "body": [],
        },
        {
            "received_ms": start,
            "endpoint": "play-by-play",
            "status": 200,
            "sha1": "p1",
            "age": 3,
            "body": [event],
        },
        {
            "received_ms": start + 2000,
            "endpoint": "play-by-play",
            "status": None,
            "sha1": None,
            "error": "ReadTimeout",
            "body": None,
        },
        {
            "received_ms": start + 4000,
            "endpoint": "game-info",
            "status": 200,
            "sha1": "i",
            "body": None,
        },
        {
            "received_ms": start + 6000,
            "endpoint": "play-by-play",
            "status": 200,
            "sha1": "p1",
            "age": 9,
            "body": None,
        },
        {
            "received_ms": start + 8000,
            "endpoint": "boxscore",
            "status": 200,
            "sha1": "b",
            "body": {},
        },
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")


async def test_recording_source(tmp_path: Path) -> None:
    start = 1_760_000_000_000
    path = tmp_path / "polls.jsonl"
    write_recording(path, start)
    clock = FakeClock(5_000_000)
    snaps = await collect(RecordingSource(path, clock, speed=2))
    t0 = 5_000_000
    assert [s.received_ms - t0 for s in snaps] == [0, 1_799_500, 1_800_000, 1_802_000, 1_803_000]
    assert [s.feed_ms for s in snaps] == [
        start - 3600_000,
        start - 1000,
        start,
        start + 4000,
        start + 6000,
    ]
    with_event = snaps[2]
    assert with_event.pbp and with_event.game_info
    # available = received − age, both mapped onto the clock
    assert with_event.available_ms == with_event.received_ms - 1500
    # timestamps shifted with the same mapping (offsets halved at 2x)
    assert parse_local_ms(with_event.pbp[0]["realWorldTime"]) == with_event.received_ms - 10_000
    assert snaps[3].pbp is with_event.pbp  # unchanged body carried forward
    assert snaps[4].pbp is with_event.pbp


async def test_recording_skip_to_first_event(tmp_path: Path) -> None:
    start = 1_760_000_000_000
    path = tmp_path / "polls.jsonl"
    write_recording(path, start)
    clock = FakeClock(0)
    snaps = await collect(RecordingSource(path, clock, skip_to_first_event=True))
    assert snaps[0].feed_ms == start - 1000  # the empty pbp just before
    assert snaps[0].game_info is not None  # earlier game-info carried in
    assert snaps[1].received_ms == 60_000  # starts 60 s before the first event


async def test_recorded_game_replays() -> None:
    path = Path(__file__).parents[2] / "data" / "recordings" / "mtn5yq64mp" / "polls.jsonl"
    snaps = await collect(RecordingSource(path, FakeClock(), speed=50, skip_to_first_event=True))
    final = snaps[-1]
    assert len([e for e in final.pbp or [] if "eventId" in e]) == 126


class FakeShl:
    """shl.se for LiveSource: game-info with a start time, play-by-play from a list of
    bodies (the last one repeats), optional failures first."""

    def __init__(self, start_ms: int, pbps: list[Any], fail: int = 0) -> None:
        self.start_ms = start_ms
        self.pbps = pbps
        self.fail = fail
        self.calls: list[tuple[str, int]] = []
        self.clock: FakeClock | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert self.clock is not None
        kind = "pbp" if "play-by-play" in request.url.path else "info"
        self.calls.append((kind, self.clock.now_ms()))
        if self.fail:
            self.fail -= 1
            return httpx.Response(503)
        if kind == "info":
            info = copy.deepcopy(INFO)
            info["gameInfo"]["state"] = "pre_game"  # stale during the game, as on shl.se
            info["gameInfo"]["startDateTime"] = format_utc_z(self.start_ms)
            return httpx.Response(200, json=info)
        body = self.pbps.pop(0) if len(self.pbps) > 1 else self.pbps[0]
        return httpx.Response(200, json=body, headers={"age": "4"})

    def source(self, clock: FakeClock) -> LiveSource:
        self.clock = clock
        transport = httpx.MockTransport(self.handler)
        return LiveSource(lambda: ShlClient(transport=transport), GAME, clock)


INFO = load_fixture(f"game_info_{GAME}.json")
PBP = load_fixture(f"pbp_{GAME}.json")


def with_state(state: str) -> list[dict[str, Any]]:
    return [e | {"gameState": state} for e in PBP if e.get("type") != "period"]


async def test_live_polls_slowly_before_and_fast_near_puck_drop() -> None:
    clock = FakeClock()
    start = clock.now_ms() + 20 * 60_000
    shl = FakeShl(start, [[]] * 3 + [with_state("Ongoing")] * 2 + [with_state("GameEnded")])
    snaps = await collect(shl.source(clock), limit=12)
    info_times = [t for k, t in shl.calls if k == "info"]
    assert info_times[1] - info_times[0] == 60_000  # 20 min before: game-info only, 60 s
    assert ("pbp", info_times[0]) not in shl.calls and snaps[0].pbp is None
    fast = [t for k, t in shl.calls if k == "pbp"]
    assert fast and fast[0] >= start - 15 * 60_000  # play-by-play from 15 min before
    assert {b - a for a, b in itertools.pairwise(fast)} == {2000}
    assert snaps[-1].age_s == 4 and snaps[-1].available_ms == snaps[-1].received_ms - 4000


async def test_live_stops_two_minutes_after_game_end_then_refreshes_once() -> None:
    clock = FakeClock()
    shl = FakeShl(clock.now_ms() - 3 * 3600_000, [with_state("Ongoing"), with_state("GameEnded")])
    snaps = await collect(shl.source(clock))
    ended = [s for s in snaps if s.pbp and s.pbp[0]["gameState"] == "GameEnded"]
    polling, final = ended[:-1], ended[-1]
    assert polling[-1].received_ms - polling[0].received_ms == 120_000
    assert final.received_ms - polling[0].received_ms == 30 * 60_000  # corrections after the game
    assert snaps[-1] is final


async def test_live_finished_game_polls_once_and_errors_back_off() -> None:
    clock = FakeClock()
    shl = FakeShl(clock.now_ms() - 5 * 3600_000, [with_state("GameEnded")], fail=4)
    snaps = await collect(shl.source(clock))
    assert len(snaps) == 1
    times = [t for _, t in shl.calls]
    assert [b - a for a, b in itertools.pairwise(times[:5])] == [2000, 4000, 8000, 16000]


async def test_live_saves_a_recording_that_replays(tmp_path: Path) -> None:
    clock = FakeClock()
    shl = FakeShl(
        clock.now_ms() - 3600_000, [with_state("Ongoing")] * 3 + [with_state("GameEnded")]
    )
    source = shl.source(clock)
    path = tmp_path / "recordings" / GAME / "polls.jsonl"
    source.poll_log = PollLog(path, clock)
    live = await collect(source)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    endpoints = [r["endpoint"] for r in rows]
    assert endpoints[-2:] == ["boxscore", "team-stats"]  # with the final refresh
    pbp_rows = [r for r in rows if r["endpoint"] == "play-by-play"]
    assert pbp_rows[0]["body"] is not None and pbp_rows[1]["body"] is None  # unchanged
    assert {r["age"] for r in pbp_rows} == {4} and all(r["status"] == 200 for r in rows)
    replayed = await collect(RecordingSource(path, FakeClock()))
    last = replayed[-1].pbp or []
    assert last and last[0]["gameState"] == "GameEnded"
    assert len(replayed) == len([r for r in rows if r["endpoint"] in ("game-info", "play-by-play")])
    assert len(live) >= 3


async def test_other_live_source_polls_every_30_s_from_15_min_before() -> None:
    clock = FakeClock()
    start = clock.now_ms() + 20 * 60_000
    shl = FakeShl(start, [[]] * 3 + [with_state("Ongoing")] * 2 + [with_state("GameEnded")])
    shl.clock = clock
    transport = httpx.MockTransport(shl.handler)
    source = OtherLiveSource(lambda: ShlClient(transport=transport), GAME, clock, start)
    snaps = await collect(source)
    times = [t for kind, t in shl.calls]
    assert {kind for kind, _ in shl.calls} == {"pbp"}  # no game-info: the schedule has it
    assert times[0] >= start - 15 * 60_000
    assert {b - a for a, b in itertools.pairwise(times[:6])} == {30_000}
    ended = [s for s in snaps if s.pbp and s.pbp[0]["gameState"] == "GameEnded"]
    assert ended[-1].received_ms - ended[0].received_ms >= 120_000  # stops 2 min after the end
