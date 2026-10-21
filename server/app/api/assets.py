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

MEDIA_KINDS = ("goal", "intro")


@media_router.get("/{kind}/{uuid}.webm")
async def team_video(kind: str, uuid: str, request: Request) -> FileResponse:
    """A team's goal stinger or intro: ``data/media`` (your own) first, then the defaults
    in ``web/media`` made by tools/make_stingers.py."""
    settings = request.app.state.settings
    path = media_path(settings.data_dir, settings.web_dir, kind, uuid)
    if path is None:
        raise HTTPException(404, "no video")
    return FileResponse(path, media_type="video/webm", headers=CACHE_HEADERS)


def media_path(data_dir: Path, web_dir: Path, kind: str, uuid: str) -> Path | None:
    if kind not in MEDIA_KINDS or not SAFE_ID.match(uuid):
        return None
    for root in (data_dir / "media", web_dir / "media"):
        path = root / kind / f"{uuid}.webm"
        if path.is_file():
            return path
    return None
