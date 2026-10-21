"""Parsing and formatting of shl.se timestamps (see docs/SHL_API.md, Time zones).

- ``realWorldTime``, ``startDateAndTime``: Swedish local time, no zone.
- ``startedAt`` / ``finishedAt`` (period objects): Swedish local time, wrongly marked ``Z``.
- ``updatedTime``: UTC, no zone.
- game-info ``startDateTime``, schedule ``rawStartDateTime``: UTC, marked ``Z``.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")


def _parse_naive(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.removesuffix("Z")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_local_ms(value: object) -> int | None:
    """A Swedish local timestamp (suffix ``Z`` ignored, it is wrong in this feed)."""
    dt = _parse_naive(value)
    return None if dt is None else int(dt.replace(tzinfo=STOCKHOLM).timestamp() * 1000)


def parse_naive_utc_ms(value: object) -> int | None:
    dt = _parse_naive(value)
    return None if dt is None else int(dt.replace(tzinfo=UTC).timestamp() * 1000)


def parse_utc_ms(value: object) -> int | None:
    """A correctly marked UTC timestamp such as ``2025-09-13T13:15:00.000Z``."""
    return parse_naive_utc_ms(value)


def format_local(ms: int) -> str:
    """Like ``realWorldTime``: ``2025-09-13T17:10:22.536784``."""
    return (
        datetime.fromtimestamp(ms / 1000, STOCKHOLM)
        .replace(tzinfo=None)
        .isoformat(timespec="microseconds")
    )


def format_local_z(ms: int) -> str:
    """Like ``startedAt``: local time with a (wrong) ``Z``, ``2025-09-13T15:14:26.032Z``."""
    local = datetime.fromtimestamp(ms / 1000, STOCKHOLM).replace(tzinfo=None)
    return local.isoformat(timespec="milliseconds") + "Z"


def format_naive_utc(ms: int) -> str:
    """Like ``updatedTime``: ``2025-09-13T15:34:22.161003``."""
    return (
        datetime.fromtimestamp(ms / 1000, UTC)
        .replace(tzinfo=None)
        .isoformat(timespec="microseconds")
    )


def format_utc_z(ms: int) -> str:
    """Like game-info ``startDateTime``: ``2025-09-13T13:15:00.000Z``."""
    utc = datetime.fromtimestamp(ms / 1000, UTC).replace(tzinfo=None)
    return utc.isoformat(timespec="milliseconds") + "Z"
