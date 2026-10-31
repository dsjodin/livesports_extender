"""League context for the pregame and idle scenes: standings, form, last meeting, next game.

Pure: takes the simplified schedule (app.feed.schedule.simplify) and standings rows.
Only finished games before ``before_ms`` are used, so nothing from tonight leaks in.
"""

import logging
from datetime import datetime
from typing import Any

from app.feedtime import STOCKHOLM

log = logging.getLogger(__name__)

FORM_GAMES = 5
# The standings' groupings (docs/SHL_API.md, Standings): SHL's own zones of the table.
ZONES = {
    "Playoff": "playoff",
    "Playin": "playin",
    "MissedPlayoff": "out",
    "QualificationDown": "qualdown",
}
_warned_zones: set[str] = set()
H2H_GAMES = 5  # head-to-head meetings, over seasons and game types


def zones(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The table's zones from the standings' ``groupings``: playoff (1–6), playin (7–10),
    out (11–12), qualdown (13–14) in 2026/27. An unknown description is logged once and
    kept as it is (CLAUDE.md rule 7)."""
    out = []
    for g in (raw or {}).get("groupings") or []:
        description = str(g.get("description"))
        zone = ZONES.get(description)
        if zone is None:
            if description not in _warned_zones:
                _warned_zones.add(description)
                log.warning("unknown standings grouping %r, shown raw", description)
            zone = description
        if isinstance(g.get("first"), int) and isinstance(g.get("last"), int):
            out.append({"zone": zone, "first": g["first"], "last": g["last"]})
    return out


def zone_for(rank: int | None, table_zones: list[dict[str, Any]]) -> str | None:
    if rank is None:
        return None
    return next((z["zone"] for z in table_zones if z["first"] <= rank <= z["last"]), None)


def standings_rows(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    table_zones = zones(raw)
    rows = []
    for row in (raw or {}).get("leagueStandings") or []:
        info = (row.get("info") or {}).get("teamInfo") or {}
        names = info.get("teamNames") or {}
        rows.append(
            {
                "rank": row.get("rank"),
                "uuid": info.get("teamUuid"),
                "code": names.get("code"),
                "short": (names.get("short") or "").strip() or None,
                "gp": row.get("GP"),
                "w": row.get("W"),
                "l": row.get("L"),
                "otw": row.get("OTW"),
                "otl": row.get("OTL"),
                "points": row.get("P"),
                "gf": row.get("GF"),
                "ga": row.get("GA"),
                "diff": row.get("Diff"),
                "zone": zone_for(row.get("rank"), table_zones),
            }
        )
    return sorted(rows, key=lambda r: r["rank"] or 99)


def _date(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, STOCKHOLM).strftime("%Y-%m-%d")


def _finished(games: list[dict[str, Any]], before_ms: int) -> list[dict[str, Any]]:
    return [
        g
        for g in games
        if g["state"] == "post-game"
        and g["start_ms"] is not None
        and g["start_ms"] < before_ms
        and g["home"]["score"] is not None
        and g["away"]["score"] is not None
    ]


def _note(game: dict[str, Any]) -> str | None:
    if game.get("shootout"):
        return "straffar"
    if game.get("overtime"):
        return "övertid"
    return None


def form(games: list[dict[str, Any]], team_uuid: str, before_ms: int) -> list[dict[str, Any]]:
    """The team's last five finished games before ``before_ms``, newest first."""
    played = [
        g
        for g in _finished(games, before_ms)
        if team_uuid in (g["home"]["uuid"], g["away"]["uuid"])
    ]
    rows = []
    for g in sorted(played, key=lambda g: g["start_ms"], reverse=True)[:FORM_GAMES]:
        home = g["home"]["uuid"] == team_uuid
        own, other = (g["home"], g["away"]) if home else (g["away"], g["home"])
        rows.append(
            {
                "uuid": g["uuid"],
                "date": _date(g["start_ms"]),
                "result": "V" if own["score"] > other["score"] else "F",
                "home_away": "H" if home else "B",
                "opponent": other["code"],
                "opponent_uuid": other["uuid"],
                "note": _note(g),
                "score": f"{own['score']}–{other['score']}",
            }
        )
    return rows


def last_meeting(
    games: list[dict[str, Any]], home_uuid: str, away_uuid: str, before_ms: int
) -> dict[str, Any] | None:
    pair = {home_uuid, away_uuid}
    met = [g for g in _finished(games, before_ms) if {g["home"]["uuid"], g["away"]["uuid"]} == pair]
    if not met:
        return None
    g = max(met, key=lambda g: g["start_ms"])
    return {
        "uuid": g["uuid"],
        "date": _date(g["start_ms"]),
        "home": g["home"]["code"],
        "away": g["away"]["code"],
        "home_uuid": g["home"]["uuid"],
        "score": f"{g['home']['score']}–{g['away']['score']}",
        "arena": g.get("arena"),
        "note": _note(g),
    }


def head_to_head(
    games: list[dict[str, Any]], home_uuid: str, away_uuid: str, before_ms: int
) -> dict[str, Any]:
    """The last H2H_GAMES meetings of the two teams before ``before_ms``, newest first,
    across seasons and game types (playoff games marked), and the wins of each side."""
    pair = {home_uuid, away_uuid}
    met = [g for g in _finished(games, before_ms) if {g["home"]["uuid"], g["away"]["uuid"]} == pair]
    seen: set[str] = set()
    rows = []
    for g in sorted(met, key=lambda g: g["start_ms"], reverse=True):
        if g["uuid"] in seen:
            continue
        seen.add(g["uuid"])
        winner = g["home"] if g["home"]["score"] > g["away"]["score"] else g["away"]
        rows.append(
            {
                "uuid": g["uuid"],
                "date": _date(g["start_ms"]),
                "home": g["home"]["code"],
                "away": g["away"]["code"],
                "home_uuid": g["home"]["uuid"],
                "away_uuid": g["away"]["uuid"],
                "score": f"{g['home']['score']}–{g['away']['score']}",
                "winner_uuid": winner["uuid"],
                "note": _note(g),
                "playoff": g.get("game_type") == "playoff",
            }
        )
        if len(rows) == H2H_GAMES:
            break
    wins = {
        side: sum(r["winner_uuid"] == uuid for r in rows)
        for side, uuid in (("home", home_uuid), ("away", away_uuid))
    }
    return {"games": rows, "wins": wins}


def leader_rows(raw: list[dict[str, Any]], team_uuid: str) -> list[dict[str, Any]]:
    """Scoring leaders from statistics-v2 stats-info rows (points or goals)."""
    rows = []
    for r in raw:
        info = r.get("info") or {}
        if not info.get("uuid"):
            continue
        rows.append(
            {
                "rank": r.get("Rank"),
                "athlete_uuid": info["uuid"],
                "team_uuid": team_uuid,
                "first": info.get("firstName"),
                "last": info.get("lastName"),
                "number": info.get("number"),
                "position": info.get("position"),
                "gp": r.get("GP"),
                "g": r.get("G"),
                "a": r.get("A"),
                "tp": r.get("TP"),
            }
        )
    return rows


def team_block(
    standings: list[dict[str, Any]], games: list[dict[str, Any]], uuid: str | None, before_ms: int
) -> dict[str, Any] | None:
    if not uuid:
        return None
    row = next((r for r in standings if r["uuid"] == uuid), None)
    gp = (row or {}).get("gp") or 0
    return {
        "rank": (row or {}).get("rank"),
        "points": (row or {}).get("points"),
        "gp": gp,
        "diff": (row or {}).get("diff"),
        "gf_per_game": round(row["gf"] / gp, 1) if row and gp else None,
        "ga_per_game": round(row["ga"] / gp, 1) if row and gp else None,
        "form": form(games, uuid, before_ms),
    }


def my_team_block(
    standings: list[dict[str, Any]],
    games: list[dict[str, Any]],
    now_ms: int,
    uuid: str | None,
    next_game: dict[str, Any] | None,
    leaders: dict[str, dict[str, Any]] | None,
    brief: Any,
) -> dict[str, Any]:
    """My team between games (the TV's idle slides): its next game, place and form, and
    its scoring leaders when they were fetched."""
    block: dict[str, Any] = {
        "uuid": uuid,
        "next_game": brief(next_game, False) if next_game else None,
        "team": team_block(standings, games, uuid, now_ms),
    }
    raw = (leaders or {}).get(uuid or "")
    if uuid and raw:
        block["leaders"] = {
            "points": leader_rows(raw.get("points") or [], uuid),
            "goals": leader_rows(raw.get("goals") or [], uuid),
        }
    return block


def build(
    standings: list[dict[str, Any]],
    games: list[dict[str, Any]],
    now_ms: int,
    *,
    home_uuid: str | None = None,
    away_uuid: str | None = None,
    start_ms: int | None = None,
    my_team_uuid: str | None = None,
    history: list[dict[str, Any]] | None = None,
    leaders: dict[str, dict[str, Any]] | None = None,
    groupings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """``history``: games outside this season's schedule (earlier seasons, playoffs), for
    head-to-head; ``leaders``: raw stats-info rows per team uuid ({"points", "goals"})."""
    before = start_ms or now_ms
    day = _date(now_ms)
    upcoming = [g for g in games if g["start_ms"] and g["start_ms"] >= now_ms - 3 * 3600_000]
    my_next = next(
        (
            g
            for g in sorted(upcoming, key=lambda g: g["start_ms"])
            if my_team_uuid in (g["home"]["uuid"], g["away"]["uuid"]) and g["state"] != "post-game"
        ),
        None,
    )
    tonight = [g for g in games if _date(g["start_ms"]) == day]
    recent = sorted(_finished(games, now_ms), key=lambda g: g["start_ms"], reverse=True)[:7]

    def brief(g: dict[str, Any], with_score: bool) -> dict[str, Any]:
        return {
            "uuid": g["uuid"],
            "start_ms": g["start_ms"],
            "home": g["home"]["code"],
            "away": g["away"]["code"],
            "home_uuid": g["home"]["uuid"],
            "away_uuid": g["away"]["uuid"],
            "arena": g.get("arena"),
            "finished": g["state"] == "post-game",
            "score": f"{g['home']['score']}–{g['away']['score']}"
            if with_score and g["state"] == "post-game"
            else None,
            "note": _note(g) if with_score else None,
        }

    teams = {
        "home": team_block(standings, games, home_uuid, before),
        "away": team_block(standings, games, away_uuid, before),
    }
    for side, uuid in (("home", home_uuid), ("away", away_uuid)):
        raw = (leaders or {}).get(uuid or "")
        if teams[side] is not None and uuid and raw:
            teams[side]["leaders"] = {
                "points": leader_rows(raw.get("points") or [], uuid),
                "goals": leader_rows(raw.get("goals") or [], uuid),
            }
    return {
        "updated_ms": now_ms,
        "standings": standings,
        "groupings": groupings or [],
        "teams": teams,
        "head_to_head": head_to_head([*games, *(history or [])], home_uuid, away_uuid, before)
        if home_uuid and away_uuid
        else None,
        "last_meeting": last_meeting(games, home_uuid, away_uuid, before)
        if home_uuid and away_uuid
        else None,
        "my_team": my_team_block(standings, games, now_ms, my_team_uuid, my_next, leaders, brief),
        # Tonight's other games show start times only: their live scores are not delayed.
        "tonight": [brief(g, False) for g in tonight],
        "recent": [brief(g, True) for g in recent],
    }


def live_table(
    standings: list[dict[str, Any]],
    games: list[dict[str, Any]],
    table_zones: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The table "om matcherna slutade nu": ``standings`` (from before tonight's games)
    plus tonight's games as they stand on the wall (delayed scores).

    ``games``: ``{"home_uuid", "away_uuid", "home", "away", "ended", "overtime",
    "shootout"}`` for games that have started; a game still on counts as if it ended now.
    Points: 3 for a regulation win; 2 and 1 after overtime or a shootout; a tie that is
    still on gives each team 1 (both are sure of the overtime point; an assumption).
    Order: points, goal difference, goals scored (SHL), then the old rank. Each row gets
    ``prev_rank``, ``move`` (places up, negative down) and ``live`` for its game tonight.
    """
    rows = {r["uuid"]: dict(r, prev_rank=r["rank"], live=None) for r in standings if r.get("uuid")}
    for g in games:
        home, away = rows.get(g["home_uuid"]), rows.get(g["away_uuid"])
        if home is None or away is None:
            continue
        h, a = g["home"], g["away"]
        extra = g.get("overtime") or g.get("shootout")
        if h == a and not g.get("ended"):
            points = {"home": 1, "away": 1}
        else:
            winner = "home" if h > a else "away"
            points = {
                winner: 2 if extra else 3,
                ("away" if winner == "home" else "home"): 1 if extra else 0,
            }
        for side, row, gf, ga in (("home", home, h, a), ("away", away, a, h)):
            row["gp"] += 1
            row["gf"] += gf
            row["ga"] += ga
            row["diff"] = row["gf"] - row["ga"]
            row["points"] += points[side]
            row["live"] = {
                "for": gf,
                "against": ga,
                "ended": bool(g.get("ended")),
                "home_away": "H" if side == "home" else "B",
                "opponent": (away if side == "home" else home).get("code"),
            }
    ordered = sorted(
        rows.values(), key=lambda r: (-r["points"], -r["diff"], -r["gf"], r["prev_rank"])
    )
    for rank, row in enumerate(ordered, start=1):
        row["rank"] = rank
        row["move"] = row["prev_rank"] - rank
        if table_zones is not None:
            row["zone"] = zone_for(rank, table_zones)  # the zone of the new place
    return ordered
