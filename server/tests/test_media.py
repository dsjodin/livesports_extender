"""Team videos: /media/<kind>/<uuid>.webm, your own in data/media before the defaults."""

import json
from pathlib import Path

from conftest import FIXTURES
from fastapi.testclient import TestClient

from app.api.assets import media_path
from app.config import REPO_ROOT, Settings
from app.main import create_app

UUID = "3db0-3db09jXTE"


def put(root: Path, kind: str, body: bytes) -> None:
    path = root / "media" / kind / f"{UUID}.webm"
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
        assert r.content == b"webm"
        assert client.get(f"/media/goal/{UUID}.webm").status_code == 404


def test_default_videos_exist_for_every_team() -> None:
    teams = json.loads((REPO_ROOT / "config" / "teams.json").read_text(encoding="utf-8"))["teams"]
    for kind in ("goal", "intro"):
        missing = [
            u for u in teams if not (REPO_ROOT / "web" / "media" / kind / f"{u}.webm").is_file()
        ]
        assert not missing, (kind, missing)
