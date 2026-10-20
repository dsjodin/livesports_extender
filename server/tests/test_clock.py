import asyncio

from app.clock import FakeClock, RealClock
from app.feedtime import (
    format_local,
    format_local_z,
    format_naive_utc,
    format_utc_z,
    parse_local_ms,
    parse_naive_utc_ms,
    parse_utc_ms,
)


async def test_fake_clock_auto_advance() -> None:
    clock = FakeClock(1000)
    await clock.sleep(2.5)
    assert clock.now_ms() == 3500
    await clock.sleep(-1)
    assert clock.now_ms() == 3500


async def test_fake_clock_advance_wakes_in_order() -> None:
    clock = FakeClock(0, auto_advance=False)
    woke: list[tuple[str, int]] = []

    async def sleeper(name: str, seconds: float) -> None:
        await clock.sleep(seconds)
        woke.append((name, clock.now_ms()))

    tasks = [asyncio.create_task(sleeper("b", 2)), asyncio.create_task(sleeper("a", 1))]
    await asyncio.sleep(0)
    await clock.advance(1500)
    assert woke == [("a", 1000)]
    await clock.advance(1000)
    assert woke == [("a", 1000), ("b", 2000)]
    assert clock.now_ms() == 2500
    await asyncio.gather(*tasks)


async def test_real_clock() -> None:
    clock = RealClock()
    before = clock.now_ms()
    await clock.sleep(0)
    assert clock.now_ms() >= before > 1_700_000_000_000


def test_feed_time_zones() -> None:
    # bdhvuc5tex: puck drop 13:15 UTC; period 1 startedAt "15:14:26.032Z" is local time.
    started = parse_local_ms("2025-09-13T15:14:26.032Z")
    assert started == parse_utc_ms("2025-09-13T13:14:26.032Z")
    assert parse_local_ms("2025-09-13T17:10:22.536784") == parse_naive_utc_ms(
        "2025-09-13T15:10:22.536784"
    )
    # Winter time is UTC+1.
    assert parse_local_ms("2026-01-10T19:00:00") == parse_utc_ms("2026-01-10T18:00:00Z")
    assert parse_local_ms(None) is None and parse_local_ms("nonsense") is None


def test_feed_time_round_trip() -> None:
    ms = parse_local_ms("2025-09-13T17:10:22.536000") or 0
    assert format_local(ms) == "2025-09-13T17:10:22.536000"
    assert format_local_z(ms) == "2025-09-13T17:10:22.536Z"
    assert format_naive_utc(ms) == "2025-09-13T15:10:22.536000"
    assert format_utc_z(ms) == "2025-09-13T15:10:22.536Z"
    assert parse_local_ms(format_local_z(ms)) == ms
