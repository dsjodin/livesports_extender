"""Fetch shl.se test fixtures into server/tests/fixtures/ as pretty-printed JSON.

Usage (from the repo root): uv run --project server python tools/fetch_fixtures.py
"""

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

import shl_http as shl

SCHEDULE_SEASON_CODE = "2026"
FIXTURE_GAMES = {
    "bdhvuc5tex": "Frölunda–Linköping 2–1, 2025-09-13",
    "m01wkdm2u1": "HV71–Skellefteå 4–3 after overtime, 2026-09-24",
    "et9erhx0si": "Frölunda–Skellefteå 3–2 after shootout, 2026-10-17",
}
GAME_FILE_PREFIX = {
    "game-info": "game_info",
    "play-by-play": "pbp",
    "boxscore": "boxscore",
    "team-stats": "team_stats",
}
PAUSE_S = 0.5  # between requests, to be polite

log = logging.getLogger("fetch_fixtures")


def pick(items: list[dict[str, Any]], code: str) -> str:
    for item in items:
        if item.get("code") == code:
            return item["uuid"]
    raise RuntimeError(f"code {code!r} not in filter: {[i.get('code') for i in items]}")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def fetch_all(client: httpx.AsyncClient, out: Path) -> list[tuple[str, str]]:
    """Fetch every fixture. Returns (file name, source URL) pairs."""
    fetched: list[tuple[str, str]] = []

    async def save(name: str, url: str) -> Any:
        data = await shl.fetch_json(client, url)
        write_json(out / name, data)
        fetched.append((name, url))
        log.info("%-32s %s", name, url)
        await asyncio.sleep(PAUSE_S)
        return data

    filt = await save("filter.json", shl.filter_url())
    season = pick(filt["season"], SCHEDULE_SEASON_CODE)
    series = pick(filt["series"], "SHL")
    game_type = pick(filt["gameType"], "regular")
    await save(f"schedule_{SCHEDULE_SEASON_CODE}.json", shl.schedule_url(season, series, game_type))
    await save("site_settings.json", shl.site_settings_url())
    ssgt = filt["ssgtUuid"]
    await save(f"standings_{ssgt}.json", shl.standings_url(ssgt))
    for game in FIXTURE_GAMES:
        for endpoint, url_for in shl.GAME_ENDPOINTS.items():
            await save(f"{GAME_FILE_PREFIX[endpoint]}_{game}.json", url_for(game))
    return fetched


def write_readme(out: Path, fetched: list[tuple[str, str]]) -> None:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    rows = "\n".join(f"| `{name}` | {url} |" for name, url in fetched)
    games = "\n".join(f"- `{uuid}`: {label}" for uuid, label in FIXTURE_GAMES.items())
    text = f"""# Test fixtures

Fetched from shl.se on {now} by `tools/fetch_fixtures.py` (User-Agent
`{shl.USER_AGENT}`). Responses are saved unchanged apart from pretty-printing.
Refresh with `uv run --project server python tools/fetch_fixtures.py`.

Games:

{games}

| File | Source URL |
|---|---|
{rows}
"""
    (out / "README.md").write_text(text, encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=shl.FIXTURES_DIR)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.out.mkdir(parents=True, exist_ok=True)
    async with shl.make_client() as client:
        fetched = await fetch_all(client, args.out)
    write_readme(args.out, fetched)
    log.info("wrote %d fixtures to %s", len(fetched), args.out)


if __name__ == "__main__":
    asyncio.run(main())
