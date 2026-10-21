import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import LiveShl, load_fixture

import record_game
import shl_http as shl
from record_game import Recorder

MIN_MS = 60_000
T0 = 1_800_000_000_000


class FakeTime:
    """Fake clock for the recorder; sleeping advances it. Cancels after max_sleeps."""

    def __init__(self, max_sleeps: int | None = None, start_ms: int = T0) -> None:
        self.ms = start_ms
        self.sleeps: list[float] = []
        self.max_sleeps = max_sleeps

    def now_ms(self) -> int:
        return self.ms

    async def sleep(self, seconds: float) -> None:
        if self.max_sleeps is not None and len(self.sleeps) >= self.max_sleeps:
            raise asyncio.CancelledError
        self.sleeps.append(seconds)
        self.ms += int(seconds * 1000)


def game_info(state: str, start_ms: int) -> dict[str, Any]:
    body = load_fixture("game_info_bdhvuc5tex.json")
    body["gameInfo"]["state"] = state
    start = datetime.fromtimestamp(start_ms / 1000, UTC)
    body["gameInfo"]["startDateTime"] = start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return body


PBP_STATE_FOR = {"pre_game": None, "live": "Ongoing", "post_game": "GameEnded"}
CACHE_HEADERS = {"age": "4", "cf-cache-status": "HIT"}


def pbp_with_state(state: str | None) -> list[dict[str, Any]]:
    """The bdhvuc5tex play-by-play with every event's gameState set, or [] before the game."""
    if state is None:
        return []
    pbp = load_fixture("pbp_bdhvuc5tex.json")
    for item in pbp:
        if "eventId" in item:
            item["gameState"] = state
    return pbp


class FakeShl:
    """httpx MockTransport handler.

    ``state_at(ms)`` decides the game-info state; ``pbp_state_at(ms)`` the play-by-play
    ``gameState`` (default: derived from the game-info state).
    """

    def __init__(
        self,
        time: FakeTime,
        state_at: Any,
        start_ms: int,
        fail: int = 0,
        pbp_state_at: Any = None,
    ) -> None:
        self.time = time
        self.state_at = state_at
        self.pbp_state_at = pbp_state_at or (lambda ms: PBP_STATE_FOR.get(state_at(ms)))
        self.start_ms = start_ms
        self.fail = fail
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == shl.USER_AGENT
        endpoint = next(k for k, f in shl.GAME_ENDPOINTS.items() if f("g1") == str(request.url))
        self.requests.append(endpoint)
        if self.fail:
            self.fail -= 1
            return httpx.Response(503, text="busy")
        if endpoint == "game-info":
            body = game_info(self.state_at(self.time.ms), self.start_ms)
        elif endpoint == "play-by-play":
            body = pbp_with_state(self.pbp_state_at(self.time.ms))
        elif endpoint == "boxscore":
            body = load_fixture("boxscore_bdhvuc5tex.json")
        else:
            body = load_fixture("team_stats_bdhvuc5tex.json")
        return httpx.Response(200, json=body, headers=CACHE_HEADERS)


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


async def run(
    tmp_path: Path,
    time: FakeTime,
    state_at: Any,
    start_ms: int,
    fail: int = 0,
    pbp_state_at: Any = None,
    echo: Any = None,
) -> tuple[Recorder, FakeShl, list[dict[str, Any]]]:
    fake = FakeShl(time, state_at, start_ms, fail, pbp_state_at)
    out = tmp_path / "polls.jsonl"
    async with shl.make_client(httpx.MockTransport(fake)) as client:
        rec = Recorder(
            "g1", out, client, now_ms=time.now_ms, sleep=time.sleep, echo=echo or (lambda _: None)
        )
        await rec.run()
    return rec, fake, read_rows(out)


async def test_finished_game_makes_one_poll_and_exits(tmp_path: Path) -> None:
    time = FakeTime()
    rec, fake, rows = await run(tmp_path, time, lambda _: "post_game", T0 - 3 * 3600_000)
    assert rec.polls == 1
    assert time.sleeps == []
    assert fake.requests == ["game-info", "play-by-play", "boxscore", "team-stats"]
    assert [r["endpoint"] for r in rows] == fake.requests
    for row in rows:
        assert row.keys() == {"received_ms", "endpoint", "status", "sha1", "age", "cache", "body"}
        assert row["status"] == 200 and row["body"] is not None and len(row["sha1"]) == 40
        assert row["age"] == 4 and row["cache"] == "HIT"


async def test_upcoming_game_polls_game_info_slowly(tmp_path: Path) -> None:
    time = FakeTime(max_sleeps=3)
    _, fake, rows = await run(tmp_path, time, lambda _: "pre_game", T0 + 2 * 3600_000)
    assert time.sleeps == [60.0, 60.0, 60.0]
    assert fake.requests == ["game-info"] * 4 + ["boxscore", "team-stats"]
    assert [r["body"] is not None for r in rows[:4]] == [True, False, False, False]
    assert len({r["sha1"] for r in rows[:4]}) == 1


async def test_switches_to_fast_polling_15_min_before_start(tmp_path: Path) -> None:
    time = FakeTime(max_sleeps=4)
    _, fake, _ = await run(tmp_path, time, lambda _: "pre_game", T0 + 16 * MIN_MS)
    assert time.sleeps == [60.0, 2.0, 2.0, 2.0]
    assert fake.requests[:3] == ["game-info", "game-info", "play-by-play"]


async def test_stops_five_minutes_after_post_game(tmp_path: Path) -> None:
    time = FakeTime()
    ends_at = T0 + 10_000
    rec, fake, rows = await run(
        tmp_path, time, lambda ms: "post_game" if ms >= ends_at else "live", T0 - 3600_000
    )
    assert set(time.sleeps) == {2.0}
    assert time.ms - ends_at == 5 * MIN_MS
    assert fake.requests[-2:] == ["boxscore", "team-stats"]
    assert rows[-1]["endpoint"] == "team-stats"
    pbp = [r for r in rows if r["endpoint"] == "play-by-play"]
    assert len(pbp) == rec.polls and sum(r["body"] is not None for r in pbp) == 2


async def test_backs_off_on_errors(tmp_path: Path) -> None:
    time = FakeTime()
    _, _, rows = await run(tmp_path, time, lambda _: "post_game", T0, fail=4)
    assert time.sleeps == [2.0, 4.0, 8.0, 16.0]
    assert [r["status"] for r in rows] == [503, 503, 503, 503, 200, 200, 200, 200]


async def test_backoff_caps_at_30_s(tmp_path: Path) -> None:
    time = FakeTime()
    await run(tmp_path, time, lambda _: "post_game", T0, fail=6)
    assert time.sleeps == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


async def test_network_error_is_recorded(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("no route")
        return httpx.Response(200, json=game_info("post_game", T0))

    time = FakeTime()
    out = tmp_path / "polls.jsonl"
    async with shl.make_client(httpx.MockTransport(handler)) as client:
        await Recorder("g1", out, client, time.now_ms, time.sleep, lambda _: None).run()
    first = read_rows(out)[0]
    assert first["status"] is None and first["sha1"] is None and "no route" in first["error"]
    assert time.sleeps == [2.0]


async def test_unknown_state_is_logged_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    time = FakeTime(max_sleeps=3)
    with caplog.at_level(logging.WARNING, logger="record_game"):
        await run(tmp_path, time, lambda _: "live", T0)
    warnings = [r for r in caplog.records if "unrecognised" in r.message]
    assert len(warnings) == 1 and "game-info state 'live'" in warnings[0].message
    assert time.sleeps == [2.0, 2.0, 2.0]


async def test_restart_continues_hash_chain(tmp_path: Path) -> None:
    await run(tmp_path, FakeTime(), lambda _: "post_game", T0)
    _, _, rows = await run(tmp_path, FakeTime(), lambda _: "post_game", T0)
    assert len(rows) == 8
    assert all(r["body"] is None for r in rows[4:])


async def test_stops_after_pbp_game_ended_while_game_info_stays_pre_game(tmp_path: Path) -> None:
    """The real case from 2026-10-20: game-info said pre_game all evening."""
    time = FakeTime()
    ends_at = T0 + 60_000
    rec, _, rows = await run(
        tmp_path,
        time,
        lambda _: "pre_game",
        T0 - 3600_000,
        pbp_state_at=lambda ms: "GameEnded" if ms >= ends_at else "Ongoing",
    )
    assert rec.state() == "GameEnded"
    assert set(time.sleeps) == {2.0}
    assert time.ms - ends_at == 5 * MIN_MS
    assert rows[-1]["endpoint"] == "team-stats"


async def test_gives_up_six_hours_after_start(tmp_path: Path) -> None:
    time = FakeTime()
    lines: list[str] = []
    await run(tmp_path, time, lambda _: "pre_game", T0, echo=lines.append)
    assert time.ms > T0 + 6 * 3600_000
    assert time.ms - (T0 + 6 * 3600_000) <= 2_000
    assert any("giving up" in line for line in lines)


async def test_status_line_uses_pbp_state_and_score(tmp_path: Path) -> None:
    lines: list[str] = []
    await run(
        tmp_path,
        FakeTime(max_sleeps=1),
        lambda _: "pre_game",
        T0 - 3600_000,
        pbp_state_at=lambda _: "Ongoing",
        echo=lines.append,
    )
    assert "state=Ongoing FHC 2–1 LHC events=128" in lines[0]


@pytest.mark.live
async def test_live_finished_game(tmp_path: Path) -> None:
    out = tmp_path / "polls.jsonl"
    async with shl.make_client() as client:
        rec = Recorder("bdhvuc5tex", out, client, echo=lambda _: None)
        await asyncio.wait_for(rec.run(), timeout=60)
    rows = read_rows(out)
    assert rec.polls == 1
    assert [r["endpoint"] for r in rows] == ["game-info", "play-by-play", "boxscore", "team-stats"]
    assert all(r["status"] == 200 for r in rows)
    assert rec.state() == "GameEnded" and rec.info_state() == "post-game"


@pytest.mark.live
async def test_live_upcoming_game_polls_slowly(tmp_path: Path, live_shl: LiveShl) -> None:
    default = load_fixture("filter.json")["defaultSsgtFilter"]
    schedule = live_shl.get(
        shl.schedule_url(default["season"], default["series"], default["gameType"])
    )
    now_ms = record_game.real_now_ms()
    upcoming = [
        g
        for g in schedule["gameInfo"]
        if g["state"] == "pre-game"
        and (record_game.parse_utc_ms(g["rawStartDateTime"]) or 0) > now_ms + 30 * MIN_MS
    ]
    if not upcoming:
        pytest.skip("no game more than 30 min ahead in the schedule")
    game = min(upcoming, key=lambda g: g["rawStartDateTime"])["uuid"]

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        if len(sleeps) == 2:
            raise asyncio.CancelledError
        sleeps.append(seconds)

    out = tmp_path / "polls.jsonl"
    async with shl.make_client() as client:
        rec = Recorder(game, out, client, sleep=fake_sleep, echo=lambda _: None)
        await asyncio.wait_for(rec.run(), timeout=60)
    rows = read_rows(out)
    assert sleeps == [60.0, 60.0]
    assert [r["endpoint"] for r in rows] == ["game-info"] * 3 + ["boxscore", "team-stats"]
    assert rec.state() == "pre-game"
