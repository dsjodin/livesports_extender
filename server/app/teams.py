"""Team jersey colours (config/teams.json plus overrides from data/state.json)."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger(__name__)

Jersey = Literal["home", "away"]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class TeamColors:
    def __init__(self, path: Path, overrides: dict[str, dict[str, str]] | None = None) -> None:
        data: dict[str, Any] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            log.warning("no team colour file at %s", path)
        self.palette: dict[str, str] = data.get("colors", {})
        self.teams: dict[str, dict[str, Any]] = data.get("teams", {})
        self.overrides = overrides if overrides is not None else {}
        self._warned: set[str] = set()

    def valid(self, value: str) -> bool:
        return value in self.palette or bool(HEX.match(value))

    def jersey(self, uuid: str | None, jersey: Jersey) -> str | None:
        """The colour name or hex for a team's home or away jersey, or None if unknown."""
        if not uuid:
            return None
        value = self.overrides.get(uuid, {}).get(jersey) or self.teams.get(uuid, {}).get(jersey)
        if value is None and uuid not in self._warned:
            self._warned.add(uuid)
            log.warning("no %s colour for team %s; screens use a neutral colour", jersey, uuid)
        return value

    def hex(self, value: str | None) -> str | None:
        if value is None:
            return None
        return value if HEX.match(value) else self.palette.get(value)

    def describe(self, uuid: str, jersey: Jersey) -> dict[str, str | None]:
        value = self.jersey(uuid, jersey)
        return {"jersey": value, "color": self.hex(value)}

    def listing(self) -> list[dict[str, Any]]:
        return [
            {
                "uuid": uuid,
                "name": team.get("name"),
                "home": self.describe(uuid, "home"),
                "away": self.describe(uuid, "away"),
                "overridden": uuid in self.overrides,
            }
            for uuid, team in self.teams.items()
        ]
