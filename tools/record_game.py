"""Record one game's game-info and play-by-play polls to data/recordings/<uuid>/polls.jsonl.

Usage (from the repo root): uv run --project server python tools/record_game.py <game_uuid>

One JSON line per request: {"received_ms", "endpoint", "status", "sha1", "age", "cache",
"body"}. "age" and "cache" are Cloudflare's Age and cf-cache-status headers. The body is
stored only when its hash changed since the last stored body for that endpoint, otherwise
it is null. Failed requests have status null and an "error" field.

Polling: game-info every 60 s while the game is pre-game and more than 15 min from
puck drop; game-info and play-by-play every 2 s otherwise. game-info is not updated
during the game, so state and score come from play-by-play. Stops 5 min after
play-by-play says GameEnded or game-info says post-game (at once if the game was already
over on the first poll), 6 h after the start time if neither happens, or on Ctrl-C. The
boxscore is fetched once at the end.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

import httpx

import shl_http as shl

SLOW_INTERVAL_S = 60.0
FAST_INTERVAL_S = 2.0
FAST_BEFORE_START_S = 15 * 60
POST_GAME_TAIL_S = 5 * 60
GIVE_UP_AFTER_S = 6 * 3600  # postponed games stay pre-game; stop polling eventually
KNOWN_INFO_STATES = {"pre-game", "post-game"}
KNOWN_PBP_STATES = {"Ongoing", "Intermission", "GameEnded"}

log = logging.getLogger("record_game")


def real_now_ms() -> int:
    return time.time_ns() // 1_000_000


def parse_utc_ms(value: object) -> int | None:
    """game-info ``startDateTime`` is real UTC, e.g. ``2025-09-13T13:15:00.000Z``."""
    if not isinstance(value, str):
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def last_hashes(path: Path) -> dict[str, str]:
    """Hash of the last stored body per endpoint, so a restarted recording continues."""
    hashes: dict[str, str] = {}
    if not path.exists():
        return hashes
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("body") is not None and row.get("sha1"):
                hashes[row["endpoint"]] = row["sha1"]
    return hashes


def pbp_state(pbp: list[dict[str, Any]]) -> str | None:
    """Play-by-play ``gameState`` (the same on every event): Ongoing, Intermission, GameEnded."""
    for item in pbp:
        if isinstance(item, dict) and isinstance(item.get("gameState"), str):
            return item["gameState"]
    return None


def pbp_score(pbp: list[dict[str, Any]]) -> tuple[int, int] | None:
    """Score after the latest goal (highest eventId), or None before the first goal."""
    goals = [e for e in pbp if isinstance(e, dict) and e.get("type") == "goal"]
    if not goals:
        return None
    latest = max(goals, key=lambda e: e.get("eventId", 0))
    return latest.get("homeGoals", 0), latest.get("awayGoals", 0)


@dataclass
class Recorder:
    game: str
    out_file: Path
    client: httpx.AsyncClient
    now_ms: Callable[[], int] = real_now_ms
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    echo: Callable[[str], None] = print
    polls: int = 0
    _hashes: dict[str, str] = field(default_factory=dict)
    _warned_states: set[tuple[str, str]] = field(default_factory=set)
    _info: dict[str, Any] | None = None
    _pbp: list[dict[str, Any]] | None = None
    _status: str = ""

    async def request(self, endpoint: str, f: TextIO) -> shl.Fetched:
        result = await shl.fetch(self.client, shl.GAME_ENDPOINTS[endpoint](self.game))
        row: dict[str, Any] = {
            "received_ms": self.now_ms(),
            "endpoint": endpoint,
            "status": result.status,
            "sha1": result.sha1,
            "age": result.age_s,
            "cache": result.cache,
            "body": None,
        }
        body: Any = None
        if result.error:
            row["error"] = result.error
        else:
            try:
                body = result.json()
            except json.JSONDecodeError:
                body = result.text
            if result.sha1 != self._hashes.get(endpoint):
                row["body"] = body
                self._hashes[endpoint] = result.sha1 or ""
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        if result.ok:
            if endpoint == "game-info" and isinstance(body, dict):
                self._info = body
            elif endpoint == "play-by-play" and isinstance(body, list):
                self._pbp = body
        return result

    def info_state(self) -> str | None:
        """game-info state, hyphenated. Only reliable before the game (see docs/SHL_API.md)."""
        info = (self._info or {}).get("gameInfo") or {}
        return self._check(shl.normalize_state(info.get("state")), KNOWN_INFO_STATES, "game-info")

    def pbp_state(self) -> str | None:
        state = pbp_state(self._pbp) if self._pbp is not None else None
        return self._check(state, KNOWN_PBP_STATES, "play-by-play")

    def state(self) -> str | None:
        """Play-by-play state once there is one, game-info state before that."""
        return self.pbp_state() or self.info_state()

    def game_over(self) -> bool:
        return self.pbp_state() == "GameEnded" or self.info_state() == "post-game"

    def _check(self, state: str | None, known: set[str], source: str) -> str | None:
        if state is not None and state not in known and (source, state) not in self._warned_states:
            self._warned_states.add((source, state))
            log.warning("unrecognised %s state %r", source, state)
        return state

    def print_status(self) -> None:
        info = self._info or {}
        home = (info.get("homeTeam") or {}).get("names", {}).get("code", "?")
        away = (info.get("awayTeam") or {}).get("names", {}).get("code", "?")
        score = pbp_score(self._pbp or [])
        shown = "–" if score is None else f"{score[0]}–{score[1]}"
        events = "-" if self._pbp is None else str(sum(1 for e in self._pbp if "eventId" in e))
        status = f"state={self.state()} {home} {shown} {away} events={events}"
        if status != self._status:
            self._status = status
            stamp = datetime.fromtimestamp(self.now_ms() / 1000).strftime("%H:%M:%S")
            self.echo(f"{stamp} {status}")

    async def run(self) -> None:
        self.out_file.parent.mkdir(parents=True, exist_ok=True)
        self._hashes = last_hashes(self.out_file)
        backoff = shl.BACKOFF_START_S
        first_ok = True
        over_since: int | None = None
        with self.out_file.open("a", encoding="utf-8") as f:
            try:
                while True:
                    self.polls += 1
                    info = await self.request("game-info", f)
                    if not info.ok:
                        log.warning(
                            "game-info: %s, retry in %.0f s", info.error or info.status, backoff
                        )
                        await self.sleep(backoff)
                        backoff = min(backoff * 2, shl.BACKOFF_MAX_S)
                        continue
                    start_ms = parse_utc_ms(
                        ((self._info or {}).get("gameInfo") or {}).get("startDateTime")
                    )
                    fast = self.info_state() != "pre-game" or (
                        start_ms is not None
                        and self.now_ms() >= start_ms - FAST_BEFORE_START_S * 1000
                    )
                    if fast:
                        pbp = await self.request("play-by-play", f)
                        if not pbp.ok:
                            log.warning(
                                "play-by-play: %s, retry in %.0f s",
                                pbp.error or pbp.status,
                                backoff,
                            )
                            await self.sleep(backoff)
                            backoff = min(backoff * 2, shl.BACKOFF_MAX_S)
                            continue
                    backoff = shl.BACKOFF_START_S
                    self.print_status()
                    if self.game_over():
                        if first_ok:
                            break
                        over_since = over_since or self.now_ms()
                        if self.now_ms() - over_since >= POST_GAME_TAIL_S * 1000:
                            break
                    elif start_ms is not None and self.now_ms() > start_ms + GIVE_UP_AFTER_S * 1000:
                        self.echo("no end of game seen 6 h after the start time, giving up")
                        break
                    first_ok = False
                    await self.sleep(FAST_INTERVAL_S if fast else SLOW_INTERVAL_S)
            except asyncio.CancelledError:
                self.echo("stopped")
            box = await self.request("boxscore", f)
            self.echo(f"boxscore: {box.status or box.error}; {self.polls} polls in {self.out_file}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("game_uuid")
    parser.add_argument(
        "--out", type=Path, help="recording directory (default data/recordings/<uuid>)"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    out_dir = args.out or shl.data_dir() / "recordings" / args.game_uuid
    async with shl.make_client() as client:
        await Recorder(args.game_uuid, out_dir / "polls.jsonl", client).run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
