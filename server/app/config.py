"""Settings from environment variables, and the persisted runtime state (data/state.json)."""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "server" / "tests" / "fixtures"

log = logging.getLogger(__name__)


def _path_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


@dataclass(frozen=True)
class Settings:
    web_dir: Path
    config_dir: Path
    data_dir: Path
    fixtures_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            web_dir=_path_env("ARENA_WEB_DIR", REPO_ROOT / "web"),
            config_dir=_path_env("ARENA_CONFIG_DIR", REPO_ROOT / "config"),
            data_dir=_path_env("ARENA_DATA_DIR", REPO_ROOT / "data"),
            fixtures_dir=_path_env(
                "ARENA_FIXTURES_DIR", REPO_ROOT / "server" / "tests" / "fixtures"
            ),
        )


SourceMode = Literal["none", "replay", "recording", "live"]


class SourceSettings(BaseModel):
    mode: SourceMode = "none"
    uuid: str | None = None
    path: str | None = None
    speed: float = 1.0


class WebhookSettings(BaseModel):
    url: str | None = None
    enabled: bool = False
    events: list[str] = [
        "shl_goal",
        "shl_goal_disallowed",
        "shl_penalty",
        "shl_period_start",
        "shl_period_end",
        "shl_game_end",
    ]


class RuntimeConfig(BaseModel):
    """Everything the user sets that must survive a restart."""

    game_uuid: str | None = None
    my_side: Literal["home", "away"] | None = None
    source: SourceSettings = SourceSettings()
    # TV delay behind the arena per TV profile, seconds. IPTV was measured at about 40 s
    # on 2026-10-20 (rough); TV4 Play is a guess until calibrated.
    profiles: dict[str, float] = {"iptv": 40.0, "tv4play": 60.0}
    active_profile: str = "iptv"
    calibration_samples: list[dict[str, object]] = []
    webhooks: WebhookSettings = WebhookSettings()
    # Jersey colour overrides per team uuid: {"home": "röd" | "#rrggbb", "away": ...}.
    # Defaults are in config/teams.json.
    team_colors: dict[str, dict[str, str]] = {}

    @property
    def offset_s(self) -> float:
        return self.profiles.get(self.active_profile, 40.0)


class StateStore:
    """Loads ``RuntimeConfig`` from a JSON file at start and saves it on every change."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.config = self._load()

    def _load(self) -> RuntimeConfig:
        if not self.path.exists():
            return RuntimeConfig()
        try:
            return RuntimeConfig.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError, OSError) as exc:
            log.warning("could not read %s (%s); starting from defaults", self.path, exc)
            return RuntimeConfig()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.config.model_dump(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
