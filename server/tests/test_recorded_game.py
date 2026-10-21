"""Phase 5 acceptance: the real live recording (FHC–DIF 6–2, 2026-10-20) through the whole
pipeline gives the official goal timeline (boxscore goals per player, final score)."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from conftest import FIXTURES

from app.clock import FakeClock
from app.config import Settings, StateStore
from app.feed.sources import RecordingSource
from app.runtime import Runtime

RECORDING = Path(__file__).parents[2] / "data" / "recordings" / "mtn5yq64mp" / "polls.jsonl"


class Collector:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def broadcast(self, message: dict[str, Any], *, raw: bool = False) -> None:
        if not raw:
            self.messages.append(message)


def official_goals() -> Counter[tuple[str, str]]:
    """(side, playerId) -> goals, from the boxscore recorded after the game."""
    with RECORDING.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    box = [r for r in rows if r["endpoint"] == "boxscore" and r.get("body")][-1]["body"]
    goals: Counter[tuple[str, str]] = Counter()
    for key, side in (("homeTeamValue", "home"), ("awayTeamValue", "away")):
        for player in box["stats"][key]:
            if player["G"]:
                goals[(side, str(player["info"]["playerId"]))] += player["G"]
    return goals


async def test_recorded_game_gives_the_official_goal_timeline(tmp_path: Path) -> None:
    clock = FakeClock()  # each source sleep jumps the clock
    settings = Settings(
        web_dir=tmp_path, config_dir=tmp_path, data_dir=tmp_path, fixtures_dir=FIXTURES
    )
    hub = Collector()
    rt = Runtime(clock, settings, StateStore(tmp_path / "state.json"), hub)
    rt.select_game("mtn5yq64mp", None)
    async for snapshot in RecordingSource(RECORDING, clock, speed=50, skip_to_first_event=True):
        rt.on_snapshot(snapshot)
        rt.pump(clock.now_ms())
    rt.pump(clock.now_ms() + 3600_000)

    played = [m for m in hub.messages if m["t"] == "event" and m["event"]["type"] == "goal"]
    assert not [
        m for m in hub.messages if m["t"] == "event" and m["event"]["type"] == "goal_disallowed"
    ]
    order = [(g["event"]["period"], g["event"]["time"]) for g in played]
    assert order == sorted(order)  # played in game order
    scores = [
        (g["event"]["data"]["score"]["home"], g["event"]["data"]["score"]["away"]) for g in played
    ]
    assert scores[-1] == (6, 2) and len(scores) == 8
    for (h0, a0), (h1, a1) in zip([(0, 0), *scores], scores, strict=False):
        assert (h1 - h0, a1 - a0) in ((1, 0), (0, 1))  # one goal at a time
    scorers = Counter((g["event"]["side"], g["event"]["player"]["id"]) for g in played)
    assert scorers == official_goals()
    for g in played:  # never before it reached us (CLAUDE.md rule 2)
        assert g["play_at_ms"] >= g["event"]["received_ms"] + 1500
    assert rt.applied["score"] == {"home": 6, "away": 2}
    assert rt.applied["phase"] == "postgame" and rt.applied["ended"]
