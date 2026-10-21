"""Injectable clocks. Engine and source code take a ``Clock``; tests use ``FakeClock``."""

import asyncio
import heapq
import itertools
import time
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> int: ...

    async def sleep(self, seconds: float) -> None: ...


class RealClock:
    def now_ms(self) -> int:
        return time.time_ns() // 1_000_000

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))


class FakeClock:
    """Test clock. Time only moves when told to.

    With ``auto_advance`` (the default) every ``sleep`` jumps the clock to its own
    deadline at once, which suits a single task such as one source being iterated.
    Without it, sleepers wait until ``advance`` moves the clock past their deadline,
    which suits several tasks sharing one timeline.
    """

    def __init__(self, start_ms: int = 1_800_000_000_000, *, auto_advance: bool = True) -> None:
        self._now = start_ms
        self.auto_advance = auto_advance
        self._waiters: list[tuple[int, int, asyncio.Future[None]]] = []
        self._seq = itertools.count()

    def now_ms(self) -> int:
        return self._now

    async def sleep(self, seconds: float) -> None:
        deadline = self._now + max(0, round(seconds * 1000))
        if self.auto_advance:
            self._now = max(self._now, deadline)
            await asyncio.sleep(0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiters, (deadline, next(self._seq), future))
        await future

    async def advance(self, ms: int) -> None:
        """Move time forward by ``ms``, waking sleepers in deadline order."""
        target = self._now + ms
        while self._waiters and self._waiters[0][0] <= target:
            deadline, _, future = heapq.heappop(self._waiters)
            self._now = max(self._now, deadline)
            if not future.done():
                future.set_result(None)
            for _ in range(5):  # let the woken task run up to its next await
                await asyncio.sleep(0)
        self._now = target
