"""Settings from environment variables.

Persisted runtime state (selected game, offsets, ...) arrives in Phase 2.
"""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _path_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


@dataclass(frozen=True)
class Settings:
    web_dir: Path
    config_dir: Path
    data_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            web_dir=_path_env("ARENA_WEB_DIR", REPO_ROOT / "web"),
            config_dir=_path_env("ARENA_CONFIG_DIR", REPO_ROOT / "config"),
            data_dir=_path_env("ARENA_DATA_DIR", REPO_ROOT / "data"),
        )
