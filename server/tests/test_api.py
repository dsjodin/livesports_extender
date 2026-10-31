"""WebSocket and REST integration on the real app (real clock, fast replay)."""

import shutil
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Any:
    settings = Settings(
        web_dir=tmp_path, config_dir=REPO_ROOT / "config", data_dir=tmp_path, fixtures_dir=FIXTURES
    )
    with TestClient(create_app(settings, fetch_league=False)) as c:
        yield c


def wait_for(client: TestClient, condition: Any, seconds: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    while True:
        tv = client.get("/api/state").json()["tv"]
        if condition(tv) or time.monotonic() > deadline:
            assert condition(tv), tv["phase"]
            return tv  # type: ignore[no-any-return]
        time.sleep(0.05)


def receive_until(ws: Any, done: Any, limit: int = 5000) -> list[dict[str, Any]]:
    out = []
    for _ in range(limit):
        message = ws.receive_json()
        out.append(message)
        if done(message):
            return out
    raise AssertionError("message not seen")


def test_websocket_hello_state_then_events_in_order(client: TestClient) -> None:
    assert client.post("/api/offset", json={"profile": "iptv", "seconds": 0}).status_code == 200
    with client.websocket_connect("/ws?role=sim&id=test") as ws:
        hello = ws.receive_json()
        assert hello["t"] == "hello" and hello["role"] == "sim" and hello["id"] == "test"
        assert hello["config"] == {
            "offset_ms": 0,
            "lead_ms": 1500,
            "profile": "iptv",
            "speed": 1.0,
            "debug": False,
            "feed_ok": True,
            "idle_dim": 0.5,
        }
        state = ws.receive_json()
        assert state["t"] == "state" and state["state"]["score"] == {"home": 0, "away": 0}
        response = client.post(
            "/api/source", json={"mode": "replay", "uuid": "bdhvuc5tex", "speed": 4000}
        )
        assert response.status_code == 200, response.text
        messages = receive_until(
            ws, lambda m: m["t"] == "event" and m["event"]["type"] == "game_end"
        )
        ws.send_json({"t": "clock_ping", "t0": 123})
        pong = receive_until(ws, lambda m: m["t"] == "clock_pong")[-1]
        assert pong["t0"] == 123 and pong["server_ms"] > 1_700_000_000_000

    events = [m for m in messages if m["t"] == "event"]
    goals = [m["event"] for m in events if m["event"]["type"] == "goal"]
    assert [(g["period"], g["time"]) for g in goals] == [(1, "04:33"), (2, "00:24"), (3, "09:07")]
    timed = [m["play_at_ms"] for m in messages if "play_at_ms" in m]
    assert timed == sorted(timed)
    assert all(m["event"]["late"] for m in events)  # offset 0: everything is late
    scenes = [m["scene"]["name"] for m in messages if m["t"] == "scene"]
    # Holds are in real time, so at 4000x the 20 s goal scene spans the intermissions and
    # the postgame scene only follows when the last goal's hold ends.
    assert scenes.count("goal") == 3 and scenes[0] == "live"
    period_ends = [m for m in events if m["event"]["type"] == "period_end"]
    assert [m["event"]["period"] for m in period_ends] == [1, 2, 3]
    patches = [m for m in messages if m["t"] == "state_patch"]
    assert patches[-1]["rev"] > patches[0]["rev"]

    tv = wait_for(client, lambda tv: tv["phase"] == "postgame")
    assert tv["score"] == {"home": 2, "away": 1}


def test_raw_events_only_after_subscribe(client: TestClient) -> None:
    client.post("/api/offset", json={"profile": "iptv", "seconds": 0})
    with client.websocket_connect("/ws?role=debug&id=d") as ws:
        ws.receive_json()
        ws.receive_json()
        client.post("/api/source", json={"mode": "replay", "uuid": "bdhvuc5tex", "speed": 4000})
        before = receive_until(ws, lambda m: m["t"] == "event")
        assert not [m for m in before if m["t"] == "raw"]
        ws.send_json({"t": "debug_subscribe"})
        backlog = receive_until(ws, lambda m: m["t"] == "raw_backlog")[-1]
        assert backlog["raw"] and {"event_ms", "first_seen_ms"} <= backlog["raw"][0].keys()
        raw = receive_until(ws, lambda m: m["t"] == "raw")[-1]
        assert raw["entry"]["change"] in ("added", "updated", "removed")
    with client.websocket_connect("/ws?role=screen&id=left") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"t": "debug_subscribe"})  # screens may not subscribe
        ws.send_json({"t": "clock_ping", "t0": 1})
        assert not [
            m
            for m in receive_until(ws, lambda m: m["t"] == "clock_pong")
            if m["t"] in ("raw", "raw_backlog", "status")
        ]


def test_rest_controls(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/wall").json()["units"] == "mm"
    r = client.post("/api/game", json={"uuid": "bdhvuc5tex", "my_side": "home"})
    assert r.json()["status"]["my_side"] == "home"
    # applied at play_at, lead_ms after the request
    assert wait_for(client, lambda tv: tv["phase"] == "pregame")["game"]["my_side"] == "home"

    assert client.post("/api/offset", json={"profile": "iptv", "seconds": 42}).status_code == 200
    r = client.post("/api/offset/nudge", json={"delta": -0.5})
    assert r.json()["status"]["offset_s"] == 41.5
    assert client.post("/api/offset", json={"profile": "iptv", "seconds": -1}).status_code == 400
    assert (
        client.post("/api/profile", json={"profile": "tv4play"}).json()["status"]["offset_s"] == 60
    )
    assert client.post("/api/profile", json={"profile": "vhs"}).status_code == 400

    assert client.post("/api/replay", json={"action": "pause"}).status_code == 400  # no replay
    r = client.post("/api/source", json={"mode": "replay", "uuid": "bdhvuc5tex", "speed": 1})
    assert r.status_code == 200 and r.json()["status"]["source"]["mode"] == "replay"
    assert client.post("/api/replay", json={"action": "pause"}).json()["status"]["paused"]
    assert not client.post("/api/replay", json={"action": "play"}).json()["status"]["paused"]
    r = client.post("/api/replay", json={"action": "speed", "speed": 20})
    assert r.json()["status"]["source"]["speed"] == 20
    for to in ("period:2", "next_period", "before_next_goal", "end"):
        r = client.post("/api/replay", json={"action": "seek", "to": to})
        assert r.status_code == 200, (to, r.text)
    assert client.post("/api/replay", json={"action": "seek", "to": "period:9"}).status_code == 400

    assert client.post("/api/scene", json={"name": "intermission", "hold_s": 30}).status_code == 200
    assert client.post("/api/scene", json={"name": "party"}).status_code == 400
    assert client.delete("/api/scene").status_code == 200

    assert client.post("/api/source", json={"mode": "live"}).status_code == 400  # needs a uuid
    r = client.post("/api/source", json={"mode": "recording", "path": "../../etc"})
    assert r.status_code == 400
    rec = tmp_path / "recordings" / "mtn5yq64mp"
    rec.mkdir(parents=True)
    shutil.copy(REPO_ROOT / "data" / "recordings" / "mtn5yq64mp" / "polls.jsonl", rec)
    replays = client.get("/api/replays").json()
    assert "bdhvuc5tex" in replays["fixtures"] and replays["recordings"] == ["mtn5yq64mp"]
    r = client.post("/api/source", json={"mode": "recording", "path": "mtn5yq64mp", "speed": 50})
    assert r.status_code == 200 and r.json()["status"]["running"]
    assert client.post("/api/source", json={"mode": "none"}).json()["status"]["running"] is False

    saved = (tmp_path / "state.json").read_text()
    assert '"tv4play": 60.0' in saved and '"game_uuid": "bdhvuc5tex"' in saved
    assert '"active_profile": "tv4play"' in saved


def test_test_video_is_broadcast_alone(client: TestClient) -> None:
    with client.websocket_connect("/ws?role=screen&id=left") as ws:
        r = client.post("/api/test/video", json={"kind": "intro"})
        assert r.status_code == 200
        at = r.json()["play_at_ms"]
        messages = receive_until(ws, lambda m: m.get("t") == "video")
        assert messages[-1] == {"t": "video", "kind": "intro", "side": None, "play_at_ms": at}
    assert client.post("/api/test/video", json={"kind": "other"}).status_code == 422


def test_idle_dim_is_saved_and_sent_to_screens(client: TestClient, tmp_path: Path) -> None:
    with client.websocket_connect("/ws?role=screen&id=bar") as ws:
        hello = ws.receive_json()
        assert hello["t"] == "hello" and hello["config"]["idle_dim"] == 0.5
        r = client.post("/api/idle-dim", json={"level": 0.7})
        assert r.status_code == 200
        assert r.json()["status"]["idle_dim"] == 0.7
        update = receive_until(ws, lambda m: m.get("t") == "config")[-1]
        assert update["config"]["idle_dim"] == 0.7
    assert '"idle_dim": 0.7' in (tmp_path / "state.json").read_text(encoding="utf-8")
    assert client.post("/api/idle-dim", json={"level": 0.95}).status_code == 422
    assert client.post("/api/idle-dim", json={"level": -0.1}).status_code == 422


def test_tv_probe_report_is_kept(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/api/tv/probe").status_code == 404
    report = {"probe": 1, "mode": "iframe", "answers": {"transparent": True}}
    assert client.post("/api/tv/probe", json=report).json() == {"ok": True}
    kept = client.get("/api/tv/probe").json()
    assert kept["report"] == report and kept["received_ms"] > 0
    assert (tmp_path / "tv_probe.json").exists()
    huge = {"errors": ["x" * 1000] * 100}
    assert client.post("/api/tv/probe", json=huge).status_code == 413


def test_cors_only_for_the_tv_shell(client: TestClient) -> None:
    # the shell on the TV runs from file:// (Origin "null"); websites get no CORS
    tv = client.get("/api/health", headers={"Origin": "null"})
    assert tv.headers.get("access-control-allow-origin") == "null"
    site = client.get("/api/health", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in site.headers
    preflight = client.options(
        "/api/tv/probe",
        headers={
            "Origin": "null",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200


def test_tv_app_shell_is_served_for_a_preview(tmp_path: Path) -> None:
    shell = tmp_path / "SHLlive"
    shell.mkdir()
    (shell / "index.html").write_text("<title>SHL live!</title>", encoding="utf-8")
    settings = Settings(
        web_dir=tmp_path,
        config_dir=REPO_ROOT / "config",
        data_dir=tmp_path,
        fixtures_dir=FIXTURES,
        tv_app_dir=shell,
    )
    with TestClient(create_app(settings, fetch_league=False)) as c:
        page = c.get("/tvapp/")
        assert page.status_code == 200 and "SHL live!" in page.text
        assert page.headers["cache-control"] == "no-cache"
