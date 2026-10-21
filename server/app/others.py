"""Runs the evening's other games next to ours (CLAUDE.md rule 5, docs/PLAN.md Phase 8).

Picks the SHL games played the same day as ours from the schedule; follows each one with
an ``OtherLiveSource`` (live: play-by-play every 30 s, saved as a recording) or a
``ReplaySource`` in step with our replay. Their events go through each game's own
DelayQueue (engine/others.py); the runtime releases them in play_at order and patches the
TV state.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from app.clock import Clock
from app.engine.delay import Output
from app.engine.events import NormalizedEvent
from app.engine.others import OtherGame
from app.feed.assets import AssetCache
from app.feed.client import ShlClient, ShlError
from app.feed.polllog import PollLog
from app.feed.schedule import ScheduleService
from app.feed.snapshot import Snapshot
from app.feed.sources import FeedSource, OtherLiveSource, ReplaySource
from app.feedtime import STOCKHOLM
from app.teams import TeamColors

log = logging.getLogger(__name__)

LoadGame = Callable[[str], Awaitable[tuple[list[Any], dict[str, Any]]]]


def same_day(a_ms: int, b_ms: int) -> bool:
    day = lambda ms: datetime.fromtimestamp(ms / 1000, STOCKHOLM).date()  # noqa: E731
    return day(a_ms) == day(b_ms)


class OtherGames:
    def __init__(
        self,
        clock: Clock,
        client_factory: Callable[[], ShlClient],
        schedule: ScheduleService | None,
        colors: TeamColors,
        data_dir: Path,
        on_change: Callable[[], None],
        assets: AssetCache | None = None,
    ) -> None:
        self.clock = clock
        self.client_factory = client_factory
        self.schedule = schedule
        self.colors = colors
        self.data_dir = data_dir
        self.on_change = on_change
        self.assets = assets
        self.games: dict[str, OtherGame] = {}
        self.sources: dict[str, FeedSource] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._main: ReplaySource | None = None

    # --- lifecycle --------------------------------------------------------------------

    async def start(
        self,
        our_uuid: str | None,
        mode: str,
        main: FeedSource | None,
        offset_ms: int,
        lead_ms: int,
        load_game: LoadGame,
    ) -> None:
        """(Re)start for our game. Live: poll the others; replay: replay them in step."""
        await self.stop()
        if self.schedule is None or not our_uuid or mode not in ("live", "replay"):
            return
        try:
            games = await self.schedule.games()
        except ShlError as exc:
            log.warning("other games: schedule unavailable: %s", exc)
            return
        ours = next((g for g in games if g["uuid"] == our_uuid), None)
        if ours is None or ours["start_ms"] is None:
            return
        others = [
            g
            for g in games
            if g["uuid"] != our_uuid and g["start_ms"] and same_day(g["start_ms"], ours["start_ms"])
        ]
        self._main = main if isinstance(main, ReplaySource) else None
        for g in others:
            uuid = g["uuid"]
            source: FeedSource
            if mode == "live":
                path = self.data_dir / "recordings" / uuid / "polls.jsonl"
                source = OtherLiveSource(
                    self.client_factory,
                    uuid,
                    self.clock,
                    g["start_ms"],
                    poll_log=PollLog(path, self.clock),
                )
            else:
                if self._main is None:
                    return
                try:
                    pbp, info = await load_game(uuid)
                except Exception as exc:  # a missing other game must not stop ours
                    log.warning("other game %s not replayable: %s", uuid, exc)
                    continue
                replay = ReplaySource(pbp, info, self.clock, speed=self._main.speed, poll_s=30.0)
                replay.follow(self._main)
                source = replay
            self.games[uuid] = OtherGame(uuid, g["start_ms"], self._teams(g), offset_ms, lead_ms)
            self.sources[uuid] = source
            self._tasks[uuid] = asyncio.get_running_loop().create_task(self._run(uuid, source))
        log.info("other games: %d (%s)", len(self.games), mode)
        self.on_change()

    def _teams(self, game: dict[str, Any]) -> dict[str, dict[str, Any]]:
        teams = {}
        for side in ("home", "away"):
            t = game[side]
            if self.assets is not None:
                self.assets.register_team(t["uuid"], t.get("icon"))
            jersey = self.colors.jersey(t["uuid"], side)
            teams[side] = {
                "uuid": t["uuid"],
                "code": t["code"],
                "short": t["short"],
                "long": t["long"],
                "logo": f"/assets/teams/{t['uuid']}.svg" if t.get("icon") else None,
                "color": self.colors.hex(jersey),
            }
        return teams

    async def _run(self, uuid: str, source: FeedSource) -> None:
        try:
            async for snapshot in source:
                self.on_snapshot(uuid, snapshot)
        except asyncio.CancelledError:
            raise
        except Exception:  # one other game failing must not affect ours
            log.exception("other game %s failed", uuid)

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        had = bool(self.games)
        self._tasks.clear()
        self.sources.clear()
        self.games.clear()
        self._main = None
        if had:
            self.on_change()

    # --- feed -------------------------------------------------------------------------

    def on_snapshot(self, uuid: str, snapshot: Snapshot) -> None:
        game = self.games.get(uuid)
        if game is not None and game.apply(snapshot, self.clock.now_ms()):
            self.on_change()

    def follow_main(self) -> None:
        """After a control on our replay (play, pause, speed, seek): keep the others in step."""
        if self._main is None:
            return
        for source in self.sources.values():
            if isinstance(source, ReplaySource):
                source.follow(self._main)

    def set_offset(self, offset_ms: int) -> None:
        for game in self.games.values():
            game.set_offset(offset_ms)

    def due(self, horizon_ms: int) -> list[tuple[int, str, Output]]:
        """(play_at, game uuid, output) due within ``horizon_ms``, in play_at order."""
        out = [
            (o.play_at, uuid, o)
            for uuid, game in self.games.items()
            for o in game.due(horizon_ms)
            if o.event is not None
        ]
        return sorted(out, key=lambda t: t[0])

    def release(self, uuid: str, event: NormalizedEvent) -> None:
        game = self.games.get(uuid)
        if game is not None:
            game.release(event)

    def next_due_ms(self) -> int | None:
        times = [t for g in self.games.values() if (t := g.queue.next_due_ms()) is not None]
        return min(times) if times else None

    def summaries(self) -> list[dict[str, Any]]:
        out = [g.summary() for g in self.games.values()]
        return sorted(out, key=lambda s: (s["start_ms"] or 0, s["teams"]["home"]["code"] or ""))

    def status(self) -> dict[str, Any]:
        return {
            "games": len(self.games),
            "polls": sum(getattr(s, "polls", 0) for s in self.sources.values()),
        }
