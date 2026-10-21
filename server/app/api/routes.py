"""REST API under /api (docs/PROTOCOL.md, REST)."""

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import __version__
from app.feed.client import ShlError
from app.runtime import Runtime, SourceError

router = APIRouter(prefix="/api")


class GameIn(BaseModel):
    uuid: str | None
    my_side: Literal["home", "away"] | None = None


class SourceIn(BaseModel):
    mode: Literal["none", "replay", "recording", "live"]
    uuid: str | None = None
    path: str | None = None
    speed: float = 1.0


class ReplayIn(BaseModel):
    action: Literal["play", "pause", "speed", "seek"]
    speed: float | None = None
    to: str | None = None


class OffsetIn(BaseModel):
    profile: str
    seconds: float


class NudgeIn(BaseModel):
    delta: float


class ProfileIn(BaseModel):
    profile: str


class MyTeamIn(BaseModel):
    uuid: str | None


class TeamColorsIn(BaseModel):
    home: str | None = None
    away: str | None = None


class SceneIn(BaseModel):
    name: str
    hold_s: float | None = None


def runtime(request: Request) -> Runtime:
    return request.app.state.runtime  # type: ignore[no-any-return]


def ok(rt: Runtime) -> dict[str, Any]:
    return {"ok": True, "status": rt.status()}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/state")
async def state(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    return {"tv": rt.applied, "config": rt.config.model_dump(), "status": rt.status()}


@router.get("/schedule")
async def schedule(request: Request, days: int = 7) -> dict[str, Any]:
    try:
        games = await request.app.state.schedule.upcoming(days)
    except ShlError as exc:
        raise HTTPException(502, f"shl.se: {exc}") from exc
    return {"games": games}


@router.get("/schedule/recent")
async def schedule_recent(request: Request, days: int = 30) -> dict[str, Any]:
    try:
        games = await request.app.state.schedule.recent(days)
    except ShlError as exc:
        raise HTTPException(502, f"shl.se: {exc}") from exc
    return {"games": games}


@router.post("/game")
async def select_game(body: GameIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    rt.select_game(body.uuid, body.my_side)
    return ok(rt)


@router.post("/source")
async def set_source(body: SourceIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    if body.speed <= 0:
        raise HTTPException(400, "speed must be positive")
    try:
        await rt.set_source(body.mode, body.uuid, body.path, body.speed)
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc)) from exc
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ShlError as exc:
        raise HTTPException(502, f"shl.se: {exc}") from exc
    return ok(rt)


@router.post("/replay")
async def replay(body: ReplayIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    try:
        rt.replay_control(body.action, body.speed, body.to)
    except (SourceError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return ok(rt)


@router.post("/offset")
async def set_offset(body: OffsetIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    if not 0 <= body.seconds <= 600:
        raise HTTPException(400, "offset must be between 0 and 600 s")
    rt.set_offset(body.profile, body.seconds)
    return ok(rt)


@router.post("/offset/nudge")
async def nudge_offset(body: NudgeIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    if not 0 <= rt.config.offset_s + body.delta <= 600:
        raise HTTPException(400, "offset must stay between 0 and 600 s")
    rt.nudge_offset(body.delta)
    return ok(rt)


@router.post("/profile")
async def set_profile(body: ProfileIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    try:
        rt.set_profile(body.profile)
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ok(rt)


@router.post("/scene")
async def set_scene(body: SceneIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    try:
        rt.set_scene(body.name, body.hold_s)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ok(rt)


@router.delete("/scene")
async def clear_scene(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    rt.clear_scene()
    return ok(rt)


@router.post("/my-team")
async def set_my_team(body: MyTeamIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    if body.uuid is not None and body.uuid not in rt.colors.teams:
        raise HTTPException(404, f"unknown team {body.uuid!r}")
    rt.set_my_team(body.uuid)
    return ok(rt)


@router.get("/teams")
async def teams(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    return {"colors": rt.colors.palette, "teams": rt.colors.listing()}


@router.put("/teams/{uuid}")
async def set_team_colors(uuid: str, body: TeamColorsIn, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    if uuid not in rt.colors.teams:
        raise HTTPException(404, f"unknown team {uuid!r}")
    try:
        rt.set_team_colors(uuid, body.home, body.away)
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"team": next(t for t in rt.colors.listing() if t["uuid"] == uuid)}


@router.delete("/teams/{uuid}")
async def reset_team_colors(uuid: str, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    rt.reset_team_colors(uuid)
    return {"team": next((t for t in rt.colors.listing() if t["uuid"] == uuid), None)}


@router.get("/wall")
async def wall(request: Request) -> Any:
    path = request.app.state.settings.config_dir / "wall.json"
    return json.loads(path.read_text(encoding="utf-8"))
