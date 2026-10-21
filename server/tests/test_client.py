import httpx
import pytest

from app.feed.client import (
    USER_AGENT,
    ShlClient,
    ShlDecodeError,
    ShlHttpError,
    ShlNetworkError,
    ShlTimeout,
)


def client_for(handler: object) -> ShlClient:
    return ShlClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


async def test_requests_and_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"ok": True}, headers={"age": "7", "cf-cache-status": "HIT"}
        )

    async with client_for(handler) as client:
        response = await client.play_by_play("bdhvuc5tex")
        await client.schedule("s", "se", "gt")
        await client.game_info("g")
        await client.boxscore("g")
        await client.standings("ss")
        await client.site_settings()
        await client.filter()
    assert response.data == {"ok": True} and response.age_s == 7 and response.cache == "HIT"
    assert seen[0].headers["User-Agent"] == USER_AGENT
    assert USER_AGENT.startswith("shl-arena/") and USER_AGENT.endswith("(private home display)")
    assert [str(r.url) for r in seen] == [
        "https://www.shl.se/api/gameday/play-by-play/bdhvuc5tex",
        "https://www.shl.se/api/sports-v2/game-schedule?seasonUuid=s&seriesUuid=se"
        "&gameTypeUuid=gt&gamePlace=all&played=all",
        "https://www.shl.se/api/sports-v2/game-info/g",
        "https://www.shl.se/api/gameday/boxscore/g",
        "https://www.shl.se/api/gameday/team-standings/ss",
        "https://www.shl.se/api/site/settings",
        "https://www.shl.se/api/sports-v2/season-series-game-types-filter",
    ]


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(503, text="busy"), ShlHttpError),
        (httpx.Response(200, text="<html>"), ShlDecodeError),
    ],
)
async def test_typed_errors(response: httpx.Response, error: type[Exception]) -> None:
    async with client_for(lambda _: response) as client:
        with pytest.raises(error):
            await client.game_info("g")


@pytest.mark.parametrize(
    ("exc", "error"),
    [(httpx.ReadTimeout("slow"), ShlTimeout), (httpx.ConnectError("down"), ShlNetworkError)],
)
async def test_transport_errors(exc: Exception, error: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    async with client_for(handler) as client:
        with pytest.raises(error):
            await client.game_info("g")


async def test_missing_or_bad_age() -> None:
    async with client_for(lambda _: httpx.Response(200, json=[], headers={"age": "x"})) as c:
        assert (await c.play_by_play("g")).age_s is None


@pytest.mark.live
async def test_live_game_info() -> None:
    async with ShlClient() as client:
        response = await client.game_info("bdhvuc5tex")
    assert response.data["gameInfo"]["gameUuid"] == "bdhvuc5tex"
    assert response.data["homeTeam"]["score"] == 2
