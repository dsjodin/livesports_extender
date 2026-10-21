"""Standings and schedule for the league block, fetched at most once an hour."""

import logging
from collections.abc import Callable
from typing import Any

from app.clock import Clock
from app.feed.client import ShlClient
from app.feed.schedule import CACHE_MS, ScheduleService

log = logging.getLogger(__name__)


class LeagueService:
    def __init__(
        self, schedule: ScheduleService, client_factory: Callable[[], ShlClient], clock: Clock
    ) -> None:
        self.schedule = schedule
        self.client_factory = client_factory
        self.clock = clock
        self._standings: dict[str, Any] | None = None
        self._fetched_ms: int | None = None

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
