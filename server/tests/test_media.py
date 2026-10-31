"""Team videos: /media/<kind>/<uuid>.webm, your own in data/media before the defaults; the
TV app's animated WebP at /media/tv<kind>/<uuid>.webp."""

import json
from pathlib import Path

from conftest import FIXTURES
from fastapi.testclient import TestClient

from app.api.assets import media_path
from app.config import REPO_ROOT, Settings
from app.main import create_app

UUID = "3db0-3db09jXTE"


def put(root: Path, kind: str, body: bytes, ext: str = "webm") -> None:
    path = root / "media" / kind / f"{UUID}.{ext}"
    path.parent.mkdir(parents=True)
    path.write_bytes(body)


def test_own_video_wins_over_the_default(tmp_path: Path) -> None:
    data, web = tmp_path / "data", tmp_path / "web"
    put(web, "goal", b"default")
    assert media_path(data, web, "goal", UUID) == web / "media" / "goal" / f"{UUID}.webm"
    put(data, "goal", b"own")
    assert media_path(data, web, "goal", UUID) == data / "media" / "goal" / f"{UUID}.webm"
    assert media_path(data, web, "intro", UUID) is None


def test_only_known_kinds_and_plain_ids(tmp_path: Path) -> None:
    put(tmp_path, "goal", b"x")
    assert media_path(tmp_path, tmp_path, "other", UUID) is None
    assert media_path(tmp_path, tmp_path, "goal", "../goal/" + UUID) is None


def test_route(tmp_path: Path) -> None:
    data, web = tmp_path / "data", tmp_path / "web"
    web.mkdir()
    put(data, "intro", b"webm")
    settings = Settings(
        web_dir=web, config_dir=REPO_ROOT / "config", data_dir=data, fixtures_dir=FIXTURES
    )
    with TestClient(create_app(settings, fetch_league=False)) as client:
        r = client.get(f"/media/intro/{UUID}.webm")
        assert r.status_code == 200
        assert r.headers["content-type"] == "video/webm"
        assert r.headers["cache-control"] == "no-cache"  # a replaced file shows on reload
        assert r.content == b"webm"
        assert client.get(f"/media/goal/{UUID}.webm").status_code == 404


def test_tv_animations_are_webp_only(tmp_path: Path) -> None:
    data, web = tmp_path / "data", tmp_path / "web"
    web.mkdir()
    put(web, "tvpp", b"webp", ext="webp")
    own = web / "media" / "tvpp" / f"{UUID}.webp"
    assert media_path(data, web, "tvpp", UUID, ext="webp") == own
    # the wall's kinds are videos, the TV's are images
    assert media_path(data, web, "pp", UUID, ext="webp") is None
    assert media_path(data, web, "tvpp", UUID) is None
    settings = Settings(
        web_dir=web, config_dir=REPO_ROOT / "config", data_dir=data, fixtures_dir=FIXTURES
    )
    with TestClient(create_app(settings, fetch_league=False)) as client:
        r = client.get(f"/media/tvpp/{UUID}.webp")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/webp"
        assert r.headers["cache-control"] == "no-cache"
        assert client.get(f"/media/tvgoal/{UUID}.webp").status_code == 404


def test_default_videos_exist_for_every_team() -> None:
    teams = json.loads((REPO_ROOT / "config" / "teams.json").read_text(encoding="utf-8"))["teams"]
    for kind in ("goal", "intro", "pp"):
        missing = [
            u for u in teams if not (REPO_ROOT / "web" / "media" / kind / f"{u}.webm").is_file()
        ]
        assert not missing, (kind, missing)


def test_pages_are_revalidated(tmp_path: Path) -> None:
    web = tmp_path / "web"
    (web / "screens").mkdir(parents=True)
    (web / "screens" / "left.html").write_text("<html></html>")
    settings = Settings(
        web_dir=web, config_dir=REPO_ROOT / "config", data_dir=tmp_path, fixtures_dir=FIXTURES
    )
    with TestClient(create_app(settings, fetch_league=False)) as client:
        r = client.get("/screens/left.html")
        # browsers would otherwise keep old scene modules after an update
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
        again = client.get("/screens/left.html", headers={"if-none-match": r.headers["etag"]})
        assert again.status_code == 304
