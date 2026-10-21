"""The evening's other games: their feed, delayed like ours, summed up for the screens.

Each other game has its own Normalizer and DelayQueue with the same offset as our game
(CLAUDE.md rules 1 and 5), so a goal elsewhere reaches the wall at its on-ice moment plus
the TV delay. Nothing about them is celebrated: a released event only changes the
summary (score, period, shots), which goes into the TV state as ``others``. Pure: callers
pass snapshots and times.
"""

from dataclasses import dataclass, field
from typing import Any

from app.engine.delay import DelayQueue, Output
from app.engine.events import NormalizedEvent
from app.engine.normalizer import Normalizer
from app.engine.state import compute_state
from app.feed.snapshot import Snapshot

PERIOD_S = 1200


def clock_text(seconds: int | None, period: object) -> str | None:
    if seconds is None or not isinstance(period, int):
        return None
    within = seconds - (period - 1) * PERIOD_S
    return f"{within // 60:02d}:{within % 60:02d}"


@dataclass
class OtherGame:
    uuid: str
    start_ms: int | None
    teams: dict[str, dict[str, Any]]  # side -> uuid, code, short, long, logo, color
    offset_ms: int
    lead_ms: int
    normalizer: Normalizer = field(default_factory=Normalizer)
    queue: DelayQueue = field(init=False)
    released: dict[str, NormalizedEvent] = field(default_factory=dict)
    _catching_up: bool = True

    def __post_init__(self) -> None:
        self.queue = DelayQueue(self.offset_ms, self.lead_ms)

    def apply(self, snapshot: Snapshot, now_ms: int) -> bool:
        """Take a poll. True if the summary changed at once (a catch-up or a reset)."""
        changes = self.normalizer.apply(snapshot)
        changed = False
        for out in self.queue.apply(changes, now_ms):
            if out.kind == "reset":
                self.released.clear()
                self._catching_up = True
                changed = True
            elif out.kind == "remove" and out.event is not None:
                changed |= self.released.pop(out.event.key, None) is not None
            elif out.kind == "update" and out.event is not None:
                self.released[out.event.key] = out.event
                changed = True
        if self._catching_up and snapshot.pbp is not None:
            # what has already happened (on TV time) is there at once, as for our game
            self._catching_up = False
            for out in self.queue.backlog():
                if out.event is not None:
                    self.released[out.event.key] = out.event
                    changed = True
        return changed

    def due(self, horizon_ms: int) -> list[Output]:
        """Events whose play_at is within ``horizon_ms``; the caller releases them in
        play_at order with ``release``."""
        return self.queue.due(horizon_ms)

    def release(self, event: NormalizedEvent) -> None:
        self.released[event.key] = event

    def set_offset(self, offset_ms: int) -> None:
        self.offset_ms = offset_ms
        self.queue.set_offset(offset_ms)

    def summary(self) -> dict[str, Any]:
        events = sorted(self.released.values(), key=lambda e: e.received_ms)
        st = compute_state(events, None, None)
        stats = {
            side: {
                "shots_on_goal": st.stats[side].shots_on_goal,
                "pim": st.stats[side].pim,
                "pp": {"goals": st.stats[side].pp_goals, "chances": st.stats[side].pp_chances},
            }
            for side in ("home", "away")
        }
        goals = [
            {
                "key": g.key,
                "side": g.side,
                "period": g.period,
                "time": g.time,
                "number": g.player.number if g.player else None,
                "last": g.player.last if g.player else None,
                "score": g.data.get("score"),
                "strength": g.data.get("strength"),
            }
            for g in st.goals
        ]
        return {
            "uuid": self.uuid,
            "start_ms": self.start_ms,
            "teams": self.teams,
            "phase": st.phase,
            "period": st.period,
            "period_running": st.period_running,
            "last_game_time": clock_text(st.last_game_seconds, st.period),
            "score": st.score,
            "ended": st.ended,
            "overtime": st.overtime,
            "went_to_shootout": st.went_to_shootout,
            "stats": stats,
            "goals": goals,
        }
