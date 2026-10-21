"""The normalized event shape (docs/PROTOCOL.md, Normalized event)."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Side = Literal["home", "away"]
EVENT_TYPES = (
    "goal",
    "shot",
    "penalty",
    "goalie_change",
    "timeout",
    "period_start",
    "period_end",
    "game_end",
    "shootout_attempt",
    "unknown",
)


class Player(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str | None = None
    number: str | None = None
    first: str | None = None
    last: str | None = None

    @property
    def name(self) -> str:
        return " ".join(p for p in (self.first, self.last) if p)


class NormalizedEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    type: str
    raw_type: str
    event_id: int | None = None
    game_uuid: str | None = None
    period: int | str | None = None
    time: str | None = None
    game_seconds: int | None = None
    side: Side | None = None
    team_uuid: str | None = None
    team_code: str | None = None
    player: Player | None = None
    data: dict[str, Any] = {}
    revision: int | None = None
    event_ms: int | None = None
    first_seen_ms: int
    received_ms: int
    test: bool = False

    def label(self) -> str:
        """Short text for logs and the CLI, e.g. ``P3 09:07 goal FHC #25 Ruotsalainen``."""
        where = "" if self.period is None else f"P{self.period}"
        where += f" {self.time}" if self.time else ""
        who = f" #{self.player.number} {self.player.name}" if self.player else ""
        team = f" {self.team_code}" if self.team_code else ""
        return f"{where} {self.type}{team}{who}".strip()


ChangeKind = Literal["added", "updated", "removed", "reset"]


@dataclass(frozen=True, slots=True)
class Change:
    """One normalizer output. ``reset`` (no event) means start over (a replay seek)."""

    kind: ChangeKind
    event: NormalizedEvent | None = None
