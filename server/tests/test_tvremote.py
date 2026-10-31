"""The TV's network remote (app/api/tvremote.py) against a fake TV on plain ws (port 8001
form), so no certificate is needed."""

import asyncio
import json
from pathlib import Path
from typing import Any

import websockets

from app.api import tvremote
from app.api.tvremote import TvRemote


async def fake_tv(reply: dict[str, Any], got: list[str], paths: list[str]) -> Any:
    async def handler(ws: Any) -> None:
        paths.append(ws.request.path)
        await ws.send(json.dumps(reply))
        async for message in ws:
            got.append(message)

    return await websockets.serve(handler, "127.0.0.1", 0)


async def test_press_pairs_saves_the_token_and_reuses_the_connection(tmp_path: Path) -> None:
    got: list[str] = []
    paths: list[str] = []
    server = await fake_tv({"event": "ms.channel.connect", "data": {"token": "777"}}, got, paths)
    port = server.sockets[0].getsockname()[1]
    remote = TvRemote("127.0.0.1", tmp_path, port=8001)  # plain ws: no certificate
    remote._url = lambda: (  # type: ignore[method-assign]
        f"ws://127.0.0.1:{port}/api/v2/channels/samsung.remote.control?name=x"
    )
    try:
        assert await remote.press() == {"ok": True, "sent": 1}
        assert await remote.press() == {"ok": True, "sent": 2}
        await asyncio.sleep(0.05)
        assert len(paths) == 1  # one connection, kept
        assert [json.loads(m)["params"]["DataOfCmd"] for m in got] == ["KEY_RED", "KEY_RED"]
        assert (tmp_path / tvremote.TOKEN_FILE).read_text() == "777"
    finally:
        await remote.close()
        server.close()


async def test_refused_says_so(tmp_path: Path) -> None:
    server = await fake_tv({"event": "ms.channel.timeOut"}, [], [])
    port = server.sockets[0].getsockname()[1]
    remote = TvRemote("127.0.0.1", tmp_path, port=8001)
    remote._url = lambda: f"ws://127.0.0.1:{port}/x"  # type: ignore[method-assign]
    try:
        r = await remote.press()
        assert not r["ok"] and "ms.channel.timeOut" in r["error"]
    finally:
        await remote.close()
        server.close()


def test_url_carries_name_and_token(tmp_path: Path) -> None:
    (tmp_path / tvremote.TOKEN_FILE).write_text("22295567\n")
    url = TvRemote("10.1.30.110", tmp_path)._url()
    assert url.startswith("wss://10.1.30.110:8002/api/v2/channels/samsung.remote.control?name=")
    assert url.endswith("&token=22295567")


async def test_endpoint_without_address() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(fetch_league=False)
    app.state.tv_remote = None
    with TestClient(app) as client:
        r = client.post("/api/tv/keepawake").json()
    assert r == {"ok": False, "error": "ingen TV-adress (ARENA_TV_REMOTE)"}
