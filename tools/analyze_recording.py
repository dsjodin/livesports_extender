"""Analyse a recording made by record_game.py and write report.md next to it.

Usage (from the repo root): uv run --project server python tools/analyze_recording.py <dir>
"""

import argparse
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")
MISSED_GOAL_SECTIONS = {-3}  # the original assumption ("rule A"), see docs/SHL_API.md
# Copied onto every event and changed at each period boundary; not a content change.
IGNORED_FIELDS = {"gameState", "attendance", "updatedTime"}

Key = tuple[str, Any]


def parse_local_ms(value: object) -> int | None:
    """A naive (or wrongly ``Z``-marked) timestamp that is really Swedish local time."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.removesuffix("Z"))
    except ValueError:
        return None
    return int(dt.replace(tzinfo=STOCKHOLM).timestamp() * 1000)


def parse_naive_utc_ms(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.removesuffix("Z"))
    except ValueError:
        return None
    return int(dt.replace(tzinfo=UTC).timestamp() * 1000)


def fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "–"
    return datetime.fromtimestamp(ms / 1000, STOCKHOLM).strftime("%H:%M:%S.%f")[:-5]


def fmt_s(ms: float | None) -> str:
    return "–" if ms is None else f"{ms / 1000:+.1f}"


def event_key(item: dict[str, Any]) -> Key:
    if "eventId" in item:
        return ("e", item["eventId"])
    return ("period", item.get("period"))


def describe(item: dict[str, Any]) -> str:
    team = (item.get("eventTeam") or {}).get("teamCode", "")
    return f"{item.get('type')} P{item.get('period')} {item.get('time', '')} {team}".strip()


def diff_paths(old: Any, new: Any, prefix: str = "") -> list[str]:
    """Dotted paths whose values differ between two JSON values."""
    if isinstance(old, dict) and isinstance(new, dict):
        paths: list[str] = []
        for k in sorted(set(old) | set(new), key=str):
            paths += diff_paths(old.get(k), new.get(k), f"{prefix}{k}.")
        return paths
    return [] if old == new else [prefix.rstrip(".") or "(value)"]


def content(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in IGNORED_FIELDS}


def iter_rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


@dataclass
class Tracked:
    first_seen_ms: int
    first_available_ms: int  # received_ms − Age, or received_ms without an Age header
    first: dict[str, Any]
    last: dict[str, Any]
    changes: list[tuple[int, Any, list[str]]] = field(default_factory=list)
    started_seen_ms: int | None = None
    finished_seen_ms: int | None = None


@dataclass
class Analysis:
    rows: int = 0
    first_ms: int | None = None
    last_ms: int | None = None
    requests: Counter[str] = field(default_factory=Counter)
    statuses: Counter[tuple[str, Any]] = field(default_factory=Counter)
    errors: Counter[tuple[str, str]] = field(default_factory=Counter)
    ages: list[int] = field(default_factory=list)
    info_states: dict[str, int] = field(default_factory=dict)
    pbp_states: dict[str, int] = field(default_factory=dict)
    events: dict[Key, Tracked] = field(default_factory=dict)
    removed: list[tuple[Key, str, int, int]] = field(default_factory=list)  # key, desc, last, gone
    reappeared: list[tuple[Key, int]] = field(default_factory=list)
    final_pbp: list[dict[str, Any]] = field(default_factory=list)
    final_info: dict[str, Any] | None = None
    boxscore: dict[str, Any] | None = None


def analyse(rows: Iterable[dict[str, Any]]) -> Analysis:
    a = Analysis()
    present: dict[Key, int] = {}  # key -> last poll it was seen in
    ever_removed: set[Key] = set()
    for row in rows:
        a.rows += 1
        ms = row["received_ms"]
        a.first_ms = ms if a.first_ms is None else a.first_ms
        a.last_ms = ms
        endpoint = row["endpoint"]
        a.requests[endpoint] += 1
        a.statuses[(endpoint, row.get("status"))] += 1
        if row.get("error"):
            a.errors[(endpoint, str(row["error"]).split(":")[0])] += 1
        age = row.get("age")
        if endpoint == "play-by-play" and isinstance(age, int):
            a.ages.append(age)
        available = ms - age * 1000 if isinstance(age, int) else ms
        body = row.get("body")
        if row.get("status") != 200 or body is None:
            if endpoint == "play-by-play" and row.get("status") == 200:
                for key in present:
                    present[key] = ms
            continue
        if endpoint == "game-info" and isinstance(body, dict):
            a.final_info = body
            raw = (body.get("gameInfo") or {}).get("state")
            if isinstance(raw, str):
                a.info_states.setdefault(raw, ms)
        elif endpoint == "boxscore" and isinstance(body, dict):
            a.boxscore = body
        elif endpoint == "play-by-play" and isinstance(body, list):
            a.final_pbp = body
            seen: set[Key] = set()
            for item in body:
                if not isinstance(item, dict):
                    continue
                key = event_key(item)
                seen.add(key)
                state = item.get("gameState")
                if isinstance(state, str):
                    a.pbp_states.setdefault(state, ms)
                tracked = a.events.get(key)
                if tracked is None:
                    tracked = a.events[key] = Tracked(ms, available, item, item)
                else:
                    paths = diff_paths(content(tracked.last), content(item))
                    if paths:
                        tracked.changes.append((ms, item.get("revision"), paths))
                    tracked.last = item
                if item.get("type") == "period":
                    if item.get("started") and tracked.started_seen_ms is None:
                        tracked.started_seen_ms = ms
                    if item.get("finished") and tracked.finished_seen_ms is None:
                        tracked.finished_seen_ms = ms
                if key in ever_removed and key not in present:
                    a.reappeared.append((key, ms))
                present[key] = ms
            for key in [k for k in present if k not in seen]:
                a.removed.append((key, describe(a.events[key].last), present.pop(key), ms))
                ever_removed.add(key)
    return a


def summary(values: list[int]) -> str:
    if not values:
        return "– | – | –"
    return f"{fmt_s(min(values))} | {fmt_s(statistics.median(values))} | {fmt_s(max(values))}"


def boxscore_shots(box: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Shots on goal per side from the boxscore: skater SOG sum and opposing goalie SOGA."""
    out: dict[str, dict[str, int]] = {}
    stats = box.get("stats") or {}
    goalies = box.get("gkStats") or {}
    for side, value_key in (("home", "homeTeamValue"), ("away", "awayTeamValue")):
        other = "awayTeamValue" if side == "home" else "homeTeamValue"
        out[side] = {
            "skater_sog": sum(int(p.get("SOG") or 0) for p in stats.get(value_key, [])),
            "opposing_goalie_soga": sum(int(g.get("SOGA") or 0) for g in goalies.get(other, [])),
        }
    return out


def render(a: Analysis, name: str, synthetic: bool) -> str:
    out: list[str] = [f"# Recording report: {name}", ""]
    if synthetic:
        out += [
            "> **Synthetic recording** built from fixtures by `tools/synth_recording.py`.",
            "> Receive times, game states and revisions are simulated; only the event",
            "> content is real. Do not draw latency conclusions from it.",
            "",
        ]
    info = (a.final_info or {}).get("gameInfo") or {}
    home = (a.final_info or {}).get("homeTeam") or {}
    away = (a.final_info or {}).get("awayTeam") or {}
    out += [
        f"- Game: `{info.get('gameUuid', '?')}`, {home.get('names', {}).get('code', '?')}–"
        f"{away.get('names', {}).get('code', '?')}, last score "
        f"{home.get('score', '?')}–{away.get('score', '?')}",
        f"- Recorded {fmt_ms(a.first_ms)} to {fmt_ms(a.last_ms)} (Europe/Stockholm), {a.rows} rows",
        "- Requests: " + ", ".join(f"{k} {v}" for k, v in sorted(a.requests.items())),
        "- Statuses: "
        + ", ".join(f"{e} {s}: {n}" for (e, s), n in sorted(a.statuses.items(), key=str)),
        "- Errors: "
        + (", ".join(f"{e} {kind}: {n}" for (e, kind), n in sorted(a.errors.items())) or "none"),
        "- Age header on play-by-play: "
        + (
            f"{len(a.ages)} polls, min {min(a.ages)} / median {statistics.median(a.ages):g}"
            f" / max {max(a.ages)} s"
            if a.ages
            else "not recorded"
        ),
        "",
        "## Game states",
        "",
        "| Source | Value | First seen |",
        "|---|---|---|",
    ]
    out += [
        f"| game-info `gameInfo.state` | `{v}` | {fmt_ms(t)} |" for v, t in a.info_states.items()
    ]
    out += [f"| play-by-play `gameState` | `{v}` | {fmt_ms(t)} |" for v, t in a.pbp_states.items()]

    out += _delay_section(a, "received_ms", lambda t: t.first_seen_ms)
    if a.ages:
        out += _delay_section(a, "received_ms − Age", lambda t: t.first_available_ms)

    out += ["", "## Revisions and changes", ""]
    changed = [(k, t) for k, t in a.events.items() if t.changes]
    if not changed:
        out.append("No event changed after it first appeared.")
    else:
        out += ["| Event | Seen | Revision | Changed fields |", "|---|---|---|---|"]
        for key, t in changed:
            out.append(
                f"| {key[1]} {describe(t.first)} | {fmt_ms(t.first_seen_ms)} | "
                f"{t.first.get('revision')} (first) | |"
            )
            for ms, rev, paths in t.changes:
                out.append(f"| | {fmt_ms(ms)} | {rev} | {', '.join(f'`{p}`' for p in paths)} |")
    out += ["", "## Disappeared events", ""]
    if not a.removed:
        out.append("No event disappeared.")
    else:
        out += ["| Event | Last seen | Gone at |", "|---|---|---|"]
        out += [
            f"| {k[1]} {d} | {fmt_ms(last)} | {fmt_ms(gone)} |" for k, d, last, gone in a.removed
        ]
    if a.reappeared:
        out += ["", "Reappeared: " + ", ".join(f"{k[1]} at {fmt_ms(ms)}" for k, ms in a.reappeared)]

    final = [e for e in a.final_pbp if isinstance(e, dict)]
    values: dict[str, Counter[Any]] = {
        "type": Counter(e.get("type") for e in final),
        "goalStatus": Counter(e["goalStatus"] for e in final if "goalStatus" in e),
        "offence": Counter(e["offence"] for e in final if "offence" in e),
        "variant.shortName": Counter(
            (e.get("variant") or {}).get("shortName") for e in final if "variant" in e
        ),
        "goalSection": Counter(e["goalSection"] for e in final if "goalSection" in e),
    }
    out += [
        "",
        "## Distinct values (final play-by-play)",
        "",
        "| Field | Values (count) |",
        "|---|---|",
    ]
    for fld, counter in values.items():
        listed = ", ".join(
            f"`{v}` ({n})" for v, n in sorted(counter.items(), key=lambda x: str(x[0]))
        )
        out.append(f"| `{fld}` | {listed or '–'} |")

    out += _shots_section(final, a.boxscore)
    out += _periods_section(a)
    return "\n".join(out) + "\n"


def _delay_section(a: Analysis, label: str, seen: Any) -> list[str]:
    by_type: dict[str, tuple[list[int], list[int]]] = defaultdict(lambda: ([], []))
    for key, t in a.events.items():
        if key[0] != "e":
            continue
        rwt = parse_local_ms(t.first.get("realWorldTime"))
        upd = parse_naive_utc_ms(t.first.get("updatedTime"))
        delays = by_type[str(t.first.get("type"))]
        if rwt is not None:
            delays[0].append(seen(t) - rwt)
        if upd is not None:
            delays[1].append(seen(t) - upd)
    out = [
        "",
        f"## Delay to first sight, per event type (to `{label}`)",
        "",
        "Seconds from the event's first-seen `realWorldTime` (parsed as Europe/Stockholm) and",
        f"`updatedTime` (parsed as UTC) to `{label}` of the first poll that contained it.",
        "",
        "| Type | n | realWorldTime min | median | max | updatedTime min | median | max |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for typ, (rw, up) in sorted(by_type.items()):
        out.append(f"| {typ} | {max(len(rw), len(up))} | {summary(rw)} | {summary(up)} |")
    return out


def _on_goal_1_to_9(section: object) -> bool:
    return isinstance(section, int) and 1 <= section <= 9


def _shots_section(final: list[dict[str, Any]], box: dict[str, Any] | None) -> list[str]:
    """Regulation and overtime shots; shootout attempts (period "shootout") are left out."""
    shots = [
        e for e in final if e.get("type") in ("shot", "goal") and isinstance(e.get("period"), int)
    ]
    teams: dict[str, str] = {}
    by_section: dict[str, Counter[Any]] = defaultdict(Counter)
    for e in shots:
        team = e.get("eventTeam") or {}
        side = str(team.get("place"))
        teams[side] = str(team.get("teamCode"))
        by_section[side][e.get("goalSection")] += 1
    sections = sorted({s for c in by_section.values() for s in c}, key=lambda v: (str(type(v)), v))
    out = [
        "",
        "## Shots by `goalSection` (types `shot` and `goal`, shootout excluded)",
        "",
        "| Team | " + " | ".join(f"`{s}`" for s in sections) + " | all | on goal A | on goal B |",
        "|---|" + "---|" * (len(sections) + 3),
    ]
    rule_a: dict[str, int] = {}
    rule_b: dict[str, int] = {}
    for side in ("home", "away"):
        c = by_section.get(side, Counter())
        rule_a[side] = sum(n for s, n in c.items() if s not in MISSED_GOAL_SECTIONS)
        rule_b[side] = sum(n for s, n in c.items() if _on_goal_1_to_9(s))
        cells = " | ".join(str(c.get(s, 0)) for s in sections)
        label = f"{teams.get(side, side)} ({side})"
        out.append(f"| {label} | {cells} | {sum(c.values())} | {rule_a[side]} | {rule_b[side]} |")
    out += [
        "",
        f"- A: `goalSection` not in {sorted(MISSED_GOAL_SECTIONS)} (the current assumption).",
        "- B: `goalSection` 1 to 9 (alternative).",
        "",
    ]
    if box is None:
        out.append("No boxscore in the recording.")
        return out
    out += [
        "| Team | A | B | boxscore skater SOG sum | boxscore opposing goalie SOGA | matches |",
        "|---|---|---|---|---|---|",
    ]
    for side, b in boxscore_shots(box).items():
        sog = b["skater_sog"]
        matches = [name for name, v in (("A", rule_a), ("B", rule_b)) if v.get(side) == sog]
        out.append(
            f"| {teams.get(side, side)} | {rule_a.get(side)} | {rule_b.get(side)} | {sog} | "
            f"{b['opposing_goalie_soga']} | {', '.join(matches) or '**none**'} |"
        )
    return out


def _game_time_key(e: dict[str, Any]) -> tuple[int, int]:
    mm, _, ss = str(e.get("time", "0:0")).partition(":")
    try:
        return int(mm), int(ss)
    except ValueError:
        return 0, 0


def _periods_section(a: Analysis) -> list[str]:
    out = [
        "",
        "## Period objects",
        "",
        "`startedAt` / `finishedAt` parsed as local time despite the `Z`. Deltas are the",
        "period object's first-seen time minus the first-seen time of the period's first or",
        "last event (negative: the period object came first).",
        "",
        "| Period | Object first seen | Started seen | `startedAt` | First event (rwt / seen) "
        "| Δ start | Finished seen | `finishedAt` | Last event (rwt / seen) | Δ end |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    periods = [(k, t) for k, t in a.events.items() if k[0] == "period"]
    if not periods:
        return [*out, "| – | | | | | | | | | |"]
    for key, t in periods:
        evs = sorted(
            (x for k, x in a.events.items() if k[0] == "e" and x.last.get("period") == key[1]),
            key=lambda x: _game_time_key(x.last),
        )
        first, last = (evs[0], evs[-1]) if evs else (None, None)
        d_start = (t.started_seen_ms - first.first_seen_ms) if first and t.started_seen_ms else None
        d_end = (t.finished_seen_ms - last.first_seen_ms) if last and t.finished_seen_ms else None

        def ev(x: Tracked | None) -> str:
            if x is None:
                return "–"
            rwt = fmt_ms(parse_local_ms(x.first.get("realWorldTime")))
            return f"{x.last.get('time')} {x.last.get('type')}: {rwt} / {fmt_ms(x.first_seen_ms)}"

        out.append(
            f"| {key[1]} | {fmt_ms(t.first_seen_ms)} | {fmt_ms(t.started_seen_ms)} | "
            f"{fmt_ms(parse_local_ms(t.last.get('startedAt')))} | {ev(first)} | {fmt_s(d_start)} | "
            f"{fmt_ms(t.finished_seen_ms)} | {fmt_ms(parse_local_ms(t.last.get('finishedAt')))} | "
            f"{ev(last)} | {fmt_s(d_end)} |"
        )
    return out


def write_report(directory: Path) -> Path:
    meta_path = directory / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    analysis = analyse(iter_rows(directory / "polls.jsonl"))
    report = directory / "report.md"
    report.write_text(
        render(analysis, directory.name, bool(meta.get("synthetic"))), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory containing polls.jsonl")
    args = parser.parse_args()
    print(write_report(args.directory))


if __name__ == "__main__":
    main()
