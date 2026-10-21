"""Webhook payloads for Home Assistant (docs/PROTOCOL.md, Webhooks). Pure: built from a
released event and the game's teams; the dispatcher (api/webhooks.py) sends them at
the event's play_at."""

from typing import Any

from app.engine.events import NormalizedEvent, Side

EVENTS = (
    "shl_goal",
    "shl_goal_disallowed",
    "shl_penalty",
    "shl_period_start",
    "shl_period_end",
    "shl_game_end",
)
TYPES = {
    "goal": "shl_goal",
    "goal_disallowed": "shl_goal_disallowed",
    "penalty": "shl_penalty",
    "period_start": "shl_period_start",
    "period_end": "shl_period_end",
    "game_end": "shl_game_end",
}
NUMBERS_SV = (
    "noll", "ett", "två", "tre", "fyra", "fem", "sex", "sju", "åtta", "nio", "tio",
    "elva", "tolv", "tretton", "fjorton", "femton", "sexton", "sjutton", "arton",
    "nitton", "tjugo",
)  # fmt: skip


def number_sv(n: int) -> str:
    return NUMBERS_SV[n] if 0 <= n < len(NUMBERS_SV) else str(n)


def rgb(hex_color: str | None) -> list[int] | None:
    if not hex_color or len(hex_color) != 7 or not hex_color.startswith("#"):
        return None
    try:
        return [int(hex_color[i : i + 2], 16) for i in (1, 3, 5)]
    except ValueError:
        return None


def _strength_sv(data: dict[str, Any]) -> str:
    if data.get("penalty_shot"):
        return " på straffslag"
    if data.get("empty_net"):
        return " i tom bur"
    status = str(data.get("strength") or "")
    if status.startswith("PP"):
        return " i powerplay"
    if status.startswith("SH"):
        return " i boxplay"
    return ""


def tts_goal(team_name: str, data: dict[str, Any], scorer: Any) -> str:
    """ "Mål för Frölunda! Nummer 25, Arttu Ruotsalainen, i powerplay. Två–ett." """
    parts = [f"Mål för {team_name}!"]
    if scorer is not None and (scorer.first or scorer.last):
        name = f"{scorer.first or ''} {scorer.last or ''}".strip()
        number = f"Nummer {scorer.number}, " if scorer.number else ""
        strength = _strength_sv(data)
        parts.append(f"{number}{name}{',' + strength if strength else ''}.")
    score = data.get("score") or {}
    if isinstance(score.get("home"), int) and isinstance(score.get("away"), int):
        parts.append(f"{number_sv(score['home']).capitalize()}–{number_sv(score['away'])}.")
    return " ".join(parts)


def _team_fields(teams: dict[str, dict[str, Any]], side: Side | None) -> dict[str, Any]:
    team = teams.get(side or "") or {}
    return {
        "team_code": team.get("code"),
        "team_name": team.get("long") or team.get("short"),
        "team_color": team.get("color"),
        "team_rgb": rgb(team.get("color")),
    }


def payload(
    event: NormalizedEvent,
    teams: dict[str, dict[str, Any]],
    my_side: Side | None,
    score: dict[str, int],
    *,
    source: str = "feed",
) -> dict[str, Any] | None:
    """The webhook body for a released event, or None if the event type has none.
    ``score`` is the TV state's score once the event has played. ``sent_ms`` is added
    when it is sent."""
    name = TYPES.get(event.type)
    if name is None or (event.type == "goal" and event.data.get("shootout")):
        return None
    side = event.side
    base: dict[str, Any] = {"event": name, "game_uuid": event.game_uuid, "test": event.test}
    mine = {"side": side, "is_my_team": side is not None and side == my_side}
    if name == "shl_goal":
        data = event.data
        team = _team_fields(teams, side)
        p = event.player
        assists = [
            f"{a.get('first', '')} {a.get('last', '')}".strip() for a in data.get("assists", [])
        ]
        goal_score = data.get("score") or score
        return (
            base
            | mine
            | team
            | {
                "source": source,
                "scorer": f"{p.first or ''} {p.last or ''}".strip() if p else "",
                "scorer_number": p.number if p else None,
                "assists": assists,
                "strength": data.get("strength"),
                "empty_net": bool(data.get("empty_net")),
                "score_home": goal_score.get("home"),
                "score_away": goal_score.get("away"),
                "period": event.period,
                "time": event.time,
                "tts_sv": tts_goal(team["team_name"] or team["team_code"] or "", data, p),
            }
        )
    if name == "shl_goal_disallowed":
        corrected = event.data.get("score") or score
        return (
            base | mine | {"score_home": corrected.get("home"), "score_away": corrected.get("away")}
        )
    if name == "shl_penalty":
        p = event.player
        return (
            base
            | mine
            | {
                "player": f"{p.first or ''} {p.last or ''}".strip() if p else None,
                "number": p.number if p else None,
                "offence_text": event.data.get("offence_text"),
                "minutes": event.data.get("minutes"),
            }
        )
    if name == "shl_period_start":
        return base | {"period": event.period}
    if name == "shl_period_end":
        return base | {
            "period": event.period,
            "score_home": score.get("home"),
            "score_away": score.get("away"),
        }
    final = event.data.get("final") or score
    h, a = final.get("home", 0), final.get("away", 0)
    winner: Side | None = "home" if h > a else "away" if a > h else None
    return base | {
        "score_home": h,
        "score_away": a,
        "winner_side": winner,
        "my_team_won": None if my_side is None else winner == my_side,
        "overtime": bool(event.data.get("overtime")),
        "shootout": bool(event.data.get("shootout")),
    }
