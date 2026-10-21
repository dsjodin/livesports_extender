"""Calibration from "Synka" presses: how far the TV lags the arena (docs/PLAN.md, Phase 4).

The user presses when an event is seen on TV and says what it was. A press matches the
raw event of that kind (and side, if given) whose ``event_ms`` lies 5–150 s before the
press. The feed can be slower than the TV, so a press without a match stays pending
for up to 150 s and is re-checked as events arrive; after that its status is final.
Two or more candidates make it ambiguous. Sample = press − ``event_ms`` − reaction time.
Proposal = median of the last 5 matched samples. Pure: callers pass times and events.
"""

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.engine.events import NormalizedEvent, Side

REACTION_MS = 300
MIN_BEFORE_MS = 5_000
WINDOW_MS = 150_000
PROPOSAL_SAMPLES = 5

Kind = Literal["period_start", "goal", "penalty", "timeout", "shot_on_goal"]
KINDS: tuple[str, ...] = ("period_start", "goal", "penalty", "timeout", "shot_on_goal")
Status = Literal["pending", "matched", "ambiguous", "unmatched"]


def matches_kind(event: NormalizedEvent, kind: str) -> bool:
    if kind == "shot_on_goal":
        return event.type == "shot" and event.data.get("result") == "on_goal"
    if kind == "goal":
        return event.type == "goal" and not event.data.get("shootout")
    return event.type == kind


@dataclass
class Press:
    id: str
    kind: str
    pressed_ms: int
    side: Side | None = None
    source: str = "sync"  # "sync" or "goal_button"
    status: Status = "pending"
    event_key: str | None = None
    event_ms: int | None = None
    candidates: int = 0

    @property
    def sample_ms(self) -> int | None:
        if self.status != "matched" or self.event_ms is None:
            return None
        return self.pressed_ms - self.event_ms - REACTION_MS

    def as_dict(self) -> dict[str, Any]:
        sample = self.sample_ms
        return {
            "id": self.id,
            "kind": self.kind,
            "side": self.side,
            "source": self.source,
            "pressed_ms": self.pressed_ms,
            "status": self.status,
            "event_key": self.event_key,
            "event_ms": self.event_ms,
            "sample_s": None if sample is None else round(sample / 1000, 1),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Press":
        return cls(
            id=str(d["id"]),
            kind=str(d["kind"]),
            pressed_ms=int(d["pressed_ms"]),
            side=d.get("side"),
            source=str(d.get("source", "sync")),
            status=d.get("status", "pending"),
            event_key=d.get("event_key"),
            event_ms=d.get("event_ms"),
        )


@dataclass
class Calibrator:
    presses: list[Press] = field(default_factory=list)
    _next: int = 1

    @classmethod
    def from_saved(cls, saved: Iterable[dict[str, Any]]) -> "Calibrator":
        presses = [Press.from_dict(d) for d in saved]
        numbers = [int(p.id[1:]) for p in presses if p.id[1:].isdigit()]
        return cls(presses, max(numbers, default=0) + 1)

    def press(
        self,
        kind: str,
        pressed_ms: int,
        side: Side | None,
        events: Iterable[NormalizedEvent],
        *,
        source: str = "sync",
    ) -> Press:
        if kind not in KINDS:
            raise ValueError(f"unknown calibration kind {kind!r}")
        press = Press(f"s{self._next}", kind, pressed_ms, side, source)
        self._next += 1
        self.presses.append(press)
        self._check(press, list(events), pressed_ms)
        return press

    def add_sample(
        self, kind: str, pressed_ms: int, side: Side | None, event: NormalizedEvent
    ) -> Press:
        """A press already tied to one event (the MÅL! button linked to a feed goal)."""
        press = Press(f"s{self._next}", kind, pressed_ms, side, "goal_button")
        self._next += 1
        press.status, press.event_key, press.event_ms = "matched", event.key, event.event_ms
        press.candidates = 1
        self.presses.append(press)
        return press

    def update(self, events: Iterable[NormalizedEvent], now_ms: int) -> bool:
        """Re-check unsettled presses against the current raw events. True if any changed."""
        evs = list(events)
        changed = False
        for press in self.presses:
            if press.source == "sync" and now_ms - press.pressed_ms <= WINDOW_MS + MIN_BEFORE_MS:
                before = (press.status, press.event_key)
                self._check(press, evs, now_ms)
                changed |= before != (press.status, press.event_key)
            elif press.status == "pending":
                press.status = "unmatched"
                changed = True
        return changed

    def _check(self, press: Press, events: list[NormalizedEvent], now_ms: int) -> None:
        candidates = [
            e
            for e in events
            if matches_kind(e, press.kind)
            and (press.side is None or e.side == press.side)
            and e.event_ms is not None
            and press.pressed_ms - WINDOW_MS <= e.event_ms <= press.pressed_ms - MIN_BEFORE_MS
        ]
        press.candidates = len(candidates)
        if len(candidates) == 1:
            press.status, press.event_key = "matched", candidates[0].key
            press.event_ms = candidates[0].event_ms
        elif len(candidates) > 1:
            press.status, press.event_key, press.event_ms = "ambiguous", None, None
        elif press.status == "matched":
            return  # its event went away (a replay seek): keep what was measured
        else:
            press.event_key = press.event_ms = None
            settled = now_ms - press.pressed_ms > WINDOW_MS
            press.status = "unmatched" if settled else "pending"

    def remove(self, press_id: str) -> bool:
        before = len(self.presses)
        self.presses = [p for p in self.presses if p.id != press_id]
        return len(self.presses) != before

    def clear(self) -> None:
        self.presses = []

    def proposal_ms(self) -> int | None:
        samples = [s for p in self.presses if (s := p.sample_ms) is not None]
        recent = samples[-PROPOSAL_SAMPLES:]
        return round(statistics.median(recent)) if recent else None

    def matched_count(self) -> int:
        return min(PROPOSAL_SAMPLES, sum(1 for p in self.presses if p.sample_ms is not None))
