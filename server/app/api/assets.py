"""Team logos and player portraits, served from the local cache (app.feed.assets)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/assets")

CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


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
