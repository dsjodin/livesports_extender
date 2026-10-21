"""Turns successive play-by-play snapshots into added / updated / removed events."""

import logging
from collections.abc import Callable
from typing import Any

from app.engine.events import Change, NormalizedEvent, Player, Side
from app.engine.offences import offence_text, parse_variant
from app.feed.snapshot import Snapshot
from app.feedtime import parse_local_ms

log = logging.getLogger(__name__)

# Shot result from goalSection (docs/SHL_API.md, shot). 1 to 9 is on goal: it matched the
# boxscore exactly in all four games checked. shl.se's game report shows 1-9 as "Skott",
# 0 as "Skott (utanför)" and -3 as "Skott (täckt av spelare)". -1 (seen once) is unknown.
ON_GOAL_SECTIONS = frozenset(range(1, 10))
SECTION_RESULT = {0: "wide", -3: "blocked"}
# Copied onto every event and rewritten at every period boundary (or by a replay's
# timestamp shift); not a content change. realWorldTime is read once, as event_ms.
IGNORED_FIELDS = frozenset({"gameState", "attendance", "updatedTime", "realWorldTime"})
KNOWN_GAME_STATES = frozenset({"Ongoing", "Intermission", "GameEnded"})
KNOWN_GOAL_STATUSES = frozenset({"EQ", "PP1", "PP2", "SH1", "SH2", "EN"})
RAW_TYPES = {
    "goal": "goal",
    "shot": "shot",
    "penalty": "penalty",
    "goalkeeper": "goalie_change",
    "timeout": "timeout",
    "shootout-penalty-shot": "shootout_attempt",
}
# event_ms further than this from first_seen_ms is not trusted (CLAUDE.md rule 2).
MAX_AHEAD_MS = 5_000
MAX_BEHIND_MS = 10 * 60_000
PERIOD_LENGTH_S = 1200
NEXT_PERIOD_ESTIMATE_MS = 18 * 60_000

_warned: set[tuple[str, str]] = set()


def warn_once(kind: str, value: object) -> None:
    if (kind, repr(value)) not in _warned:
        _warned.add((kind, repr(value)))
        log.warning("unknown %s %r, shown raw", kind, value)


def shot_result(section: object) -> str:
    """``on_goal``, ``wide``, ``blocked`` or ``unknown`` (logged once)."""
    if section in ON_GOAL_SECTIONS:
        return "on_goal"
    if isinstance(section, int) and section in SECTION_RESULT:
        return SECTION_RESULT[section]
    warn_once("goalSection", section)
    return "unknown"


def game_seconds(period: object, time: object) -> int | None:
    if not isinstance(period, int) or not isinstance(time, str):
        return None
    mm, sep, ss = time.partition(":")
    if not sep or not mm.isdigit() or not ss.isdigit():
        return None
    return (period - 1) * PERIOD_LENGTH_S + int(mm) * 60 + int(ss)


def player(raw: object) -> Player | None:
    if not isinstance(raw, dict) or not raw:
        return None
    return Player(
        id=None if raw.get("playerId") is None else str(raw["playerId"]),
        number=None if raw.get("jerseyToday") is None else str(raw["jerseyToday"]),
        first=raw.get("firstName"),
        last=raw.get("familyName"),
    )


def players(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [p.model_dump() for item in raw if (p := player(item))]


def stat(raw: object, key: str) -> int | None:
    if not isinstance(raw, dict):
        return None
    for entry in raw.get("statistics") or []:
        if isinstance(entry, dict) and entry.get("key") == key:
            try:
                return int(entry.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def scorer_game_goals(pbp: list[Any]) -> dict[Any, int]:
    """eventId -> the scorer's goals in this game up to and including this one (regulation
    and overtime; shootout goals do not count)."""
    goals = [
        e
        for e in pbp
        if isinstance(e, dict) and e.get("type") == "goal" and isinstance(e.get("period"), int)
    ]
    goals.sort(
        key=lambda e: (game_seconds(e.get("period"), e.get("time")) or 0, e.get("eventId", 0))
    )
    counts: dict[Any, int] = {}
    out: dict[Any, int] = {}
    for e in goals:
        who = (e.get("player") or {}).get("playerId")
        if who is None:
            continue
        counts[who] = counts.get(who, 0) + 1
        out[e.get("eventId")] = counts[who]
    return out


def content(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in IGNORED_FIELDS}


class Normalizer:
    """Diffs successive play-by-play lists. Pure and synchronous.

    Events are keyed ``e<eventId>``; a period object gives ``period-<n>-start`` (once
    started) and ``period-<n>-end`` (once finished); ``game-end`` appears when the
    play-by-play ``gameState`` is ``GameEnded``. ``first_seen_ms`` is the snapshot's
    ``available_ms`` on first appearance and is kept on updates, as is ``event_ms``.
    A key that disappears is ``removed``; if it comes back it is ``added`` again.
    """

    def __init__(self) -> None:
        self.events: dict[str, NormalizedEvent] = {}
        self.game_state: str | None = None
        self.game_info: dict[str, Any] | None = None
        self._content: dict[str, Any] = {}
        self._last_pbp: list[dict[str, Any]] | None = None
        self._epoch: int | None = None
        self._game_goals: dict[Any, int] = {}

    def reset(self) -> None:
        self.events.clear()
        self._content.clear()
        self.game_state = None
        self._last_pbp = None

    def apply(self, snapshot: Snapshot) -> list[Change]:
        changes: list[Change] = []
        if self._epoch is not None and snapshot.epoch != self._epoch:
            self.reset()
            changes.append(Change("reset"))
        self._epoch = snapshot.epoch
        if snapshot.game_info is not None:
            self.game_info = snapshot.game_info
        pbp = snapshot.pbp
        if pbp is None or pbp is self._last_pbp:
            return changes
        self._last_pbp = pbp

        self.game_state = None
        for item in pbp:
            if isinstance(item, dict) and isinstance(item.get("gameState"), str):
                self.game_state = item["gameState"]
                break
        if self.game_state is not None and self.game_state not in KNOWN_GAME_STATES:
            warn_once("gameState", self.game_state)

        self._game_goals = scorer_game_goals(pbp)
        current: dict[str, tuple[Any, Callable[[int, int | None], NormalizedEvent]]] = {}
        for item in pbp:
            if isinstance(item, dict):
                current.update(self._entries(item, snapshot))
        if self.game_state == "GameEnded":
            current["game-end"] = self._game_end(pbp, snapshot)

        for key, (compare, build) in current.items():
            old = self.events.get(key)
            if old is None:
                first_seen = snapshot.available_ms
                event = build(first_seen, None)
                changes.append(Change("added", event))
            elif compare != self._content[key]:
                event = build(old.first_seen_ms, old.event_ms)
                changes.append(Change("updated", event))
            else:
                continue
            self.events[key] = event
            self._content[key] = compare
        for key in [k for k in self.events if k not in current]:
            changes.append(Change("removed", self.events.pop(key)))
            del self._content[key]
        return changes

    # --- building events ------------------------------------------------------------

    def _team(self, side: Side | None) -> dict[str, Any]:
        if side is None or not self.game_info:
            return {}
        return self.game_info.get("homeTeam" if side == "home" else "awayTeam") or {}

    def _event_ms(self, raw_ms: int | None, first_seen: int, key: str) -> int | None:
        if raw_ms is None:
            return None
        if raw_ms > first_seen + MAX_AHEAD_MS or raw_ms < first_seen - MAX_BEHIND_MS:
            log.debug("%s: event_ms %d implausible against first_seen %d", key, raw_ms, first_seen)
            return None
        return raw_ms

    def _entries(
        self, item: dict[str, Any], snapshot: Snapshot
    ) -> dict[str, tuple[Any, Callable[[int, int | None], NormalizedEvent]]]:
        raw_type = str(item.get("type"))
        if raw_type == "period":
            return self._period_entries(item, snapshot)
        if "eventId" not in item:
            return {}
        key = f"e{item['eventId']}"
        typ = RAW_TYPES.get(raw_type)
        if typ is None:
            warn_once("event type", raw_type)
            typ = "unknown"
        team = item.get("eventTeam") or {}
        side: Side | None = team.get("place") if team.get("place") in ("home", "away") else None
        data = self._data(typ, item)
        if typ == "unknown":
            data["raw_type"] = raw_type
        rwt = parse_local_ms(item.get("realWorldTime"))

        def build(first_seen: int, event_ms: int | None) -> NormalizedEvent:
            return NormalizedEvent(
                key=key,
                type=typ,
                raw_type=raw_type,
                event_id=item.get("eventId"),
                game_uuid=item.get("gameUuid"),
                period=item.get("period"),
                time=item.get("time"),
                game_seconds=game_seconds(item.get("period"), item.get("time")),
                side=side,
                team_uuid=self._team(side).get("uuid"),
                team_code=team.get("teamCode"),
                player=player(item.get("player")),
                data=data,
                revision=item.get("revision"),
                event_ms=event_ms if event_ms is not None else self._event_ms(rwt, first_seen, key),
                first_seen_ms=first_seen,
                received_ms=snapshot.received_ms,
            )

        return {key: (content(item), build)}

    def _data(self, typ: str, item: dict[str, Any]) -> dict[str, Any]:
        if typ == "goal":
            status = item.get("goalStatus")
            if status not in KNOWN_GOAL_STATUSES:
                warn_once("goalStatus", status)
            assists = item.get("assists") or {}
            return {
                "score": {"home": item.get("homeGoals"), "away": item.get("awayGoals")},
                "strength": status,
                "empty_net": bool(item.get("isEmptyNetGoal")),
                "penalty_shot": bool(item.get("isPenaltyShot")),
                "shootout": item.get("period") == "shootout",
                "assists": [
                    p.model_dump() for k in ("first", "second") if (p := player(assists.get(k)))
                ],
                "on_ice": players(item.get("pop")),
                "opponents_on_ice": players(item.get("nep")),
                "scorer_game_goals": self._game_goals.get(item.get("eventId")),
                # player.statistics G is the season's goals after this one, not the game's
                # (checked 2026-10-21 against the 2026-10-20 recording)
                "scorer_season_goals": stat(item.get("player"), "G"),
                "x_dm": item.get("locationX"),
                "y_dm": item.get("locationY"),
                "goal_section": item.get("goalSection"),
            }
        if typ == "shot":
            section = item.get("goalSection")
            return {
                "x_dm": item.get("locationX"),
                "y_dm": item.get("locationY"),
                "goal_section": section,
                "on_goal": section in ON_GOAL_SECTIONS,
                "result": shot_result(section),
                "penalty_shot": bool(item.get("isPenaltyShot")),
            }
        if typ == "penalty":
            code = item.get("offence")
            variant = parse_variant(item.get("variant"), code)
            raw_variant = item.get("variant") or {}
            return {
                "offence_code": code,
                "offence_text": offence_text(code),
                "minutes": variant.minutes,
                "kind": variant.kind,
                "segments_s": list(variant.segments_s),
                "variant": raw_variant.get("shortName"),
                "description": raw_variant.get("description"),
                "penalty_shot_awarded": bool(item.get("didRenderInPenaltyShot")),
                "team_penalty": not item.get("player"),
            }
        if typ == "goalie_change":
            return {"entering": bool(item.get("isEntering"))}
        if typ == "shootout_attempt":
            score = item.get("shootoutScore") or {}
            return {
                "scored": bool(item.get("isGoal")),
                "index": item.get("shootoutIndex"),
                "shootout_score": {"home": score.get("homeGoals"), "away": score.get("awayGoals")},
                "game_winning": bool(item.get("isGameWinningGoal")),
            }
        return {}

    def _period_entries(
        self, item: dict[str, Any], snapshot: Snapshot
    ) -> dict[str, tuple[Any, Callable[[int, int | None], NormalizedEvent]]]:
        period = item.get("period")
        entries: dict[str, tuple[Any, Callable[[int, int | None], NormalizedEvent]]] = {}
        for typ, flag, field in (
            ("period_start", "started", "startedAt"),
            ("period_end", "finished", "finishedAt"),
        ):
            if not item.get(flag):
                continue
            key = f"period-{period}-{typ.removeprefix('period_')}"
            raw_ms = parse_local_ms(item.get(field))

            def build(
                first_seen: int,
                event_ms: int | None,
                key: str = key,
                typ: str = typ,
                raw_ms: int | None = raw_ms,
            ) -> NormalizedEvent:
                ms = event_ms if event_ms is not None else self._event_ms(raw_ms, first_seen, key)
                data: dict[str, Any] = {}
                if typ == "period_end" and ms is not None:
                    data["next_period_estimate_ms"] = ms + NEXT_PERIOD_ESTIMATE_MS
                return NormalizedEvent(
                    key=key,
                    type=typ,
                    raw_type="period",
                    game_uuid=item.get("gameUuid"),
                    period=period,
                    data=data,
                    event_ms=ms,
                    first_seen_ms=first_seen,
                    received_ms=snapshot.received_ms,
                )

            entries[key] = ((period, item.get(field)), build)
        return entries

    def _game_end(
        self, pbp: list[dict[str, Any]], snapshot: Snapshot
    ) -> tuple[Any, Callable[[int, int | None], NormalizedEvent]]:
        goals = [e for e in pbp if isinstance(e, dict) and e.get("type") == "goal"]
        latest = max(goals, key=lambda e: e.get("eventId", 0)) if goals else {}
        final = {"home": latest.get("homeGoals", 0), "away": latest.get("awayGoals", 0)}
        periods = [e for e in pbp if isinstance(e, dict) and e.get("type") == "period"]
        overtime = any(isinstance(p.get("period"), int) and p["period"] > 3 for p in periods)
        shootout = any(p.get("period") == "shootout" for p in periods)
        ends = [ms for p in periods if (ms := parse_local_ms(p.get("finishedAt"))) is not None]
        raw_ms = max(ends) if ends else None
        data = {"final": final, "overtime": overtime, "shootout": shootout}

        def build(first_seen: int, event_ms: int | None) -> NormalizedEvent:
            return NormalizedEvent(
                key="game-end",
                type="game_end",
                raw_type="gameState",
                game_uuid=(self.game_info or {}).get("gameInfo", {}).get("gameUuid"),
                data=data,
                event_ms=event_ms
                if event_ms is not None
                else self._event_ms(raw_ms, first_seen, "game-end"),
                first_seen_ms=first_seen,
                received_ms=snapshot.received_ms,
            )

        return (data, build)
