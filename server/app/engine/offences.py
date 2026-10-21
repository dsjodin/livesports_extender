"""Offence codes and penalty variants (docs/SHL_API.md, penalty)."""

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# Text shown on screen: the English names, as Swedish hockey uses them (hooking,
# tripping; decided by the user 2026-10-21). Unknown codes are shown raw and logged once.
OFFENCE_TEXT: dict[str, str] = {
    "TRIP": "Tripping",
    "HOLD": "Holding",
    "CROSS": "Cross-checking",
    "INTRF": "Interference",
    "BOARD": "Boarding",
    "ROUGH": "Roughing",
    "SLASH": "Slashing",
    "FIGHT": "Fighting",
    "HOOK": "Hooking",
    "DELAY": "Delay of game",
    "TOO-M": "Too many men",
    "P-SHOT": "Penalty shot",
}

MINOR_S = 120
MAJOR_S = 300

_warned: set[str] = set()


def offence_text(code: str | None) -> str:
    if not code:
        return ""
    if code in OFFENCE_TEXT:
        return OFFENCE_TEXT[code]
    if code not in _warned:
        _warned.add(code)
        log.warning("unknown offence code %r, shown raw", code)
    return code


def _minutes(variant: dict[str, Any], key: str) -> int:
    try:
        return int(variant.get(key) or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True, slots=True)
class PenaltyVariant:
    kind: str  # minor, double_minor, major, bench_minor, misconduct, ... joined with "+"
    minutes: int  # penalty minutes (PIM), all parts summed
    segments_s: tuple[int, ...]  # shorthanded time, served in order


# (variant field, kind name, shorthanded segments)
_PARTS: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("minorTime", "minor", (MINOR_S,)),
    ("benchTime", "bench_minor", (MINOR_S,)),
    ("doubleMinorTime", "double_minor", (MINOR_S, MINOR_S)),
    ("majorTime", "major", (MAJOR_S,)),
    ("mPTime", "match", (MAJOR_S,)),  # assumption: a match penalty is 5 min shorthanded
    ("misconductTime", "misconduct", ()),
    ("gMTime", "game_misconduct", ()),
)


def parse_variant(variant: dict[str, Any] | None, offence: str | None) -> PenaltyVariant:
    """Penalty kind, PIM and shorthanded segments from the feed's ``variant``.

    ``Minor + Major + GM`` gives kind ``minor+major+game_misconduct``, 27 PIM and
    segments (120, 300): the minor is served first, then the major (assumption).
    A penalty shot (``P-SHOT``, empty variant) has no minutes and no segments.
    """
    variant = variant or {}
    kinds: list[str] = []
    segments: list[int] = []
    minutes = 0
    for field, kind, segs in _PARTS:
        value = _minutes(variant, field)
        if value:
            kinds.append(kind)
            segments.extend(segs)
            minutes += value
    if not kinds:
        kinds.append("penalty_shot" if offence == "P-SHOT" else "none")
    return PenaltyVariant("+".join(kinds), minutes, tuple(segments))
