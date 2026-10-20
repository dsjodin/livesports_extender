from app.engine.powerplay import GoalIn, PenaltyIn, compute

MINOR = (120,)
MAJOR = (300,)


def pen(key: str, side: str, at: int, segs: tuple[int, ...] = MINOR, order: int = 0) -> PenaltyIn:
    return PenaltyIn(key, side, at, order or at, segs)  # type: ignore[arg-type]


def goal(key: str, side: str, at: int) -> GoalIn:
    return GoalIn(key, side, at, at)  # type: ignore[arg-type]


def status(result, key: str):  # type: ignore[no-untyped-def]
    return next(p for p in result.penalties if p.key == key)


def test_single_minor() -> None:
    p = [pen("p1", "away", 100)]
    during = compute(p, [], 150)
    assert during.strength.label == "5v4" and during.strength.pp_side == "home"
    assert status(during, "p1").active and status(during, "p1").expires_at == 220
    after = compute(p, [], 220)
    assert after.strength.label == "5v5" and not status(after, "p1").active
    assert after.pp_chances == {"home": 1, "away": 0}


def test_pp_goal_ends_minor_early_but_sh_goal_does_not() -> None:
    p = [pen("p1", "away", 100)]
    sh = compute(p, [goal("g1", "away", 130)], 150)
    assert status(sh, "p1").active and sh.pp_goals == {"home": 0, "away": 0}
    pp = compute(p, [goal("g1", "home", 130)], 150)
    s = status(pp, "p1")
    assert not s.active and s.expires_at == 130 and s.ended_early_by == "g1"
    assert pp.strength.label == "5v5" and pp.pp_goals == {"home": 1, "away": 0}
    assert pp.pp_goal_keys == ["g1"]


def test_major_is_not_ended_by_a_goal() -> None:
    r = compute(
        [pen("p1", "away", 100, MAJOR)], [goal("g1", "home", 130), goal("g2", "home", 200)], 250
    )
    assert status(r, "p1").active and status(r, "p1").expires_at == 400
    assert r.pp_goals["home"] == 2


def test_double_minor_goal_ends_current_half() -> None:
    r = compute([pen("p1", "away", 100, (120, 120))], [goal("g1", "home", 150)], 160)
    s = status(r, "p1")
    assert s.active and s.expires_at == 270  # second half runs 150..270
    r = compute([pen("p1", "away", 100, (120, 120))], [goal("g1", "home", 150)], 270)
    assert not status(r, "p1").active


def test_combined_minor_and_major() -> None:
    r = compute([pen("p1", "away", 100, (120, 300))], [goal("g1", "home", 150)], 200)
    assert status(r, "p1").active and status(r, "p1").expires_at == 450


def test_two_minors_and_a_goal() -> None:
    p = [pen("p1", "away", 100), pen("p2", "away", 130)]
    r = compute(p, [], 140)
    assert r.strength.label == "5v3"
    r = compute(p, [goal("g1", "home", 140)], 145)
    assert status(r, "p1").ended_early_by == "g1" and status(r, "p2").active
    assert r.strength.label == "5v4"


def test_third_penalty_waits_for_a_place() -> None:
    p = [pen("p1", "away", 100), pen("p2", "away", 110), pen("p3", "away", 120)]
    r = compute(p, [], 150)
    assert r.strength.label == "5v3" and status(r, "p3").waiting
    r = compute(p, [], 225)
    s = status(r, "p3")
    assert s.started_at == 220 and s.active and s.expires_at == 340


def test_overlapping_penalties_give_4v4() -> None:
    p = [pen("p1", "home", 100), pen("p2", "away", 130)]
    r = compute(p, [goal("g1", "home", 140)], 150)
    assert r.strength.label == "4v4" and r.strength.pp_side is None
    assert status(r, "p2").active and r.pp_goals["home"] == 0


def test_coincidental_penalties_cancel() -> None:
    r = compute([pen("p1", "home", 100), pen("p2", "away", 100)], [], 150)
    assert r.strength.label == "5v5" and r.pp_chances == {"home": 0, "away": 0}
    assert status(r, "p1").coincidental and status(r, "p2").coincidental


def test_fight_with_unequal_penalties() -> None:
    """P3 10:26 on 2026-10-20: FHC major + 3 minors, DIF 2+5+GM, 4 more minors."""
    t = 3026
    home = [pen("h1", "home", t, MAJOR, 1)] + [pen(f"h{i}", "home", t, MINOR, i) for i in (2, 3, 4)]
    away = [pen("a1", "away", t, MINOR, 5), pen("a2", "away", t, (120, 300), 6)] + [
        pen(f"a{i}", "away", t, MINOR, i) for i in (7, 8, 9)
    ]
    r = compute(home + away, [], t + 10)
    assert r.strength.label == "5v3" and r.strength.pp_side == "home"
    assert [p.key for p in r.penalties if p.active] == ["a8", "a9"]
    assert r.pp_chances == {"home": 1, "away": 0}


def test_penalties_carry_over_periods() -> None:
    r = compute([pen("p1", "away", 1170)], [], 1230)  # P1 19:30, now P2 00:30
    assert status(r, "p1").active and r.strength.label == "5v4"


def test_overtime_three_on_three() -> None:
    p = [pen("p1", "away", 3700)]
    r = compute(p, [], 3720, overtime_now=True)
    assert r.strength.label == "4v3" and r.strength.pp_side == "home"
    r = compute([*p, pen("p2", "away", 3710)], [], 3720, overtime_now=True)
    assert r.strength.label == "5v3"


def test_game_over_clears_everything() -> None:
    r = compute([pen("p1", "away", 3550)], [], 3600, game_over=True)
    assert r.strength.label == "5v5" and not status(r, "p1").active


def test_no_segments_no_power_play() -> None:
    r = compute([pen("p1", "away", 100, ())], [], 150)  # misconduct only, or a penalty shot
    assert r.strength.label == "5v5" and r.pp_chances == {"home": 0, "away": 0}
