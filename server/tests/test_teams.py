from pathlib import Path

from conftest import FIXTURES, load_fixture
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.engine.tvstate import GameMeta
from app.main import create_app
from app.teams import TeamColors

TEAMS = REPO_ROOT / "config" / "teams.json"


def test_config_covers_this_seasons_teams() -> None:
    colors = TeamColors(TEAMS)
    standings = load_fixture("standings_qa98unlbd6.json")["leagueStandings"]
    uuids = {t["info"]["teamInfo"]["teamUuid"] for t in standings}
    assert uuids == set(colors.teams)
    for uuid in uuids:
        for jersey in ("home", "away"):
            assert colors.hex(colors.jersey(uuid, jersey)), (uuid, jersey)


def test_home_team_wears_home_away_team_wears_away() -> None:
    meta = GameMeta.from_game_info(
        load_fixture("game_info_bdhvuc5tex.json"), None, None, TeamColors(TEAMS)
    )
    assert (meta.teams["home"]["jersey"], meta.teams["home"]["color"]) == ("röd", "#c8102e")
    assert (meta.teams["away"]["jersey"], meta.teams["away"]["color"]) == ("vit", "#f4f6f8")


def test_overrides_win_and_hex_is_allowed() -> None:
    colors = TeamColors(TEAMS, {"087a-087aTQv9u": {"home": "#00ff00"}})
    assert colors.hex(colors.jersey("087a-087aTQv9u", "home")) == "#00ff00"
    assert colors.jersey("087a-087aTQv9u", "away") == "vit"
    assert colors.valid("grön") and colors.valid("#A1B2C3") and not colors.valid("lila")


def test_rest(tmp_path: Path) -> None:
    settings = Settings(
        web_dir=tmp_path, config_dir=REPO_ROOT / "config", data_dir=tmp_path, fixtures_dir=FIXTURES
    )
    with TestClient(create_app(settings)) as client:
        listing = client.get("/api/teams").json()
        assert listing["colors"]["röd"] == "#c8102e" and len(listing["teams"]) == 14
        r = client.put("/api/teams/8e6f-8e6fUXJvi", json={"home": "röd", "away": "gul"})
        assert r.status_code == 200
        team = r.json()["team"]
        assert team["home"] == {"jersey": "röd", "color": "#c8102e"} and team["overridden"]
        assert client.put("/api/teams/8e6f-8e6fUXJvi", json={"home": "lila"}).status_code == 400
        assert client.put("/api/teams/nope", json={"home": "röd"}).status_code == 404
        assert '"8e6f-8e6fUXJvi"' in (tmp_path / "state.json").read_text()
        r = client.delete("/api/teams/8e6f-8e6fUXJvi")
        assert r.json()["team"]["home"]["jersey"] == "svart"  # back to config/teams.json
