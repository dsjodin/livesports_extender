"""Measure how large the text on the three screens is on the wall, in millimetres.

Usage (from the repo root, with the service running):

    uv run --project server python tools/legibility.py [--distance 3] [--game et9erhx0si]

Plays ``--game`` to its end (a replay, so every list is full), then shows each scene in
turn (pregame, live, goal, intermission, postgame, idle) and, on each screen (the wall's
three and the TV app's overlay, ``tv`` in config/wall.json), measures every
element that holds text: its font, the cap height of that font (the height of an "H",
measured in the page) and so its cap height on the glass, from ``config/wall.json``
(millimetres per pixel). Text hidden for now (another intermission slide, a ticker page)
is measured too.

Thresholds, from the viewing distance (default 3 m, the far end of the sofa; the TV uses
its own, ``tv.viewing.distance_m``):

- minimum: 3.3 mm cap height per metre (10 mm at 3 m), the size below which text on a
  wall screen stops being readable at a glance (10-foot UI guidance for TVs);
- comfortable: 5 mm per metre (15 mm at 3 m), for anything meant to be read, not
  only recognised.

Writes ``artifacts/legibility.md`` (worst first) and prints a summary. Afterwards the
scene override is cleared and the previous source started again.
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENES = ["pregame", "live", "goal", "intermission", "postgame", "idle"]

MEASURE = """() => {
  const ctx = document.createElement("canvas").getContext("2d");
  const caps = new Map();
  const cap = (font) => {
    if (!caps.has(font)) {
      ctx.font = font;
      caps.set(font, ctx.measureText("H").actualBoundingBoxAscent);
    }
    return caps.get(font);
  };
  const out = [];
  for (const el of document.querySelectorAll("#app *")) {
    const own = [...el.childNodes]
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.trim())
      .join(" ")
      .trim();
    if (!own) continue;
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden") continue;
    const size = parseFloat(st.fontSize);
    const font = `${st.fontWeight} ${st.fontSize} ${st.fontFamily}`;
    const cls = [el.tagName.toLowerCase(), ...el.classList].join(".");
    out.push({ text: own.slice(0, 48), cls, size, cap: cap(font) });
  }
  return out;
}"""


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://localhost:8010")
    parser.add_argument("--game", default="et9erhx0si")
    parser.add_argument("--distance", type=float, default=3.0, help="viewing distance, m")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "artifacts" / "legibility.md")
    parser.add_argument("--chromium", help="Chromium executable (default: Playwright's)")
    parser.add_argument("--scene", action="append", choices=SCENES, help="only these scenes")
    args = parser.parse_args()

    wall = json.loads((REPO_ROOT / "config" / "wall.json").read_text(encoding="utf-8"))
    screens = {s["id"]: s for s in wall["screens"]}
    if wall.get("tv"):
        screens["tv"] = wall["tv"]
    mm_per_px = {i: s["physical_mm"][1] / s["resolution"][1] for i, s in screens.items()}
    distance = {
        i: s.get("viewing", {}).get("distance_m", args.distance) for i, s in screens.items()
    }
    minimum = {i: 3.3 * d for i, d in distance.items()}
    comfortable = {i: 5.0 * d for i, d in distance.items()}

    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=args.base + "/api/", timeout=10) as api:
        before = (await api.get("state")).json()["status"]["source"]
        await api.post("source", json={"mode": "replay", "uuid": args.game, "speed": 50})
        await api.post("replay", json={"action": "seek", "to": "end"})
        await asyncio.sleep(4)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=args.chromium)
            pages = {}
            for sid, s in screens.items():
                w, h = s["resolution"]
                page = await browser.new_page(viewport={"width": w, "height": h})
                await page.goto(f"{args.base}{s['page']}")
                pages[sid] = page
            await asyncio.sleep(2)
            for scene in args.scene or SCENES:
                await api.post("scene", json={"name": scene, "hold_s": 60})
                await asyncio.sleep(3.5)  # lead, cross-fade, entry animations
                for sid, page in pages.items():
                    for item in await page.evaluate(MEASURE):
                        mm = item["cap"] * mm_per_px[sid]
                        rows.append({**item, "scene": scene, "screen": sid, "mm": mm})
            await browser.close()
        await api.delete("scene")
        if before.get("mode") in ("replay", "recording", "live"):
            await api.post("source", json=before)
        else:
            await api.post("source", json={"mode": "none"})

    small = [r for r in rows if r["mm"] < minimum[r["screen"]]]
    medium = [r for r in rows if minimum[r["screen"]] <= r["mm"] < comfortable[r["screen"]]]
    limits = ", ".join(
        f"{i} at {distance[i]:g} m: minimum {minimum[i]:.0f} mm, "
        f"comfortable {comfortable[i]:.0f} mm"
        for i in screens
    )
    lines = [
        "# Legibility",
        "",
        f"Cap height on the glass. {limits}.",
        f"Text elements measured: {len(rows)}; below the minimum: {len(small)}; "
        f"between minimum and comfortable: {len(medium)}.",
        "",
        "| Scene | Screen | Element | Font px | Cap mm | Example |",
        "|---|---|---|---|---|---|",
    ]
    grouped: dict[tuple[str, str, str, float], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[(r["scene"], r["screen"], r["cls"], r["size"])].append(r)
    for (scene, sid, cls, size), items in sorted(grouped.items(), key=lambda kv: kv[1][0]["mm"]):
        mm = items[0]["mm"]
        flag = " ⚠" if mm < minimum[sid] else ""
        example = items[0]["text"].replace("|", "/")
        lines.append(f"| {scene} | {sid} | `{cls}` | {size:g} | {mm:.1f}{flag} | {example} |")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for sid in screens:
        mine = [r for r in rows if r["screen"] == sid]
        under = [r for r in mine if r["mm"] < minimum[sid]]
        sizes = sorted({round(r["mm"], 1) for r in mine})
        print(
            f"{sid:6} {len(mine):4} texts, {len(under):4} under {minimum[sid]:.0f} mm, "
            f"caps {sizes[:6]} … {sizes[-3:]}"
        )
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
