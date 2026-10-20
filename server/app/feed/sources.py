"""Snapshot sources, all async iterators of ``Snapshot`` driven by an injectable ``Clock``.

- ``ReplaySource`` plays a finished game from its final play-by-play.
- ``RecordingSource`` plays a ``polls.jsonl`` made by ``tools/record_game.py``.
- ``LiveSource`` follows a real game (Phase 5; interface only).

Replay and recording sources move the feed's timestamps onto the clock's timeline
(scaled by speed), so ``event_ms`` parsed from them lines up with ``first_seen_ms``.
"""

import bisect
import copy
import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from app.clock import Clock
from app.feed.client import ShlClient
from app.feed.snapshot import Snapshot
from app.feedtime import (
    format_local,
    format_local_z,
    format_naive_utc,
    format_utc_z,
    parse_local_ms,
    parse_naive_utc_ms,
    parse_utc_ms,
)

log = logging.getLogger(__name__)

# Seconds from the on-ice moment to the event appearing in the feed, per raw type.
# Medians from the 2026-10-20 recording (docs/SHL_API.md, Feed latency).
DEFAULT_LAG_S: dict[str, float] = {
    "goal": 48,
    "shot": 35,
    "penalty": 42,
    "period": 25,
    "goalkeeper": 16,
    "timeout": 37,
}
OTHER_LAG_S = 35.0
SPEEDS = (1, 2, 5, 20, 50)  # offered in the UI; any positive speed works

TimeMap = Callable[[int], int]


class FeedSource(Protocol):
    def __aiter__(self) -> AsyncIterator[Snapshot]: ...


def shift_item(item: dict[str, Any], to_clock: TimeMap) -> dict[str, Any]:
    """A copy of a play-by-play item with its timestamps moved by ``to_clock``."""
    out = dict(item)
    if (ms := parse_local_ms(item.get("realWorldTime"))) is not None:
        out["realWorldTime"] = format_local(to_clock(ms))
    if (ms := parse_naive_utc_ms(item.get("updatedTime"))) is not None:
        out["updatedTime"] = format_naive_utc(to_clock(ms))
    for key in ("startedAt", "finishedAt"):
        if (ms := parse_local_ms(item.get(key))) is not None:
            out[key] = format_local_z(to_clock(ms))
    return out


def shift_info(info: dict[str, Any], to_clock: TimeMap) -> dict[str, Any]:
    out = copy.deepcopy(info)
    game = out.get("gameInfo") or {}
    if (ms := parse_utc_ms(game.get("startDateTime"))) is not None:
        game["startDateTime"] = format_utc_z(to_clock(ms))
    return out


class ReplaySource:
    """Replays a finished game from its final play-by-play and game-info.

    Each event appears ``lag_s`` (per raw type) after its ``realWorldTime``; a period
    object appears ``lag_s["period"]`` after ``startedAt`` and is marked finished the
    same lag after ``finishedAt``. A snapshot is emitted every ``poll_s`` of feed time.
    The play-by-play ``gameState`` is synthesised (``Ongoing``, ``Intermission``,
    ``GameEnded``). game-info behaves as observed live: ``pre_game`` with empty scores
    until ``post_game_after_s`` after the game ended (assumption: the real delay is
    unknown, over 10 min on 2026-10-20), then the final game-info. Only event content
    is real; revisions are always the final ones.
    """

    def __init__(
        self,
        pbp_full: list[dict[str, Any]],
        game_info_final: dict[str, Any],
        clock: Clock,
        *,
        speed: float = 1.0,
        lag_s: Mapping[str, float] | float | None = None,
        poll_s: float = 2.0,
        pregame_s: float = 120.0,
        post_game_after_s: float = 60.0,
        tail_s: float = 60.0,
    ) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.clock = clock
        self.speed = speed
        self.poll_s = poll_s
        self._info_final = game_info_final

        def lag_ms(raw_type: str) -> int:
            if isinstance(lag_s, int | float):
                return round(lag_s * 1000)
            lags = DEFAULT_LAG_S if lag_s is None else lag_s
            return round(lags.get(raw_type, OTHER_LAG_S) * 1000)

        timed: list[tuple[int, dict[str, Any]]] = []
        self._goals: list[int] = []
        for item in pbp_full:
            if not isinstance(item, dict) or item.get("type") == "period":
                continue
            at = parse_local_ms(item.get("realWorldTime"))
            if at is None:
                log.warning("replay: event %s has no realWorldTime, left out", item.get("eventId"))
                continue
            timed.append((at + lag_ms(str(item.get("type"))), item))
            if item.get("type") == "goal" and isinstance(item.get("period"), int):
                self._goals.append(at)
        timed.sort(key=lambda t: t[0])
        self._event_vis = [t[0] for t in timed]
        self._events = [t[1] for t in timed]
        self._goals.sort()

        period_lag = lag_ms("period")
        self._periods: list[tuple[int, int | None, dict[str, Any]]] = []
        for item in pbp_full:
            if isinstance(item, dict) and item.get("type") == "period":
                started = parse_local_ms(item.get("startedAt"))
                finished = parse_local_ms(item.get("finishedAt"))
                if started is None:
                    continue
                self._periods.append(
                    (
                        started + period_lag,
                        None if finished is None else finished + period_lag,
                        item,
                    )
                )
        if not self._periods:
            raise ValueError("play-by-play has no started periods")
        finishes = [f for _, f, _ in self._periods]
        self._ended_f = max(f for f in finishes if f) if all(finishes) else None
        last_vis = max([*self._event_vis, *(f or s for s, f, _ in self._periods)])
        self._post_game_f = (
            None if self._ended_f is None else self._ended_f + round(post_game_after_s * 1000)
        )
        self.start_f = min(s for s, _, _ in self._periods) - period_lag - round(pregame_s * 1000)
        self.end_f = max(last_vis, self._post_game_f or last_vis) + round(tail_s * 1000)

        self.epoch = 0
        self.paused = False
        self._t_anchor: int | None = None
        self._f_anchor = self.start_f
        self._version = 0
        self._cache_key: tuple[Any, ...] | None = None
        self._cache: tuple[dict[str, Any], list[dict[str, Any]]] | None = None

    @classmethod
    def from_fixtures(
        cls, fixtures: Path, game_uuid: str, clock: Clock, **kwargs: Any
    ) -> "ReplaySource":
        pbp = json.loads((fixtures / f"pbp_{game_uuid}.json").read_text(encoding="utf-8"))
        info = json.loads((fixtures / f"game_info_{game_uuid}.json").read_text(encoding="utf-8"))
        return cls(pbp, info, clock, **kwargs)

    # --- timeline -------------------------------------------------------------------

    def feed_now(self) -> int:
        """Current position on the original feed timeline (epoch ms)."""
        if self._t_anchor is None or self.paused:
            return self._f_anchor
        return self._f_anchor + round((self.clock.now_ms() - self._t_anchor) * self.speed)

    def to_clock(self, feed_ms: int) -> int:
        t_anchor = self.clock.now_ms() if self._t_anchor is None else self._t_anchor
        return t_anchor + round((feed_ms - self._f_anchor) / self.speed)

    def _reanchor(self, feed_ms: int) -> None:
        self._f_anchor = feed_ms
        self._t_anchor = self.clock.now_ms()
        self._version += 1

    # --- controls -------------------------------------------------------------------

    def play(self) -> None:
        if self.paused:
            self.paused = False
            self._reanchor(self._f_anchor)

    def pause(self) -> None:
        if not self.paused:
            self._reanchor(self.feed_now())
            self.paused = True

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        position = self.feed_now()
        self.speed = speed
        self._reanchor(position)

    def seek(self, feed_ms: int) -> None:
        """Jump to a feed time. Consumers see a new ``epoch`` and should start over."""
        self._reanchor(min(max(feed_ms, self.start_f), self.end_f))
        self.epoch += 1

    def seek_period(self, period: int | str, before_s: float = 10.0) -> bool:
        for _, _, item in self._periods:
            if item.get("period") == period:
                started = parse_local_ms(item.get("startedAt"))
                if started is not None:
                    self.seek(started - round(before_s * 1000))
                    return True
        return False

    def seek_before_next_goal(self, before_s: float = 10.0) -> bool:
        """Seek to ``before_s`` before the next goal's on-ice moment."""
        now = self.feed_now()
        i = bisect.bisect_right(self._goals, now + round(before_s * 1000))
        if i == len(self._goals):
            return False
        self.seek(self._goals[i] - round(before_s * 1000))
        return True

    # --- rendering ------------------------------------------------------------------

    def _render(self, f: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        visible = bisect.bisect_right(self._event_vis, f)
        flags = tuple((s <= f, e is not None and e <= f) for s, e, _ in self._periods)
        ended = self._ended_f is not None and f >= self._ended_f
        post = self._post_game_f is not None and f >= self._post_game_f
        key = (visible, flags, ended, post, self._version)
        if key == self._cache_key and self._cache is not None:
            return self._cache

        if ended:
            state: str | None = "GameEnded"
        elif any(s and not e for s, e in flags):
            state = "Ongoing"
        elif any(s for s, _ in flags):
            state = "Intermission"
        else:
            state = "Ongoing" if visible else None

        events = sorted(self._events[:visible], key=lambda e: e.get("eventId", 0), reverse=True)
        pbp = [shift_item(e, self.to_clock) | {"gameState": state} for e in events]
        for (started, finished), (_, _, item) in zip(flags, self._periods, strict=True):
            if not started:
                continue
            period = shift_item(item, self.to_clock)
            if not finished:
                period.pop("finishedAt", None)
                period["finished"] = False
                period["realWorldTime"] = period["startedAt"].removesuffix("Z")
            pbp.append(period)

        info = shift_info(self._info_final, self.to_clock)
        if not post:
            info.setdefault("gameInfo", {}).update(state="pre_game", overtime=False, shootout=False)
            for side in ("homeTeam", "awayTeam"):
                info.setdefault(side, {})["score"] = ""
        self._cache_key, self._cache = key, (info, pbp)
        return info, pbp

    def __aiter__(self) -> AsyncIterator[Snapshot]:
        return self._run()

    async def _run(self) -> AsyncIterator[Snapshot]:
        if self._t_anchor is None:
            self._t_anchor = self.clock.now_ms()
        while True:
            while self.paused:
                await self.clock.sleep(self.poll_s)
            f = self.feed_now()
            info, pbp = self._render(f)
            yield Snapshot.at(self.clock.now_ms(), info, pbp, epoch=self.epoch, feed_ms=f)
            if f >= self.end_f:
                return
            await self.clock.sleep(self.poll_s / self.speed)


class RecordingSource:
    """Replays a ``polls.jsonl`` recording with its original spacing, scaled by ``speed``.

    Each successful game-info or play-by-play row becomes one snapshot carrying the latest
    body of both (rows store a body only when it changed). ``available_ms`` comes from the
    row's Age header when recorded. With ``skip_to_first_event`` the replay starts 60 s
    before the first play-by-play row with an event, skipping the hours of pre-game polls.
    """

    def __init__(
        self,
        path: Path,
        clock: Clock,
        *,
        speed: float = 1.0,
        skip_to_first_event: bool = False,
    ) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.clock = clock
        self.speed = speed
        with path.open(encoding="utf-8") as f:
            self.rows = [
                row
                for line in f
                if line.strip()
                and (row := json.loads(line))["endpoint"] in ("game-info", "play-by-play")
            ]
        if not self.rows:
            raise ValueError(f"{path}: no game-info or play-by-play rows")
        self.start_f = self.rows[0]["received_ms"]
        if skip_to_first_event:
            for row in self.rows:
                body = row.get("body")
                has_event = isinstance(body, list) and any("eventId" in e for e in body)
                if row["endpoint"] == "play-by-play" and has_event:
                    self.start_f = max(self.start_f, row["received_ms"] - 60_000)
                    break

    def __aiter__(self) -> AsyncIterator[Snapshot]:
        return self._run()

    async def _run(self) -> AsyncIterator[Snapshot]:
        t0 = self.clock.now_ms()

        def to_clock(feed_ms: int) -> int:
            return t0 + round((feed_ms - self.start_f) / self.speed)

        info: dict[str, Any] | None = None
        pbp: list[dict[str, Any]] | None = None
        raw_info: dict[str, Any] | None = None
        available: int | None = None
        age: int | None = None
        for row in self.rows:
            received = row["received_ms"]
            if received >= self.start_f:
                wait_ms = to_clock(received) - self.clock.now_ms()
                if wait_ms > 0:
                    await self.clock.sleep(wait_ms / 1000)
            if row.get("status") != 200:
                continue
            body = row.get("body")
            if row["endpoint"] == "game-info":
                if isinstance(body, dict):
                    raw_info = body
                    info = shift_info(body, to_clock)
            elif isinstance(body, list):
                pbp = [shift_item(e, to_clock) for e in body if isinstance(e, dict)]
                age = row.get("age") if isinstance(row.get("age"), int) else None
                available = to_clock(received - (age or 0) * 1000)
            if received < self.start_f:
                continue
            if info is None and raw_info is not None:
                info = shift_info(raw_info, to_clock)
            now = to_clock(received)
            yield Snapshot(
                received_ms=now,
                game_info=info,
                pbp=pbp,
                available_ms=available if available is not None else now,
                age_s=age,
                feed_ms=received,
            )


class LiveSource:
    """Follows one game on shl.se (Phase 5). Interface only for now.

    Planned behaviour (CLAUDE.md rule 5, docs/PLAN.md Phase 5): game-info every 60 s
    until 15 min before puck drop, then game-info and play-by-play every 2 s; state from
    play-by-play; stop 2 min after ``GameEnded``; backoff 2 s doubling to 30 s on errors;
    ``Snapshot.age_s`` from the Age header.
    """

    def __init__(self, client: ShlClient, game_uuid: str, clock: Clock) -> None:
        self.client = client
        self.game_uuid = game_uuid
        self.clock = clock

    def __aiter__(self) -> AsyncIterator[Snapshot]:
        raise NotImplementedError("LiveSource arrives in Phase 5")
