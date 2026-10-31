"""Default goal stingers and intro videos per team (docs/PLAN.md Phase 8, docs/SCREENS.md).

Usage (from the repo root):

    uv run --project server python tools/make_stingers.py                 # all teams
    uv run --project server python tools/make_stingers.py --team 3db0-3db09jXTE --kind goal

Needs Playwright's Chromium (or ``--chromium /path/to/chrome``) and ffmpeg with libvpx-vp9 and
libwebp (the TV kinds).

Each frame is drawn by Chromium on a transparent background (GSAP timeline, seeked frame
by frame, so the result does not depend on how fast the machine renders) and the frames
are encoded to WebM VP9 with an alpha channel, silent (Home Assistant plays the sound,
decided 2026-10-21):

- ``web/media/goal/<team uuid>.webm``: 2.2 s, 1080×1920. Team-coloured and gold bands
  sweep over the screen, the logo and "MÅL!" pop, then everything sweeps out and the
  last frame is fully transparent, so the goal scene underneath shows through.
- ``web/media/intro/<team uuid>.webm``: 4.5 s, 1080×1920, before puck drop: the team's
  colour, logo, name and "MATCHSTART", ending transparent.
- ``web/media/pp/<team uuid>.webm``: 4 s, 1920×360, for the bar when my team gets a power
  play: slashes sweep across, the team colour wipes in, logo, "POWERPLAY" letter by
  letter, the team name, a light sweep and pulsing arrows, then out to the right.

For the Samsung TV app (docs/TV_APP.md, Videos) the same frames are encoded as animated
WebP with alpha, since a <video> on the TV takes the HDMI picture away:

- ``web/media/tvgoal/<team uuid>.webp``: 2 s, 1920×1080, bands sweep over the picture,
  logo, "MÅL!" and the team name, all gone by 1.8 s (the goal's lower third is underneath).
- ``web/media/tvintro/<team uuid>.webp``: 3 s, 1920×360, the power-play band with
  "MATCHSTART", low in the picture at puck drop (never over the whole of it).
- ``web/media/tvpp/<team uuid>.webp``: the bar's power-play band, 4 s, 1920×360.

Colours come from ``config/teams.json`` (home jersey first, away jersey as the accent),
logos from ``data/cache/teams/<uuid>.svg`` (the service's logo cache; a team without one
gets its name only). Your own videos go in ``data/media/<kind>/<uuid>.webm`` and win over
these (the service serves that file first).
"""

import argparse
import asyncio
import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, async_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FPS = 30
KINDS = ("goal", "intro", "pp", "tvgoal", "tvintro", "tvpp")
SIZE = {
    "goal": (1080, 1920),
    "intro": (1080, 1920),
    "pp": (1920, 360),
    "tvgoal": (1920, 1080),
    "tvintro": (1920, 360),
    "tvpp": (1920, 360),
}
DURATION_S = {"goal": 2.2, "intro": 4.5, "pp": 4.0, "tvgoal": 2.0, "tvintro": 3.0, "tvpp": 4.0}
WEBP_QUALITY = 70  # libwebp 0-100; the TV kinds
GOLD = "#F5C542"

PAGE = Path(__file__).with_name("stinger.html")  # the animation, filled in per team


def luminance(hex_: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def on_color(hex_: str) -> str:
    """Text on a team colour: the same rule as web/shared/format.js onColor."""
    return "#0B0F17" if contrast(hex_, "#0B0F17") >= contrast(hex_, "#F2F4F8") else "#F2F4F8"


def load_teams(path: Path) -> dict[str, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    palette = data.get("colors", {})

    def hex_(value: str | None, fallback: str) -> str:
        if not value:
            return fallback
        return value if value.startswith("#") else palette.get(value, fallback)

    return {
        uuid: {
            "name": t.get("name", uuid),
            "color": hex_(t.get("home"), "#8A93A6"),
            "accent": hex_(t.get("away"), "#F2F4F8"),
        }
        for uuid, t in data.get("teams", {}).items()
    }


def logo_uri(logos: Path, uuid: str) -> str | None:
    path = logos / f"{uuid}.svg"
    if not path.exists():
        return None
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()


def page_html(kind: str, team: dict[str, Any]) -> str:
    fonts = REPO_ROOT / "web" / "vendor" / "fonts"
    b64 = lambda p: base64.b64encode(p.read_bytes()).decode()  # noqa: E731
    values = {
        "c800": b64(fonts / "barlow-condensed-800.woff2"),
        "c700": b64(fonts / "barlow-condensed-700.woff2"),
        "gsap": (REPO_ROOT / "web" / "vendor" / "gsap" / "gsap.min.js").read_text(encoding="utf-8"),
        "team": json.dumps({**team, "kind": kind}),
    }
    html = PAGE.read_text(encoding="utf-8")
    for key, value in values.items():
        html = html.replace(f"@@{key}@@", value)
    return html


def encode_cmd(kind: str, frames: str, out: Path, crf: int) -> list[str]:
    """ffmpeg for the frames: VP9 with alpha for the wall, animated WebP for the TV (played
    once, no loop)."""
    if kind.startswith("tv"):
        return [
            "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", frames,
            "-c:v", "libwebp_anim", "-lossless", "0", "-q:v", str(WEBP_QUALITY),
            "-compression_level", "4", "-loop", "1", "-an", str(out),
        ]  # fmt: skip
    return [
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", frames,
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", str(crf),
        "-auto-alt-ref", "0", "-row-mt", "1", "-an", str(out),
    ]  # fmt: skip


async def render(browser: Browser, kind: str, team: dict[str, Any], out: Path, crf: int) -> None:
    # a fresh page per video: set_content writes into the same document otherwise
    width, height = SIZE[kind]
    page = await browser.new_page(viewport={"width": width, "height": height})
    page.on("pageerror", lambda e: print(f"page error: {e}", file=sys.stderr))
    await page.set_content(page_html(kind, team))
    # fonts and the logo are data URIs: wait until both are decoded
    ready = "document.fonts.status === 'loaded' && [...document.images].every((i) => i.complete)"
    await page.wait_for_function(ready, polling=50)
    frames = round(DURATION_S[kind] * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(frames):
            # the last frame lands on the end of the timeline: fully transparent
            await page.evaluate("t => window.seek(t)", i / (frames - 1) * DURATION_S[kind])
            await page.screenshot(path=f"{tmp}/f{i:04d}.png", omit_background=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(*encode_cmd(kind, f"{tmp}/f%04d.png", out, crf))
        if await proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed for {out}")
    await page.close()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--team", action="append", help="team uuid (default: all in teams.json)")
    parser.add_argument("--kind", choices=KINDS, action="append")
    parser.add_argument("--teams-file", type=Path, default=REPO_ROOT / "config" / "teams.json")
    parser.add_argument("--logos", type=Path, default=REPO_ROOT / "data" / "cache" / "teams")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "web" / "media")
    parser.add_argument("--crf", type=int, default=36, help="VP9 quality (lower is better)")
    parser.add_argument("--chromium", help="Chromium executable (default: Playwright's)")
    args = parser.parse_args()
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found", file=sys.stderr)
        return 1
    teams = load_teams(args.teams_file)
    uuids = args.team or list(teams)
    kinds = args.kind or list(KINDS)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=args.chromium)
        for uuid in uuids:
            if uuid not in teams:
                print(f"{uuid}: not in {args.teams_file}", file=sys.stderr)
                continue
            t = teams[uuid]
            logo = logo_uri(args.logos, uuid)
            team = {**t, "on": on_color(t["color"]), "gold": GOLD, "logo": logo}
            for kind in kinds:
                ext = "webp" if kind.startswith("tv") else "webm"
                out = args.out / kind / f"{uuid}.{ext}"
                await render(browser, kind, team, out, args.crf)
                note = "" if logo else " (no logo)"
                print(f"{kind:5} {t['name']:16} {out.stat().st_size / 1024:6.0f} kB  {out}{note}")
        await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
