"""Team logos and player portraits from shl.se, fetched once and served from data/cache.

Teams are registered with their ``icon`` URL (from game-info or the schedule); players
with their play-by-play id (the ``isa`` id), name, number and team. A portrait is found
in the team's roster (``athletes/by-team-uuid``) by name, then by number.
"""

import asyncio
import json
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.clock import Clock
from app.feed.client import ShlClient, ShlError

log = logging.getLogger(__name__)

ROSTER_MAX_AGE_MS = 24 * 3600_000
PORTRAIT_WIDTH = 480
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def name_key(*parts: str | None) -> str:
    text = " ".join(p for p in parts if p)
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^a-z]", "", "".join(c for c in text if not unicodedata.combining(c)).lower())


@dataclass(frozen=True)
class PlayerRef:
    team_uuid: str
    first: str | None
    last: str | None
    number: str | None


class AssetCache:
    def __init__(
        self, cache_dir: Path, client_factory: Callable[[], ShlClient], clock: Clock
    ) -> None:
        self.dir = cache_dir
        self.client_factory = client_factory
        self.clock = clock
        self.team_icons: dict[str, str] = {}
        self.players: dict[str, PlayerRef] = {}
        self._rosters: dict[str, tuple[int, list[dict[str, Any]]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._failed: set[str] = set()

    # --- registration (cheap, synchronous) ----------------------------------------------

    def register_team(self, uuid: str | None, icon: str | None) -> None:
        if uuid and icon and SAFE_ID.match(uuid):
            self.team_icons[uuid] = icon

    def register_player(
        self,
        player_id: str | None,
        team_uuid: str | None,
        first: str | None,
        last: str | None,
        number: str | None,
    ) -> None:
        if player_id and team_uuid and SAFE_ID.match(player_id):
            self.players[player_id] = PlayerRef(team_uuid, first, last, number)

    # --- files ----------------------------------------------------------------------

    def _lock(self, key: str) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def team_logo(self, uuid: str) -> Path | None:
        if not SAFE_ID.match(uuid):
            return None
        path = self.dir / "teams" / f"{uuid}.svg"
        if path.exists():
            return path
        icon = self.team_icons.get(uuid)
        if icon is None or icon in self._failed:
            return None
        async with self._lock(path.name):
            if not path.exists():
                await self._download(icon, path)
        return path if path.exists() else None

    async def player_portrait(self, player_id: str) -> Path | None:
        if not SAFE_ID.match(player_id):
            return None
        path = self.dir / "players" / f"{player_id}.png"
        if path.exists():
            return path
        ref = self.players.get(player_id)
        if ref is None:
            return None
        async with self._lock(path.name):
            if path.exists():
                return path
            url = await self._portrait_url(ref)
            if url and url not in self._failed:
                await self._download(url, path)
        return path if path.exists() else None

    async def _download(self, url: str, path: Path) -> None:
        try:
            async with self.client_factory() as client:
                data = await client.download(url)
        except ShlError as exc:
            self._failed.add(url)
            log.warning("could not fetch %s: %s", url, exc)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    async def roster(self, team_uuid: str) -> list[dict[str, Any]]:
        now = self.clock.now_ms()
        cached = self._rosters.get(team_uuid)
        if cached and now - cached[0] < ROSTER_MAX_AGE_MS:
            return cached[1]
        file = self.dir / "rosters" / f"{team_uuid}.json"
        players: list[dict[str, Any]] = []
        try:
            async with self.client_factory() as client:
                groups = (await client.athletes(team_uuid)).data
            players = [p for g in groups or [] for p in g.get("players") or []]
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(players, ensure_ascii=False), encoding="utf-8")
        except ShlError as exc:
            log.warning("could not fetch the roster of %s: %s", team_uuid, exc)
            if file.exists():
                players = json.loads(file.read_text(encoding="utf-8"))
        self._rosters[team_uuid] = (now, players)
        return players

    async def _portrait_url(self, ref: PlayerRef) -> str | None:
        players = await self.roster(ref.team_uuid)
        wanted = name_key(ref.first, ref.last)
        match = next(
            (p for p in players if name_key(p.get("firstName"), p.get("lastName")) == wanted), None
        )
        if match is None and ref.number:
            by_number = [p for p in players if str(p.get("jerseyNumber")) == ref.number]
            same_last = [p for p in by_number if name_key(p.get("lastName")) == name_key(ref.last)]
            match = (same_last or by_number or [None])[0]
        return portrait_url((match or {}).get("renderedLatestPortrait") or {})


def portrait_url(rendered: dict[str, Any], width: int = PORTRAIT_WIDTH) -> str | None:
    """The smallest signed ``srcset`` variant at least ``width`` wide, else the plain URL.

    The imgix URLs are signed (``s=``), so a width cannot be added by hand.
    """
    candidates: list[tuple[int, str]] = []
    for entry in str(rendered.get("srcset") or "").split(","):
        parts = entry.strip().split()
        if len(parts) == 2 and parts[1].endswith("w") and parts[1][:-1].isdigit():
            candidates.append((int(parts[1][:-1]), parts[0]))
    wide = sorted(c for c in candidates if c[0] >= width)
    if wide:
        return wide[0][1]
    return rendered.get("url") or None
