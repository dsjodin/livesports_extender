"""FastAPI entry point: REST, WebSocket, page index and the static web/ mount."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from html import escape
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import ws
from app.api.assets import media_router
from app.api.assets import router as assets_router
from app.api.routes import router
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
    league = LeagueService(schedule, client_factory, clock) if fetch_league else None
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

    app = FastAPI(title="SHL Arena", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.runtime = runtime
    app.state.hub = hub
    app.state.schedule = schedule
    app.include_router(router)
    app.include_router(assets_router)
    app.include_router(media_router)

    @app.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        await ws.serve(socket, hub, runtime, clock)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return render_index(list_pages(settings.web_dir))

    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


app = create_app()
