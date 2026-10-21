"""The season schedule from shl.se, cached for one hour (CLAUDE.md rule 5)."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.clock import Clock
from app.feed.client import ShlClient
from app.feedtime import STOCKHOLM, parse_utc_ms

CACHE_MS = 3600_000
DAY_MS = 86_400_000


def simplify(game: dict[str, Any]) -> dict[str, Any]:
    def team(raw: dict[str, Any]) -> dict[str, Any]:
        names = raw.get("names") or {}
        score = raw.get("score")
        return {
            "uuid": raw.get("uuid"),
            "code": names.get("code"),
            "short": (names.get("short") or "").strip() or None,
            "long": names.get("long"),
            "icon": raw.get("icon"),
            "score": score if isinstance(score, int) else None,
        }

    state = game.get("state")
    return {
        "uuid": game.get("uuid"),
        "start_ms": parse_utc_ms(game.get("rawStartDateTime")),
        "state": state.replace("_", "-") if isinstance(state, str) else None,
        "overtime": bool(game.get("overtime")),
        "shootout": bool(game.get("shootout")),
        "arena": (game.get("venueInfo") or {}).get("name"),
        "home": team(game.get("homeTeamInfo") or {}),
        "away": team(game.get("awayTeamInfo") or {}),
    }


def local_midnight_ms(now_ms: int) -> int:
    day = datetime.fromtimestamp(now_ms / 1000, STOCKHOLM).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int(day.timestamp() * 1000)


class ScheduleService:
    def __init__(self, client_factory: Callable[[], ShlClient], clock: Clock) -> None:
        self.client_factory = client_factory
        self.clock = clock
        self._games: list[dict[str, Any]] | None = None
        self._fetched_ms: int | None = None

    async def games(self) -> list[dict[str, Any]]:
        now = self.clock.now_ms()
        if self._games is None or self._fetched_ms is None or now - self._fetched_ms >= CACHE_MS:
            async with self.client_factory() as client:
                default = (await client.filter()).data["defaultSsgtFilter"]
                raw = await client.schedule(
                    default["season"], default["series"], default["gameType"]
                )
            self._games = sorted(
                (simplify(g) for g in raw.data.get("gameInfo", [])),
                key=lambda g: g["start_ms"] or 0,
            )
            self._fetched_ms = now
        return self._games

    async def upcoming(self, days: int) -> list[dict[str, Any]]:
        """Games from local midnight today to the end of day ``days`` (today = day 0)."""
        start = local_midnight_ms(self.clock.now_ms())
        end = start + (days + 1) * DAY_MS
        return [g for g in await self.games() if g["start_ms"] and start <= g["start_ms"] < end]

    async def recent(self, days: int) -> list[dict[str, Any]]:
        """Finished games of the last ``days`` days, newest first (for replay)."""
        now = self.clock.now_ms()
        games = [
            g
            for g in await self.games()
            if g["state"] == "post-game" and g["start_ms"] and now - days * DAY_MS <= g["start_ms"]
        ]
        return sorted(games, key=lambda g: g["start_ms"], reverse=True)
