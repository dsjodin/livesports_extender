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
