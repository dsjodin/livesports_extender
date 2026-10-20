import json
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES

from analyze_recording import analyse, parse_local_ms, parse_naive_utc_ms, write_report
from synth_recording import build


@pytest.fixture(scope="module")
def synthetic_report(tmp_path_factory: pytest.TempPathFactory) -> str:
    out_dir = tmp_path_factory.mktemp("synthetic")
    build(FIXTURES, "bdhvuc5tex", out_dir)
    return write_report(out_dir).read_text(encoding="utf-8")


def test_time_zone_parsing() -> None:
    # 15:14:26 Swedish summer time is 13:14:26 UTC, whatever the suffix says.
    assert parse_local_ms("2025-09-13T15:14:26.000Z") == parse_naive_utc_ms("2025-09-13T13:14:26")
    assert parse_local_ms(None) is None and parse_naive_utc_ms("garbage") is None


def test_synthetic_report_states(synthetic_report: str) -> None:
    assert "**Synthetic recording**" in synthetic_report
    for state in ("`pre_game`", "`live`", "`post_game`", "`GameEnded`"):
        assert state in synthetic_report


def test_synthetic_report_values(synthetic_report: str) -> None:
    assert "| `goalStatus` | `EQ` (1), `PP1` (2) |" in synthetic_report
    assert "`BOARD` (1), `CROSS` (1), `HOLD` (1), `INTRF` (1), `TRIP` (1)" in synthetic_report
    assert "| `variant.shortName` | `Minor` (5) |" in synthetic_report
    assert "| shot | 115 |" in synthetic_report


def test_synthetic_report_shots_against_boxscore(synthetic_report: str) -> None:
    assert "| FHC | 40 | 31 | 31 | 31 | B |" in synthetic_report
    assert "| LHC | 43 | 29 | 29 | 29 | B |" in synthetic_report


def test_synthetic_report_periods(synthetic_report: str) -> None:
    section = synthetic_report.split("## Period objects")[1]
    rows = [line for line in section.splitlines() if line.startswith("| ") and line[2].isdigit()]
    assert [r.split("|")[1].strip() for r in rows] == ["1", "2", "3"]
    assert "No event disappeared." in synthetic_report


def shot(event_id: int, revision: int, last_name: str) -> dict[str, Any]:
    return {
        "eventId": event_id,
        "type": "shot",
        "period": 1,
        "time": "01:00",
        "revision": revision,
        "goalSection": 2,
        "realWorldTime": "2025-09-13T15:20:00",
        "updatedTime": "2025-09-13T13:20:01",
        "eventTeam": {"place": "home", "teamCode": "FHC"},
        "player": {"familyName": last_name},
    }


def test_revisions_and_disappearances(tmp_path: Path) -> None:
    t = parse_naive_utc_ms("2025-09-13T13:20:03") or 0
    pbp1 = [shot(1, 1, "Andersson")]
    pbp2 = [shot(2, 1, "Berg"), shot(1, 2, "Carlsson")]
    pbp3 = [shot(1, 2, "Carlsson")]
    polls = [(0, "a", pbp1), (2000, "a", None), (4000, "b", pbp2), (6000, "c", pbp3)]
    rows = [
        {"received_ms": t + dt, "endpoint": "play-by-play", "status": 200, "sha1": h, "body": b}
        for dt, h, b in polls
    ]
    a = analyse(rows)
    tracked = a.events[("e", 1)]
    assert tracked.first_seen_ms == t
    assert tracked.changes == [(t + 4000, 2, ["player.familyName", "revision"])]
    assert [(k, last, gone) for k, _, last, gone in a.removed] == [(("e", 2), t + 4000, t + 6000)]

    (tmp_path / "polls.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    report = write_report(tmp_path).read_text()
    assert "`player.familyName`, `revision`" in report
    assert "| 2 shot P1 01:00 FHC |" in report
    assert "| shot | 2 | +3.0 | +5.0 | +7.0 | +2.0 | +4.0 | +6.0 |" in report
    assert "No boxscore in the recording." in report
