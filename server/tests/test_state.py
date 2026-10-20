"""Phase 1 acceptance: replayed fixtures and the live recording give the right state."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from conftest import load_fixture, replay_to_end

from app.clock import FakeClock
from app.engine.normalizer import Normalizer
from app.engine.state import RawState, compute_state
from app.feed.sources import RecordingSource

RECORDING = Path(__file__).parents[2] / "data" / "recordings" / "mtn5yq64mp" / "polls.jsonl"


def goal_rows(state: RawState) -> list[tuple[Any, ...]]:
    rows = []
    for g in state.goals:
        assert g.player is not None
        score = g.data["score"]
        rows.append(
            (
                f"P{g.period} {g.time}",
                g.team_code,
                f"#{g.player.number} {g.player.name}",
                [f"#{a['number']} {a['first']} {a['last']}" for a in g.data["assists"]],
                g.data["strength"],
                f"{score['home']}–{score['away']}",
            )
        )
    return rows


def boxscore_sog(game: str) -> dict[str, int]:
    box = load_fixture(f"boxscore_{game}.json")
    return {
        side: sum(int(p.get("SOG") or 0) for p in box["stats"][f"{side}TeamValue"])
        for side in ("home", "away")
    }


@pytest.fixture(scope="module")
def bdh() -> RawState:
    return asyncio.run(replay_to_end("bdhvuc5tex"))[1]


async def test_goals_in_order(bdh: RawState) -> None:
    assert goal_rows(bdh) == [
        (
            "P1 04:33",
            "FHC",
            "#40 Jacob Peterson",
            ["#12 Max Friberg", "#21 Jere Innala"],
            "EQ",
            "1–0",
        ),
        (
            "P2 00:24",
            "LHC",
            "#70 Fredrik Karlström",
            ["#73 Nick Shore", "#39 Ty Rattie"],
            "PP1",
            "1–1",
        ),
        (
            "P3 09:07",
            "FHC",
            "#25 Arttu Ruotsalainen",
            ["#46 Dominik Egli", "#41 Ivar Stenberg"],
            "PP1",
            "2–1",
        ),
    ]


async def test_penalties(bdh: RawState) -> None:
    rows = [
        (
            f"P{p.period} {p.time}",
            p.side,
            f"#{p.player.number} {p.player.name}" if p.player else "",
            p.offence_code,
            p.kind,
        )
        for p in bdh.penalties
    ]
    assert rows == [
        ("P1 01:42", "away", "#9 Erik Norén", "BOARD", "minor"),
        ("P1 18:35", "home", "#46 Dominik Egli", "TRIP", "minor"),
        ("P2 11:20", "away", "#81 Theodor Lennström", "INTRF", "minor"),
        ("P3 07:39", "away", "#8 Jonathan Myrenberg", "HOLD", "minor"),
        ("P3 11:10", "home", "#46 Dominik Egli", "CROSS", "minor"),
    ]
    assert (bdh.stats["home"].pim, bdh.stats["away"].pim) == (4, 6)


async def test_power_play(bdh: RawState) -> None:
    by_time = {p.time: p for p in bdh.penalties}
    goals = {g.time: g for g in bdh.goals}
    egli = by_time["18:35"]  # natural end P2 00:35 = 1235
    assert egli.started_at == 1115 and egli.ended_early_by == goals["00:24"].key
    assert egli.expires_at == 1224  # ended by LHC's power-play goal at P2 00:24
    myrenberg = by_time["07:39"]  # natural end P3 09:39
    assert myrenberg.ended_early_by == goals["09:07"].key and myrenberg.expires_at == 2947
    assert (bdh.stats["home"].pp_goals, bdh.stats["home"].pp_chances) == (1, 3)
    assert (bdh.stats["away"].pp_goals, bdh.stats["away"].pp_chances) == (1, 2)


async def test_strength_at_the_power_play_goals() -> None:
    seen: dict[str, Any] = {}

    def watch(n: Normalizer, changes: list[Any], snapshot: Any) -> None:
        for c in changes:
            if c.kind == "added" and c.event.type == "goal" and c.event.time in ("00:24", "09:07"):
                events = [e for e in n.events.values() if e.key != c.event.key]
                seen[c.event.time] = compute_state(events, n.game_state, n.game_info).strength

    await replay_to_end("bdhvuc5tex", watch, lag_s=0)
    assert seen["00:24"]["label"] == "4v5" and seen["00:24"]["pp_side"] == "away"
    assert seen["09:07"]["label"] == "5v4" and seen["09:07"]["pp_side"] == "home"


async def test_timeout_and_pulled_goalie() -> None:
    states: list[RawState] = []
    at_pull_events: list[Any] = []

    def watch(n: Normalizer, changes: list[Any], snapshot: Any) -> None:
        if any(c.kind == "added" and c.event.key == "e118" for c in changes):
            states.append(compute_state(n.events.values(), n.game_state, n.game_info))
            at_pull_events.extend(n.events.values())

    _, final = await replay_to_end("bdhvuc5tex", watch)
    [at_pull] = states  # just after LHC pulled Myrenberg at P3 17:13
    timeout = next(e for e in at_pull_events if e.type == "timeout")
    assert (timeout.period, timeout.time, timeout.team_code) == (3, "17:13", "LHC")
    assert at_pull.stats["away"].timeouts == 1
    assert at_pull.goalie_pulled == {"home": False, "away": True}
    assert at_pull.goalies["away"] is None
    assert at_pull.goalies["home"] and at_pull.goalies["home"].number == "1"
    assert at_pull.strength["label"] == "5v6"
    assert final.goalie_pulled == {"home": False, "away": False}  # game over


async def test_shots(bdh: RawState) -> None:
    home, away = bdh.stats["home"], bdh.stats["away"]
    assert list(home.shots_on_goal_by_period.values()) == [15, 11, 5]
    assert list(away.shots_on_goal_by_period.values()) == [4, 10, 15]
    assert (home.shots_on_goal, away.shots_on_goal) == (31, 29)
    assert list(home.shot_attempts_by_period.values()) == [19, 20, 16]
    assert list(away.shot_attempts_by_period.values()) == [10, 21, 32]
    assert (home.shot_attempts, away.shot_attempts) == (55, 63)
    assert boxscore_sog("bdhvuc5tex") == {"home": 31, "away": 29}


async def test_final_state(bdh: RawState) -> None:
    assert bdh.score == {"home": 2, "away": 1}
    assert bdh.ended and bdh.phase == "postgame" and not bdh.period_running
    assert [(p.period, p.started, p.finished) for p in bdh.periods] == [
        (1, True, True),
        (2, True, True),
        (3, True, True),
    ]
    assert all(p.started_ms and p.finished_ms for p in bdh.periods)
    assert bdh.strength["label"] == "5v5" and not any(p.active for p in bdh.penalties)


async def test_overtime_game() -> None:
    _, st = await replay_to_end("m01wkdm2u1")
    assert st.score == {"home": 4, "away": 3} and st.overtime and not st.went_to_shootout
    assert goal_rows(st)[-1][:3] == ("P4 01:16", "HV71", "#96 Nikola Pasic")
    assert (st.stats["home"].goals, st.stats["away"].goals) == (4, 3)
    assert {s: st.stats[s].shots_on_goal for s in ("home", "away")} == boxscore_sog("m01wkdm2u1")
    assert st.goalie_pulled == {"home": False, "away": False}


async def test_shootout_game() -> None:
    _, st = await replay_to_end("et9erhx0si")
    assert st.score == {"home": 3, "away": 2} and st.went_to_shootout and st.overtime
    # The deciding shootout goal sets the score but is not a goal or a shot in the stats.
    assert (st.stats["home"].goals, st.stats["away"].goals) == (2, 2)
    assert [g.period for g in st.goals] == [1, 2, 2, 2]
    assert (st.stats["home"].shots_on_goal, st.stats["away"].shots_on_goal) == (15, 23)
    # Boxscore skater SOG counts the shootout winner (16); the goalie's SOGA does not (15).
    assert boxscore_sog("et9erhx0si") == {"home": 16, "away": 23}
    soga = sum(
        int(g["SOGA"]) for g in load_fixture("boxscore_et9erhx0si.json")["gkStats"]["awayTeamValue"]
    )
    assert soga == 15
    assert len(st.shootout) == 8
    assert [a.data["scored"] for a in st.shootout] == [False] * 7 + [True]
    assert st.shootout[-1].player and st.shootout[-1].player.last == "Cederqvist"
    ot_bench = next(p for p in st.penalties if p.offence_code == "TOO-M")
    assert ot_bench.kind == "bench_minor" and ot_bench.player is None


async def test_recorded_live_game() -> None:
    """The 2026-10-20 recording (FHC–DIF) replays to the official result."""
    normalizer = Normalizer()
    counts: dict[str, int] = {}
    source = RecordingSource(RECORDING, FakeClock(), speed=50, skip_to_first_event=True)
    async for snapshot in source:
        for c in normalizer.apply(snapshot):
            counts[c.kind] = counts.get(c.kind, 0) + 1
    st = compute_state(normalizer.events.values(), normalizer.game_state, normalizer.game_info)
    assert st.score == {"home": 6, "away": 2} and st.ended
    assert [(r[0], r[1], r[2], r[5]) for r in goal_rows(st)] == [
        ("P1 03:47", "FHC", "#26 Isac Heens", "1–0"),
        ("P1 10:01", "FHC", "#86 Erik Thorell", "2–0"),
        ("P2 05:04", "FHC", "#7 Henrik Tömmernes", "3–0"),
        ("P2 07:36", "DIF", "#89 Oliver Wahlstrom", "3–1"),
        ("P2 10:50", "FHC", "#11 Samuel Fagemo", "4–1"),  # first reported as Hasa
        ("P3 07:20", "FHC", "#77 Max Lindholm", "5–1"),
        ("P3 09:21", "FHC", "#10 Max Westergård", "6–1"),
        ("P3 17:09", "DIF", "#55 Charles Hudon", "6–2"),
    ]
    assert (st.stats["home"].pim, st.stats["away"].pim) == (17, 45)  # = boxscore
    assert (st.stats["home"].shots_on_goal, st.stats["away"].shots_on_goal) == (44, 14)
    assert counts["removed"] == 27  # the precursor shots and other deletions
    assert counts["updated"] < 40  # real revisions only, no gameState noise
