"""Sends webhook payloads to Home Assistant at their play_at (CLAUDE.md rule 1).

Each call waits on the injectable clock until play_at (never before), POSTs with a 3 s
timeout, retries once, and is logged; the log goes to /sim and the phone. A replay seek
or a new source cancels what has not been sent yet.
"""

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

from app import __version__
from app.clock import Clock
from app.config import WebhookSettings

log = logging.getLogger(__name__)

TIMEOUT_S = 3.0
RETRY_AFTER_S = 1.0
LOG_SIZE = 100


class WebhookDispatcher:
    def __init__(
        self,
        clock: Clock,
        settings: Callable[[], WebhookSettings],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        on_log: Callable[[dict[str, Any]], None] = lambda entry: None,
    ) -> None:
        self.clock = clock
        self.settings = settings
        self.transport = transport
        self.on_log = on_log
        self.log: deque[dict[str, Any]] = deque(maxlen=LOG_SIZE)
        self._tasks: set[asyncio.Task[None]] = set()
        self._seq = 0
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        """One client for all calls: creating one per call costs tens of ms at play_at."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=TIMEOUT_S,
                transport=self.transport,
                headers={"User-Agent": f"shl-arena/{__version__} (private home display)"},
            )
        return self._client

    def schedule(self, play_at: int, body: dict[str, Any]) -> bool:
        """Queue ``body`` for ``play_at`` if webhooks are on and want this event."""
        settings = self.settings()
        if not settings.enabled or not settings.url or body["event"] not in settings.events:
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # no loop (a synchronous caller): nothing can be sent
            return False
        self._seq += 1
        self._http()  # ready before play_at
        task = loop.create_task(self._send(self._seq, play_at, dict(body), settings.url))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    def cancel_pending(self) -> None:
        for task in list(self._tasks):
            task.cancel()

    async def close(self) -> None:
        self.cancel_pending()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def pending(self) -> int:
        return len(self._tasks)

    async def _send(self, seq: int, play_at: int, body: dict[str, Any], url: str) -> None:
        while (wait := play_at - self.clock.now_ms()) > 0:
            await self.clock.sleep(wait / 1000)
        entry: dict[str, Any] = {
            "id": seq,
            "event": body["event"],
            "test": body.get("test", False),
            "source": body.get("source"),
            "play_at_ms": play_at,
            "sent_ms": None,
            "status": None,
            "error": None,
            "attempts": 0,
        }
        client = self._http()
        for attempt in (1, 2):
            entry["attempts"] = attempt
            sent = self.clock.now_ms()
            entry["sent_ms"] = sent
            try:
                response = await client.post(url, json=body | {"sent_ms": sent})
                entry["status"], entry["error"] = response.status_code, None
                if response.status_code < 400:
                    break
                entry["error"] = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                entry["status"], entry["error"] = None, f"{type(exc).__name__}: {exc}"
            if attempt == 1:
                await self.clock.sleep(RETRY_AFTER_S)
        if entry["error"]:
            log.warning("webhook %s failed: %s", body["event"], entry["error"])
        self.log.append(entry)
        self.on_log(entry)
