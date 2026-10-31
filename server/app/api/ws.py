"""WebSocket hub: ``/ws?role=screen|sim|phone|debug&id=…`` (docs/PROTOCOL.md, WebSocket).

On connect a client gets ``hello``, then the applied TV state, then every message that is
still waiting for its ``play_at``; after that it gets broadcasts as they happen. Raw
(undelayed) events only go to clients that sent ``debug_subscribe`` (CLAUDE.md rule 1).
"""

import asyncio
import contextlib
import logging
import secrets
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.clock import Clock

log = logging.getLogger(__name__)

ROLES = frozenset({"screen", "sim", "phone", "debug"})
RAW_ROLES = frozenset({"phone", "debug", "sim"})
HEARTBEAT_S = 10.0
QUEUE_SIZE = 2000


class Client:
    def __init__(self, ws: WebSocket, role: str, client_id: str) -> None:
        self.ws = ws
        self.role = role
        self.id = client_id
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.raw = False
        self.overflowed = False

    def send(self, message: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            if not self.overflowed:
                log.warning("client %s/%s is not keeping up; disconnecting", self.role, self.id)
            self.overflowed = True


class Hub:
    def __init__(self) -> None:
        self.clients: set[Client] = set()
        # new on every start of the service: a client that sees it change on a reconnect
        # knows the pages may have changed too (the TV app reloads itself)
        self.boot = secrets.token_hex(6)

    def broadcast(self, message: dict[str, Any], *, raw: bool = False) -> None:
        for client in list(self.clients):
            if raw and not client.raw:
                continue
            if message.get("t") == "status" and client.role == "screen":
                continue
            client.send(message)

    async def heartbeat(self, clock: Clock) -> None:
        while True:
            await clock.sleep(HEARTBEAT_S)
            self.broadcast({"t": "heartbeat", "server_ms": clock.now_ms()})


async def serve(ws: WebSocket, hub: Hub, runtime: Any, clock: Clock) -> None:
    role = ws.query_params.get("role", "screen")
    client_id = ws.query_params.get("id", "")
    await ws.accept()
    if role not in ROLES:
        await ws.close(code=4400, reason=f"unknown role {role!r}")
        return
    client = Client(ws, role, client_id)
    # Queue the greeting and the current state in the same step as joining the hub, so no
    # broadcast can slip in between.
    client.send(
        {
            "t": "hello",
            "server_ms": clock.now_ms(),
            "boot": hub.boot,
            "role": role,
            "id": client_id,
            "config": runtime.config_message(),
        }
    )
    for message in runtime.full_state_messages():
        client.send(message)
    if role != "screen":
        client.send({"t": "status", "status": runtime.status()})
    hub.clients.add(client)

    async def sender() -> None:
        while not client.overflowed:
            message = await client.queue.get()
            await ws.send_json(message)
        await ws.close(code=1013)

    task = asyncio.create_task(sender())
    try:
        while True:
            message = await ws.receive_json()
            kind = message.get("t") if isinstance(message, dict) else None
            if kind == "clock_ping":
                await ws.send_json(
                    {"t": "clock_pong", "t0": message.get("t0"), "server_ms": clock.now_ms()}
                )
            elif kind == "debug_subscribe" and role in RAW_ROLES:
                client.raw = True
                client.send(
                    {
                        "t": "raw_backlog",
                        "raw": list(runtime.raw_log),
                        "released": list(runtime.release_log),
                    }
                )
            elif kind == "debug_unsubscribe":
                client.raw = False
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.clients.discard(client)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
