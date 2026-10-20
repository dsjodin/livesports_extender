from pathlib import Path

from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app, list_pages


def make_client(web_dir: Path) -> TestClient:
    settings = Settings(web_dir=web_dir, config_dir=web_dir, data_dir=web_dir)
    return TestClient(create_app(settings))


def test_health(tmp_path: Path) -> None:
    response = make_client(tmp_path).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_index_without_pages(tmp_path: Path) -> None:
    response = make_client(tmp_path).get("/")
    assert response.status_code == 200
    assert "Inga sidor ännu" in response.text


def test_index_lists_existing_pages(tmp_path: Path) -> None:
    (tmp_path / "sim").mkdir()
    (tmp_path / "sim" / "index.html").write_text("<p>sim</p>")
    (tmp_path / "screens").mkdir()
    (tmp_path / "screens" / "bar.html").write_text("<p>bar</p>")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "demo.html").write_text("x")

    assert list_pages(tmp_path) == ["/screens/bar.html", "/sim/"]
    client = make_client(tmp_path)
    index = client.get("/").text
    assert 'href="/sim/"' in index and 'href="/screens/bar.html"' in index
    assert "vendor" not in index
    assert client.get("/sim/").text == "<p>sim</p>"
    assert client.get("/screens/bar.html").text == "<p>bar</p>"
