"""Phase 4 acceptance in a real browser: the phone app driving the service, seen in /sim.

Usage (from the repo root, with the service running):

    uv run --project server python tools/check_phone.py [--chromium PATH]

1. Calibration: fake TV delay 75 s in /sim, system offset 60 s. For periods 1–3 the replay
   seeks to just before the period, and when the fake TV pane shows the period start the
   phone app's "Synka" (Nedsläpp) is tapped. The proposal must be 75 ± 0.5 s; "Använd"
   stores it, /sim's offset follows, and the next event plays 75 s after the ice.
2. MÅL! on a late goal: offset 40 s. The replay seeks to 10 s before a goal; the phone's
   MÅL! is tapped when a TV 40 s behind would show it (before the feed has it, as the
   replay feed shows goals 48 s after the ice). The screens start the goal scene once;
   the feed goal then links to it ("[sync] goal/linked"), with no second goal start.

Uses the bdhvuc5tex replay at 1x. Takes about 6 minutes. Restores the offset and source.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from typing import Any

import httpx
from playwright.async_api import Page, async_playwright

GAME = "bdhvuc5tex"
FAKE_TV_S = 75.0
START_OFFSET_S = 60.0
LATE_OFFSET_S = 40.0
SYNC_RE = re.compile(r"\[sync\] (\S+)(?: start)? screen=(\w+)")


async def post(client: httpx.AsyncClient, path: str, body: Any = None, method: str = "POST") -> Any:
    r = await client.request(method, f"/api/{path}", json=body)
    if r.status_code >= 400:
        raise SystemExit(f"{method} /api/{path} {body}: {r.status_code} {r.text}")
    return r.json()


async def wait_for(condition: Any, timeout_s: float, what: str) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = await condition()
        if value:
            return value
        await asyncio.sleep(0.05)
    raise SystemExit(f"timed out waiting for {what}")


async def calibration(client: httpx.AsyncClient, sim: Page, app: Page) -> bool:
    print("1. calibration: fake TV 75 s, offset 60 s, three period starts")
    await post(client, "offset", {"profile": "iptv", "seconds": START_OFFSET_S})
    await post(client, "calibrate", method="DELETE")
    await post(client, "source", {"mode": "replay", "uuid": GAME, "speed": 1})
    await app.click("[data-act=kind][data-kind=period_start]")
    for n in (1, 2, 3):
        await post(client, "replay", {"action": "seek", "to": f"period:{n}"})

        async def shown(n: int = n) -> bool:
            text = await sim.inner_text("#tv-events")
            return f"P{n} period_start" in text

        await wait_for(shown, 150, f"the fake TV showing period {n}")
        await app.click("[data-act=sync]")
        await asyncio.sleep(1.0)
        samples = (await post(client, "calibrate", method="GET"))["samples"]
        print(f"   period {n}: {samples[-1]['status']} {samples[-1]['sample_s']} s")
    cal = await post(client, "calibrate", method="GET")
    proposal = cal["proposal_s"]
    ok = proposal is not None and abs(proposal - FAKE_TV_S) <= 0.5
    print(
        f"   proposal {proposal} s from {cal['proposal_samples']} samples: {'ok' if ok else 'FAIL'}"
    )
    await app.click("[data-act=accept]")

    async def sim_offset() -> str | None:
        value = await sim.input_value("#offset")
        return value if abs(float(value) - (proposal or 0)) < 0.01 else None

    await wait_for(sim_offset, 10, "/sim to show the new offset")
    print(f"   /sim offset now {await sim.input_value('#offset')} s")

    # the next events play offset after the ice (not late)
    plays = await sim.evaluate(
        """() => new Promise((resolve) => {
          const url = `ws://${location.host}/ws?role=debug&id=check`;
          const ws = new WebSocket(url);
          const seen = [];
          ws.onmessage = (m) => {
            const msg = JSON.parse(m.data);
            if (msg.t === 'event' && !msg.event.late && msg.event.event_ms) {
              seen.push(msg.play_at_ms - msg.event.event_ms);
              if (seen.length >= 3) { ws.close(); resolve(seen); }
            }
          };
          setTimeout(() => { ws.close(); resolve(seen); }, 120000);
        })"""
    )
    aligned = bool(plays) and all(abs(d - (proposal or 0) * 1000) <= 1 for d in plays)
    print(
        f"   next events play {[round(d / 1000, 1) for d in plays]} s after the ice: "
        f"{'ok' if aligned else 'FAIL'}"
    )
    return ok and aligned


async def goal_button(
    client: httpx.AsyncClient, screens: list[Page], app: Page, log: list[str]
) -> bool:
    print("2. MÅL! with a late feed goal: offset 40 s")
    await post(client, "offset", {"profile": "iptv", "seconds": LATE_OFFSET_S})
    await post(client, "source", {"mode": "replay", "uuid": GAME, "speed": 1})
    await post(client, "replay", {"action": "seek", "to": "period:3"})
    await post(client, "replay", {"action": "seek", "to": "before_next_goal"})
    seek_at = time.monotonic()  # the goal is 10 s ahead on the ice
    await asyncio.sleep(1.0)
    state = (await client.get("/api/state")).json()["tv"]
    side = "home"  # FHC's 09:07 goal in bdhvuc5tex
    log.clear()
    await asyncio.sleep(max(0.0, seek_at + 10 + LATE_OFFSET_S - time.monotonic()))
    await app.click(f"[data-act=goal][data-side={side}]")
    pressed = time.monotonic()

    async def linked() -> bool:
        st = (await client.get("/api/state")).json()["status"]
        return any(p["status"] == "linked" and p.get("scorer") for p in st["manual"])

    await wait_for(linked, 60, "the feed goal to link")
    await asyncio.sleep(2.0)
    starts = [line for line in log if " goal start" in line or "goal/linked" in line]
    by_screen: dict[str, list[str]] = {}
    for line in starts:
        m = SYNC_RE.search(line)
        if m:
            by_screen.setdefault(m[2], []).append(m[1])
    took = time.monotonic() - pressed
    print(f"   linked {took:.1f} s after the press; screens: {json.dumps(by_screen)}")
    st = (await client.get("/api/state")).json()
    score = st["tv"]["score"]
    was = state["score"]
    print(f"   score {was['home']}–{was['away']} before, {score['home']}–{score['away']} after")
    once = all(v == ["goal", "goal/linked"] for v in by_screen.values()) and len(by_screen) == 3
    print(f"   one celebration, then linked: {'ok' if once else 'FAIL'}")
    return once


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--chromium", help="Chromium executable (default: Playwright's)")
    args = parser.parse_args()
    async with httpx.AsyncClient(base_url=args.base, timeout=30) as client:
        before = (await client.get("/api/state")).json()["config"]
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=args.chromium)
            sim_ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
            await sim_ctx.add_init_script(f"localStorage.setItem('sim.fakeDelay', '{FAKE_TV_S}')")
            sim = await sim_ctx.new_page()
            await sim.goto(f"{args.base}/sim/")
            phone = await browser.new_context(
                viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
            )
            app = await phone.new_page()
            await app.goto(f"{args.base}/app/")
            log: list[str] = []
            screens = []
            for screen, size in (
                ("left", (1080, 1920)),
                ("bar", (1920, 360)),
                ("right", (1080, 1920)),
            ):
                page = await browser.new_page(viewport={"width": size[0], "height": size[1]})
                page.on("console", lambda m: log.append(m.text))
                await page.goto(f"{args.base}/screens/{screen}.html")
                screens.append(page)
            await asyncio.sleep(2.0)
            try:
                ok = await calibration(client, sim, app)
                ok = await goal_button(client, screens, app, log) and ok
            finally:
                profile = before["active_profile"]
                await post(
                    client, "offset", {"profile": profile, "seconds": before["profiles"][profile]}
                )
                src = before["source"]
                await post(client, "source", src if src["mode"] != "none" else {"mode": "none"})
                await browser.close()
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
