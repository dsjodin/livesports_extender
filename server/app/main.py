"""FastAPI entry point: health check, page index and the static web/ mount."""

from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import Settings


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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="SHL Arena", version=__version__)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return render_index(list_pages(settings.web_dir))

    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


app = create_app()
