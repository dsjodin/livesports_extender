"""SHL Arena server."""

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

with _PYPROJECT.open("rb") as _f:
    __version__: str = tomllib.load(_f)["project"]["version"]
