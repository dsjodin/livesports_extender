"""Developer CLI.

    python -m app.cli replay <fixture-uuid> [--speed 50] [--lag default|<seconds>] [--instant]
    python -m app.cli recording <polls.jsonl or its directory> [--speed 50] [--instant]

Prints the normalized event timeline as it happens, then the final raw state.
``--instant`` runs on a fake clock and finishes at once.
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.clock import Clock, FakeClock, RealClock
from app.config import REPO_ROOT
from app.engine.events import Change, NormalizedEvent
from app.engine.normalizer import Normalizer
from app.engine.state import RawState, compute_state
from app.feed.sources import FeedSource, RecordingSource, ReplaySource
from app.feedtime import STOCKHOLM

FIXTURES = REPO_ROOT / "server" / "tests" / "fixtures"


def describe(e: NormalizedEvent) -> str:
    d = e.data
    text = e.label()
    if e.type == "goal":
        assists = ", ".join(f"{a['number']} {a['last']}" for a in d.get("assists", []))
        score = d.get("score") or {}
        text += f" ({assists})" if assists else ""
        text += f" {d.get('strength')} {score.get('home')}–{score.get('away')}"
    elif e.type == "penalty":
        text += f" {d.get('offence_code')} {d.get('kind')} {d.get('minutes')} min"
    elif e.type == "goalie_change":
        text += " in" if d.get("entering") else " out"
    elif e.type == "game_end":
        final = d.get("final") or {}
        text += f" {final.get('home')}–{final.get('away')}"
        text += " OT" if d.get("overtime") else ""
        text += " SO" if d.get("shootout") else ""
    elif e.type == "shootout_attempt":
        text += f" {'goal' if d.get('scored') else 'miss'} #{d.get('index')}"
    return text


def format_change(change: Change, feed_ms: int | None) -> str:
    stamp = (
        datetime.fromtimestamp(feed_ms / 1000, STOCKHOLM).strftime("%H:%M:%S")
        if feed_ms is not None
        else "--:--:--"
    )
    if change.event is None:
        return f"{stamp} {change.kind}"
    return f"{stamp} {change.kind:<7} {describe(change.event)}"


def format_state(state: RawState) -> str:
    lines = [
        f"phase {state.phase}, game state {state.game_state}, period {state.period}",
        f"score {state.score['home']}–{state.score['away']}"
        + (" (OT)" if state.overtime else "")
        + (" (SO)" if state.went_to_shootout else ""),
        f"strength {state.strength['label']}, pp {state.strength['pp_side']}",
        "periods "
        + ", ".join(
            f"{p.period}:{'s' if p.started else '-'}{'f' if p.finished else '-'}"
            for p in state.periods
        ),
    ]
    for side in ("home", "away"):
        s = state.stats[side]
        on_goal = "/".join(str(v) for v in s.shots_on_goal_by_period.values())
        attempts = "/".join(str(v) for v in s.shot_attempts_by_period.values())
        lines.append(
            f"{side}: goals {s.goals}, shots on goal {s.shots_on_goal} ({on_goal}), "
            f"attempts {s.shot_attempts} ({attempts}), PIM {s.pim}, "
            f"PP {s.pp_goals}/{s.pp_chances}, timeouts {s.timeouts}"
        )
    return "\n".join(lines)


async def run(source: FeedSource, out: Callable[[str], None] = print) -> RawState:
    normalizer = Normalizer()
    async for snapshot in source:
        for change in normalizer.apply(snapshot):
            out(format_change(change, snapshot.feed_ms))
    state = compute_state(normalizer.events.values(), normalizer.game_state, normalizer.game_info)
    out(format_state(state))
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser("replay", help="replay a fixture game")
    replay.add_argument("game_uuid")
    replay.add_argument(
        "--lag", default="default", help="feed lag: 'default' (per type) or seconds for all types"
    )
    recording = sub.add_parser("recording", help="replay a recording")
    recording.add_argument("path", type=Path)
    for p in (replay, recording):
        p.add_argument("--speed", type=float, default=50.0)
        p.add_argument("--instant", action="store_true", help="fake clock, no waiting")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    clock: Clock = FakeClock() if args.instant else RealClock()
    source: FeedSource
    if args.command == "replay":
        lag = None if args.lag == "default" else float(args.lag)
        source = ReplaySource.from_fixtures(
            FIXTURES, args.game_uuid, clock, speed=args.speed, lag_s=lag
        )
    else:
        path = args.path / "polls.jsonl" if args.path.is_dir() else args.path
        source = RecordingSource(path, clock, speed=args.speed, skip_to_first_event=True)
    asyncio.run(run(source))
    return 0


if __name__ == "__main__":
    sys.exit(main())
