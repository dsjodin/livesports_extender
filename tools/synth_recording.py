"""Build a synthetic recording from a finished game's fixtures, in record_game.py's format.

Usage (from the repo root):
    uv run --project server python tools/synth_recording.py bdhvuc5tex [--out DIR]

Events appear LAG_MS after their realWorldTime (Swedish local time); period objects
appear when their startedAt passes and are marked finished when finishedAt passes
(both local time despite the Z). Polls follow record_game.py's schedule. Game-info
state and score are simulated: `pre_game`, then `live` (the real live value is
unknown), then `post_game` POST_GAME_AFTER_MS after the last period finished.
Only event content is real; revisions, deletions and receive times are not.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import shl_http as shl
from analyze_recording import parse_local_ms
from record_game import (
    FAST_BEFORE_START_S,
    FAST_INTERVAL_S,
    POST_GAME_TAIL_S,
    SLOW_INTERVAL_S,
    parse_utc_ms,
)

LAG_MS = 2_000
START_BEFORE_MS = 30 * 60 * 1000
POST_GAME_AFTER_MS = 60_000


def load(fixtures: Path, name: str) -> Any:
    return json.loads((fixtures / name).read_text(encoding="utf-8"))


def sha1(body: Any) -> str:
    return hashlib.sha1(json.dumps(body, ensure_ascii=False).encode()).hexdigest()


class Synth:
    def __init__(self, game_info: dict[str, Any], pbp: list[dict[str, Any]]) -> None:
        self.game_info = game_info
        self.events = [e for e in pbp if e.get("type") != "period"]
        self.periods = [e for e in pbp if e.get("type") == "period"]
        self.event_at = [parse_local_ms(e.get("realWorldTime")) or 0 for e in self.events]
        self.started_at = [parse_local_ms(p.get("startedAt")) or 0 for p in self.periods]
        self.finished_at = [parse_local_ms(p.get("finishedAt")) or 0 for p in self.periods]
        last = max([*self.finished_at, *self.event_at])
        self.post_game_ms = last + LAG_MS + POST_GAME_AFTER_MS
        self.start_ms = parse_utc_ms(game_info["gameInfo"]["startDateTime"]) or 0

    def signature(self, t: int) -> tuple[int, ...]:
        return (
            sum(1 for at in self.event_at if at + LAG_MS <= t),
            sum(1 for at in self.started_at if at + LAG_MS <= t),
            sum(1 for at in self.finished_at if at + LAG_MS <= t),
            int(t >= self.post_game_ms),
        )

    def pbp(self, t: int) -> list[dict[str, Any]]:
        visible = [e for e, at in zip(self.events, self.event_at, strict=True) if at + LAG_MS <= t]
        visible.sort(key=lambda e: e.get("eventId", 0), reverse=True)
        for period, started, finished in zip(
            self.periods, self.started_at, self.finished_at, strict=True
        ):
            if started + LAG_MS > t:
                continue
            item = dict(period)
            if finished + LAG_MS > t:
                item.update(finished=False, finishedAt=None, realWorldTime=period["startedAt"])
            visible.append(item)
        return visible

    def info(self, t: int, pbp: list[dict[str, Any]]) -> dict[str, Any]:
        body = copy.deepcopy(self.game_info)
        started = any(e.get("type") == "period" for e in pbp)
        if t >= self.post_game_ms:
            state = "post_game"
        elif started:
            state = "live"
        else:
            state = "pre_game"
        body["gameInfo"]["state"] = state
        goals = [e for e in pbp if e.get("type") == "goal"]
        if state == "pre_game":
            home = away = ""
        elif goals:
            latest = max(goals, key=lambda e: e.get("eventId", 0))
            home, away = latest.get("homeGoals", 0), latest.get("awayGoals", 0)
        else:
            home = away = 0
        if state == "post_game":
            home, away = self.game_info["homeTeam"]["score"], self.game_info["awayTeam"]["score"]
        body["homeTeam"]["score"], body["awayTeam"]["score"] = home, away
        return body


def build(fixtures: Path, game: str, out_dir: Path) -> Path:
    synth = Synth(load(fixtures, f"game_info_{game}.json"), load(fixtures, f"pbp_{game}.json"))
    boxscore = load(fixtures, f"boxscore_{game}.json")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "polls.jsonl"
    last_sha: dict[str, str] = {}
    signature: tuple[int, ...] | None = None
    pbp: list[dict[str, Any]] = []
    info: dict[str, Any] = {}

    with out.open("w", encoding="utf-8") as f:

        def write(t: int, endpoint: str, body: Any) -> None:
            digest = sha1(body)
            stored = body if digest != last_sha.get(endpoint) else None
            last_sha[endpoint] = digest
            row = {"received_ms": t, "endpoint": endpoint, "status": 200, "sha1": digest}
            f.write(json.dumps({**row, "body": stored}, ensure_ascii=False) + "\n")

        t = synth.start_ms - START_BEFORE_MS
        end = synth.post_game_ms + POST_GAME_TAIL_S * 1000
        while t <= end:
            sig = synth.signature(t)
            if sig != signature:
                signature = sig
                pbp = synth.pbp(t)
                info = synth.info(t, pbp)
            write(t, "game-info", info)
            pre = info["gameInfo"]["state"] == "pre_game"
            fast = not pre or t >= synth.start_ms - FAST_BEFORE_START_S * 1000
            if fast:
                write(t + 150, "play-by-play", pbp)
            t += int((FAST_INTERVAL_S if fast else SLOW_INTERVAL_S) * 1000)
        write(t, "boxscore", boxscore)

    meta = {"synthetic": True, "source_game": game, "lag_ms": LAG_MS}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("game_uuid")
    parser.add_argument("--fixtures", type=Path, default=shl.FIXTURES_DIR)
    parser.add_argument("--out", type=Path, help="default data/recordings/synthetic-<uuid>")
    args = parser.parse_args()
    out_dir = args.out or shl.data_dir() / "recordings" / f"synthetic-{args.game_uuid}"
    print(build(args.fixtures, args.game_uuid, out_dir))


if __name__ == "__main__":
    main()
