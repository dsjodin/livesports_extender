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

import httpx

from app.api.webhooks import WebhookDispatcher
from app.clock import Clock
from app.config import RuntimeConfig, Settings, SourceSettings, StateStore, WebhookSettings
from app.engine import league as league_engine
from app.engine import tvstate
from app.engine import webhooks as webhook_payloads
from app.engine.calibration import Calibrator
from app.engine.delay import DelayQueue, Output
from app.engine.director import Scene, SceneDirector
from app.engine.events import Change, NormalizedEvent
from app.engine.normalizer import Normalizer
from app.feed.assets import AssetCache
from app.feed.client import ShlClient, ShlError
from app.feed.league import LeagueService
from app.feed.polllog import PollLog
from app.feed.schedule import ScheduleService
from app.feed.snapshot import Snapshot
from app.feed.sources import FeedSource, LiveSource, RecordingSource, ReplaySource, Timeline
from app.others import OtherGames
from app.teams import TeamColors

log = logging.getLogger(__name__)

LEAD_MS = 1500
TICK_S = 0.25
STATUS_EVERY_MS = 1000
LOG_SIZE = 400
LEAGUE_REFRESH_S = 600
FOLLOW_CHECK_S = 600  # "follow my team": look at today's schedule (cached 1 h) this often
MANUAL_LEAD_MS = 300  # a MÅL! press plays this soon: the clients need the message first
MANUAL_LINK_BEFORE_MS = 150_000  # a feed goal links if its event_ms is this far before
MANUAL_LINK_AFTER_MS = 5_000  # ... or at most this far after the press
MANUAL_CONFIRM_MS = 180_000  # no feed goal by then: the press is unconfirmed


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
        assets: AssetCache | None = None,
        league: LeagueService | None = None,
        schedule: ScheduleService | None = None,
        webhook_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.clock = clock
        self.assets = assets
        self.league = league
        self.schedule = schedule
        self._follow_task: asyncio.Task[None] | None = None
        self.league_block: dict[str, Any] | None = None
        self._league_task: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[Any]] = set()
        self._league_warned = False
        self.settings = settings
        self.store = store
        self.out = broadcaster
        self.client_factory = client_factory
        self.lead_ms = lead_ms
        self.source: FeedSource | None = None
        self.source_error: str | None = None
        self._source_task: asyncio.Task[None] | None = None
        self.feed_ok = True  # contact with shl.se (feed_health), shown as a red dot on the bar
        self._scheduler_task: asyncio.Task[None] | None = None
        self._last_status_ms = 0
        self.raw_log: deque[dict[str, Any]] = deque(maxlen=LOG_SIZE)
        self.release_log: deque[dict[str, Any]] = deque(maxlen=LOG_SIZE)
        self.colors = TeamColors(settings.config_dir / "teams.json", store.config.team_colors)
        self.calibrator = Calibrator.from_saved(store.config.calibration_samples)
        self.others = OtherGames(
            clock,
            client_factory,
            schedule,
            self.colors,
            settings.data_dir,
            on_change=lambda: self._patch(self.clock.now_ms() + self.lead_ms),
            assets=assets,
        )
        self.webhooks = WebhookDispatcher(
            clock,
            lambda: self.config.webhooks,
            transport=webhook_transport,
            on_log=lambda entry: self.out.broadcast({"t": "webhook", "entry": entry}),
        )
        self.manual: list[dict[str, Any]] = []  # MÅL! presses and test goals, newest last
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
        if hasattr(self, "webhooks"):
            self.webhooks.cancel_pending()  # nothing from the old timeline may still fire
        self.league_block = None
        self.normalizer = Normalizer()
        self.queue = DelayQueue(round(self.config.offset_s * 1000), self.lead_ms)
        self.director = SceneDirector(now)
        self.director.set_game(self.selected, now)
        self.released: dict[str, NormalizedEvent] = {}
        self.timeline: list[dict[str, Any]] = []
        self.meta = tvstate.GameMeta(uuid=self.config.game_uuid, my_side=self.my_side)
        self._attendance: int | None = None
        self.rev = getattr(self, "rev", 0) + 1
        self.planned = self._build()
        self.planned["rev"] = self.rev
        self.applied = copy.deepcopy(self.planned)
        self.pending: list[tuple[int, int, dict[str, Any]]] = []
        self._seq = 0
        self._catching_up = True
        self._linked: dict[str, dict[str, Any]] = {}  # feed goal key -> its MÅL! press
        self.late_goals = 0  # goals that reached us after the TV showed them
        self.last_snapshot_ms: int | None = None
        self.raw_log.clear()
        self.release_log.clear()

    def _build(self) -> dict[str, Any]:
        events = sorted(self.released.values(), key=lambda e: e.received_ms)
        return tvstate.build(
            events,
            self.meta,
            self.director.current.as_dict(),
            self.timeline,
            self.selected,
            self.league_block,
            self.others.summaries(),
        )

    def full_state_messages(self) -> list[dict[str, Any]]:
        """What a newly connected client gets after ``hello``: state, then pending messages."""
        return [{"t": "state", "state": self.applied}] + [m for _, _, m in sorted(self.pending)]

    def config_message(self) -> dict[str, Any]:
        return {
            "offset_ms": round(self.config.offset_s * 1000),
            "lead_ms": self.lead_ms,
            "profile": self.config.active_profile,
            "speed": self.config.source.speed if self.config.source.mode != "none" else 1.0,
            "debug": False,
            "feed_ok": self.feed_ok,
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
        self.last_snapshot_ms = now
        for item in snapshot.pbp or []:
            if isinstance(item, dict) and isinstance(item.get("attendance"), int):
                self._attendance = item["attendance"]
                break
        changes = self.normalizer.apply(snapshot)
        meta = self._meta()
        if meta != self.meta:
            self.meta = meta
            self._patch(now + self.lead_ms)
        for change in changes:
            self._log_raw(change)
            self._register_players(change)
        for out in self.queue.apply(changes, now):
            self._correction(out, now)
        for change in changes:
            if change.kind == "added" and change.event is not None:
                self._link_manual(change.event, now)
        if self.calibrator.update(self.normalizer.events.values(), now):
            self._save_calibration()
        if self._catching_up and snapshot.pbp is not None:
            self._catching_up = False
            self._catch_up(now)
        self.pump(now)

    def _catch_up(self, now: int) -> None:
        """First snapshot after a start or a seek: events the TV has already shown become
        the starting state at once, without event or scene messages (no old goals
        celebrated), and clients get a fresh ``state``."""
        backlog = self.queue.backlog()
        if not backlog:
            return
        for out in backlog:
            event = out.event
            if event is None:
                continue
            self.released[event.key] = event
            if event.type != "shot":
                self.timeline.append(_summary(event, out.play_at))
            self.director.on_event(event, out.play_at)
        self.director.advance(now)
        self.rev += 1
        self.planned = self._build()
        self.planned["rev"] = self.rev
        self.applied = copy.deepcopy(self.planned)
        self.pending.clear()
        self._broadcast_state()

    def _meta(self) -> tvstate.GameMeta:
        meta = tvstate.GameMeta.from_game_info(
            self.normalizer.game_info, self._attendance, self.my_side, self.colors
        )
        if meta.uuid is None:
            meta.uuid = self.config.game_uuid
        info = self.normalizer.game_info or {}
        for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
            team = meta.teams.get(side)
            if team is None:
                continue
            icon = (info.get(key) or {}).get("icon")
            if self.assets is not None:
                self.assets.register_team(team.get("uuid"), icon)
            team["logo"] = (
                f"/assets/teams/{team['uuid']}.svg" if icon and team.get("uuid") else None
            )
        return meta

    def _register_players(self, change: Change) -> None:
        """Tell the asset cache who is who; prefetch a scorer's portrait (not a spoiler: it
        only warms a server-side cache)."""
        event = change.event
        if self.assets is None or event is None or change.kind == "removed" or not event.side:
            return
        own = (self.meta.teams.get(event.side) or {}).get("uuid")
        other = (self.meta.teams.get("away" if event.side == "home" else "home") or {}).get("uuid")
        people: list[tuple[dict[str, Any], str | None]] = []
        if event.player is not None:
            people.append((event.player.model_dump(), own))
        people += [(p, own) for p in event.data.get("assists", [])]
        people += [(p, own) for p in event.data.get("on_ice", [])]
        people += [(p, other) for p in event.data.get("opponents_on_ice", [])]
        for person, team in people:
            self.assets.register_player(
                person.get("id"),
                team,
                person.get("first"),
                person.get("last"),
                person.get("number"),
            )
        if event.type == "goal" and event.player is not None and event.player.id:
            self._spawn(self.assets.player_portrait(event.player.id))

    def _spawn(self, coroutine: Any) -> None:
        task = asyncio.get_running_loop().create_task(coroutine)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # --- league context (pregame, idle) ---------------------------------------------

    async def refresh_league(self) -> None:
        """Standings, form and next games. Only before puck drop: during and after a game
        the block stays as it was, so tonight's results cannot leak in early."""
        if self.league is None or self.applied.get("phase") not in ("idle", "pregame"):
            return
        try:
            standings_raw, games = await self.league.snapshot()
        except ShlError as exc:
            if not self._league_warned:
                log.warning("league data unavailable: %s", exc)
                self._league_warned = True
            return
        self._league_warned = False
        if self.assets is not None:
            for g in games:
                for side in ("home", "away"):
                    self.assets.register_team(g[side]["uuid"], g[side]["icon"])
        game = next((g for g in games if g["uuid"] == self.config.game_uuid), None)
        home = (game or {}).get("home", {}).get("uuid") or (self.meta.teams.get("home") or {}).get(
            "uuid"
        )
        away = (game or {}).get("away", {}).get("uuid") or (self.meta.teams.get("away") or {}).get(
            "uuid"
        )
        start = (game or {}).get("start_ms") or self.meta.start_ms
        history, leaders = await self._league_extras(home, away)
        now = self.clock.now_ms()
        self.league_block = league_engine.build(
            league_engine.standings_rows(standings_raw),
            games,
            now,
            home_uuid=home,
            away_uuid=away,
            start_ms=start,
            my_team_uuid=self.config.my_team_uuid,
            history=history,
            leaders=leaders,
        )
        for block in (self.league_block["teams"] or {}).values():
            for row in [r for rows in ((block or {}).get("leaders") or {}).values() for r in rows]:
                row["portrait"] = f"/assets/players/{row['athlete_uuid']}.png"
                if self.assets is not None:
                    self.assets.register_athlete(
                        row["athlete_uuid"], row["team_uuid"], row["first"], row["last"],
                        str(row["number"]) if row["number"] is not None else None,
                    )  # fmt: skip
        for row in self.league_block["standings"]:
            row["logo"] = f"/assets/teams/{row['uuid']}.svg" if row.get("uuid") else None
        self._patch(now + self.lead_ms)

    async def _league_extras(
        self, home: str | None, away: str | None
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        """Earlier seasons' games and both teams' scoring leaders for the pregame slides;
        empty when shl.se cannot give them (the slides then leave them out)."""
        assert self.league is not None
        history: list[dict[str, Any]] = []
        leaders: dict[str, dict[str, Any]] = {}
        try:
            history = await self.league.history()
        except Exception as exc:  # the rest of the block still updates without it
            log.warning("earlier seasons unavailable: %s", exc)
        for uuid in (home, away):
            if uuid:
                try:
                    leaders[uuid] = await self.league.leaders(uuid)
                except Exception as exc:
                    log.warning("scoring leaders of %s unavailable: %s", uuid, exc)
        return history, leaders

    async def _league_loop(self) -> None:
        while True:
            try:
                await self.refresh_league()
            except asyncio.CancelledError:
                raise
            except Exception:  # a bug must not stop the refreshes for good
                log.exception("league refresh failed")
            await self.clock.sleep(LEAGUE_REFRESH_S)

    @property
    def my_side(self) -> Literal["home", "away"] | None:
        """The explicit side for this game, else the side my team plays on, if it plays."""
        if self.config.my_side == "none":
            return None
        if self.config.my_side is not None:
            return self.config.my_side
        info = self.normalizer.game_info
        if not info or not self.config.my_team_uuid:
            return None
        if (info.get("homeTeam") or {}).get("uuid") == self.config.my_team_uuid:
            return "home"
        if (info.get("awayTeam") or {}).get("uuid") == self.config.my_team_uuid:
            return "away"
        return None

    def set_my_team(self, uuid: str | None) -> None:
        self.config.my_team_uuid = uuid
        self.store.save()
        self.meta = self._meta()
        self._patch(self.clock.now_ms() + self.lead_ms)

    def set_team_colors(self, uuid: str, home: str | None, away: str | None) -> None:
        """Override a team's jersey colours (a palette name or #rrggbb); None keeps it."""
        for value in (home, away):
            if value is not None and not self.colors.valid(value):
                raise SourceError(f"unknown colour {value!r}")
        current = dict(self.config.team_colors.get(uuid, {}))
        if home is not None:
            current["home"] = home
        if away is not None:
            current["away"] = away
        self.config.team_colors[uuid] = current
        self.store.save()
        self.meta = self._meta()
        self._patch(self.clock.now_ms() + self.lead_ms)

    def reset_team_colors(self, uuid: str) -> None:
        self.config.team_colors.pop(uuid, None)
        self.store.save()
        self.meta = self._meta()
        self._patch(self.clock.now_ms() + self.lead_ms)

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
            self.webhooks.cancel_pending()
            self._catching_up = True
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
                self._webhook(disallowed, out.play_at)
                return
            self._patch(out.play_at)

    # --- time -----------------------------------------------------------------------

    def pump(self, now: int) -> None:
        """Hand out everything due within ``lead_ms`` and apply what has reached play_at.
        Our events and the other games' go out together in play_at order, so each patch
        holds only what has played by then."""
        horizon = now + self.lead_ms
        due: list[tuple[int, int, str | None, Output]] = [
            (o.play_at, 0, None, o) for o in self.queue.due(horizon) if o.event is not None
        ]
        due += [(at, 1, uuid, o) for at, uuid, o in self.others.due(horizon)]
        due.sort(key=lambda t: (t[0], t[1]))
        for play_at, _, other, out in due:
            if other is not None and out.event is not None:
                self.others.release(other, out.event)
                self._patch(play_at)
            else:
                self._release(out)
        self._scenes(self.director.advance(horizon))
        self._apply_pending(now)
        if now - self._last_status_ms >= STATUS_EVERY_MS:
            self._last_status_ms = now
            for press in self.manual:
                if press["status"] == "waiting" and now - press["pressed_ms"] > MANUAL_CONFIRM_MS:
                    press["status"] = "unconfirmed"
            if self.calibrator.update(self.normalizer.events.values(), now):
                self._save_calibration()
            self.out.broadcast({"t": "status", "status": self.status()})

    def _release(self, out: Output) -> None:
        """One of our events reaches its play_at window: event, scenes, patch, webhook."""
        event = out.event
        if event is not None:
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
            if event.type == "goal" and out.late:
                self.late_goals += 1
            press = self._linked.get(event.key)
            if press is not None:
                # celebrated already by the MÅL! button: fill in, do not start over
                press["released"] = True
                self._scenes(self.director.relink(press["key"], event, out.play_at))
            else:
                self._scenes(self.director.on_event(event, out.play_at))
            self._patch(out.play_at)
            if press is None:  # a linked goal sent its shl_goal at the press
                self._webhook(event, out.play_at)

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
            self.others.next_due_ms(),
            None if (t := self.director.next_timer_ms()) is None else t - self.lead_ms,
            self.pending[0][0] if self.pending else None,
        ]
        present = [t for t in times if t is not None]
        return min(present) if present else None

    def feed_health(self) -> bool:
        """Is the live feed in contact with shl.se? Always true for replays, recordings
        and a live game that has been followed to its end."""
        source = self.source
        if not isinstance(source, LiveSource):
            return True
        if self._source_task is None or self._source_task.done():
            return self.source_error is None
        return source.healthy()

    def _check_feed(self) -> None:
        ok = self.feed_health()
        if ok != self.feed_ok:
            self.feed_ok = ok
            if ok:
                log.info("contact with shl.se is back")
            else:
                log.warning("contact with shl.se lost")
            self.out.broadcast({"t": "config", "config": self.config_message()})

    async def _scheduler(self) -> None:
        while True:
            now = self.clock.now_ms()
            self._check_feed()
            self.pump(now)
            wake = self.next_wake_ms()
            delay = TICK_S if wake is None else min(TICK_S, max(0.01, (wake - now) / 1000))
            await self.clock.sleep(delay)

    # --- lifecycle ------------------------------------------------------------------

    def start(self) -> None:
        if self._scheduler_task is None:
            self._scheduler_task = asyncio.get_running_loop().create_task(self._scheduler())
        if self.league is not None and self._league_task is None:
            self._league_task = asyncio.get_running_loop().create_task(self._league_loop())
        if self.config.source.mode != "none" and self.source is None:
            self._spawn(self._resume_source())
        if self.schedule is not None and self._follow_task is None:
            self._follow_task = asyncio.get_running_loop().create_task(self._follow_loop())

    # --- follow my team -------------------------------------------------------------

    async def _follow_loop(self) -> None:
        while True:
            try:
                await self.follow_my_team()
            except ShlError as exc:
                log.warning("follow my team: schedule unavailable: %s", exc)
            await self.clock.sleep(FOLLOW_CHECK_S)

    async def follow_my_team(self) -> str | None:
        """Start following my team's game today if that is on and nothing else runs: no
        source, or a live source that has finished. Never interrupts a replay, a recording
        or a live game in progress. Returns the uuid it started, if any."""
        team = self.config.my_team_uuid
        if not self.config.follow_my_team or not team or self.schedule is None:
            return None
        mode = self.config.source.mode
        running = self._source_task is not None and not self._source_task.done()
        if mode in ("replay", "recording") and running:
            return None
        if mode == "live" and running:
            return None
        games = await self.schedule.upcoming(0)
        mine = [
            g
            for g in games
            if team in (g["home"]["uuid"], g["away"]["uuid"]) and g["state"] != "post-game"
        ]
        if not mine:
            return None
        game = mine[0]["uuid"]
        if mode == "live" and self.config.source.uuid == game:
            return None  # already followed today (finished, or stopped by the user)
        log.info("follow my team: following %s", game)
        await self.set_source("live", game)
        self.config.my_side = None  # my side follows my team
        self.store.save()
        return game

    async def set_follow(self, enabled: bool) -> None:
        self.config.follow_my_team = enabled
        self.store.save()
        if enabled:
            await self.follow_my_team()

    async def _resume_source(self) -> None:
        """After a restart, start the saved source again (a replay starts from the top)."""
        src = self.config.source
        try:
            await self.set_source(src.mode, src.uuid, src.path, src.speed)
        except (SourceError, ShlError) as exc:
            self.source_error = str(exc)
            log.warning("could not resume source %s: %s", src.mode, exc)

    async def stop(self) -> None:
        await self._stop_source()
        await self.others.stop()
        await self.webhooks.close()
        for task in [self._league_task, self._follow_task, *self._background]:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._league_task = None
        self._follow_task = None
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

    def select_game(
        self, uuid: str | None, my_side: Literal["home", "away", "none"] | None
    ) -> None:
        self.config.game_uuid = uuid
        self.config.my_side = my_side
        self.store.save()
        now = self.clock.now_ms()
        self.meta = self._meta()
        self._scenes(self.director.set_game(self.selected, now + self.lead_ms))
        self._patch(now + self.lead_ms)
        if self.league is not None:
            self._spawn(self.refresh_league())

    async def set_source(
        self,
        mode: str,
        uuid: str | None = None,
        path: str | None = None,
        speed: float = 1.0,
    ) -> None:
        """Start a source. Raises ``SourceError``."""
        source: FeedSource | None = None
        if mode == "live":
            if not uuid:
                raise SourceError("live needs a game uuid")
            # saved as a recording too, so no second poller is needed (CLAUDE.md rule 5)
            log_path = self.settings.data_dir / "recordings" / uuid / "polls.jsonl"
            source = LiveSource(
                self.client_factory, uuid, self.clock, poll_log=PollLog(log_path, self.clock)
            )
        elif mode == "replay":
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
        self.out.broadcast({"t": "config", "config": self.config_message()})
        self._broadcast_state()
        if source is not None:
            self.source = source
            self._source_task = asyncio.get_running_loop().create_task(self._run_source(source))
        # the evening's other games, live or in step with this replay
        self._spawn(
            self.others.start(
                self.config.game_uuid if mode != "none" else None,
                mode,
                source,
                round(self.config.offset_s * 1000),
                self.lead_ms,
                self._load_finished_game,
            )
        )
        if self.league is not None:
            self._spawn(self.refresh_league())

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
        if not isinstance(source, Timeline):
            # live: shl.se is the clock, nothing to pause or seek
            raise SourceError("only a replay or a recording can be paused or seeked")
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
            self.out.broadcast({"t": "config", "config": self.config_message()})
        elif action == "seek":
            if to == "before_next_goal":
                ok = source.seek_before_next_goal()
            elif to == "end":
                ok = source.seek_end()
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
            if self._source_task is not None and self._source_task.done():
                # it had played to the end: read on from the new position
                self._source_task = asyncio.get_running_loop().create_task(self._run_source(source))
        else:
            raise SourceError(f"unknown replay action {action!r}")
        self.others.follow_main()

    def set_offset(self, profile: str, seconds: float) -> None:
        self.config.profiles[profile] = round(seconds, 3)
        if profile == self.config.active_profile:
            self.queue.set_offset(round(seconds * 1000))
            self.others.set_offset(round(seconds * 1000))
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
        self.others.set_offset(round(self.config.offset_s * 1000))
        self.store.save()
        self.out.broadcast({"t": "config", "config": self.config_message()})
        self.pump(self.clock.now_ms())

    def set_scene(self, name: str, hold_s: float | None) -> None:
        at = self.clock.now_ms() + self.lead_ms
        hold = round(hold_s * 1000) if hold_s else None
        data: dict[str, Any] = {}
        if name == "goal":  # "Mål igen": the latest goal on screen
            goals = [g for g in self.applied.get("goals", []) if not g["data"].get("shootout")]
            if not goals:
                raise SourceError("no goal to show again")
            data = {"event_key": goals[-1]["key"], "side": goals[-1]["side"]}
            hold = hold or 20_000
        self._scenes(self.director.set_override(name, hold, at, data))

    # --- MÅL! button and test goal --------------------------------------------------

    def test_video(
        self, kind: Literal["goal", "intro"], side: Literal["home", "away"] | None
    ) -> int:
        """Play a team video now on the portrait screens (one side, or both), to check the
        files. Only the video: no scene, no state, no webhook. Returns its play_at."""
        at = self.clock.now_ms() + MANUAL_LEAD_MS
        self.out.broadcast({"t": "video", "kind": kind, "side": side, "play_at_ms": at})
        return at

    def manual_goal(self, side: Literal["home", "away"], *, test: bool = False) -> dict[str, Any]:
        """Celebrate now: the goal scene with the team only. A real press waits for the
        feed goal behind it (``_link_manual``); a test goal links to nothing."""
        now = self.clock.now_ms()
        at = now + MANUAL_LEAD_MS
        n = len(self.manual) + 1
        key = f"{'test' if test else 'manual'}-{n}"
        score = dict(self.applied.get("score") or {"home": 0, "away": 0})
        score[side] = score.get(side, 0) + 1
        team = self.meta.teams.get(side) or {}
        period = self.applied.get("period")
        event = NormalizedEvent(
            key=key,
            type="goal",
            raw_type="manual",
            game_uuid=self.meta.uuid,
            period=period if isinstance(period, int) else None,
            side=side,
            team_uuid=team.get("uuid"),
            team_code=team.get("code"),
            data={"manual": True, "score": score, "assists": [], "on_ice": []},
            first_seen_ms=now,
            received_ms=now,
            test=test,
        )
        press: dict[str, Any] = {
            "id": key,
            "key": key,
            "side": side,
            "test": test,
            "pressed_ms": now,
            "status": "test" if test else "waiting",
            "goal_key": None,
            "released": False,
        }
        self.manual.append(press)
        self._emit(_event_message("event", None, event), at)
        self._scenes(self.director.manual_goal(key, side, at, {"manual": True, "score": score}))
        self._webhook(event, at, source="manual")
        if not test:
            # the feed may already hold the goal, waiting for its play_at
            for planned in self.queue.pending():
                if self._link_manual(planned.event, now, only=press):
                    break
        return press

    def _link_manual(
        self, event: NormalizedEvent, now: int, only: dict[str, Any] | None = None
    ) -> bool:
        if event.type != "goal" or event.data.get("shootout") or event.key in self._linked:
            return False
        for press in [only] if only else self.manual:
            if press["status"] != "waiting" or press["side"] != event.side:
                continue
            pressed = press["pressed_ms"]
            if now - pressed > MANUAL_CONFIRM_MS:
                continue
            if event.event_ms is not None and not (
                pressed - MANUAL_LINK_BEFORE_MS <= event.event_ms <= pressed + MANUAL_LINK_AFTER_MS
            ):
                continue
            press["status"], press["goal_key"] = "linked", event.key
            self._linked[event.key] = press
            if self.config.goal_button_sync and event.event_ms is not None:
                self.calibrator.add_sample("goal", pressed, event.side, event)
                self._save_calibration()
            return True
        return False

    def _webhook(self, event: NormalizedEvent, play_at: int, *, source: str = "feed") -> None:
        """Queue the Home Assistant call for an event that plays at ``play_at``."""
        body = webhook_payloads.payload(
            event, self.meta.teams, self.my_side, self.planned.get("score") or {}, source=source
        )
        if body is None:
            return
        if event.test:
            # a test goal is always for my team, so "my team" automations can be tried
            # without a game, or during someone else's game
            body["is_my_team"] = True
            team_uuid = self.config.my_team_uuid
            if team_uuid and self.my_side is None:
                color = self.colors.hex(self.colors.jersey(team_uuid, "home"))
                name = (self.colors.teams.get(team_uuid) or {}).get("name")
                body |= {
                    "team_name": name,
                    "team_color": color,
                    "team_rgb": webhook_payloads.rgb(color),
                }
                body["tts_sv"] = f"Mål för {name}! Det här är ett test." if name else body["tts_sv"]
        self.webhooks.schedule(play_at, body)

    def set_webhooks(self, url: str | None, enabled: bool, events: list[str]) -> None:
        unknown = [e for e in events if e not in webhook_payloads.EVENTS]
        if unknown:
            raise SourceError(f"unknown webhook events {unknown}")
        if enabled and not url:
            raise SourceError("webhooks need a URL")
        self.config.webhooks = WebhookSettings(url=url or None, enabled=enabled, events=events)
        self.store.save()

    def manual_status(self) -> list[dict[str, Any]]:
        """Presses for the phone. The scorer only once the feed goal has played."""
        out = []
        for press in self.manual[-10:]:
            item = {k: press[k] for k in ("id", "side", "test", "pressed_ms", "status")}
            goal = self.released.get(press["goal_key"] or "") if press["released"] else None
            item["scorer"] = goal.player.model_dump() if goal and goal.player else None
            out.append(item)
        return out

    # --- calibration ----------------------------------------------------------------

    def _save_calibration(self) -> None:
        self.config.calibration_samples = [p.as_dict() for p in self.calibrator.presses]
        self.store.save()

    def calibrate(self, kind: str, side: Literal["home", "away"] | None) -> dict[str, Any]:
        now = self.clock.now_ms()
        try:
            press = self.calibrator.press(kind, now, side, self.normalizer.events.values())
        except ValueError as exc:
            raise SourceError(str(exc)) from exc
        self._save_calibration()
        return press.as_dict()

    def calibration(self) -> dict[str, Any]:
        proposal = self.calibrator.proposal_ms()
        return {
            "profile": self.config.active_profile,
            "current_offset_s": self.config.offset_s,
            "samples": [p.as_dict() for p in self.calibrator.presses],
            "proposal_s": None if proposal is None else round(proposal / 1000, 1),
            "proposal_samples": self.calibrator.matched_count(),
            "reaction_ms": 300,
        }

    def accept_calibration(self) -> None:
        proposal = self.calibrator.proposal_ms()
        if proposal is None:
            raise SourceError("no proposal yet")
        self.set_offset(self.config.active_profile, round(proposal / 1000, 1))

    def remove_sample(self, sample_id: str) -> None:
        if not self.calibrator.remove(sample_id):
            raise SourceError(f"no sample {sample_id!r}")
        self._save_calibration()

    def clear_samples(self) -> None:
        self.calibrator.clear()
        self._save_calibration()

    def clear_scene(self) -> None:
        self._scenes(self.director.clear_override(self.clock.now_ms() + self.lead_ms))

    def status(self) -> dict[str, Any]:
        source = self.source if isinstance(self.source, Timeline) else None
        return {
            "source": self.config.source.model_dump(),
            "running": self._source_task is not None and not self._source_task.done(),
            "error": self.source_error,
            "paused": source.paused if source else False,
            "feed_ms": source.feed_now() if source else None,
            "game_uuid": self.config.game_uuid,
            "my_side": self.my_side,
            "my_side_choice": self.config.my_side,
            "my_team_uuid": self.config.my_team_uuid,
            "profile": self.config.active_profile,
            "offset_s": self.config.offset_s,
            "lead_ms": self.lead_ms,
            "raw_events": len(self.normalizer.events),
            "released_events": len(self.released),
            "pending_messages": len(self.pending),
            "others": self.others.status(),
            "last_snapshot_ms": self.last_snapshot_ms,
            "feed_ok": self.feed_ok,
            "late_goals": self.late_goals,
            "manual": self.manual_status(),
            "calibration": self.calibration(),
            "goal_button_sync": self.config.goal_button_sync,
            "follow_my_team": self.config.follow_my_team,
            "webhooks": {
                "enabled": self.config.webhooks.enabled,
                "url_set": bool(self.config.webhooks.url),
                "pending": self.webhooks.pending,
            },
        }
