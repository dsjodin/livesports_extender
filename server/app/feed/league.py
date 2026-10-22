"""Standings and schedule for the league block, fetched at most once an hour; for the
pregame slides also earlier seasons' games (head-to-head) and each team's scoring
leaders (docs/SHL_API.md, Statistics)."""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.clock import Clock
from app.feed.client import ShlClient, ShlError
from app.feed.schedule import CACHE_MS, ScheduleService, simplify

log = logging.getLogger(__name__)

HISTORY_SEASONS = 2  # seasons before this one searched for head-to-head meetings
HISTORY_TYPES = ("regular", "playoff")
LEADERS = 3  # players per list (points, goals)
LEADER_MODULES = {"points": "players_point", "goals": "players_goal"}


class LeagueService:
    def __init__(
        self,
        schedule: ScheduleService,
        client_factory: Callable[[], ShlClient],
        clock: Clock,
        cache_dir: Path | None = None,
    ) -> None:
        self.schedule = schedule
        self.client_factory = client_factory
        self.clock = clock
        self.cache_dir = cache_dir
        self._standings: dict[str, Any] | None = None
        self._fetched_ms: int | None = None
        self._history: tuple[int, list[dict[str, Any]]] | None = None
        self._leaders: dict[str, tuple[int, dict[str, Any]]] = {}

    async def standings(self) -> dict[str, Any] | None:
        now = self.clock.now_ms()
        if (
            self._standings is None
            or self._fetched_ms is None
            or now - self._fetched_ms >= CACHE_MS
        ):
            async with self.client_factory() as client:
                ssgt = (await client.filter()).data["ssgtUuid"]
                self._standings = (await client.standings(ssgt)).data
            self._fetched_ms = now
        return self._standings

    async def snapshot(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        return await self.standings(), await self.schedule.games()

    # --- head-to-head ----------------------------------------------------------------

    async def history(self) -> list[dict[str, Any]]:
        """Games outside this season's regular-season schedule: this season's playoffs
        and the regular season and playoffs of the HISTORY_SEASONS before. Finished
        seasons are kept on disk for good (they do not change); refreshed hourly."""
        now = self.clock.now_ms()
        if self._history and now - self._history[0] < CACHE_MS:
            return self._history[1]
        games: list[dict[str, Any]] = []
        async with self.client_factory() as client:
            filt = (await client.filter()).data
            current = filt["defaultSsgtFilter"]["season"]
            series = filt["defaultSsgtFilter"]["series"]
            seasons = [s["uuid"] for s in filt.get("season") or []]
            start = seasons.index(current) if current in seasons else 0
            for season in seasons[start : start + 1 + HISTORY_SEASONS]:
                closed = season != current
                types = (await client.season_filter(season)).data.get("gameType") or []
                for game_type in types:
                    code = game_type.get("code")
                    if code not in HISTORY_TYPES or (not closed and code == "regular"):
                        continue  # this season's regular games come from the schedule
                    raw = await self._season_games(
                        client, season, series, game_type["uuid"], closed
                    )
                    games += [simplify(g, code) for g in raw]
        self._history = (now, games)
        return games

    async def _season_games(
        self, client: ShlClient, season: str, series: str, game_type: str, closed: bool
    ) -> list[dict[str, Any]]:
        file = (
            self.cache_dir / "schedules" / f"{season}_{game_type}.json" if self.cache_dir else None
        )
        if closed and file is not None and file.exists():
            return list(json.loads(file.read_text(encoding="utf-8")))
        raw = list((await client.schedule(season, series, game_type)).data.get("gameInfo") or [])
        if closed and file is not None:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return raw

    # --- scoring leaders -------------------------------------------------------------

    async def leaders(self, team_uuid: str) -> dict[str, Any]:
        """The team's top LEADERS by points and by goals this season, raw rows from
        stats-info; cached for an hour per team. Empty lists when shl.se has none."""
        now = self.clock.now_ms()
        cached = self._leaders.get(team_uuid)
        if cached and now - cached[0] < CACHE_MS:
            return cached[1]
        standings = await self.standings() or {}
        provider = standings.get("provider") or "statnet"
        out: dict[str, Any] = {}
        async with self.client_factory() as client:
            ssgt = (await client.filter()).data["ssgtUuid"]
            for name, module in LEADER_MODULES.items():
                try:
                    data = (
                        await client.stats_info(module, ssgt, team_uuid, LEADERS, provider)
                    ).data
                except ShlError as exc:
                    log.warning("no %s leaders for %s: %s", name, team_uuid, exc)
                    data = []
                first = data[0] if isinstance(data, list) and data else {}
                out[name] = list(first.get("stats") or [])[:LEADERS]
        self._leaders[team_uuid] = (now, out)
        return out
