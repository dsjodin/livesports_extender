"""Async client for shl.se's JSON API. Responses stay plain dicts/lists."""

from dataclasses import dataclass
from types import TracebackType
from typing import Any

import httpx

from app import __version__

BASE_URL = "https://www.shl.se/api"
TIMEOUT_S = 15.0  # origin refreshes behind Cloudflare took up to 8.6 s on game night
USER_AGENT = f"shl-arena/{__version__} (private home display)"


class ShlError(Exception):
    """Any failure talking to shl.se."""


class ShlTimeout(ShlError):
    pass


class ShlNetworkError(ShlError):
    pass


class ShlHttpError(ShlError):
    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"{url}: HTTP {status}")
        self.url = url
        self.status = status


class ShlDecodeError(ShlError):
    pass


@dataclass(frozen=True, slots=True)
class FeedResponse:
    data: Any
    age_s: int | None  # Cloudflare's Age header
    cache: str | None  # cf-cache-status


def _age(value: str | None) -> int | None:
    try:
        age = int(value) if value is not None else None
    except ValueError:
        return None
    return age if age is not None and age >= 0 else None


class ShlClient:
    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        *,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url
        self._http = http or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT_S,
            transport=transport,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "ShlClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, params: dict[str, str] | None = None) -> FeedResponse:
        url = f"{self.base_url}/{path}"
        try:
            response = await self._http.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise ShlTimeout(f"{url}: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise ShlNetworkError(f"{url}: {type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise ShlHttpError(url, response.status_code)
        try:
            data = response.json()
        except ValueError as exc:
            raise ShlDecodeError(f"{url}: not JSON") from exc
        return FeedResponse(
            data=data,
            age_s=_age(response.headers.get("age")),
            cache=response.headers.get("cf-cache-status"),
        )

    async def filter(self) -> FeedResponse:
        return await self.get("sports-v2/season-series-game-types-filter")

    async def schedule(self, season: str, series: str, game_type: str) -> FeedResponse:
        params = {
            "seasonUuid": season,
            "seriesUuid": series,
            "gameTypeUuid": game_type,
            "gamePlace": "all",
            "played": "all",
        }
        return await self.get("sports-v2/game-schedule", params)

    async def season_filter(self, season: str) -> FeedResponse:
        """The filter for one season: its game types (regular, playoff, qualdown)."""
        return await self.get("sports-v2/season-series-game-types-filter", {"season": season})

    async def stats_info(
        self, module: str, ssgt: str, team_uuid: str, count: int, provider: str = "statnet"
    ) -> FeedResponse:
        """A team's statistics leaders (docs/SHL_API.md, Statistics): module
        ``players_point`` or ``players_goal``."""
        params = {
            "ssgtUuid": ssgt,
            "provider": provider,
            "count": str(count),
            "teamUuid": team_uuid,
        }
        return await self.get(f"statistics-v2/stats-info/{module}", params)

    async def game_info(self, game_uuid: str) -> FeedResponse:
        return await self.get(f"sports-v2/game-info/{game_uuid}")

    async def play_by_play(self, game_uuid: str) -> FeedResponse:
        return await self.get(f"gameday/play-by-play/{game_uuid}")

    async def boxscore(self, game_uuid: str) -> FeedResponse:
        return await self.get(f"gameday/boxscore/{game_uuid}")

    async def standings(self, ssgt_uuid: str) -> FeedResponse:
        return await self.get(f"gameday/team-standings/{ssgt_uuid}")

    async def site_settings(self) -> FeedResponse:
        return await self.get("site/settings")

    async def team_stats(self, game_uuid: str) -> FeedResponse:
        return await self.get(f"gameday/team-stats/{game_uuid}")

    async def athletes(self, team_uuid: str) -> FeedResponse:
        """The current roster of a team with portrait URLs (docs/SHL_API.md, Players)."""
        return await self.get(f"sports-v2/athletes/by-team-uuid/{team_uuid}")

    async def download(self, url: str) -> bytes:
        """A file from shl.se's CDNs (team logos, player portraits)."""
        try:
            response = await self._http.get(url)
        except httpx.TimeoutException as exc:
            raise ShlTimeout(f"{url}: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise ShlNetworkError(f"{url}: {type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise ShlHttpError(url, response.status_code)
        return response.content
