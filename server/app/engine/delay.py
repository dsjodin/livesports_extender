"""DelayQueue: decides when each normalized event plays (CLAUDE.md rules 1 and 2).

``play_at = max(event_ms + offset_ms, received_ms + lead_ms)``

- ``event_ms`` is the on-ice moment and ``offset_ms`` how far the TV lags the arena, so
  the first term lines the event up with the TV.
- ``received_ms`` is when the snapshot that first contained the event arrived. The second
  term is the earliest we can play it while still giving clients ``lead_ms`` to prepare;
  when it wins the event is ``late`` (it reached us after the TV showed it). We use
  ``received_ms`` rather than ``first_seen_ms`` (= received − Age): with a 9 s Age the
  latter would put ``play_at`` in the past.
- Without a plausible ``event_ms`` the event plays at ``received_ms + lead_ms``, ``late``.

Items are handed out (``due``) ``lead_ms`` before ``play_at``. The queue is pure: callers
pass the current time.
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

from app.engine.events import Change, NormalizedEvent

log = logging.getLogger(__name__)

DEFAULT_LEAD_MS = 1500


@dataclass(slots=True)
class Planned:
    event: NormalizedEvent
    received_ms: int  # when the event first reached us
    play_at: int
    late: bool
    late_by_ms: int | None
    order: tuple[int, int, int]
    released: bool = False


OutputKind = Literal["release", "update", "remove", "reset"]


@dataclass(frozen=True, slots=True)
class Output:
    """``release``: play this event at ``play_at``. ``update``: an already released event
    changed (play the correction at ``play_at``). ``remove``: an already released event
    disappeared. ``reset``: start over (a replay seek)."""

    kind: OutputKind
    play_at: int
    event: NormalizedEvent | None = None
    late: bool = False
    late_by_ms: int | None = None


def _order(e: NormalizedEvent) -> tuple[int, int, int]:
    period = e.period if isinstance(e.period, int) else 99
    return (period, e.game_seconds if e.game_seconds is not None else -1, e.event_id or 0)


@dataclass
class DelayQueue:
    offset_ms: int
    lead_ms: int = DEFAULT_LEAD_MS
    items: dict[str, Planned] = field(default_factory=dict)
    _warned_no_event_ms: bool = False

    def plan(self, event: NormalizedEvent, received_ms: int) -> tuple[int, bool, int | None]:
        earliest = received_ms + self.lead_ms
        if event.event_ms is None:
            if not self._warned_no_event_ms:
                self._warned_no_event_ms = True
                log.warning("%s has no plausible event_ms; playing it as late", event.key)
            return earliest, True, None
        synced = event.event_ms + self.offset_ms
        if synced >= earliest:
            return synced, False, None
        return earliest, True, earliest - synced

    def apply(self, changes: list[Change], now_ms: int) -> list[Output]:
        """Take normalizer changes. Returns corrections to already released events."""
        out: list[Output] = []
        for change in changes:
            if change.kind == "reset":
                self.items.clear()
                out.append(Output("reset", now_ms))
                continue
            event = change.event
            if event is None:
                continue
            planned = self.items.get(event.key)
            if change.kind == "added":
                play_at, late, late_by = self.plan(event, event.received_ms)
                self.items[event.key] = Planned(
                    event, event.received_ms, play_at, late, late_by, _order(event)
                )
            elif change.kind == "updated" and planned is not None:
                planned.event = event
                planned.order = _order(event)
                if planned.released:
                    out.append(Output("update", now_ms + self.lead_ms, event))
            elif change.kind == "removed" and planned is not None:
                del self.items[event.key]
                if planned.released:
                    out.append(Output("remove", now_ms + self.lead_ms, planned.event))
        return out

    def due(self, now_ms: int) -> list[Output]:
        """Release every pending event whose ``play_at - lead_ms`` has come, in play order."""
        ready = [
            p for p in self.items.values() if not p.released and p.play_at - self.lead_ms <= now_ms
        ]
        ready.sort(key=lambda p: (p.play_at, p.order))
        for p in ready:
            p.released = True
        return [Output("release", p.play_at, p.event, p.late, p.late_by_ms) for p in ready]

    def next_due_ms(self) -> int | None:
        """When ``due`` will next have something to hand out."""
        pending = [p.play_at - self.lead_ms for p in self.items.values() if not p.released]
        return min(pending) if pending else None

    def set_offset(self, offset_ms: int) -> None:
        """Re-plan everything not yet released; released events keep their time."""
        self.offset_ms = offset_ms
        for p in self.items.values():
            if not p.released:
                p.play_at, p.late, p.late_by_ms = self.plan(p.event, p.received_ms)

    def released(self) -> list[Planned]:
        return sorted((p for p in self.items.values() if p.released), key=lambda p: p.play_at)

    def pending(self) -> list[Planned]:
        return sorted((p for p in self.items.values() if not p.released), key=lambda p: p.play_at)
