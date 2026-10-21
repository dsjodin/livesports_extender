"""SceneDirector: one scene for the whole wall, changed at released events' play_at.

Rules from docs/SCREENS.md (Scenes). Pure: callers pass times. The effective scene is
the manual override if any, else a temporary scene (goal, or live with an overlay), else
the base scene (idle, pregame, live, intermission, postgame).
"""

from dataclasses import dataclass, field
from typing import Any

from app.engine.events import NormalizedEvent

GOAL_HOLD_MS = 20_000
POSTGAME_HOLD_MS = 15 * 60_000
OVERLAY_MS = {"penalty": 8_000, "goal_disallowed": 8_000, "timeout": 5_000}
SCENES = ("idle", "pregame", "live", "goal", "intermission", "postgame")


@dataclass(frozen=True)
class Scene:
    name: str
    since_ms: int
    hold_ms: int | None = None
    data: dict[str, Any] = field(default_factory=dict)
    override: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "since_ms": self.since_ms,
            "hold_ms": self.hold_ms,
            "data": self.data,
            "override": self.override,
        }

    def same(self, other: "Scene | None") -> bool:
        return other is not None and (self.name, self.data, self.override) == (
            other.name,
            other.data,
            other.override,
        )


class SceneDirector:
    def __init__(self, at_ms: int = 0) -> None:
        self.base = "idle"
        self._temp: tuple[Scene, int] | None = None  # scene, until
        self._override: tuple[Scene, int | None] | None = None
        self._postgame_until: int | None = None
        self.current = Scene("idle", at_ms)

    # --- inputs ---------------------------------------------------------------------

    def set_game(self, selected: bool, at: int) -> list[Scene]:
        """A game was selected (or cleared). Only moves between idle and pregame."""
        out = self.advance(at)
        if self.base in ("idle", "pregame"):
            self.base = "pregame" if selected else "idle"
        if not selected:
            self.base, self._temp, self._postgame_until = "idle", None, None
        return out + self._emit(at)

    def reset(self, selected: bool, at: int) -> list[Scene]:
        """Start over (a replay seek)."""
        self.base = "pregame" if selected else "idle"
        self._temp = None
        self._postgame_until = None
        return self._emit(at)

    def on_event(self, event: NormalizedEvent, at: int) -> list[Scene]:
        out = self.advance(at)
        t = event.type
        if t == "period_start":
            self.base = "live"
            self._temp = None
        elif t == "period_end":
            self.base = "intermission"
            if self._temp and self._temp[0].name == "live":
                self._temp = None
        elif t == "game_end":
            self.base = "postgame"
            self._postgame_until = at + POSTGAME_HOLD_MS
            if self._temp and self._temp[0].name == "live":
                self._temp = None
        elif t == "goal" and isinstance(event.period, int):
            self._goal({"event_key": event.key, "side": event.side}, at)
        elif t in OVERLAY_MS:
            overlay_ok = self.base == "live" and (
                self._temp is None or self._temp[0].name == "live" or t == "goal_disallowed"
            )
            if overlay_ok:
                hold = OVERLAY_MS[t]
                data = {"overlay": t, "event_key": event.key, "side": event.side}
                self._temp = (Scene("live", at, hold, data), at + hold)
        return out + self._emit(at)

    def _goal(self, data: dict[str, Any], at: int) -> None:
        self._temp = (Scene("goal", at, GOAL_HOLD_MS, data), at + GOAL_HOLD_MS)

    def manual_goal(self, key: str, side: str, at: int, extra: dict[str, Any]) -> list[Scene]:
        """The MÅL! button (or a test goal): the goal scene at once, team only."""
        out = self.advance(at)
        self._goal({"event_key": key, "side": side, **extra}, at)
        return out + self._emit(at)

    def relink(self, manual_key: str, event: NormalizedEvent, at: int) -> list[Scene]:
        """The feed goal behind a MÅL! press plays: if that press's goal scene is still on,
        it takes the feed goal's key (scorer and score fill in) without starting over."""
        out = self.advance(at)
        if self._temp and self._temp[0].data.get("event_key") == manual_key:
            scene, until = self._temp
            data = {"event_key": event.key, "side": event.side, "linked_from": manual_key}
            self._temp = (Scene("goal", scene.since_ms, scene.hold_ms, data), until)
        return out + self._emit(at)

    def set_override(
        self, name: str, hold_ms: int | None, at: int, data: dict[str, Any] | None = None
    ) -> list[Scene]:
        if name not in SCENES:
            raise ValueError(f"unknown scene {name!r}")
        out = self.advance(at)
        until = at + hold_ms if hold_ms else None
        self._override = (Scene(name, at, hold_ms, data or {}, override=True), until)
        return out + self._emit(at)

    def clear_override(self, at: int) -> list[Scene]:
        out = self.advance(at)
        self._override = None
        return out + self._emit(at)

    # --- time -----------------------------------------------------------------------

    def next_timer_ms(self) -> int | None:
        timers = [
            t
            for t in (
                self._temp[1] if self._temp else None,
                self._override[1] if self._override else None,
                self._postgame_until,
            )
            if t is not None
        ]
        return min(timers) if timers else None

    def advance(self, until: int) -> list[Scene]:
        """Expire holds up to ``until``, each at its own time."""
        out: list[Scene] = []
        while (t := self.next_timer_ms()) is not None and t <= until:
            if self._temp and self._temp[1] == t:
                self._temp = None
            elif self._override and self._override[1] == t:
                self._override = None
            elif self._postgame_until == t:
                self._postgame_until = None
                self.base = "idle"
            out += self._emit(t)
        return out

    # --- output ---------------------------------------------------------------------

    def effective(self, at: int) -> Scene:
        if self._override:
            return self._override[0]
        if self._temp:
            return self._temp[0]
        hold = POSTGAME_HOLD_MS if self.base == "postgame" else None
        return Scene(self.base, at, hold)

    def _emit(self, at: int) -> list[Scene]:
        scene = self.effective(at)
        if scene.same(self.current):
            return []
        if scene.since_ms != at and not scene.override:
            scene = Scene(scene.name, at, scene.hold_ms, scene.data, scene.override)
        self.current = scene
        return [scene]
