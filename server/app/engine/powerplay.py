"""Power-play tracking from penalties and goals, in game seconds.

Rules implemented (IIHF/SHL as understood; the assumptions are marked):

- A minor is 2 min, a double minor two consecutive 2 min, a major 5 min. Combined
  penalties are served in feed order of their parts (``Minor + Major + GM``: 2 then 5).
  Misconducts and game misconducts do not make a team shorthanded.
- A team has at most two players serving shorthanded time; a third penalty waits and
  its clock starts when a place frees up.
- A power-play goal ends the shorthanded team's running *minor* part that expires
  first (a double minor's current half). Majors are not ended by goals. Goals at even
  strength or by the shorthanded team end nothing.
- Coincidental penalties (assumption, IIHF rule): at the same game second, equal
  numbers of minor parts and of major parts on both teams cancel; those players sit
  but neither team is shorthanded by them.
- Penalties carry over between periods; game seconds run continuously. A penalty is
  over when the latest known game time passes its end, or when the game is over.
- Overtime in the regular season is 3 on 3 (assumption, SHL format): a penalised
  team stays at 3 and the other team gets an extra skater per penalty, up to 5.
- One power-play chance per game second at which a team is given non-cancelled
  shorthanded time (several penalties at once are one chance; assumption).
"""

from dataclasses import dataclass, field

from app.engine.events import Side
from app.engine.offences import MINOR_S

REGULATION_S = 3 * 1200
SKATERS = 5
OT_SKATERS = 3
MIN_SKATERS = 3
MAX_SERVING = 2


def other(side: Side) -> Side:
    return "away" if side == "home" else "home"


@dataclass(frozen=True, slots=True)
class PenaltyIn:
    key: str
    side: Side
    at: int  # game seconds when called
    order: int  # feed order (eventId) for ties
    segments_s: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class GoalIn:
    key: str
    side: Side
    at: int
    order: int


@dataclass(slots=True)
class PenaltyStatus:
    key: str
    side: Side
    called_at: int
    segments_s: tuple[int, ...]  # after coincidental cancellation
    cancelled_s: tuple[int, ...] = ()
    started_at: int | None = None  # when its shorthanded time began (may be delayed)
    expires_at: int | None = None  # projected end of its last segment
    ended_early_by: str | None = None  # goal key
    active: bool = False
    waiting: bool = False  # waiting for a free place in the box

    @property
    def coincidental(self) -> bool:
        return not self.segments_s and bool(self.cancelled_s)


@dataclass(frozen=True, slots=True)
class Strength:
    home: int
    away: int
    pp_side: Side | None

    @property
    def label(self) -> str:
        return f"{self.home}v{self.away}"


@dataclass
class PowerPlayResult:
    strength: Strength
    penalties: list[PenaltyStatus]
    pp_goals: dict[Side, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    pp_chances: dict[Side, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    pp_goal_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _Serving:
    status: PenaltyStatus
    remaining: list[int]  # segments still to serve after the current one
    seg_end: int
    seg_len: int


def _cancel_coincidental(penalties: list[PenaltyIn]) -> dict[str, tuple[list[int], list[int]]]:
    """Per penalty key: (segments kept, segments cancelled)."""
    kept: dict[str, list[int]] = {p.key: list(p.segments_s) for p in penalties}
    cancelled: dict[str, list[int]] = {p.key: [] for p in penalties}
    by_time: dict[int, list[PenaltyIn]] = {}
    for p in penalties:
        by_time.setdefault(p.at, []).append(p)
    for group in by_time.values():
        for length in sorted({s for p in group for s in p.segments_s}):
            parts: dict[Side, list[str]] = {"home": [], "away": []}
            for p in sorted(group, key=lambda p: p.order):
                parts[p.side].extend(p.key for s in p.segments_s if s == length)
            n = min(len(parts["home"]), len(parts["away"]))
            for side in ("home", "away"):
                for key in parts[side][:n]:
                    kept[key].remove(length)
                    cancelled[key].append(length)
    return {k: (kept[k], cancelled[k]) for k in kept}


def strength_from(serving: dict[Side, int], overtime: bool) -> Strength:
    """Skaters per team from the number of players serving shorthanded time."""
    home_pen, away_pen = serving["home"], serving["away"]
    if overtime:
        home = min(SKATERS, OT_SKATERS + max(0, away_pen - home_pen))
        away = min(SKATERS, OT_SKATERS + max(0, home_pen - away_pen))
    else:
        home = max(MIN_SKATERS, SKATERS - home_pen)
        away = max(MIN_SKATERS, SKATERS - away_pen)
    pp: Side | None = "home" if home > away else "away" if away > home else None
    return Strength(home, away, pp)


def compute(
    penalties: list[PenaltyIn],
    goals: list[GoalIn],
    now: int,
    *,
    game_over: bool = False,
    overtime_now: bool = False,
    regular_season: bool = True,
) -> PowerPlayResult:
    """Simulate penalties and goals up to game second ``now``.

    ``overtime_now``: the current period is overtime (game second 3600 is both the end
    of period 3 and the start of overtime, so the caller decides).
    """
    split = _cancel_coincidental(penalties)
    statuses = {
        p.key: PenaltyStatus(
            key=p.key,
            side=p.side,
            called_at=p.at,
            segments_s=tuple(split[p.key][0]),
            cancelled_s=tuple(split[p.key][1]),
        )
        for p in penalties
    }
    result = PowerPlayResult(Strength(SKATERS, SKATERS, None), list(statuses.values()))
    serving: dict[Side, list[_Serving]] = {"home": [], "away": []}
    waiting: dict[Side, list[PenaltyStatus]] = {"home": [], "away": []}

    def start(status: PenaltyStatus, at: int) -> None:
        segs = list(status.segments_s)
        status.started_at = at
        status.waiting = False
        first = segs.pop(0)
        serving[status.side].append(_Serving(status, segs, at + first, first))

    def finish_segment(entry: _Serving, at: int) -> None:
        side = entry.status.side
        if entry.remaining:
            entry.seg_len = entry.remaining.pop(0)
            entry.seg_end = at + entry.seg_len
            return
        serving[side].remove(entry)
        entry.status.expires_at = at
        if waiting[side]:
            start(waiting[side].pop(0), at)

    def expire_until(t: int) -> None:
        while True:
            due = [e for side in serving.values() for e in side if e.seg_end <= t]
            if not due:
                return
            entry = min(due, key=lambda e: (e.seg_end, e.status.called_at))
            finish_segment(entry, entry.seg_end)

    def count() -> dict[Side, int]:
        return {"home": len(serving["home"]), "away": len(serving["away"])}

    timeline: list[tuple[int, int, int, PenaltyIn | GoalIn]] = [
        (p.at, p.order, 0, p) for p in penalties if p.at <= now
    ] + [(g.at, g.order, 1, g) for g in goals if g.at <= now]
    timeline.sort(key=lambda t: (t[0], t[1], t[2]))
    chance_times: dict[Side, set[int]] = {"home": set(), "away": set()}

    for at, _, _, item in timeline:
        expire_until(at)
        if isinstance(item, PenaltyIn):
            status = statuses[item.key]
            if not status.segments_s:
                continue
            chance_times[other(item.side)].add(at)
            if len(serving[item.side]) < MAX_SERVING:
                start(status, at)
            else:
                status.waiting = True
                waiting[item.side].append(status)
            continue
        strength = strength_from(count(), regular_season and at > REGULATION_S)
        if strength.pp_side != item.side or len(serving[other(item.side)]) <= len(
            serving[item.side]
        ):
            continue
        result.pp_goals[item.side] += 1
        result.pp_goal_keys.append(item.key)
        minors = [e for e in serving[other(item.side)] if e.seg_len == MINOR_S]
        if minors:
            entry = min(minors, key=lambda e: e.seg_end)
            entry.status.ended_early_by = item.key
            finish_segment(entry, at)

    expire_until(now)
    for side in ("home", "away"):
        result.pp_chances[side] = len(chance_times[side])
    if game_over:
        for side in ("home", "away"):
            for entry in list(serving[side]):
                entry.status.expires_at = entry.seg_end + sum(entry.remaining)
            serving[side].clear()
            waiting[side].clear()
    for side in ("home", "away"):
        for entry in serving[side]:
            entry.status.active = True
            entry.status.expires_at = entry.seg_end + sum(entry.remaining)
    if game_over:
        result.strength = Strength(SKATERS, SKATERS, None)
    else:
        result.strength = strength_from(count(), regular_season and overtime_now)
    return result
