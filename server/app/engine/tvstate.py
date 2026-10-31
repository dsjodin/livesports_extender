"""The TV state: what the screens show, built only from released (delayed) events.

``build`` is pure. It never looks at undelayed data: no raw play-by-play, no game-info
score, no game state string. Phase and period come from released period events.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.engine import league as league_engine
from app.engine.events import NormalizedEvent, Side
from app.engine.state import compute_state
from app.feedtime import parse_utc_ms
from app.teams import TeamColors

SHOT_MAP_MAX_X_DM = 300  # skip outliers (docs/SHL_API.md)
RECENT = 10


@dataclass
class GameMeta:
    """Facts about the game that are not spoilers."""

    uuid: str | None = None
    arena: str | None = None
    attendance: int | None = None
    start_ms: int | None = None
    my_side: Side | None = None
    teams: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_game_info(
        cls,
        info: dict[str, Any] | None,
        attendance: int | None,
        my_side: Side | None,
        colors: TeamColors | None = None,
    ) -> "GameMeta":
        if not info:
            return cls(attendance=attendance, my_side=my_side)
        game = info.get("gameInfo") or {}
        teams: dict[str, dict[str, Any]] = {}
        for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
            team = info.get(key) or {}
            names = team.get("names") or {}
            # The home team wears its home jersey, the away team its away jersey.
            jersey = colors.jersey(team.get("uuid"), side) if colors else None
            teams[side] = {
                "uuid": team.get("uuid"),
                "code": names.get("code"),
                "short": (names.get("short") or "").strip() or None,
                "long": names.get("long"),
                "jersey": jersey,
                "color": colors.hex(jersey) if colors else None,
                "icon": team.get("icon"),
            }
        return cls(
            uuid=game.get("gameUuid"),
            arena=game.get("arenaName"),
            attendance=attendance,
            start_ms=parse_utc_ms(game.get("startDateTime")),
            my_side=my_side,
            teams=teams,
        )


def _clock(seconds: int | None, period: object) -> str | None:
    if seconds is None or not isinstance(period, int):
        return None
    within = seconds - (period - 1) * 1200
    return f"{within // 60:02d}:{within % 60:02d}"


def build(
    events: Iterable[NormalizedEvent],
    meta: GameMeta,
    scene: dict[str, Any],
    recent: list[dict[str, Any]] | None = None,
    selected: bool = True,
    league: dict[str, Any] | None = None,
    others: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evs = list(events)
    st = compute_state(evs, None, None)
    phase = st.phase if selected or evs else "idle"
    others = others or []

    shots: dict[str, list[dict[str, Any]]] = {"home": [], "away": []}
    for e in evs:
        if e.type not in ("shot", "goal") or e.side is None or not isinstance(e.period, int):
            continue
        x, y = e.data.get("x_dm"), e.data.get("y_dm")
        if not isinstance(x, int) or not isinstance(y, int) or not 0 <= x <= SHOT_MAP_MAX_X_DM:
            continue
        shots[e.side].append(
            {
                "key": e.key,
                "x_dm": x,
                "y_dm": y,
                "result": "on_goal" if e.type == "goal" else e.data.get("result"),
                "goal": e.type == "goal",
                "period": e.period,
            }
        )

    goals = st.goals
    stats: dict[str, Any] = {}
    for side, other in (("home", "away"), ("away", "home")):
        s, o = st.stats[side], st.stats[other]
        periods = max([int(p) for p in s.shot_attempts_by_period] + [0])
        against_goals = [g for g in goals if g.side == other]
        empty_net = sum(1 for g in against_goals if g.data.get("empty_net"))
        shots_against = o.shots_on_goal - empty_net
        goalie = st.goalies[side]
        stats[side] = {
            "shots_on_goal": s.shots_on_goal,
            "shots_wide": s.shots_wide,
            "shots_blocked": s.shots_blocked,
            "shot_attempts": s.shot_attempts,
            "shots_by_period": [
                s.shots_on_goal_by_period.get(str(p), 0) for p in range(1, periods + 1)
            ],
            "goals": s.goals,
            "pim": s.pim,
            "timeouts": s.timeouts,
            "pp": {"goals": s.pp_goals, "chances": s.pp_chances},
            "goalie": {
                "number": goalie.number if goalie else None,
                "name": goalie.name if goalie else None,
                "saves": shots_against - (len(against_goals) - empty_net),
                "shots_against": shots_against,
                "on_ice": goalie is not None,
                "pulled": st.goalie_pulled[side],
            },
        }

    by_key = {e.key: e for e in evs}
    penalties_active = []
    for p in st.penalties:
        if not p.active:
            continue
        penalties_active.append(
            {
                "key": p.key,
                "side": p.side,
                "number": p.player.number if p.player else None,
                "name": p.player.name if p.player else None,
                "offence_text": p.offence_text,
                "minutes": p.minutes,
                "kind": p.kind,
                "started": f"P{p.period} {p.time}",
                "expires_game_seconds": p.expires_at,
            }
        )

    return {
        "game": {
            "uuid": meta.uuid,
            "arena": meta.arena,
            "attendance": meta.attendance,
            "start_ms": meta.start_ms,
            "my_side": meta.my_side,
        },
        "teams": meta.teams,
        "phase": phase,
        "period": st.period,
        "period_running": st.period_running,
        "last_game_time": _clock(st.last_game_seconds, st.period),
        "score": st.score,
        "strength": st.strength,
        "penalties_active": penalties_active,
        "stats": stats,
        "shots": shots,
        "goals": [g.model_dump() for g in goals],
        "penalties": [by_key[p.key].model_dump() for p in st.penalties if p.key in by_key],
        "shootout": [a.model_dump() for a in st.shootout],
        "recent": (recent or [])[-RECENT:],
        "ended": st.ended,
        "overtime": st.overtime,
        "went_to_shootout": st.went_to_shootout,
        "league": league,
        "others": others,
        "live_table": _live_table(league, meta, st, phase, others),
        "scene": scene,
    }


def _live_table(
    league: dict[str, Any] | None,
    meta: GameMeta,
    st: Any,
    phase: str,
    others: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """The standings if tonight's games ended now, from delayed scores only. Only games
    that were not finished when the standings were fetched count (``league.tonight``)."""
    if not league or not league.get("standings"):
        return None
    tonight = {g["uuid"] for g in league.get("tonight", [])}
    games = []
    if meta.uuid in tonight and phase not in ("idle", "pregame") and meta.teams:
        games.append(
            {
                "home_uuid": meta.teams["home"].get("uuid"),
                "away_uuid": meta.teams["away"].get("uuid"),
                "home": st.score["home"],
                "away": st.score["away"],
                "ended": st.ended,
                "overtime": st.overtime,
                "shootout": st.went_to_shootout,
            }
        )
    for o in others:
        if o["uuid"] in tonight and o["phase"] not in ("idle", "pregame"):
            games.append(
                {
                    "home_uuid": o["teams"]["home"]["uuid"],
                    "away_uuid": o["teams"]["away"]["uuid"],
                    "home": o["score"]["home"],
                    "away": o["score"]["away"],
                    "ended": o["ended"],
                    "overtime": o["overtime"],
                    "shootout": o["went_to_shootout"],
                }
            )
    if not games:
        return None
    return league_engine.live_table(league["standings"], games, league.get("groupings"))


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Top-level keys whose value changed (``rev`` excluded)."""
    return {k: v for k, v in new.items() if k != "rev" and old.get(k) != v}
