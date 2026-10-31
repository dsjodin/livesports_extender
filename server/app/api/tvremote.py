"""The Samsung TV's network remote: one key now and then keeps its screen saver away.

Samsung's screen saver comes after about 2 min while the TV app shows the TV picture
shrunk (the L-frame), and the app cannot turn it off; a remote key resets it
(docs/TV_APP.md, Screen saver). The TV app asks for a key every minute while the L-frame
is up (``POST /api/tv/keepawake``) and this sends KEY_RED, which the user's remote does
not have and the graphics ignore, over the TV's remote-control WebSocket (port 8002, the
one phone remote apps use). The TV takes it only from its own subnet (the container's
macvlan address, docs/DEPLOY.md) and with the token it gave "SHL Arena", kept in the data
directory; a new token in the TV's answer replaces it.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import ssl
from pathlib import Path
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

log = logging.getLogger(__name__)

NAME = "SHL Arena"
TOKEN_FILE = "tv_remote_token.txt"
TIMEOUT_S = 5.0


class TvRemoteError(Exception):
    pass


def key_message(key: str) -> str:
    params = {"Cmd": "Click", "DataOfCmd": key, "Option": "false", "TypeOfRemote": "SendRemoteKey"}
    return json.dumps({"method": "ms.remote.control", "params": params})


class TvRemote:
    def __init__(self, host: str, data_dir: Path, port: int = 8002) -> None:
        self.host = host
        self.port = port
        self.token_path = data_dir / TOKEN_FILE
        self._ws: ClientConnection | None = None
        self._lock = asyncio.Lock()
        self.sent = 0
        self.last_error: str | None = None

    def _url(self) -> str:
        name = base64.b64encode(NAME.encode()).decode()
        scheme = "ws" if self.port == 8001 else "wss"
        url = (
            f"{scheme}://{self.host}:{self.port}/api/v2/channels/samsung.remote.control?name={name}"
        )
        token = self._token()
        return url + (f"&token={token}" if token else "")

    def _token(self) -> str | None:
        try:
            return self.token_path.read_text().strip() or None
        except OSError:
            return None

    async def _connect(self) -> ClientConnection:
        context = None
        if self.port != 8001:
            # the TV's own self-signed certificate, on our LAN
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        ws = await websockets.connect(self._url(), ssl=context, open_timeout=TIMEOUT_S)
        try:
            while True:
                reply: dict[str, Any] = json.loads(await asyncio.wait_for(ws.recv(), TIMEOUT_S))
                event = reply.get("event")
                if event == "ms.channel.connect":
                    token = (reply.get("data") or {}).get("token")
                    if token and token != self._token():
                        self.token_path.parent.mkdir(parents=True, exist_ok=True)
                        self.token_path.write_text(str(token))
                        log.info("TV remote: new token saved")
                    return ws
                if event in ("ms.channel.unauthorized", "ms.channel.timeOut"):
                    raise TvRemoteError(
                        f"TV:n släppte inte in oss ({event}): tillåt SHL Arena på TV:n"
                    )
        except BaseException:
            await ws.close()
            raise

    async def press(self, key: str = "KEY_RED") -> dict[str, Any]:
        """Send one key; reconnects once if the kept connection has gone."""
        async with self._lock:
            for attempt in (1, 2):
                try:
                    if self._ws is None:
                        self._ws = await self._connect()
                    await asyncio.wait_for(self._ws.send(key_message(key)), TIMEOUT_S)
                    self.sent += 1
                    self.last_error = None
                    return {"ok": True, "sent": self.sent}
                except (OSError, TimeoutError, TvRemoteError, websockets.WebSocketException) as err:
                    await self.close_locked()
                    if attempt == 2 or isinstance(err, TvRemoteError):
                        self.last_error = str(err) or type(err).__name__
                        log.warning("TV remote %s:%s: %s", self.host, self.port, self.last_error)
                        return {"ok": False, "error": self.last_error}
        return {"ok": False, "error": "unreachable"}  # pragma: no cover

    async def close_locked(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            with contextlib.suppress(Exception):  # closing a broken connection
                await ws.close()

    async def close(self) -> None:
        async with self._lock:
            await self.close_locked()
