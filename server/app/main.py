"""FastAPI entry point: REST, WebSocket, page index and the static web/ mount."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from html import escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import ws
from app.api.assets import media_router
from app.api.assets import router as assets_router
from app.api.routes import router
from app.api.tvremote import TvRemote
from app.clock import Clock, RealClock
from app.config import Settings, StateStore
from app.feed.assets import AssetCache
from app.feed.client import ShlClient
from app.feed.league import LeagueService
from app.feed.schedule import ScheduleService
from app.runtime import Runtime


def list_pages(web_dir: Path) -> list[str]:
    """URL paths of the HTML pages under web/ (vendored files excluded)."""
    pages: list[str] = []
    for path in sorted(web_dir.rglob("*.html")):
        rel = path.relative_to(web_dir)
        if rel.parts[0] == "vendor":
            continue
        if rel.name == "index.html":
            parent = rel.parent.as_posix()
            pages.append("/" if parent == "." else f"/{parent}/")
        else:
            pages.append(f"/{rel.as_posix()}")
    return pages


def render_index(pages: list[str]) -> str:
    if pages:
        items = "\n".join(f'<li><a href="{escape(p)}">{escape(p)}</a></li>' for p in pages)
        body = f"<ul>\n{items}\n</ul>"
    else:
        body = "<p>Inga sidor ännu.</p>"
    return (
        '<!doctype html>\n<html lang="sv">\n<head><meta charset="utf-8">'
        "<title>SHL Arena</title></head>\n"
        f"<body>\n<h1>SHL Arena</h1>\n<p>Version {escape(__version__)}</p>\n{body}\n"
        "</body>\n</html>\n"
    )


class RevalidatedStaticFiles(StaticFiles):
    """The pages and their modules, revalidated on every load (``Cache-Control: no-cache``,
    a cheap 304 by ETag on the LAN). Without it browsers guess a freshness from the file's
    age and keep running old scene modules after an update."""

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    client_factory: Callable[[], ShlClient] = ShlClient,
    fetch_league: bool = True,
) -> FastAPI:
    """``fetch_league=False`` keeps the service from fetching standings and the schedule on
    its own, and from following my team (tests)."""
    settings = settings or Settings.from_env()
    clock = clock or RealClock()
    hub = ws.Hub()
    store = StateStore(settings.data_dir / "state.json")
    schedule = ScheduleService(client_factory, clock)
    assets = AssetCache(settings.data_dir / "cache", client_factory, clock)
    league = (
        LeagueService(schedule, client_factory, clock, settings.data_dir / "cache")
        if fetch_league
        else None
    )
    runtime = Runtime(
        clock,
        settings,
        store,
        hub,
        client_factory,
        assets=assets,
        league=league,
        schedule=schedule if fetch_league else None,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime.start()
        heartbeat = asyncio.get_running_loop().create_task(hub.heartbeat(clock))
        try:
            yield
        finally:
            heartbeat.cancel()
            await runtime.stop()
            if app.state.tv_remote is not None:
                await app.state.tv_remote.close()

    app = FastAPI(title="SHL Arena", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.runtime = runtime
    app.state.hub = hub
    app.state.schedule = schedule
    app.state.tv_remote = (
        TvRemote(settings.tv_remote_host, settings.data_dir) if settings.tv_remote_host else None
    )
    # The TV app's shell runs from file:// on the TV (Origin "null"). Only it may read the
    # service cross-origin, for the fallback that imports /tv/tv.js into the shell itself
    # (docs/TV_APP.md); the pages here are same-origin and need no CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["null"],
        allow_origin_regex=r"(file|app)://.*",
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
    app.include_router(router)
    app.include_router(assets_router)
    app.include_router(media_router)

    @app.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        await ws.serve(socket, hub, runtime, clock)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return render_index(list_pages(settings.web_dir))

    if settings.tv_app_dir and settings.tv_app_dir.is_dir():
        app.mount(
            "/tvapp", RevalidatedStaticFiles(directory=settings.tv_app_dir, html=True), name="tvapp"
        )
    app.mount("/", RevalidatedStaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


app = create_app()
