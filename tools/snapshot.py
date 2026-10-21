"""Snapshots of the three screens at native size, and the Phase 3 scene-flow check.

Usage (from the repo root, with the service running):

    uv run --project server python tools/snapshot.py               # snapshots
    uv run --project server python tools/snapshot.py --flow        # whole replay at 5x

Needs Playwright's Chromium: ``uv run --project server playwright install chromium``
(or ``--chromium /path/to/chrome``).

Snapshots: drives the service through its REST API with a replay of ``--game``, sets the
TV offset to 2 s, and saves left, bar and right at native resolution plus the /sim page
to ``artifacts/snapshots/``: pregame, live (P3 before 09:07, FHC power play), goal
(P3 09:07 + 2 s), intermission (after P2), postgame and idle. The goal sequence's
``[sync]`` lines from the three screens must be within 20 ms of play_at.

``--flow`` replays the whole game at ``--speed`` with the current offset and checks that
the screens go pregame → live → goals → intermissions → postgame, with every goal
sequence within 20 ms of its play_at on all three screens; other scene changes over
20 ms are listed.

Afterwards the TV offset is restored and the previous source started again.
"""

import argparse
import asyncio
import itertools
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import Browser, Page, async_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENS = {"left": (1080, 1920), "bar": (1920, 360), "right": (1080, 1920)}
SYNC_RE = re.compile(r"\[sync\] (\S+)(?: start)? screen=(\w+) delta=(-?[\d.]+)ms")
MAX_DELTA_MS = 20.0
SNAPSHOT_OFFSET_S = 2.0


class Wall:
    """The three screen pages at native size, plus the simulator, with their sync logs."""

    def __init__(self, browser: Browser, base: str) -> None:
        self.browser = browser
        self.base = base
        self.pages: dict[str, Page] = {}
        self.sim: Page | None = None
        self.sync: list[tuple[str, str, float]] = []  # (scene, screen, delta ms)
        self.slow: list[str] = []  # sync lines over MAX_DELTA_MS, with the local time
        self.errors: list[str] = []

    async def open(self) -> None:
        for screen, (w, h) in SCREENS.items():
            page = await self.browser.new_page(viewport={"width": w, "height": h})
            page.on("console", self._console)
            page.on("pageerror", lambda e, s=screen: self.errors.append(f"{s}: {e}"))
            await page.goto(f"{self.base}/screens/{screen}.html")
            self.pages[screen] = page
        self.sim = await self.browser.new_page(viewport={"width": 1600, "height": 1000})
        await self.sim.goto(f"{self.base}/sim/")

    def _console(self, message: Any) -> None:
        match = SYNC_RE.search(message.text)
        if match:
            self.sync.append((match[1], match[2], float(match[3])))
            if abs(float(match[3])) > MAX_DELTA_MS:
                self.slow.append(f"{time.strftime('%H:%M:%S')} {message.text}")

    async def wait_scene(self, name: str, timeout_s: float = 60) -> None:
        await asyncio.gather(
            *(
                p.wait_for_selector(f".scene-{name}:last-child", timeout=timeout_s * 1000)
                for p in self.pages.values()
            )
        )

    async def shoot(self, out: Path, name: str) -> None:
        await asyncio.to_thread(out.mkdir, parents=True, exist_ok=True)
        await asyncio.gather(
            *(p.screenshot(path=out / f"{name}-{s}.png") for s, p in self.pages.items())
        )
        if self.sim is not None:
            await self.sim.screenshot(path=out / f"{name}-sim.png")
        print(f"  {name}: {', '.join(f'{name}-{s}.png' for s in [*self.pages, 'sim'])}")


class Service:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = await self.client.post(f"/api/{path}", json=body)
        if r.status_code >= 400:
            raise SystemExit(f"POST /api/{path} {body}: {r.status_code} {r.text}")
        return r.json()  # type: ignore[no-any-return]

    async def state(self) -> dict[str, Any]:
        return (await self.client.get("/api/state")).json()  # type: ignore[no-any-return]

    async def replay(self, **body: Any) -> None:
        await self.post("replay", body)

    async def wait(self, condition: Any, timeout_s: float = 60) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            st = await self.state()
            if condition(st["tv"]):
                return st
            await asyncio.sleep(0.1)
        raise SystemExit("timed out waiting for the service")


def check_sync(sync: list[tuple[str, str, float]], scene: str | None = None) -> bool:
    rows = [r for r in sync if scene is None or r[0] == scene]
    worst = max((abs(d) for _, _, d in rows), default=0.0)
    screens = sorted({s for _, s, _ in rows})
    label = scene or "all scenes"
    where = ", ".join(screens) or "-"
    print(f"  sync {label}: {len(rows)} lines from {where}, worst {worst:.1f} ms")
    return bool(rows) and worst <= MAX_DELTA_MS and screens == sorted(SCREENS)


async def snapshots(svc: Service, wall: Wall, game: str, out: Path) -> bool:
    await svc.post("offset", {"profile": "iptv", "seconds": SNAPSHOT_OFFSET_S})
    await svc.post("profile", {"profile": "iptv"})
    await svc.post("source", {"mode": "replay", "uuid": game, "speed": 1})
    await wall.wait_scene("pregame")
    await asyncio.sleep(1.5)  # logos, entrance animations
    await wall.shoot(out, "pregame")

    # The replay feed shows events 35-48 s after the on-ice moment (like shl.se), so at
    # 5x the FHC power play (penalty P3 07:39) is on screen a little before the 09:07 goal.
    await svc.replay(action="seek", to="period:3")
    await svc.replay(action="seek", to="before_next_goal")
    await svc.replay(action="speed", speed=5)
    await svc.wait(
        lambda tv: (
            tv["period"] == 3
            and tv["strength"]["pp_side"] == "home"
            and tv["scene"]["name"] == "live"
            and not tv["scene"]["data"].get("overlay")
        )
    )
    await svc.replay(action="pause")
    await wall.wait_scene("live")
    await asyncio.sleep(1.0)
    await wall.shoot(out, "live")

    wall.sync.clear()
    await svc.replay(action="play")
    st = await svc.wait(lambda tv: tv["scene"]["name"] == "goal", timeout_s=90)
    since = st["tv"]["scene"]["since_ms"]
    await asyncio.sleep(max(0.0, (since + 2000) / 1000 - time.time()))
    await wall.shoot(out, "goal")
    goal_ok = check_sync(wall.sync, "goal")

    await svc.replay(action="seek", to="period:3")
    await wall.wait_scene("intermission")
    await svc.replay(action="pause")
    await asyncio.sleep(1.0)
    await wall.shoot(out, "intermission")

    await svc.replay(action="play")
    await svc.replay(action="seek", to="end")
    await wall.wait_scene("postgame")
    await svc.replay(action="pause")
    await asyncio.sleep(1.0)
    await wall.shoot(out, "postgame")

    await svc.post("source", {"mode": "none"})
    await svc.post("game", {"uuid": None})
    await wall.wait_scene("idle")
    await asyncio.sleep(1.5)
    await wall.shoot(out, "idle")
    return goal_ok


async def flow(svc: Service, wall: Wall, game: str, speed: float) -> bool:
    """The whole replay; scene order from the bar's sync log."""
    wall.sync.clear()
    await svc.post("source", {"mode": "replay", "uuid": game, "speed": speed})
    await wall.wait_scene("pregame")
    started = time.monotonic()
    await svc.wait(lambda tv: tv["scene"]["name"] == "postgame", timeout_s=4 * 3600)
    await asyncio.sleep(1.0)
    order: list[str] = ["pregame"]
    for scene, screen, _ in wall.sync:
        name = scene.split("/")[0]
        if screen == "bar" and name != order[-1]:
            order.append(name)
    print(f"  {(time.monotonic() - started) / 60:.1f} min: {' → '.join(order)}")
    expected = ["pregame", "live", "goal", "intermission", "postgame"]
    in_order = all(s in order for s in expected) and all(
        order.index(s) < order.index(t) for s, t in itertools.pairwise(expected)
    )
    # The acceptance is about the goal sequence; other scene changes are reported.
    ok = check_sync(wall.sync, "goal") and in_order
    for scene in sorted({s for s, _, _ in wall.sync} - {"goal"}):
        check_sync(wall.sync, scene)
    for line in wall.slow:
        print(f"  over {MAX_DELTA_MS:.0f} ms: {line}")
    return ok


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--game", default="bdhvuc5tex")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "artifacts" / "snapshots")
    parser.add_argument("--flow", action="store_true", help="check the whole replay instead")
    parser.add_argument("--speed", type=float, default=5.0, help="replay speed for --flow")
    parser.add_argument("--chromium", help="Chromium executable (default: Playwright's)")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=30) as client:
        svc = Service(client)
        before = await svc.state()
        config = before["config"]
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=args.chromium)
            wall = Wall(browser, args.base)
            await wall.open()
            try:
                if args.flow:
                    ok = await flow(svc, wall, args.game, args.speed)
                else:
                    ok = await snapshots(svc, wall, args.game, args.out)
            finally:
                profile = config["active_profile"]
                await svc.post(
                    "offset", {"profile": profile, "seconds": config["profiles"][profile]}
                )
                src = config["source"]
                if src["mode"] != "none":
                    await svc.post("source", src)
                await browser.close()
        for error in wall.errors:
            print(f"  page error: {error}")
    print("OK" if ok and not wall.errors else "FAILED")
    return 0 if ok and not wall.errors else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
