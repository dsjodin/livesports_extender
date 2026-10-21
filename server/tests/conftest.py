import json
from pathlib import Path
from typing import Any

import httpx
import pytest

import shl_http as shl
from app.clock import FakeClock
from app.engine.normalizer import Normalizer
from app.engine.state import RawState, compute_state
from app.feed.sources import ReplaySource

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class LiveShl:
    """Fetches from shl.se once per URL per test session, to stay polite."""

    def __init__(self) -> None:
        self._client = httpx.Client(headers={"User-Agent": shl.USER_AGENT}, timeout=10.0)
        self._cache: dict[str, Any] = {}

    def get(self, url: str) -> Any:
        if url not in self._cache:
            response = self._client.get(url)
            response.raise_for_status()
            self._cache[url] = response.json()
        return self._cache[url]

    def close(self) -> None:
        self._client.close()


@pytest.fixture(scope="session")
def live_shl() -> Any:
    live = LiveShl()
    yield live
    live.close()


async def replay_to_end(
    uuid: str, on_snapshot: Any = None, **kwargs: Any
) -> tuple[Normalizer, RawState]:
    """Replay a fixture game on a fake clock through the normalizer; final state."""
    kwargs.setdefault("speed", 50)
    source = ReplaySource.from_fixtures(FIXTURES, uuid, FakeClock(), **kwargs)
    normalizer = Normalizer()
    async for snapshot in source:
        changes = normalizer.apply(snapshot)
        if on_snapshot is not None:
            on_snapshot(normalizer, changes, snapshot)
    state = compute_state(normalizer.events.values(), normalizer.game_state, normalizer.game_info)
    return normalizer, state
