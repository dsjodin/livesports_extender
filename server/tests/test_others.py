"""Phase 8: the evening's other games (delayed like ours) and the live table."""

import json
import time
from pathlib import Path
from typing import Any

import httpx
from conftest import FIXTURES, load_fixture
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.engine.league import live_table, standings_rows
from app.engine.others import OtherGame
from app.feed.client import ShlClient
from app.feed.snapshot import Snapshot
from app.feedtime import parse_local_ms
from app.main import create_app

TEAMS = {"home": {"uuid": "h", "code": "DIF"}, "away": {"uuid": "a", "code": "MIF"}}


def game(offset_s: int = 40) -> OtherGame:
    return OtherGame("pmch0rrshr", None, TEAMS, offset_s * 1000, 1500)


def test_other_game_catches_up_then_delays_new_goals() -> None:
    pbp = load_fixture("pbp_pmch0rrshr.json")
    goals = sorted((e for e in pbp if e["type"] == "goal"), key=lambda e: e["eventId"])
    last = goals[-1]
    before = [e for e in pbp if e.get("eventId") != last["eventId"]]
    on_ice = parse_local_ms(last["realWorldTime"])
    assert on_ice is not None
    g = game()
    # joined after the game: everything is there at once (it was on TV long ago)
    g.apply(Snapshot.at(on_ice + 3600_000, None, pbp), on_ice + 3600_000)
    final = g.summary()
    assert final["score"] == {"home": 3, "away": 2} and final["ended"]
    # a goal arriving 20 s after the ice plays at ice + 40 s, not before
    g = game()
    g.apply(Snapshot.at(on_ice - 60_000, None, before), on_ice - 60_000)
    assert g.summary()["score"] != {"home": 3, "away": 2}
    g.apply(Snapshot.at(on_ice + 20_000, None, pbp), on_ice + 20_000)
    assert g.due(on_ice + 40_000 - 1501) == []
    [out] = g.due(on_ice + 40_000 - 1500)
    assert out.play_at == on_ice + 40_000 and out.event is not None
    g.release(out.event)
    assert g.summary()["score"] == {"home": 3, "away": 2}


def test_live_table_points_and_moves() -> None:
    rows = standings_rows(load_fixture("standings_qa98unlbd6.json"))
    by_code = {r["code"]: r for r in rows}
    last, first = rows[-1], rows[0]
    games = [
        # the last team leads the first: 3 points now, and they are still playing
        {"home_uuid": last["uuid"], "away_uuid": first["uuid"], "home": 2, "away": 0,
         "ended": False},
        # a tie still on: 1 point each (the overtime point)
        {"home_uuid": rows[1]["uuid"], "away_uuid": rows[2]["uuid"], "home": 1, "away": 1,
         "ended": False},
        # over after overtime: 2 and 1
        {"home_uuid": rows[3]["uuid"], "away_uuid": rows[4]["uuid"], "home": 3, "away": 2,
         "ended": True, "overtime": True},
    ]  # fmt: skip
    table = {r["uuid"]: r for r in live_table(rows, games)}
    assert table[last["uuid"]]["points"] == last["points"] + 3
    assert table[first["uuid"]]["points"] == first["points"]
    assert table[first["uuid"]]["live"] == {
        "for": 0, "against": 2, "ended": False, "home_away": "B", "opponent": last["code"],
    }  # fmt: skip
    assert table[rows[1]["uuid"]]["points"] == rows[1]["points"] + 1
    assert table[rows[2]["uuid"]]["points"] == rows[2]["points"] + 1
    assert table[rows[3]["uuid"]]["points"] == rows[3]["points"] + 2
    assert table[rows[4]["uuid"]]["points"] == rows[4]["points"] + 1
    assert table[last["uuid"]]["gp"] == last["gp"] + 1
    ranks = sorted(table.values(), key=lambda r: r["rank"])
    assert [r["rank"] for r in ranks] == list(range(1, len(rows) + 1))
    assert all(r["move"] == r["prev_rank"] - r["rank"] for r in ranks)
    untouched = by_code[rows[7]["code"]]
    assert table[untouched["uuid"]]["live"] is None


def fixtures_transport() -> httpx.MockTransport:
    """shl.se from the fixtures: filter, schedule, standings, game-info, play-by-play."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        name = None
        if path.endswith("season-series-game-types-filter"):
            name = "filter.json"
        elif "game-schedule" in path:
            name = "schedule_2026.json"
        elif "team-standings" in path:
            name = "standings_qa98unlbd6.json"
        elif "/game-info/" in path:
            name = f"game_info_{path.rsplit('/', 1)[1]}.json"
        elif "/play-by-play/" in path:
            name = f"pbp_{path.rsplit('/', 1)[1]}.json"
        if name is None or not (FIXTURES / name).exists():
            return httpx.Response(404)
        return httpx.Response(200, json=json.loads((FIXTURES / name).read_text("utf-8")))

    return httpx.MockTransport(handler)


def test_replay_follows_the_evenings_other_games(tmp_path: Path) -> None:
    settings = Settings(
        web_dir=tmp_path, config_dir=REPO_ROOT / "config", data_dir=tmp_path, fixtures_dir=FIXTURES
    )
    transport = fixtures_transport()
    app = create_app(settings, client_factory=lambda: ShlClient(transport=transport))
    with TestClient(app) as client:
        # a short TV delay: the offset is in real seconds, so at 50x a 40 s delay would keep
        # the last minutes of the other games waiting after the seek
        client.post("/api/offset", json={"profile": "iptv", "seconds": 2})
        r = client.post("/api/source", json={"mode": "replay", "uuid": "et9erhx0si", "speed": 50})
        assert r.status_code == 200
        others: list[dict[str, Any]] = []
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and len(others) < 4:
            others = client.get("/api/state").json()["tv"]["others"]
            time.sleep(0.1)
        assert {o["uuid"] for o in others} >= {
            "pmch0rrshr",
            "ux4bplsxbh",
            "wffn21lxeb",
            "yklkh1aqmw",
        }
        assert client.post("/api/replay", json={"action": "seek", "to": "end"}).status_code == 200
        want = {
            "pmch0rrshr": (3, 2),
            "ux4bplsxbh": (5, 2),
            "wffn21lxeb": (1, 2),
            "yklkh1aqmw": (2, 4),
        }
        got: dict[str, tuple[int, int]] = {}
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            tv = client.get("/api/state").json()["tv"]
            got = {o["uuid"]: (o["score"]["home"], o["score"]["away"]) for o in tv["others"]}
            if all(got.get(k) == v for k, v in want.items()):
                break
            time.sleep(0.2)
        assert {k: got.get(k) for k in want} == want
        status = client.get("/api/state").json()["status"]
        assert status["others"]["games"] >= 4
