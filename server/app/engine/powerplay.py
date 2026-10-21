"""Power-play tracking from penalties and goals, in game seconds.

Rules implemented (IIHF/SHL as understood; the assumptions are marked):

- A minor is 2 min, a double minor two consecutive 2 min, a major 5 min. Combined
  penalties are served in feed order of their parts (``Minor + Major + GM``: 2 then 5).
  Misconducts and game misconducts do not make a team shorthanded.
- Penalties on the same player at the same time are served one after the other in one
  place in the box (2 + 2 = 4 minutes at 5 on 4, not 2 minutes at 5 on 3).
- A team has at most two places serving shorthanded time; a third penalty waits and its
  clock starts when a place frees up.
- A power-play goal ends the shorthanded team's running *minor* part that expires
  first (a double minor's current half). Majors are not ended by goals. Goals at even
  strength or by the shorthanded team end nothing.
- Coincidental penalties: at the same game second, minor parts cancel minor parts and
  major parts cancel major parts between the teams, the same offence first (roughing
  against roughing, fighting against fighting), then the rest in feed order. Those
  players sit but neither team is shorthanded by them. (Checked against SHL's own power-
  play count for the 2026-10-20 fight: docs/SHL_API.md, Team stats.)
- Penalties carry over between periods; game seconds run continuously. A penalty is
  over when the latest known game time passes its end, or when the game is over.
- Overtime in the regular season is 3 on 3 (assumption, SHL format): a penalised
  team stays at 3 and the other team gets an extra skater per penalty, up to 5.
- A power-play chance is counted each time a team goes from no man advantage to a man
  advantage from penalties: when penalties start (several at one game second count once)
  or when the other team's penalty ends and leaves one (4 on 4 turning into 5 on 4). A
  penalty during a power play the team already has is not a new chance. This matches
  SHL's `NumPP` in all four games checked.
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
    offence: str | None = None
    player: str | None = None  # player id; None for a team (bench) penalty


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
    expires_at: int | None = None  # (projected) end of its last segment
    ended_early_by: str | None = None  # goal key
    active: bool = False  # serving now
    waiting: bool = False  # waiting for a place, or behind the same player's penalty

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


Unit = list[tuple[PenaltyStatus, int]]  # one place in the box: (penalty, segment) in order


@dataclass(slots=True)
class _Serving:
    status: PenaltyStatus
    seg_len: int
    seg_end: int
    rest: Unit


def _cancel_coincidental(penalties: list[PenaltyIn]) -> dict[str, tuple[list[int], list[int]]]:
    """Per penalty key: (segments kept, segments cancelled)."""
    kept: dict[str, list[int]] = {p.key: list(p.segments_s) for p in penalties}
    cancelled: dict[str, list[int]] = {p.key: [] for p in penalties}

    def cancel(key: str, length: int) -> None:
        kept[key].remove(length)
        cancelled[key].append(length)

    by_time: dict[int, list[PenaltyIn]] = {}
    for p in penalties:
        by_time.setdefault(p.at, []).append(p)
    for group in by_time.values():
        group.sort(key=lambda p: p.order)
        for length in sorted({s for p in group for s in p.segments_s}):
            parts: dict[Side, list[tuple[str, str | None]]] = {"home": [], "away": []}
            for p in group:
                parts[p.side].extend((p.key, p.offence) for s in p.segments_s if s == length)
            offences = {o for _, o in parts["home"]} & {o for _, o in parts["away"]}
            for offence in sorted(o for o in offences if o is not None):
                home = [x for x in parts["home"] if x[1] == offence]
                away = [x for x in parts["away"] if x[1] == offence]
                for pair in zip(home, away, strict=False):
                    for side, part in zip(("home", "away"), pair, strict=True):
                        cancel(part[0], length)
                        parts[side].remove(part)
            for h, a in zip(parts["home"], parts["away"], strict=False):
                cancel(h[0], length)
                cancel(a[0], length)
    return {k: (kept[k], cancelled[k]) for k in kept}


def strength_from(serving: dict[Side, int], overtime: bool) -> Strength:
    """Skaters per team from the number of places serving shorthanded time."""
    home_pen, away_pen = serving["home"], serving["away"]
    if overtime:
        home = min(SKATERS, OT_SKATERS + max(0, away_pen - home_pen))
        away = min(SKATERS, OT_SKATERS + max(0, home_pen - away_pen))
    else:
        home = max(MIN_SKATERS, SKATERS - home_pen)
        away = max(MIN_SKATERS, SKATERS - away_pen)
    pp: Side | None = "home" if home > away else "away" if away > home else None
    return Strength(home, away, pp)


def _units(group: list[PenaltyIn], statuses: dict[str, PenaltyStatus]) -> list[Unit]:
    """Penalties called together, one unit per player (team penalties alone)."""
    units: dict[tuple[str, str], Unit] = {}
    for p in sorted(group, key=lambda p: p.order):
        status = statuses[p.key]
        if not status.segments_s:
            continue
        owner = (p.side, p.player or f"team:{p.key}")
        units.setdefault(owner, []).extend((status, s) for s in status.segments_s)
    return list(units.values())


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
    waiting: dict[Side, list[Unit]] = {"home": [], "away": []}

    def start(unit: Unit, at: int) -> None:
        (status, seg), *rest = unit
        side = status.side
        status.started_at = at if status.started_at is None else status.started_at
        serving[side].append(_Serving(status, seg, at + seg, list(rest)))

    def finish_segment(entry: _Serving, at: int) -> None:
        previous = entry.status
        if entry.rest:
            status, seg = entry.rest.pop(0)
            if status is not previous:
                previous.expires_at = at
                status.started_at = at if status.started_at is None else status.started_at
            entry.status, entry.seg_len, entry.seg_end = status, seg, at + seg
            return
        side = previous.side
        serving[side].remove(entry)
        previous.expires_at = at
        if waiting[side]:
            start(waiting[side].pop(0), at)

    def expire_until(t: int) -> None:
        while True:
            due = [e for side in serving.values() for e in side if e.seg_end <= t]
            if not due:
                return
            entry = min(due, key=lambda e: (e.seg_end, e.status.called_at))
            finish_segment(entry, entry.seg_end)
            note(entry.seg_end)

    def count() -> dict[Side, int]:
        return {"home": len(serving["home"]), "away": len(serving["away"])}

    def pp_side(at: int) -> Side | None:
        return strength_from(count(), regular_season and at > REGULATION_S).pp_side

    advantage: list[Side | None] = [None]

    def note(at: int) -> None:
        """Count a chance when a team gains a man advantage it did not have."""
        now_side = pp_side(at)
        if now_side is not None and now_side != advantage[0]:
            result.pp_chances[now_side] += 1
        advantage[0] = now_side

    groups: dict[int, list[PenaltyIn]] = {}
    for p in penalties:
        if p.at <= now:
            groups.setdefault(p.at, []).append(p)
    timeline: list[tuple[int, int, int, list[PenaltyIn] | GoalIn]] = [
        (at, min(p.order for p in group), 0, group) for at, group in groups.items()
    ] + [(g.at, g.order, 1, g) for g in goals if g.at <= now]
    timeline.sort(key=lambda t: (t[0], t[1], t[2]))

    for at, _, _, item in timeline:
        expire_until(at)
        if isinstance(item, list):
            for unit in _units(item, statuses):
                side = unit[0][0].side
                if len(serving[side]) < MAX_SERVING:
                    start(unit, at)
                else:
                    waiting[side].append(unit)
            note(at)
            continue
        goal = item
        shorthanded = serving[other(goal.side)]
        if pp_side(at) != goal.side or len(shorthanded) <= len(serving[goal.side]):
            continue
        result.pp_goals[goal.side] += 1
        result.pp_goal_keys.append(goal.key)
        minors = [e for e in shorthanded if e.seg_len == MINOR_S]
        if minors:
            entry = min(minors, key=lambda e: e.seg_end)
            entry.status.ended_early_by = goal.key
            finish_segment(entry, at)
            note(at)

    expire_until(now)
    if game_over:
        for side in ("home", "away"):
            serving[side].clear()
            waiting[side].clear()
        result.strength = Strength(SKATERS, SKATERS, None)
        return result
    for side in ("home", "away"):
        for entry in serving[side]:
            entry.status.active = True
            projected, current = entry.seg_end, entry.status
            for status, seg in entry.rest:
                if status is not current:
                    current.expires_at = projected
                    status.waiting = True
                    current = status
                projected += seg
            current.expires_at = projected
        for unit in waiting[side]:
            for status, _ in unit:
                status.waiting = True
    result.strength = strength_from(count(), regular_season and overtime_now)
    return result
