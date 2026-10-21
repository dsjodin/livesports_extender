"""Snapshot sources, all async iterators of ``Snapshot`` driven by an injectable ``Clock``.

- ``ReplaySource`` plays a finished game from its final play-by-play.
- ``RecordingSource`` plays a ``polls.jsonl`` made by ``tools/record_game.py`` or by
  following a game live.

Both can be paused, sped up and seeked (``Timeline``).
- ``LiveSource`` follows a real game on shl.se.

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
from app.feed.client import FeedResponse, ShlClient, ShlError
from app.feed.polllog import PollLog
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


class Timeline:
    """Play, pause, speed and seek on a feed timeline, shared by the replay and recording
    sources. ``feed_now`` is the position on the original feed's clock; ``to_clock`` maps
    a feed time onto our clock. A seek starts a new ``epoch``: consumers start over.

    Subclasses set ``start_f``/``end_f``, ``_goals`` (on-ice goal times),
    ``_period_starts`` (period -> on-ice start) and ``_end_seek_f`` (when the game ended,
    or None), and call ``_init_timeline`` first.
    """

    clock: Clock
    speed: float
    start_f: int
    end_f: int
    _goals: list[int]
    _period_starts: dict[int | str, int]
    _end_seek_f: int | None

    def _init_timeline(self) -> None:
        self.epoch = 0
        self.paused = False
        self._t_anchor: int | None = None
        self._f_anchor = self.start_f
        self._version = 0

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
        started = self._period_starts.get(period)
        if started is None:
            return False
        self.seek(started - round(before_s * 1000))
        return True

    def seek_end(self, after_s: float = 5.0) -> bool:
        """Seek to just after the game ended (``after_s`` past the last period's end)."""
        if self._end_seek_f is None:
            return False
        self.seek(self._end_seek_f + round(after_s * 1000))
        return True

    def seek_before_next_goal(self, before_s: float = 10.0) -> bool:
        """Seek to ``before_s`` before the next goal's on-ice moment."""
        now = self.feed_now()
        i = bisect.bisect_right(self._goals, now + round(before_s * 1000))
        if i == len(self._goals):
            return False
        self.seek(self._goals[i] - round(before_s * 1000))
        return True


class ReplaySource(Timeline):
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

        self._period_starts = {
            item["period"]: started
            for item in pbp_full
            if isinstance(item, dict)
            and item.get("type") == "period"
            and (started := parse_local_ms(item.get("startedAt"))) is not None
        }
        self._end_seek_f = self._ended_f
        self._init_timeline()
        self._cache_key: tuple[Any, ...] | None = None
        self._cache: tuple[dict[str, Any], list[dict[str, Any]]] | None = None

    @classmethod
    def from_fixtures(
        cls, fixtures: Path, game_uuid: str, clock: Clock, **kwargs: Any
    ) -> "ReplaySource":
        pbp = json.loads((fixtures / f"pbp_{game_uuid}.json").read_text(encoding="utf-8"))
        info = json.loads((fixtures / f"game_info_{game_uuid}.json").read_text(encoding="utf-8"))
        return cls(pbp, info, clock, **kwargs)

    # --- controls -------------------------------------------------------------------

    def follow(self, main: "ReplaySource") -> None:
        """Run on ``main``'s timeline: same position, speed and pause (for the evening's
        other games, so they replay in step with ours). A jump starts over (new epoch)."""
        jumped = abs(self.feed_now() - main.feed_now()) > 5_000
        self._f_anchor, self._t_anchor = main._f_anchor, main._t_anchor
        self.speed, self.paused = main.speed, main.paused
        self._version += 1
        if jumped:
            self.epoch += 1

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


class RecordingSource(Timeline):
    """Replays a ``polls.jsonl`` recording with its original spacing, scaled by ``speed``.

    Each successful game-info or play-by-play row becomes one snapshot carrying the latest
    body of both (rows store a body only when it changed). ``available_ms`` comes from the
    row's Age header when recorded. With ``skip_to_first_event`` the replay starts 60 s
    before the first play-by-play row with an event, skipping the hours of pre-game polls.
    Play, pause, speed and seek work as for ``ReplaySource``; the seek targets (goals,
    period starts, the end) come from the last play-by-play in the recording, and a seek
    shows what had been received by then.
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
        self.end_f = self.rows[-1]["received_ms"]
        if skip_to_first_event:
            for row in self.rows:
                body = row.get("body")
                has_event = isinstance(body, list) and any("eventId" in e for e in body)
                if row["endpoint"] == "play-by-play" and has_event:
                    self.start_f = max(self.start_f, row["received_ms"] - 60_000)
                    break
        self._index_final()
        self._init_timeline()
        self._shifted: dict[str, tuple[tuple[int, int], Any]] = {}

    def _index_final(self) -> None:
        """Seek targets from the last play-by-play body (the most complete one)."""
        final: list[dict[str, Any]] = next(
            (
                [e for e in row["body"] if isinstance(e, dict)]
                for row in reversed(self.rows)
                if row["endpoint"] == "play-by-play" and isinstance(row.get("body"), list)
            ),
            [],
        )
        self._goals = sorted(
            at
            for e in final
            if e.get("type") == "goal"
            and isinstance(e.get("period"), int)
            and (at := parse_local_ms(e.get("realWorldTime"))) is not None
        )
        periods = [e for e in final if e.get("type") == "period"]
        self._period_starts = {
            e["period"]: at for e in periods if (at := parse_local_ms(e.get("startedAt")))
        }
        ended = any(e.get("gameState") == "GameEnded" for e in final)
        finishes = [at for e in periods if (at := parse_local_ms(e.get("finishedAt")))]
        self._end_seek_f = max(finishes) if ended and finishes else None

    def __aiter__(self) -> AsyncIterator[Snapshot]:
        return self._run()

    def _restore(self, position: int) -> tuple[int, dict[str, Any]]:
        """The latest bodies received before ``position``; returns the next row's index."""
        latest: dict[str, Any] = {"info": None, "pbp": None, "avail_f": None, "age": None}
        i = 0
        while i < len(self.rows) and self.rows[i]["received_ms"] < position:
            self._take(latest, self.rows[i])
            i += 1
        return i, latest

    @staticmethod
    def _take(latest: dict[str, Any], row: dict[str, Any]) -> None:
        if row.get("status") != 200:
            return
        body = row.get("body")
        if row["endpoint"] == "game-info":
            if isinstance(body, dict):
                latest["info"] = body
        elif isinstance(body, list):
            latest["pbp"] = body
            age = row.get("age") if isinstance(row.get("age"), int) else None
            latest["age"] = age
            latest["avail_f"] = row["received_ms"] - (age or 0) * 1000

    def _shift(self, name: str, body: Any) -> Any:
        """``body`` moved onto the clock; the same object until it or the mapping changes."""
        if body is None:
            return None
        key = (id(body), self._version)
        cached = self._shifted.get(name)
        if cached is None or cached[0] != key:
            if name == "info":
                value: Any = shift_info(body, self.to_clock)
            else:
                value = [shift_item(e, self.to_clock) for e in body if isinstance(e, dict)]
            cached = (key, value)
            self._shifted[name] = cached
        return cached[1]

    def _snapshot(self, latest: dict[str, Any], feed_ms: int) -> Snapshot:
        now = self.to_clock(feed_ms)
        avail = latest["avail_f"]
        return Snapshot(
            received_ms=now,
            game_info=self._shift("info", latest["info"]),
            pbp=self._shift("pbp", latest["pbp"]),
            available_ms=self.to_clock(avail) if avail is not None else now,
            age_s=latest["age"],
            epoch=self.epoch,
            feed_ms=feed_ms,
        )

    async def _run(self) -> AsyncIterator[Snapshot]:
        if self._t_anchor is None:
            self._t_anchor = self.clock.now_ms()
        epoch = self.epoch
        i, latest = self._restore(self.feed_now())
        while i < len(self.rows):
            if self.epoch != epoch:
                # a seek: start over from what had been received by the new position
                epoch = self.epoch
                position = self.feed_now()
                i, latest = self._restore(position)
                if latest["info"] is not None or latest["pbp"] is not None:
                    yield self._snapshot(latest, position)
                continue
            row = self.rows[i]
            if self.paused:
                await self.clock.sleep(0.5)
                continue
            wait_ms = self.to_clock(row["received_ms"]) - self.clock.now_ms()
            if wait_ms > 0:
                # in steps, so a pause or a seek is picked up within a second
                await self.clock.sleep(min(wait_ms, 1000) / 1000)
                continue
            self._take(latest, row)
            i += 1
            if row.get("status") == 200:
                yield self._snapshot(latest, row["received_ms"])


LIVE_FAST_S = 2.0
LIVE_SLOW_S = 60.0
LIVE_FAST_BEFORE_S = 15 * 60
LIVE_STOP_AFTER_S = 120.0
LIVE_FINAL_REFRESH_S = 30 * 60
LIVE_FINAL_TRIES = 3
BACKOFF_START_S = 2.0
BACKOFF_MAX_S = 30.0
KNOWN_INFO_STATES = {"pre-game", "post-game"}


class LiveSource:
    """Follows one game on shl.se (CLAUDE.md rule 5).

    ``game-info`` every 60 s until 15 min before puck drop, then ``game-info`` and
    ``play-by-play`` every 2 s. game-info goes stale during the game (docs/SHL_API.md),
    so the game is over when play-by-play says ``GameEnded`` (or game-info says
    post-game); polling stops 2 min after that, at once if the game was already over on
    the first poll. shl.se keeps correcting events after the game, so 30 min after the
    end both are fetched once more (up to 3 tries) before the source ends. Errors back
    off from 2 s doubling to 30 s. ``Snapshot.age_s`` is play-by-play's Age header.

    With a ``PollLog`` every request is also saved as a recording; the final refresh
    then adds the boxscore and team-stats, as ``tools/record_game.py`` does.
    """

    def __init__(
        self,
        client_factory: Callable[[], ShlClient],
        game_uuid: str,
        clock: Clock,
        *,
        stop_after_s: float = LIVE_STOP_AFTER_S,
        final_refresh_s: float | None = LIVE_FINAL_REFRESH_S,
        poll_log: PollLog | None = None,
    ) -> None:
        self.client_factory = client_factory
        self.game_uuid = game_uuid
        self.clock = clock
        self.stop_after_s = stop_after_s
        self.final_refresh_s = final_refresh_s
        self.poll_log = poll_log
        self.polls = 0
        self._warned: set[str] = set()

    def __aiter__(self) -> AsyncIterator[Snapshot]:
        return self._run()

    async def _get(self, client: ShlClient, endpoint: str) -> FeedResponse:
        """One request, saved to the poll log when there is one."""
        calls = {
            "game-info": client.game_info,
            "play-by-play": client.play_by_play,
            "boxscore": client.boxscore,
            "team-stats": client.team_stats,
        }
        try:
            response = await calls[endpoint](self.game_uuid)
        except ShlError as exc:
            if self.poll_log is not None:
                self.poll_log.error(endpoint, exc)
            raise
        if self.poll_log is not None:
            self.poll_log.ok(endpoint, response.data, response.age_s, response.cache)
        return response

    async def _final_refresh(self, client: ShlClient, over_since: int) -> Snapshot | None:
        assert self.final_refresh_s is not None
        wait_ms = over_since + round(self.final_refresh_s * 1000) - self.clock.now_ms()
        if wait_ms > 0:
            await self.clock.sleep(wait_ms / 1000)
        backoff = BACKOFF_START_S
        for _ in range(LIVE_FINAL_TRIES):
            self.polls += 1
            try:
                info = (await self._get(client, "game-info")).data
                response = await self._get(client, "play-by-play")
            except ShlError as exc:
                log.warning("live %s final refresh: %s", self.game_uuid, exc)
                await self.clock.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX_S)
                continue
            if self.poll_log is not None:
                for extra in ("boxscore", "team-stats"):
                    try:
                        await self._get(client, extra)
                    except ShlError as exc:
                        log.warning("live %s %s: %s", self.game_uuid, extra, exc)
            return Snapshot.at(self.clock.now_ms(), info, response.data, age_s=response.age_s)
        return None

    def _info_state(self, info: dict[str, Any]) -> str | None:
        raw = (info.get("gameInfo") or {}).get("state")
        state = raw.replace("_", "-") if isinstance(raw, str) else None
        if state is not None and state not in KNOWN_INFO_STATES and state not in self._warned:
            self._warned.add(state)
            log.warning("live: unrecognised game-info state %r", raw)
        return state

    async def _run(self) -> AsyncIterator[Snapshot]:
        try:
            async for snapshot in self._poll():
                yield snapshot
        finally:
            if self.poll_log is not None:
                self.poll_log.close()

    async def _poll(self) -> AsyncIterator[Snapshot]:
        backoff = BACKOFF_START_S
        over_since: int | None = None
        first = True
        async with self.client_factory() as client:
            while True:
                self.polls += 1
                try:
                    info = (await self._get(client, "game-info")).data
                    state = self._info_state(info)
                    start = parse_utc_ms((info.get("gameInfo") or {}).get("startDateTime"))
                    now = self.clock.now_ms()
                    fast = state != "pre-game" or (
                        start is not None and now >= start - LIVE_FAST_BEFORE_S * 1000
                    )
                    pbp: list[dict[str, Any]] | None = None
                    age: int | None = None
                    if fast:
                        response = await self._get(client, "play-by-play")
                        pbp, age = response.data, response.age_s
                except ShlError as exc:
                    log.warning("live %s: %s, retry in %.0f s", self.game_uuid, exc, backoff)
                    await self.clock.sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX_S)
                    continue
                backoff = BACKOFF_START_S
                yield Snapshot.at(self.clock.now_ms(), info, pbp, age_s=age)
                ended = state == "post-game" or any(
                    isinstance(e, dict) and e.get("gameState") == "GameEnded" for e in pbp or []
                )
                if ended:
                    if first:
                        return
                    over_since = over_since or self.clock.now_ms()
                    if self.clock.now_ms() - over_since >= self.stop_after_s * 1000:
                        if self.final_refresh_s is not None:
                            final = await self._final_refresh(client, over_since)
                            if final is not None:
                                yield final
                        return
                first = False
                await self.clock.sleep(LIVE_FAST_S if fast else LIVE_SLOW_S)


OTHER_POLL_S = 30.0


class OtherLiveSource:
    """Another game of the evening (CLAUDE.md rule 5): play-by-play every 30 s from 15 min
    before its start until 2 min after ``GameEnded``; once if it is already over. No
    game-info: the schedule has the teams. Errors back off from 2 s doubling to 30 s."""

    def __init__(
        self,
        client_factory: Callable[[], ShlClient],
        game_uuid: str,
        clock: Clock,
        start_ms: int | None,
        *,
        poll_s: float = OTHER_POLL_S,
        stop_after_s: float = LIVE_STOP_AFTER_S,
        poll_log: PollLog | None = None,
    ) -> None:
        self.client_factory = client_factory
        self.game_uuid = game_uuid
        self.clock = clock
        self.start_ms = start_ms
        self.poll_s = poll_s
        self.stop_after_s = stop_after_s
        self.poll_log = poll_log
        self.polls = 0

    def __aiter__(self) -> AsyncIterator[Snapshot]:
        return self._run()

    async def _run(self) -> AsyncIterator[Snapshot]:
        try:
            async for snapshot in self._poll():
                yield snapshot
        finally:
            if self.poll_log is not None:
                self.poll_log.close()

    async def _poll(self) -> AsyncIterator[Snapshot]:
        if self.start_ms is not None:
            while (wait := self.start_ms - LIVE_FAST_BEFORE_S * 1000 - self.clock.now_ms()) > 0:
                await self.clock.sleep(min(wait, 60_000) / 1000)
        backoff = BACKOFF_START_S
        over_since: int | None = None
        first = True
        async with self.client_factory() as client:
            while True:
                self.polls += 1
                try:
                    response = await client.play_by_play(self.game_uuid)
                except ShlError as exc:
                    if self.poll_log is not None:
                        self.poll_log.error("play-by-play", exc)
                    log.warning("other game %s: %s, retry in %.0f s", self.game_uuid, exc, backoff)
                    await self.clock.sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX_S)
                    continue
                backoff = BACKOFF_START_S
                if self.poll_log is not None:
                    self.poll_log.ok("play-by-play", response.data, response.age_s, response.cache)
                pbp = response.data if isinstance(response.data, list) else []
                yield Snapshot.at(self.clock.now_ms(), None, pbp, age_s=response.age_s)
                if any(isinstance(e, dict) and e.get("gameState") == "GameEnded" for e in pbp):
                    if first:
                        return
                    over_since = over_since or self.clock.now_ms()
                    if self.clock.now_ms() - over_since >= self.stop_after_s * 1000:
                        return
                first = False
                await self.clock.sleep(self.poll_s)
