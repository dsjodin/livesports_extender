from pathlib import Path

import pytest

from app.cli import main


def test_replay_prints_timeline_and_final_state(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["replay", "bdhvuc5tex", "--instant", "--lag", "0"]) == 0
    out = capsys.readouterr().out
    assert "added   P1 04:33 goal FHC #40 Jacob Peterson (12 Friberg, 21 Innala) EQ 1–0" in out
    assert "added   P3 09:07 goal FHC #25 Arttu Ruotsalainen (46 Egli, 41 Stenberg) PP1 2–1" in out
    assert "game_end 2–1" in out
    assert "score 2–1" in out
    assert "home: goals 2, shots on goal 31 (15/11/5)" in out
    assert "PP 1/3" in out and "PP 1/2" in out


def test_recording_cli(capsys: pytest.CaptureFixture[str]) -> None:
    path = Path(__file__).parents[2] / "data" / "recordings" / "mtn5yq64mp"
    assert main(["recording", str(path), "--instant"]) == 0
    out = capsys.readouterr().out
    assert "removed" in out and "score 6–2" in out
