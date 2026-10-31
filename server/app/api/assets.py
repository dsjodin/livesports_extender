"""Team logos and player portraits, served from the local cache (app.feed.assets)."""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/assets")

CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}
SAFE_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


@router.get("/teams/{uuid}.svg")
async def team_logo(uuid: str, request: Request) -> FileResponse:
    assets = request.app.state.runtime.assets
    path = await assets.team_logo(uuid) if assets else None
    if path is None:
        raise HTTPException(404, "no logo")
    return FileResponse(path, media_type="image/svg+xml", headers=CACHE_HEADERS)


@router.get("/players/{player_id}.png")
async def player_portrait(player_id: str, request: Request) -> FileResponse:
    assets = request.app.state.runtime.assets
    path = await assets.player_portrait(player_id) if assets else None
    if path is None:
        raise HTTPException(404, "no portrait")
    return FileResponse(path, media_type="image/png", headers=CACHE_HEADERS)


# --- videos (Phase 8) -----------------------------------------------------------------

media_router = APIRouter(prefix="/media")

MEDIA_KINDS = ("goal", "intro", "pp")
# The TV app's versions (docs/TV_APP.md, Videos): animated WebP, since a <video> on the TV
# takes its media player from the HDMI picture.
TV_MEDIA_KINDS = ("tvgoal", "tvintro", "tvpp")
# revalidated on every page load, so a replaced video shows after a reload (docs/VIDEOS.md)
MEDIA_HEADERS = {"Cache-Control": "no-cache"}


@media_router.get("/{kind}/{uuid}.webm")
async def team_video(kind: str, uuid: str, request: Request) -> FileResponse:
    """A team's goal stinger, intro or power-play video: ``data/media`` (your own) first,
    then the defaults in ``web/media`` made by tools/make_stingers.py."""
    settings = request.app.state.settings
    path = media_path(settings.data_dir, settings.web_dir, kind, uuid)
    if path is None:
        raise HTTPException(404, "no video")
    return FileResponse(path, media_type="video/webm", headers=MEDIA_HEADERS)


@media_router.get("/{kind}/{uuid}.webp")
async def team_animation(kind: str, uuid: str, request: Request) -> FileResponse:
    """The TV app's animated WebP of a team's goal, intro or power play, found as the
    videos are."""
    settings = request.app.state.settings
    path = media_path(settings.data_dir, settings.web_dir, kind, uuid, ext="webp")
    if path is None:
        raise HTTPException(404, "no animation")
    return FileResponse(path, media_type="image/webp", headers=MEDIA_HEADERS)


def media_path(
    data_dir: Path, web_dir: Path, kind: str, uuid: str, ext: str = "webm"
) -> Path | None:
    kinds = TV_MEDIA_KINDS if ext == "webp" else MEDIA_KINDS
    if kind not in kinds or not SAFE_ID.match(uuid):
        return None
    for root in (data_dir / "media", web_dir / "media"):
        path = root / kind / f"{uuid}.{ext}"
        if path.is_file():
            return path
    return None
