"""Phase 6: webhook payloads and the dispatcher (fires at play_at ± 50 ms, never before)."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from conftest import FIXTURES

from app.api.webhooks import WebhookDispatcher
from app.clock import FakeClock
from app.config import Settings, StateStore, WebhookSettings
from app.engine.events import NormalizedEvent, Player
from app.engine.webhooks import payload, tts_goal
from app.runtime import Runtime

T = 1_800_000_000_000
S = 1000
TEAMS = {
    "home": {"code": "FHC", "short": "Frölunda", "long": "Frölunda HC", "color": "#c8102e"},
    "away": {"code": "LHC", "short": "Linköping", "long": "Linköping HC", "color": "#f4f6f8"},
}
URL = "http://ha.local:8123/api/webhook/shl-arena"


def ev(typ: str, side: str | None = "home", **kw: Any) -> NormalizedEvent:
    fields: dict[str, Any] = {
        "key": "e96",
        "type": typ,
        "raw_type": typ,
        "game_uuid": "bdhvuc5tex",
        "period": 3,
        "time": "09:07",
        "side": side,
        "first_seen_ms": T,
        "received_ms": T,
    }
    return NormalizedEvent(**(fields | kw))


def goal(**kw: Any) -> NormalizedEvent:
    data = {
        "score": {"home": 2, "away": 1},
        "strength": "PP1",
        "empty_net": False,
        "assists": [{"first": "Dominik", "last": "Egli"}, {"first": "Ivar", "last": "Stenberg"}],
    }
    player = Player(id="6433", number="25", first="Arttu", last="Ruotsalainen")
    return ev("goal", player=player, data=data, **kw)


def test_goal_payload_as_documented() -> None:
    body = payload(goal(), TEAMS, "home", {"home": 2, "away": 1})
    assert body == {
        "event": "shl_goal",
        "game_uuid": "bdhvuc5tex",
        "test": False,
        "side": "home",
        "is_my_team": True,
        "team_code": "FHC",
        "team_name": "Frölunda HC",
        "team_color": "#c8102e",
        "team_rgb": [200, 16, 46],
        "source": "feed",
        "scorer": "Arttu Ruotsalainen",
        "scorer_number": "25",
        "assists": ["Dominik Egli", "Ivar Stenberg"],
        "strength": "PP1",
        "empty_net": False,
        "score_home": 2,
        "score_away": 1,
        "period": 3,
        "time": "09:07",
        "tts_sv": "Mål för Frölunda HC! Nummer 25, Arttu Ruotsalainen, i powerplay. Två–ett.",
    }
    away = payload(goal(), TEAMS, "away", {"home": 2, "away": 1})
    assert away is not None and away["is_my_team"] is False


def test_other_payloads() -> None:
    score = {"home": 2, "away": 1}
    pen = ev("penalty", "away", player=Player(number="8", first="Jonathan", last="Myrenberg"),
             data={"offence_text": "Holding", "minutes": 2})  # fmt: skip
    assert payload(pen, TEAMS, "home", score) == {
        "event": "shl_penalty", "game_uuid": "bdhvuc5tex", "test": False, "side": "away",
        "is_my_team": False, "player": "Jonathan Myrenberg", "number": "8",
        "offence_text": "Holding", "minutes": 2,
    }  # fmt: skip
    end = payload(ev("game_end", None, data={"final": score, "overtime": False, "shootout": False}),
                  TEAMS, "away", score)  # fmt: skip
    assert end is not None and end["winner_side"] == "home" and end["my_team_won"] is False
    start = payload(ev("period_start", None, period=2), TEAMS, None, score)
    assert start == {
        "event": "shl_period_start",
        "game_uuid": "bdhvuc5tex",
        "test": False,
        "period": 2,
    }
    assert payload(ev("shot"), TEAMS, "home", score) is None
    manual = ev("goal", data={"manual": True, "score": {"home": 1, "away": 0}}, time=None)
    assert (
        payload(manual, TEAMS, "home", {}, source="manual")["tts_sv"]
        == "Mål för Frölunda HC! Ett–noll."
    )  # type: ignore[index]
    scorer = Player(number="9", first="A", last="B")
    empty_net = {"empty_net": True, "score": {"home": 3, "away": 2}}
    expected = "Mål för Örebro Hockey! Nummer 9, A B, i tom bur. Tre–två."
    assert tts_goal("Örebro Hockey", empty_net, scorer) == expected


class HA:
    """Home Assistant: records when each call arrives (by the fake clock)."""

    def __init__(self, clock: FakeClock, fail_first: int = 0) -> None:
        self.clock = clock
        self.fail_first = fail_first
        self.calls: list[tuple[int, dict[str, Any]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((self.clock.now_ms(), json.loads(request.content)))
        if self.fail_first:
            self.fail_first -= 1
            return httpx.Response(500)
        return httpx.Response(200)


async def run_until(clock: FakeClock, ms: int, step: int = 10) -> None:
    while clock.now_ms() < ms:
        await clock.advance(step)
        for _ in range(20):
            await asyncio.sleep(0)


async def test_fires_at_play_at_never_before() -> None:
    clock = FakeClock(T, auto_advance=False)
    ha = HA(clock)
    settings = WebhookSettings(url=URL, enabled=True)
    hooks = WebhookDispatcher(clock, lambda: settings, transport=httpx.MockTransport(ha.handler))
    for i, delay in enumerate((1500, 2000, 4321)):
        assert hooks.schedule(T + delay, {"event": "shl_goal", "n": i})
    await run_until(clock, T + 1490)
    assert ha.calls == []  # not before play_at
    await run_until(clock, T + 5000)
    assert [b["n"] for _, b in ha.calls] == [0, 1, 2]
    for (at, body), delay in zip(ha.calls, (1500, 2000, 4321), strict=True):
        assert T + delay <= at <= T + delay + 50
        assert body["sent_ms"] == at
    assert [e["status"] for e in hooks.log] == [200, 200, 200]


async def test_one_retry_settings_and_cancel() -> None:
    clock = FakeClock(T, auto_advance=False)
    ha = HA(clock, fail_first=1)
    settings = WebhookSettings(url=URL, enabled=True, events=["shl_goal"])
    hooks = WebhookDispatcher(clock, lambda: settings, transport=httpx.MockTransport(ha.handler))
    assert not hooks.schedule(T, {"event": "shl_penalty"})  # not a chosen event
    assert hooks.schedule(T + 100, {"event": "shl_goal"})
    await run_until(clock, T + 3000)
    [entry] = hooks.log
    assert entry["attempts"] == 2 and entry["status"] == 200 and len(ha.calls) == 2
    assert ha.calls[1][0] - ha.calls[0][0] == 1000
    assert hooks.schedule(T + 10_000, {"event": "shl_goal"})
    hooks.cancel_pending()  # a replay seek
    await run_until(clock, T + 12_000)
    assert len(ha.calls) == 2
    settings.enabled = False
    assert not hooks.schedule(T + 20_000, {"event": "shl_goal"})


async def test_runtime_sends_one_goal_for_a_linked_button_press(tmp_path: Path) -> None:
    """MÅL! sends shl_goal (source manual) at once; the feed goal it links to sends none."""
    from test_runtime import goal as raw_goal  # the hand-made play-by-play items
    from test_runtime import period

    from app.feed.snapshot import Snapshot

    clock = FakeClock(T, auto_advance=False)
    ha = HA(clock)
    settings = Settings(
        web_dir=tmp_path, config_dir=tmp_path, data_dir=tmp_path, fixtures_dir=FIXTURES
    )
    store = StateStore(tmp_path / "state.json")
    store.config.profiles["iptv"] = 40.0
    store.config.webhooks = WebhookSettings(url=URL, enabled=True)
    rt = Runtime(clock, settings, store, type("Hub", (), {"broadcast": lambda *a, **k: None})(),
                 webhook_transport=httpx.MockTransport(ha.handler))  # fmt: skip
    rt.select_game("bdhvuc5tex", "home")
    info = json.loads((FIXTURES / "game_info_bdhvuc5tex.json").read_text(encoding="utf-8"))

    async def at(ms: int) -> None:
        while clock.now_ms() < ms:
            await run_until(clock, min(ms, clock.now_ms() + 250))
            rt.pump(clock.now_ms())

    await at(T + 5 * S)
    rt.on_snapshot(Snapshot.at(clock.now_ms(), info, [period(T)]))
    on_ice = T + 100 * S
    await at(on_ice + 40 * S)
    rt.manual_goal("home")
    await at(on_ice + 48 * S)
    rt.on_snapshot(Snapshot.at(clock.now_ms(), info, [raw_goal(7, on_ice, 1, 0), period(T)]))
    await at(on_ice + 60 * S)
    goals = [b for _, b in ha.calls if b["event"] == "shl_goal"]
    assert len(goals) == 1 and goals[0]["source"] == "manual" and goals[0]["score_home"] == 1
    starts = [b for _, b in ha.calls if b["event"] == "shl_period_start"]
    assert len(starts) == 1
    await rt.webhooks.close()
