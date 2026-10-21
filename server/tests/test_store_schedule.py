from pathlib import Path

import httpx
from conftest import load_fixture

from app.clock import FakeClock
from app.config import RuntimeConfig, StateStore
from app.feed.client import ShlClient
from app.feed.schedule import ScheduleService
from app.feedtime import parse_utc_ms


def test_store_round_trip(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    assert store.config == RuntimeConfig() and store.config.offset_s == 40.0
    store.config.game_uuid = "abc"
    store.config.profiles["iptv"] = 38.5
    store.save()
    again = StateStore(tmp_path / "state.json")
    assert again.config.game_uuid == "abc" and again.config.offset_s == 38.5


def test_store_survives_a_broken_file(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text("{not json")
    assert StateStore(tmp_path / "state.json").config == RuntimeConfig()


async def test_schedule_is_cached_for_an_hour() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("season-series-game-types-filter"):
            return httpx.Response(200, json=load_fixture("filter.json"))
        return httpx.Response(200, json=load_fixture("schedule_2026.json"))

    now = parse_utc_ms("2026-10-20T12:00:00Z") or 0
    clock = FakeClock(now)
    service = ScheduleService(lambda: ShlClient(transport=httpx.MockTransport(handler)), clock)
    today = await service.upcoming(0)
    assert "mtn5yq64mp" in [g["uuid"] for g in today]
    game = next(g for g in today if g["uuid"] == "mtn5yq64mp")
    assert game["home"]["code"] == "FHC" and game["arena"] == "Scandinavium"
    assert game["start_ms"] == parse_utc_ms("2026-10-20T17:00:00Z")
    recent = await service.recent(30)
    assert recent and all(g["state"] == "post-game" for g in recent)
    assert recent[0]["start_ms"] >= recent[-1]["start_ms"]
    assert len(calls) == 2  # one fetch served three calls
    await clock.sleep(3601)
    await service.upcoming(7)
    assert len(calls) == 4
