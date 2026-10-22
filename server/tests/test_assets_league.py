from pathlib import Path
from typing import Any

import httpx
from conftest import load_fixture

from app.clock import FakeClock
from app.engine import league
from app.feed.assets import AssetCache, name_key, portrait_url
from app.feed.client import ShlClient
from app.feed.schedule import simplify
from app.feedtime import parse_utc_ms

LOGO = "https://sportality.cdn.s8y.se/team-logos/fhc1_fhc.svg"
FHC = "087a-087aTQv9u"
DIF = "2459-2459QTs1f"


def srcset(name: str) -> str:
    return ",\n".join(
        f"https://img.test/{name}.png?ixlib=x&w={w}&s=sig{w} {w}w" for w in (160, 320, 480, 640)
    )


ROSTER = [
    {
        "positionCode": "F",
        "players": [
            {
                "firstName": "Jacob",
                "lastName": "Peterson",
                "jerseyNumber": 44,
                "renderedLatestPortrait": {
                    "url": "https://img.test/jp.png?s=a",
                    "srcset": srcset("jp"),
                },
            },
            {
                "firstName": "Henrik",
                "lastName": "Tömmernes",
                "jerseyNumber": 7,
                "renderedLatestPortrait": {
                    "url": "https://img.test/ht.png?s=b",
                    "srcset": srcset("ht"),
                },
            },
        ],
    },
]


class Shl:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if url == LOGO:
            return httpx.Response(200, content=b"<svg/>")
        if "athletes/by-team-uuid" in url:
            return httpx.Response(200, json=ROSTER)
        if url.startswith("https://img.test/jp.png") and "w=480" in url:
            return httpx.Response(200, content=b"PNG-jp")
        if url.startswith("https://img.test/ht.png"):
            return httpx.Response(200, content=b"PNG-ht")
        return httpx.Response(404)


def cache(tmp_path: Path, shl: Shl) -> AssetCache:
    return AssetCache(tmp_path, lambda: ShlClient(transport=httpx.MockTransport(shl)), FakeClock())


async def test_logo_is_fetched_once(tmp_path: Path) -> None:
    shl = Shl()
    assets = cache(tmp_path, shl)
    assert await assets.team_logo(FHC) is None  # not registered yet
    assets.register_team(FHC, LOGO)
    path = await assets.team_logo(FHC)
    assert path is not None and path.read_bytes() == b"<svg/>"
    assert await assets.team_logo(FHC) == path and shl.calls.count(LOGO) == 1
    assert await assets.team_logo("../etc") is None


async def test_portraits_by_name_then_number(tmp_path: Path) -> None:
    shl = Shl()
    assets = cache(tmp_path, shl)
    assets.register_player("3770", FHC, "Jacob", "Peterson", "40")  # number changed since
    assets.register_player("1332", FHC, "Henrik", "Tommernes", "7")  # no diacritics in feed
    assets.register_player("9999", FHC, "Nobody", "Atall", "99")
    jp = await assets.player_portrait("3770")
    assert jp is not None and jp.read_bytes() == b"PNG-jp"
    ht = await assets.player_portrait("1332")
    assert ht is not None and ht.read_bytes() == b"PNG-ht"
    assert await assets.player_portrait("9999") is None
    assert await assets.player_portrait("unknown") is None
    assert sum("athletes" in c for c in shl.calls) == 1  # roster cached


def test_portrait_url_and_names() -> None:
    assert (
        portrait_url({"url": "u", "srcset": srcset("x")})
        == "https://img.test/x.png?ixlib=x&w=480&s=sig480"
    )
    assert portrait_url({"url": "plain"}) == "plain"
    assert name_key("Henrik", "Tömmernes") == name_key("henrik", "TOMMERNES") == "henriktommernes"


def games() -> list[dict[str, Any]]:
    return [simplify(g) for g in load_fixture("schedule_2026.json")["gameInfo"]]


def test_league_block_for_fhc_dif() -> None:
    start = parse_utc_ms("2026-10-20T17:00:00Z") or 0
    standings = league.standings_rows(load_fixture("standings_qa98unlbd6.json"))
    assert len(standings) == 14 and standings[0]["rank"] == 1
    block = league.build(
        standings,
        games(),
        start - 3600_000,
        home_uuid=FHC,
        away_uuid=DIF,
        start_ms=start,
        my_team_uuid="82eb-82ebmgaJ8",
    )
    fhc = block["teams"]["home"]
    assert fhc["points"] is not None and len(fhc["form"]) == 5
    dates = [f["date"] for f in fhc["form"]]
    assert dates == sorted(dates, reverse=True) and dates[0] < "2026-10-20"
    for f in fhc["form"]:
        own, other = (int(x) for x in f["score"].split("–"))
        assert f["result"] == ("V" if own > other else "F") and f["home_away"] in ("H", "B")
    tonight = {g["uuid"]: g for g in block["tonight"]}
    assert "mtn5yq64mp" in tonight and tonight["mtn5yq64mp"]["score"] is None
    nxt = block["my_team"]["next_game"]
    assert nxt and "82eb-82ebmgaJ8" in (nxt["home_uuid"], nxt["away_uuid"])
    assert all(g["score"] for g in block["recent"])
    meeting = block["last_meeting"]
    assert meeting is None or meeting["date"] < "2026-10-20"


# --- pregame slides: head-to-head and scoring leaders (Phase 8) -----------------------

SKE = "50e6-50e6DYeWM"
LHF = "1a71-1a71gTHKh"


def all_games() -> list[dict[str, Any]]:
    return [
        *(simplify(g) for g in load_fixture("schedule_2026.json")["gameInfo"]),
        *(simplify(g, "regular") for g in load_fixture("schedule_2025_regular.json")["gameInfo"]),
        *(simplify(g, "playoff") for g in load_fixture("schedule_2025_playoff.json")["gameInfo"]),
    ]


ET_START = parse_utc_ms("2026-10-17T13:15:00.000Z")


def test_head_to_head_over_seasons_and_playoffs() -> None:
    h2h = league.head_to_head(all_games(), FHC, LHF, ET_START)
    rows = [
        (r["date"], r["home"], r["score"], r["away"], r["playoff"], r["note"]) for r in h2h["games"]
    ]
    assert rows == [
        ("2026-09-24", "LHF", "3–7", "FHC", False, None),  # this season
        ("2026-04-02", "LHF", "1–0", "FHC", True, None),  # last spring's quarter-final
        ("2026-03-31", "FHC", "2–1", "LHF", True, None),
        ("2026-03-29", "LHF", "4–3", "FHC", True, "övertid"),
        ("2026-03-27", "LHF", "2–1", "FHC", True, "övertid"),
    ]
    assert h2h["wins"] == {"home": 2, "away": 3}  # home = FHC here


def test_head_to_head_with_fewer_meetings() -> None:
    h2h = league.head_to_head(all_games(), FHC, SKE, ET_START)
    assert [r["date"] for r in h2h["games"]] == [
        "2026-02-26",
        "2026-01-22",
        "2025-11-27",
        "2025-10-02",
    ]
    assert h2h["wins"] == {"home": 2, "away": 2}
    assert (
        league.head_to_head(all_games(), FHC, SKE, ET_START + 4 * 3600_000)["games"][0]["date"]
        == "2026-10-17"
    )  # the game itself once it is over


def test_leader_rows_and_the_block() -> None:
    raw = {
        FHC: {
            "points": load_fixture("leaders_points_fhc.json")[0]["stats"],
            "goals": load_fixture("leaders_goals_fhc.json")[0]["stats"],
        }
    }
    rows = league.leader_rows(raw[FHC]["points"], FHC)
    assert [(r["last"], r["number"], r["tp"], r["g"], r["a"]) for r in rows] == [
        ("Clarke", 9, 9, 4, 5),
        ("Fagemo", 11, 8, 4, 4),
        ("Westergård", 10, 8, 3, 5),
    ]
    assert rows[0]["athlete_uuid"] == "kczux7nz3f" and rows[0]["team_uuid"] == FHC
    standings = league.standings_rows(load_fixture("standings_qa98unlbd6.json"))
    games = [simplify(g) for g in load_fixture("schedule_2026.json")["gameInfo"]]
    block = league.build(
        standings, games, ET_START, home_uuid=FHC, away_uuid=SKE, start_ms=ET_START,
        history=all_games(), leaders=raw,
    )  # fmt: skip
    goals = block["teams"]["home"]["leaders"]["goals"]
    assert goals[0]["last"] in ("Clarke", "Fagemo") and goals[0]["g"] == 4
    assert "leaders" not in block["teams"]["away"]  # none fetched for SKE here
    assert len(block["head_to_head"]["games"]) == 4


async def test_league_history_and_leaders_cached(tmp_path: Path) -> None:
    from app.feed.league import LeagueService
    from app.feed.schedule import ScheduleService

    calls: list[str] = []
    filt = load_fixture("filter.json")
    seasons = {s["code"]: s["uuid"] for s in filt["season"]}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        season = request.url.params.get("season") or request.url.params.get("seasonUuid")
        if "game-types-filter" in url and season == seasons["2025"]:
            return httpx.Response(200, json=load_fixture("filter_2025.json"))
        if "game-types-filter" in url and season:  # this season and 2024: regular only here
            return httpx.Response(200, json=filt)
        if "game-types-filter" in url:
            return httpx.Response(200, json=filt)
        if "game-schedule" in url and season == seasons["2025"]:
            kind = "playoff" if request.url.params["gameTypeUuid"] == "qQ9-7debq38kX" else "regular"
            return httpx.Response(200, json=load_fixture(f"schedule_2025_{kind}.json"))
        if "game-schedule" in url:
            return httpx.Response(200, json={"gameInfo": []})
        if "team-standings" in url:
            return httpx.Response(200, json=load_fixture("standings_qa98unlbd6.json"))
        if "stats-info/players_point" in url:
            return httpx.Response(200, json=load_fixture("leaders_points_fhc.json"))
        if "stats-info/players_goal" in url:
            return httpx.Response(200, json=load_fixture("leaders_goals_fhc.json"))
        return httpx.Response(404)

    clock = FakeClock(auto_advance=False)

    def factory() -> ShlClient:
        return ShlClient(transport=httpx.MockTransport(handler))

    service = LeagueService(ScheduleService(factory, clock), factory, clock, tmp_path)
    history = await service.history()
    assert {g["game_type"] for g in history} == {"regular", "playoff"}
    assert len(history) == 364 + 44  # last season; this season's regular games are not in it
    assert (tmp_path / "schedules").is_dir()
    leaders = await service.leaders(FHC)
    assert [r["info"]["lastName"] for r in leaders["points"]] == ["Clarke", "Fagemo", "Westergård"]
    assert "teamUuid=087a-087aTQv9u" in next(c for c in calls if "players_point" in c)
    await clock.advance(2 * 3600_000)
    schedule_calls = sum("game-schedule" in c for c in calls)
    await service.history()  # an hour later: the finished seasons come from disk
    assert sum("game-schedule" in c for c in calls) == schedule_calls


async def test_athlete_portrait_by_uuid(tmp_path: Path) -> None:
    shl = Shl()
    ROSTER[0]["players"][0]["uuid"] = "qZk-athlete1"
    try:
        assets = cache(tmp_path, shl)
        # the name does not match (a nickname), the athlete uuid does
        assets.register_athlete("qZk-athlete1", FHC, "Jake", "Pete", "1")
        path = await assets.player_portrait("qZk-athlete1")
        assert path is not None and path.read_bytes() == b"PNG-jp"
    finally:
        del ROSTER[0]["players"][0]["uuid"]
