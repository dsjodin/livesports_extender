"""Saves a live game's polls as a recording, in the format of ``tools/record_game.py``.

One JSON line per request: ``{"received_ms", "endpoint", "status", "sha1", "age",
"cache", "body"}``; ``body`` only when it changed since the last stored body for that
endpoint, failed requests with ``status`` null (or the HTTP status) and ``error``. So a
game followed live can be replayed (``RecordingSource``, /sim) and analysed
(``tools/analyze_recording.py``) without a second poller hitting shl.se.

``sha1`` is of the re-serialised JSON, not of the raw bytes as in the recorder; it only
serves to spot changes.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, TextIO

from app.clock import Clock
from app.feed.client import ShlError, ShlHttpError

log = logging.getLogger(__name__)


class PollLog:
    def __init__(self, path: Path, clock: Clock) -> None:
        self.path = path
        self.clock = clock
        self.rows = 0
        self._hashes: dict[str, str] = {}
        self._file: TextIO | None = None

    def _write(self, row: dict[str, Any]) -> None:
        if self._file is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("a", encoding="utf-8")
        self._file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._file.flush()
        self.rows += 1

    def ok(self, endpoint: str, data: Any, age_s: int | None, cache: str | None) -> None:
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        sha1 = hashlib.sha1(text.encode("utf-8")).hexdigest()
        changed = self._hashes.get(endpoint) != sha1
        self._hashes[endpoint] = sha1
        self._write(
            {
                "received_ms": self.clock.now_ms(),
                "endpoint": endpoint,
                "status": 200,
                "sha1": sha1,
                "age": age_s,
                "cache": cache,
                "body": data if changed else None,
            }
        )

    def error(self, endpoint: str, exc: ShlError) -> None:
        self._write(
            {
                "received_ms": self.clock.now_ms(),
                "endpoint": endpoint,
                "status": exc.status if isinstance(exc, ShlHttpError) else None,
                "sha1": None,
                "age": None,
                "cache": None,
                "body": None,
                "error": str(exc),
            }
        )

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
            log.info("live recording: %d rows in %s", self.rows, self.path)
