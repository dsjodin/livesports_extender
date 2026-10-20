"""Shared bits for the tools/ scripts: shl.se URLs, User-Agent and polite fetching.

Tools are run from the repo root with the server's environment, for example
``uv run --project server python tools/record_game.py <uuid>``.
"""

import asyncio
import hashlib
import json
import logging
import os
import tomllib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "server" / "tests" / "fixtures"

BASE_URL = "https://www.shl.se/api"
TIMEOUT_S = 15.0  # origin refreshes behind Cloudflare took up to 8.6 s on game night
BACKOFF_START_S = 2.0
BACKOFF_MAX_S = 30.0

log = logging.getLogger("shl")


def _version() -> str:
    with (REPO_ROOT / "server" / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


USER_AGENT = f"shl-arena/{_version()} (private home display)"


def data_dir() -> Path:
    value = os.environ.get("ARENA_DATA_DIR")
    return Path(value) if value else REPO_ROOT / "data"


def filter_url() -> str:
    return f"{BASE_URL}/sports-v2/season-series-game-types-filter"


def schedule_url(season: str, series: str, game_type: str) -> str:
    return (
        f"{BASE_URL}/sports-v2/game-schedule?seasonUuid={season}&seriesUuid={series}"
        f"&gameTypeUuid={game_type}&gamePlace=all&played=all"
    )


def site_settings_url() -> str:
    return f"{BASE_URL}/site/settings"


def standings_url(ssgt: str) -> str:
    return f"{BASE_URL}/gameday/team-standings/{ssgt}"


def game_info_url(game: str) -> str:
    return f"{BASE_URL}/sports-v2/game-info/{game}"


def pbp_url(game: str) -> str:
    return f"{BASE_URL}/gameday/play-by-play/{game}"


def boxscore_url(game: str) -> str:
    return f"{BASE_URL}/gameday/boxscore/{game}"


GAME_ENDPOINTS: dict[str, Callable[[str], str]] = {
    "game-info": game_info_url,
    "play-by-play": pbp_url,
    "boxscore": boxscore_url,
}


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT_S,
        transport=transport,
        follow_redirects=True,
    )


@dataclass
class Fetched:
    """One HTTP response, or the error that replaced it (status None)."""

    status: int | None
    text: str
    error: str | None = None
    age_s: int | None = None  # Cloudflare's Age header: seconds the cached copy had been held
    cache: str | None = None  # cf-cache-status (HIT, MISS, EXPIRED, ...)

    @property
    def ok(self) -> bool:
        return self.status == 200

    @property
    def sha1(self) -> str | None:
        return hashlib.sha1(self.text.encode()).hexdigest() if self.status is not None else None

    def json(self) -> Any:
        return json.loads(self.text)


async def fetch(client: httpx.AsyncClient, url: str) -> Fetched:
    """A single GET that never raises for network or HTTP errors."""
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        detail = f": {exc}" if str(exc) else ""
        return Fetched(status=None, text="", error=f"{type(exc).__name__}{detail}")
    return Fetched(
        status=response.status_code,
        text=response.text,
        age_s=parse_age(response.headers.get("age")),
        cache=response.headers.get("cf-cache-status"),
    )


def parse_age(value: str | None) -> int | None:
    """The HTTP Age header as whole seconds, or None if missing or malformed."""
    try:
        age = int(value) if value is not None else None
    except ValueError:
        return None
    return age if age is not None and age >= 0 else None


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    attempts: int = 5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Any:
    """GET and parse JSON, retrying with exponential backoff (2 s doubling to 30 s)."""
    delay = BACKOFF_START_S
    for attempt in range(1, attempts + 1):
        result = await fetch(client, url)
        if result.ok:
            return result.json()
        reason = result.error or f"HTTP {result.status}"
        if attempt == attempts:
            raise RuntimeError(f"{url}: {reason} after {attempts} attempts")
        log.warning("%s: %s, retrying in %.0f s", url, reason, delay)
        await sleep(delay)
        delay = min(delay * 2, BACKOFF_MAX_S)
    raise AssertionError("unreachable")


def normalize_state(state: object) -> str | None:
    """game-info says ``post_game``, the schedule says ``post-game``."""
    return state.replace("_", "-") if isinstance(state, str) else None
