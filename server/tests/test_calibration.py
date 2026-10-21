from typing import Any

from app.engine.calibration import Calibrator
from app.engine.events import NormalizedEvent

T = 1_800_000_000_000
S = 1000


def ev(key: str, typ: str, event_ms: int | None, side: str | None = None, **data: Any):
    return NormalizedEvent(
        key=key,
        type=typ,
        raw_type=typ,
        side=side,
        data=data,
        event_ms=event_ms,
        first_seen_ms=T,
        received_ms=T,
    )


def test_period_starts_propose_the_median() -> None:
    cal = Calibrator()
    events = []
    for n, lag_s in enumerate((75.0, 75.4, 74.9), start=1):
        start = T + n * 3600 * S
        events.append(ev(f"period-{n}-start", "period_start", start))
        press = cal.press("period_start", start + round(lag_s * 1000) + 300, None, events)
        assert press.status == "matched" and press.event_key == f"period-{n}-start"
    assert cal.proposal_ms() == 75_000
    assert cal.matched_count() == 3
    assert [p.as_dict()["sample_s"] for p in cal.presses] == [75.0, 75.4, 74.9]


def test_press_before_the_feed_has_the_goal_matches_when_it_arrives() -> None:
    cal = Calibrator()
    press = cal.press("goal", T + 41 * S, "home", [])
    assert press.status == "pending"
    goal = ev("e7", "goal", T, "home")
    assert cal.update([goal], T + 60 * S)  # the feed shows the goal 60 s after the ice
    assert press.status == "matched" and press.sample_ms == 41 * S - 300


def test_window_side_ambiguity_and_expiry() -> None:
    cal = Calibrator()
    shots = [
        ev("e1", "shot", T, "home", result="on_goal"),
        ev("e2", "shot", T + 9 * S, "away", result="on_goal"),
    ]
    wide = ev("e3", "shot", T + 10 * S, "home", result="wide")
    both = cal.press("shot_on_goal", T + 40 * S, None, [*shots, wide])
    home = cal.press("shot_on_goal", T + 40 * S, "home", [*shots, wide])
    too_soon = cal.press("goal", T + 3 * S, None, [ev("e9", "goal", T, "home")])
    assert both.status == "ambiguous" and both.sample_ms is None
    assert home.status == "matched" and home.event_key == "e1"
    assert too_soon.status == "pending"
    cal.update([], T + 200 * S)
    assert too_soon.status == "unmatched"
    assert cal.proposal_ms() == 40 * S - 300
    assert cal.remove(home.id) and cal.proposal_ms() is None


def test_matched_press_survives_its_event_going_away_and_restores() -> None:
    cal = Calibrator()
    press = cal.press("period_start", T + 60 * S, None, [ev("period-1-start", "period_start", T)])
    cal.update([], T + 70 * S)  # a replay seek cleared the raw events
    assert press.status == "matched"
    again = Calibrator.from_saved([p.as_dict() for p in cal.presses])
    assert again.presses[0].sample_ms == 60 * S - 300
    assert again.press("goal", T, None, []).id == "s2"
