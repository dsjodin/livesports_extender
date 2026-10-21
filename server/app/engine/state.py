"""RawState: the undelayed game state computed from the normalizer's current events."""

import logging
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel

from app.engine import powerplay
from app.engine.events import NormalizedEvent, Player, Side
from app.engine.normalizer import ON_GOAL_SECTIONS, PERIOD_LENGTH_S

log = logging.getLogger(__name__)

Phase = Literal["pregame", "live", "intermission", "postgame"]
PHASE_FOR_STATE: dict[str, Phase] = {
    "Ongoing": "live",
    "Intermission": "intermission",
    "GameEnded": "postgame",
}
OT_LENGTH_S = 5 * 60  # regular-season overtime


class TeamStats(BaseModel):
    shots_on_goal: int = 0
    shots_wide: int = 0  # "utanför"
    shots_blocked: int = 0  # "täckt av spelare"
    shot_attempts: int = 0  # all of the above, plus any unknown goalSection
    shots_on_goal_by_period: dict[str, int] = {}
    shot_attempts_by_period: dict[str, int] = {}
    goals: int = 0  # excludes the shootout
    pim: int = 0
    pp_goals: int = 0
    pp_chances: int = 0
    timeouts: int = 0


class PenaltyState(BaseModel):
    key: str
    side: Side
    player: Player | None
    offence_code: str | None
    offence_text: str
    minutes: int
    kind: str
    period: int | str | None
    time: str | None
    called_at: int | None
    started_at: int | None
    expires_at: int | None
    ended_early_by: str | None
    coincidental: bool
    active: bool
    waiting: bool


class PeriodState(BaseModel):
    period: int | str
    started_ms: int | None = None
    finished_ms: int | None = None
    started: bool = False
    finished: bool = False


class RawState(BaseModel):
    game_uuid: str | None
    phase: Phase
    game_state: str | None
    period: int | str | None
    period_running: bool
    last_game_seconds: int | None
    score: dict[Side, int]
    goals: list[NormalizedEvent]  # regulation and overtime, in game order
    shootout: list[NormalizedEvent]  # shootout attempts in order
    penalties: list[PenaltyState]
    goalies: dict[Side, Player | None]
    goalie_pulled: dict[Side, bool]
    strength: dict[str, Any]  # {"home": 5, "away": 4, "pp_side": "home", "label": "5v4"}
    stats: dict[Side, TeamStats]
    periods: list[PeriodState]
    ended: bool
    overtime: bool
    went_to_shootout: bool


def order_key(e: NormalizedEvent) -> tuple[int, int, int]:
    period = e.period if isinstance(e.period, int) else 99
    return (period, e.game_seconds if e.game_seconds is not None else 0, e.event_id or 0)


def _is_end_exit(e: NormalizedEvent, goals: list[NormalizedEvent]) -> bool:
    """A goalie leaving at the end of a period or game, not pulled for an extra skater."""
    if e.time == "20:00":
        return True
    if isinstance(e.period, int) and e.period > 3:
        if e.time == "05:00":
            return True
        return any(g.period == e.period and g.time == e.time for g in goals)
    return False


def _period_end_seconds(period: int, goals: list[NormalizedEvent]) -> int:
    start = (period - 1) * PERIOD_LENGTH_S
    if period <= 3:
        return start + PERIOD_LENGTH_S
    ot_goals = [g.game_seconds for g in goals if g.period == period and g.game_seconds]
    return min(ot_goals) if ot_goals else start + OT_LENGTH_S


def compute_state(
    events: Iterable[NormalizedEvent],
    game_state: str | None,
    game_info: dict[str, Any] | None = None,
) -> RawState:
    evs = sorted(events, key=order_key)
    by_type: dict[str, list[NormalizedEvent]] = {}
    for e in evs:
        by_type.setdefault(e.type, []).append(e)
    all_goals = by_type.get("goal", [])
    goals = [g for g in all_goals if isinstance(g.period, int)]

    # periods
    periods: dict[Any, PeriodState] = {}
    for e in by_type.get("period_start", []) + by_type.get("period_end", []):
        p = periods.setdefault(e.period, PeriodState(period=e.period))
        if e.type == "period_start":
            p.started, p.started_ms = True, e.event_ms
        else:
            p.finished, p.finished_ms = True, e.event_ms
    period_list = sorted(
        periods.values(), key=lambda p: p.period if isinstance(p.period, int) else 99
    )
    current = next((p for p in reversed(period_list) if p.started), None)
    running = current is not None and not current.finished

    ended = game_state == "GameEnded" or "game_end" in by_type
    if game_state in PHASE_FOR_STATE:
        phase: Phase = PHASE_FOR_STATE[game_state]
    elif current is None:
        phase = "pregame"
    else:
        phase = "live" if running else "intermission"
    if ended:
        phase = "postgame"

    # score: latest goal (shootout winner included), game-info as fallback
    score: dict[Side, int] = {"home": 0, "away": 0}
    if all_goals:
        latest = all_goals[-1].data.get("score") or {}
        score = {"home": int(latest.get("home") or 0), "away": int(latest.get("away") or 0)}
    elif game_info:
        raw = [(game_info.get(t) or {}).get("score") for t in ("homeTeam", "awayTeam")]
        if all(isinstance(v, int) for v in raw):
            score = {"home": raw[0], "away": raw[1]}

    # latest known game time
    times = [e.game_seconds for e in evs if e.game_seconds is not None]
    for p in period_list:
        if p.finished and isinstance(p.period, int):
            times.append(_period_end_seconds(p.period, goals))
    now = max(times) if times else None

    # goalies
    goalies: dict[Side, Player | None] = {"home": None, "away": None}
    pulled: dict[Side, bool] = {"home": False, "away": False}
    for e in by_type.get("goalie_change", []):
        if e.side is None:
            continue
        if e.data.get("entering"):
            goalies[e.side], pulled[e.side] = e.player, False
        elif not _is_end_exit(e, all_goals):
            goalies[e.side], pulled[e.side] = None, True
    if not running or ended:
        pulled = {"home": False, "away": False}

    # stats
    stats: dict[Side, TeamStats] = {"home": TeamStats(), "away": TeamStats()}
    for e in by_type.get("shot", []) + goals:
        if e.side is None or not isinstance(e.period, int):
            continue
        s = stats[e.side]
        on_goal = e.type == "goal" or e.data.get("goal_section") in ON_GOAL_SECTIONS
        p = str(e.period)
        s.shot_attempts += 1
        s.shot_attempts_by_period[p] = s.shot_attempts_by_period.get(p, 0) + 1
        if on_goal:
            s.shots_on_goal += 1
            s.shots_on_goal_by_period[p] = s.shots_on_goal_by_period.get(p, 0) + 1
        elif e.data.get("result") == "wide":
            s.shots_wide += 1
        elif e.data.get("result") == "blocked":
            s.shots_blocked += 1
    for g in goals:
        if g.side:
            stats[g.side].goals += 1
    for e in by_type.get("penalty", []):
        if e.side:
            stats[e.side].pim += int(e.data.get("minutes") or 0)
    for e in by_type.get("timeout", []):
        if e.side:
            stats[e.side].timeouts += 1

    # power play
    pen_events = [e for e in by_type.get("penalty", []) if e.side and e.game_seconds is not None]
    pp = powerplay.compute(
        [
            powerplay.PenaltyIn(
                e.key,
                e.side,
                e.game_seconds,
                e.event_id or 0,
                tuple(e.data.get("segments_s", ())),
                e.data.get("offence_code"),
                e.player.id if e.player else None,
            )
            for e in pen_events
            if e.side is not None and e.game_seconds is not None
        ],
        [
            powerplay.GoalIn(g.key, g.side, g.game_seconds, g.event_id or 0)
            for g in goals
            if g.side is not None and g.game_seconds is not None
        ],
        now if now is not None else 0,
        game_over=ended,
        overtime_now=isinstance(current.period, int) and current.period > 3 if current else False,
    )
    for side in ("home", "away"):
        stats[side].pp_goals = pp.pp_goals[side]
        stats[side].pp_chances = pp.pp_chances[side]
    statuses = {s.key: s for s in pp.penalties}
    penalties = []
    for e in pen_events:
        s = statuses[e.key]
        penalties.append(
            PenaltyState(
                key=e.key,
                side=s.side,
                player=e.player,
                offence_code=e.data.get("offence_code"),
                offence_text=e.data.get("offence_text", ""),
                minutes=int(e.data.get("minutes") or 0),
                kind=e.data.get("kind", ""),
                period=e.period,
                time=e.time,
                called_at=s.called_at,
                started_at=s.started_at,
                expires_at=s.expires_at,
                ended_early_by=s.ended_early_by,
                coincidental=s.coincidental,
                active=s.active,
                waiting=s.waiting,
            )
        )
    home = pp.strength.home + (1 if pulled["home"] else 0)
    away = pp.strength.away + (1 if pulled["away"] else 0)
    strength = {
        "home": home,
        "away": away,
        "pp_side": pp.strength.pp_side,
        "label": f"{home}v{away}",
    }

    game_uuid = (game_info or {}).get("gameInfo", {}).get("gameUuid") or next(
        (e.game_uuid for e in evs if e.game_uuid), None
    )
    return RawState(
        game_uuid=game_uuid,
        phase=phase,
        game_state=game_state,
        period=current.period if current else None,
        period_running=running and not ended,
        last_game_seconds=now,
        score=score,
        goals=goals,
        shootout=by_type.get("shootout_attempt", []),
        penalties=penalties,
        goalies=goalies,
        goalie_pulled=pulled,
        strength=strength,
        stats=stats,
        periods=period_list,
        ended=ended,
        overtime=any(isinstance(p.period, int) and p.period > 3 for p in period_list),
        went_to_shootout=any(p.period == "shootout" for p in period_list),
    )
