"""REST API under /api (docs/PROTOCOL.md, REST)."""

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import __version__
from app.engine import webhooks as webhook_payloads
from app.feed.client import ShlError
from app.runtime import Runtime, SourceError

router = APIRouter(prefix="/api")


class GameIn(BaseModel):
    uuid: str | None
    # "none": no side is mine for this game; null: follow my team
    my_side: Literal["home", "away", "none"] | None = None


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


class CalibrateIn(BaseModel):
    kind: Literal["period_start", "goal", "penalty", "timeout", "shot_on_goal"]
    side: Literal["home", "away"] | None = None


class GoalIn(BaseModel):
    side: Literal["home", "away"]


class TestGoalIn(BaseModel):
    side: Literal["home", "away"] | None = None


class TestVideoIn(BaseModel):
    kind: Literal["goal", "intro", "pp"]
    side: Literal["home", "away"] | None = None


class EnabledIn(BaseModel):
    enabled: bool


class DimIn(BaseModel):
    level: float = Field(ge=0, le=0.9)


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


@router.get("/replays")
async def replays(request: Request) -> dict[str, Any]:
    """Games that can be replayed without the network, and saved recordings."""
    settings = runtime(request).settings
    fixtures = sorted(
        p.name.removeprefix("pbp_").removesuffix(".json")
        for p in settings.fixtures_dir.glob("pbp_*.json")
        if (settings.fixtures_dir / p.name.replace("pbp_", "game_info_")).exists()
    )
    base = settings.data_dir / "recordings"
    recordings = sorted(p.parent.name for p in base.glob("*/polls.jsonl")) if base.is_dir() else []
    return {"fixtures": fixtures, "recordings": recordings}


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
    except (ValueError, SourceError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return ok(rt)


@router.post("/calibrate")
async def calibrate(body: CalibrateIn, request: Request) -> dict[str, Any]:
    """A "Synka" press; the server stamps the time."""
    rt = runtime(request)
    press = rt.calibrate(body.kind, body.side)
    return {"press": press, **rt.calibration()}


@router.get("/calibrate")
async def calibration(request: Request) -> dict[str, Any]:
    return runtime(request).calibration()


@router.post("/calibrate/accept")
async def accept_calibration(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    try:
        rt.accept_calibration()
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return rt.calibration()


@router.post("/calibrate/goal-button")
async def goal_button_sync(body: EnabledIn, request: Request) -> dict[str, Any]:
    """Whether a linked MÅL! press counts as a goal sync sample."""
    rt = runtime(request)
    rt.config.goal_button_sync = body.enabled
    rt.store.save()
    return ok(rt)


@router.post("/idle-dim")
async def idle_dim(body: DimIn, request: Request) -> dict[str, Any]:
    """How much darker the screens are while idle (0 = not at all, 0.9 = nearly black)."""
    rt = runtime(request)
    rt.set_idle_dim(body.level)
    return ok(rt)


@router.delete("/calibrate")
async def clear_calibration(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    rt.clear_samples()
    return rt.calibration()


@router.delete("/calibrate/{sample_id}")
async def remove_sample(sample_id: str, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    try:
        rt.remove_sample(sample_id)
    except SourceError as exc:
        raise HTTPException(404, str(exc)) from exc
    return rt.calibration()


class WebhooksIn(BaseModel):
    url: str | None = None
    enabled: bool = False
    events: list[str] = list(webhook_payloads.EVENTS)


@router.get("/webhooks")
async def webhooks(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    return {"settings": rt.config.webhooks.model_dump(), "events": list(webhook_payloads.EVENTS)}


@router.post("/webhooks")
async def set_webhooks(body: WebhooksIn, request: Request) -> dict[str, Any]:
    """Home Assistant webhook: URL, on/off and which events."""
    rt = runtime(request)
    try:
        rt.set_webhooks(body.url, body.enabled, body.events)
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"settings": rt.config.webhooks.model_dump(), "status": rt.status()}


@router.get("/webhooks/log")
async def webhook_log(request: Request) -> dict[str, Any]:
    return {"log": list(runtime(request).webhooks.log)}


@router.post("/follow")
async def follow(body: EnabledIn, request: Request) -> dict[str, Any]:
    """ "Följ mitt lag": follow my team's game of the day by itself."""
    rt = runtime(request)
    try:
        await rt.set_follow(body.enabled)
    except (SourceError, ShlError) as exc:
        raise HTTPException(502, str(exc)) from exc
    return ok(rt)


@router.post("/goal")
async def manual_goal(body: GoalIn, request: Request) -> dict[str, Any]:
    """The MÅL! button: celebrate now; the feed goal behind it links when it arrives."""
    rt = runtime(request)
    return {"press": rt.manual_goal(body.side), "status": rt.status()}


@router.post("/test/goal")
async def test_goal(body: TestGoalIn, request: Request) -> dict[str, Any]:
    """A synthetic goal for my team (or the given side), at once, marked test."""
    rt = runtime(request)
    side = body.side or rt.my_side or "home"
    return {"press": rt.manual_goal(side, test=True), "status": rt.status()}


@router.post("/test/video")
async def test_video(body: TestVideoIn, request: Request) -> dict[str, Any]:
    """Play a team's goal or intro video now (one side, or both screens), or my team's
    power-play video on the bar; the video only."""
    return {"play_at_ms": runtime(request).test_video(body.kind, body.side)}


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


TV_PROBE_MAX_BYTES = 64_000


@router.post("/tv/probe")
async def tv_probe_save(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """The TV app's test page reports what works on the TV (docs/TV_APP.md, task 9.1)."""
    rt = runtime(request)
    text = json.dumps(
        {"received_ms": rt.clock.now_ms(), "report": body}, indent=2, ensure_ascii=False
    )
    if len(text.encode()) > TV_PROBE_MAX_BYTES:
        raise HTTPException(413, "report too large")
    path = request.app.state.settings.data_dir / "tv_probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return {"ok": True}


@router.post("/tv/start")
async def tv_start(request: Request) -> dict[str, Any]:
    """The TV app started: back to the defaults (my team's game today, else idle)."""
    rt = runtime(request)
    try:
        did = await rt.tv_start()
    except ShlError as exc:
        raise HTTPException(502, f"shl.se: {exc}") from exc
    return {"did": did, **ok(rt)}


@router.post("/tv/keepawake")
async def tv_keepawake(request: Request) -> dict[str, Any]:
    """One red key over the TV's network remote: Samsung's screen saver stays away while
    the TV app shows the L-frame (app/api/tvremote.py)."""
    remote = request.app.state.tv_remote
    if remote is None:
        return {"ok": False, "error": "ingen TV-adress (ARENA_TV_REMOTE)"}
    result: dict[str, Any] = await remote.press()
    return result


@router.post("/tv/probe-mode")
async def tv_probe_mode(body: EnabledIn, request: Request) -> dict[str, Any]:
    """Show the test page on the TV instead of the graphics (and back)."""
    rt = runtime(request)
    rt.set_tv_probe(body.enabled)
    return ok(rt)


@router.get("/tv/probe")
async def tv_probe_get(request: Request) -> dict[str, Any]:
    """The latest report from the TV app's test page, or 404."""
    path = request.app.state.settings.data_dir / "tv_probe.json"
    if not path.exists():
        raise HTTPException(404, "no report from the TV yet")
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@router.get("/wall")
async def wall(request: Request) -> Any:
    path = request.app.state.settings.config_dir / "wall.json"
    return json.loads(path.read_text(encoding="utf-8"))
