"""League context for the pregame and idle scenes: standings, form, last meeting, next game.

Pure: takes the simplified schedule (app.feed.schedule.simplify) and standings rows.
Only finished games before ``before_ms`` are used, so nothing from tonight leaks in.
"""

from datetime import datetime
from typing import Any

from app.feedtime import STOCKHOLM

FORM_GAMES = 5


def standings_rows(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
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


def build(
    standings: list[dict[str, Any]],
    games: list[dict[str, Any]],
    now_ms: int,
    *,
    home_uuid: str | None = None,
    away_uuid: str | None = None,
    start_ms: int | None = None,
    my_team_uuid: str | None = None,
) -> dict[str, Any]:
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

    return {
        "updated_ms": now_ms,
        "standings": standings,
        "teams": {
            "home": team_block(standings, games, home_uuid, before),
            "away": team_block(standings, games, away_uuid, before),
        },
        "last_meeting": last_meeting(games, home_uuid, away_uuid, before)
        if home_uuid and away_uuid
        else None,
        "my_team": {"uuid": my_team_uuid, "next_game": brief(my_next, False) if my_next else None},
        # Tonight's other games show start times only: their live scores are not delayed.
        "tonight": [brief(g, False) for g in tonight],
        "recent": [brief(g, True) for g in recent],
    }
