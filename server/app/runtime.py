"""Runtime: feed source → normalizer → delay queue → TV state and director → messages.

Every message that changes what the screens show carries ``play_at_ms`` and is handed to
the broadcaster ``lead_ms`` before it (CLAUDE.md rule 1). The runtime keeps two TV
states: ``planned`` (after every message sent so far, including future ones) and
``applied`` (only messages whose ``play_at`` has passed). A client that connects gets
``applied`` plus the still-pending messages, so nothing reaches it early.
"""

import asyncio
import contextlib
import copy
import heapq
import json
import logging
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol

from app.clock import Clock
from app.config import RuntimeConfig, Settings, SourceSettings, StateStore
from app.engine import tvstate
from app.engine.delay import DelayQueue, Output
from app.engine.director import Scene, SceneDirector
from app.engine.events import Change, NormalizedEvent
from app.engine.normalizer import Normalizer
from app.feed.client import ShlClient
from app.feed.snapshot import Snapshot
from app.feed.sources import FeedSource, RecordingSource, ReplaySource

log = logging.getLogger(__name__)

LEAD_MS = 1500
TICK_S = 0.25
STATUS_EVERY_MS = 1000
LOG_SIZE = 400


class Broadcaster(Protocol):
    def broadcast(self, message: dict[str, Any], *, raw: bool = False) -> None: ...


class SourceError(Exception):
    """A source could not be started (bad uuid, unfinished game, missing file, ...)."""


def _event_message(t: str, out: Output | None, event: NormalizedEvent) -> dict[str, Any]:
    body = event.model_dump()
    body["late"] = bool(out and out.late)
    body["late_by_ms"] = out.late_by_ms if out else None
    return {"t": t, "event": body}


def _summary(event: NormalizedEvent, play_at: int) -> dict[str, Any]:
    return {
        "key": event.key,
        "type": event.type,
        "period": event.period,
        "time": event.time,
        "side": event.side,
        "label": event.label(),
        "play_at_ms": play_at,
    }


class Runtime:
    def __init__(
        self,
        clock: Clock,
        settings: Settings,
        store: StateStore,
        broadcaster: Broadcaster,
        client_factory: Callable[[], ShlClient] = ShlClient,
        lead_ms: int = LEAD_MS,
    ) -> None:
        self.clock = clock
        self.settings = settings
        self.store = store
        self.out = broadcaster
        self.client_factory = client_factory
        self.lead_ms = lead_ms
        self.source: FeedSource | None = None
        self.source_error: str | None = None
        self._source_task: asyncio.Task[None] | None = None
        self._scheduler_task: asyncio.Task[None] | None = None
        self._last_status_ms = 0
        self.raw_log: deque[dict[str, Any]] = deque(maxlen=LOG_SIZE)
        self.release_log: deque[dict[str, Any]] = deque(maxlen=LOG_SIZE)
        self._reset_engine()

    # --- engine state ---------------------------------------------------------------

    @property
    def config(self) -> RuntimeConfig:
        return self.store.config

    @property
    def selected(self) -> bool:
        return self.config.game_uuid is not None or self.config.source.mode != "none"

    def _reset_engine(self) -> None:
        now = self.clock.now_ms()
        self.normalizer = Normalizer()
        self.queue = DelayQueue(round(self.config.offset_s * 1000), self.lead_ms)
        self.director = SceneDirector(now)
        self.director.set_game(self.selected, now)
        self.released: dict[str, NormalizedEvent] = {}
        self.timeline: list[dict[str, Any]] = []
        self.meta = tvstate.GameMeta(uuid=self.config.game_uuid, my_side=self.config.my_side)
        self._attendance: int | None = None
        self.rev = getattr(self, "rev", 0) + 1
        self.planned = self._build()
        self.planned["rev"] = self.rev
        self.applied = copy.deepcopy(self.planned)
        self.pending: list[tuple[int, int, dict[str, Any]]] = []
        self._seq = 0
        self.raw_log.clear()
        self.release_log.clear()

    def _build(self) -> dict[str, Any]:
        events = sorted(self.released.values(), key=lambda e: e.received_ms)
        return tvstate.build(
            events, self.meta, self.director.current.as_dict(), self.timeline, self.selected
        )

    def full_state_messages(self) -> list[dict[str, Any]]:
        """What a newly connected client gets after ``hello``: state, then pending messages."""
        return [{"t": "state", "state": self.applied}] + [m for _, _, m in sorted(self.pending)]

    def config_message(self) -> dict[str, Any]:
        return {
            "offset_ms": round(self.config.offset_s * 1000),
            "lead_ms": self.lead_ms,
            "profile": self.config.active_profile,
            "debug": False,
        }

    # --- messages -------------------------------------------------------------------

    def _emit(self, message: dict[str, Any], play_at: int) -> None:
        message["play_at_ms"] = play_at
        self._seq += 1
        heapq.heappush(self.pending, (play_at, self._seq, message))
        self.out.broadcast(message)

    def _patch(self, play_at: int) -> None:
        new = self._build()
        changes = {k: v for k, v in tvstate.diff(self.planned, new).items() if k != "scene"}
        if not changes:
            return
        self.rev += 1
        new["rev"] = self.rev
        new["scene"] = self.planned.get("scene")
        self.planned = new
        self._emit({"t": "state_patch", "rev": self.rev, "patch": changes}, play_at)

    def _scenes(self, scenes: list[Scene]) -> None:
        for scene in scenes:
            body = scene.as_dict()
            self.planned["scene"] = body
            self._emit({"t": "scene", "scene": body}, scene.since_ms)

    def _broadcast_state(self) -> None:
        self.out.broadcast({"t": "state", "state": self.applied})

    # --- input ----------------------------------------------------------------------

    def on_snapshot(self, snapshot: Snapshot) -> None:
        now = self.clock.now_ms()
        for item in snapshot.pbp or []:
            if isinstance(item, dict) and isinstance(item.get("attendance"), int):
                self._attendance = item["attendance"]
                break
        changes = self.normalizer.apply(snapshot)
        meta = tvstate.GameMeta.from_game_info(
            self.normalizer.game_info, self._attendance, self.config.my_side
        )
        if meta != self.meta:
            self.meta = meta
            self._patch(now + self.lead_ms)
        for change in changes:
            self._log_raw(change)
        for out in self.queue.apply(changes, now):
            self._correction(out, now)
        self.pump(now)

    def _log_raw(self, change: Change) -> None:
        event = change.event
        entry: dict[str, Any] = {"change": change.kind, "at_ms": self.clock.now_ms()}
        if event is not None:
            entry |= {
                "key": event.key,
                "type": event.type,
                "label": event.label(),
                "event_ms": event.event_ms,
                "first_seen_ms": event.first_seen_ms,
                "received_ms": event.received_ms,
            }
        self.raw_log.append(entry)
        self.out.broadcast({"t": "raw", "entry": entry}, raw=True)

    def _correction(self, out: Output, now: int) -> None:
        if out.kind == "reset":
            self.released.clear()
            self.timeline.clear()
            self.director.reset(self.selected, now)
            self.rev += 1
            self.planned = self._build()
            self.planned["rev"] = self.rev
            self.applied = copy.deepcopy(self.planned)
            self.pending.clear()
            self._broadcast_state()
            return
        event = out.event
        if event is None:
            return
        if out.kind == "update":
            self.released[event.key] = event
            self._emit(_event_message("event_update", None, event), out.play_at)
            self._patch(out.play_at)
        elif out.kind == "remove":
            self.released.pop(event.key, None)
            if event.type == "goal" and isinstance(event.period, int):
                self._scenes(self.director.advance(out.play_at))
                score = tvstate.build(
                    self.released.values(), self.meta, {}, selected=self.selected
                )["score"]
                disallowed = event.model_copy(
                    update={
                        "key": f"{event.key}-disallowed",
                        "type": "goal_disallowed",
                        "data": {"original_key": event.key, "score": score},
                        "received_ms": now,
                    }
                )
                self._emit(_event_message("event", None, disallowed), out.play_at)
                self.timeline.append(_summary(disallowed, out.play_at))
                self._scenes(self.director.on_event(disallowed, out.play_at))
            self._patch(out.play_at)

    # --- time -----------------------------------------------------------------------

    def pump(self, now: int) -> None:
        """Hand out everything due within ``lead_ms`` and apply what has reached play_at."""
        horizon = now + self.lead_ms
        for out in self.queue.due(horizon):
            event = out.event
            if event is None:
                continue
            self._scenes(self.director.advance(out.play_at))
            self.released[event.key] = event
            self._emit(_event_message("event", out, event), out.play_at)
            self.release_log.append(
                {
                    "key": event.key,
                    "label": event.label(),
                    "event_ms": event.event_ms,
                    "first_seen_ms": event.first_seen_ms,
                    "received_ms": event.received_ms,
                    "play_at_ms": out.play_at,
                    "late": out.late,
                    "late_by_ms": out.late_by_ms,
                }
            )
            if event.type not in ("shot",):
                self.timeline.append(_summary(event, out.play_at))
            self._scenes(self.director.on_event(event, out.play_at))
            self._patch(out.play_at)
        self._scenes(self.director.advance(horizon))
        self._apply_pending(now)
        if now - self._last_status_ms >= STATUS_EVERY_MS:
            self._last_status_ms = now
            self.out.broadcast({"t": "status", "status": self.status()})

    def _apply_pending(self, now: int) -> None:
        while self.pending and self.pending[0][0] <= now:
            _, _, message = heapq.heappop(self.pending)
            if message["t"] == "state_patch":
                self.applied.update(copy.deepcopy(message["patch"]))
                self.applied["rev"] = message["rev"]
            elif message["t"] == "scene":
                self.applied["scene"] = message["scene"]

    def next_wake_ms(self) -> int | None:
        times = [
            self.queue.next_due_ms(),
            None if (t := self.director.next_timer_ms()) is None else t - self.lead_ms,
            self.pending[0][0] if self.pending else None,
        ]
        present = [t for t in times if t is not None]
        return min(present) if present else None

    async def _scheduler(self) -> None:
        while True:
            now = self.clock.now_ms()
            self.pump(now)
            wake = self.next_wake_ms()
            delay = TICK_S if wake is None else min(TICK_S, max(0.01, (wake - now) / 1000))
            await self.clock.sleep(delay)

    # --- lifecycle ------------------------------------------------------------------

    def start(self) -> None:
        if self._scheduler_task is None:
            self._scheduler_task = asyncio.get_running_loop().create_task(self._scheduler())

    async def stop(self) -> None:
        await self._stop_source()
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task
            self._scheduler_task = None

    async def _stop_source(self) -> None:
        if self._source_task is not None:
            self._source_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._source_task
        self._source_task = None
        self.source = None

    async def _run_source(self, source: FeedSource) -> None:
        try:
            async for snapshot in source:
                self.on_snapshot(snapshot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a broken source must not kill the service
            log.exception("source failed")
            self.source_error = f"{type(exc).__name__}: {exc}"

    # --- controls -------------------------------------------------------------------

    def select_game(self, uuid: str | None, my_side: Literal["home", "away"] | None) -> None:
        self.config.game_uuid = uuid
        self.config.my_side = my_side
        self.store.save()
        now = self.clock.now_ms()
        self.meta.my_side = my_side
        self._scenes(self.director.set_game(self.selected, now + self.lead_ms))
        self._patch(now + self.lead_ms)

    async def set_source(
        self,
        mode: str,
        uuid: str | None = None,
        path: str | None = None,
        speed: float = 1.0,
    ) -> None:
        """Start a source. Raises ``SourceError`` or ``NotImplementedError`` (live)."""
        if mode == "live":
            raise NotImplementedError("live source arrives in Phase 5")
        source: FeedSource | None = None
        if mode == "replay":
            if not uuid:
                raise SourceError("replay needs a game uuid")
            pbp, info = await self._load_finished_game(uuid)
            source = ReplaySource(pbp, info, self.clock, speed=speed)
        elif mode == "recording":
            source = RecordingSource(
                self._recording_path(path), self.clock, speed=speed, skip_to_first_event=True
            )
        elif mode != "none":
            raise SourceError(f"unknown source mode {mode!r}")
        await self._stop_source()
        if uuid and uuid != self.config.game_uuid:
            self.config.my_side = None
        if uuid:
            self.config.game_uuid = uuid
        self.config.source = SourceSettings.model_validate(
            {"mode": mode, "uuid": uuid, "path": path, "speed": speed}
        )
        self.store.save()
        self.source_error = None
        self._reset_engine()
        self._broadcast_state()
        if source is not None:
            self.source = source
            self._source_task = asyncio.get_running_loop().create_task(self._run_source(source))

    async def _load_finished_game(self, uuid: str) -> tuple[list[Any], dict[str, Any]]:
        fixtures = self.settings.fixtures_dir
        pbp_file, info_file = fixtures / f"pbp_{uuid}.json", fixtures / f"game_info_{uuid}.json"
        if pbp_file.exists() and info_file.exists():
            return (
                json.loads(pbp_file.read_text(encoding="utf-8")),
                json.loads(info_file.read_text(encoding="utf-8")),
            )
        async with self.client_factory() as client:
            info = (await client.game_info(uuid)).data
            state = ((info or {}).get("gameInfo") or {}).get("state")
            if state not in ("post_game", "post-game"):
                raise SourceError(f"{uuid} is not a finished game (state {state!r})")
            pbp = (await client.play_by_play(uuid)).data
        return pbp, info

    def _recording_path(self, path: str | None) -> Path:
        if not path:
            raise SourceError("recording needs a path")
        base = (self.settings.data_dir / "recordings").resolve()
        candidate = (base / path).resolve()
        if candidate.is_dir():
            candidate = candidate / "polls.jsonl"
        if base not in candidate.parents or not candidate.is_file():
            raise SourceError(f"no recording at {path!r} under {base}")
        return candidate

    def replay_control(
        self, action: str, speed: float | None = None, to: str | None = None
    ) -> None:
        source = self.source
        if not isinstance(source, ReplaySource):
            raise SourceError("no replay is running")
        if action == "play":
            source.play()
        elif action == "pause":
            source.pause()
        elif action == "speed":
            if not speed:
                raise SourceError("speed needs a value")
            source.set_speed(speed)
            self.config.source.speed = speed
            self.store.save()
        elif action == "seek":
            if to == "before_next_goal":
                ok = source.seek_before_next_goal()
            elif to == "next_period":
                current = max(
                    (
                        e.period
                        for e in self.normalizer.events.values()
                        if e.type == "period_start" and isinstance(e.period, int)
                    ),
                    default=0,
                )
                ok = source.seek_period(current + 1)
            elif to and to.startswith("period:"):
                ok = source.seek_period(int(to.split(":", 1)[1]))
            else:
                raise SourceError(f"unknown seek target {to!r}")
            if not ok:
                raise SourceError(f"nothing to seek to for {to!r}")
        else:
            raise SourceError(f"unknown replay action {action!r}")

    def set_offset(self, profile: str, seconds: float) -> None:
        self.config.profiles[profile] = round(seconds, 3)
        if profile == self.config.active_profile:
            self.queue.set_offset(round(seconds * 1000))
        self.store.save()
        self.out.broadcast({"t": "config", "config": self.config_message()})
        self.pump(self.clock.now_ms())

    def nudge_offset(self, delta: float) -> None:
        self.set_offset(self.config.active_profile, self.config.offset_s + delta)

    def set_profile(self, profile: str) -> None:
        if profile not in self.config.profiles:
            raise SourceError(f"unknown TV profile {profile!r}")
        self.config.active_profile = profile
        self.queue.set_offset(round(self.config.offset_s * 1000))
        self.store.save()
        self.out.broadcast({"t": "config", "config": self.config_message()})
        self.pump(self.clock.now_ms())

    def set_scene(self, name: str, hold_s: float | None) -> None:
        at = self.clock.now_ms() + self.lead_ms
        hold = round(hold_s * 1000) if hold_s else None
        self._scenes(self.director.set_override(name, hold, at))

    def clear_scene(self) -> None:
        self._scenes(self.director.clear_override(self.clock.now_ms() + self.lead_ms))

    def status(self) -> dict[str, Any]:
        source = self.source if isinstance(self.source, ReplaySource) else None
        return {
            "source": self.config.source.model_dump(),
            "running": self._source_task is not None and not self._source_task.done(),
            "error": self.source_error,
            "paused": source.paused if source else False,
            "feed_ms": source.feed_now() if source else None,
            "game_uuid": self.config.game_uuid,
            "my_side": self.config.my_side,
            "profile": self.config.active_profile,
            "offset_s": self.config.offset_s,
            "lead_ms": self.lead_ms,
            "raw_events": len(self.normalizer.events),
            "released_events": len(self.released),
            "pending_messages": len(self.pending),
        }
