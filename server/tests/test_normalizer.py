import logging
from typing import Any

import pytest
from conftest import load_fixture

from app.engine.normalizer import Normalizer, game_seconds
from app.feed.snapshot import Snapshot
from app.feedtime import format_local, format_local_z

T = 1_760_000_000_000
INFO = load_fixture("game_info_bdhvuc5tex.json")


def ev(event_id: int, typ: str = "shot", **extra: Any) -> dict[str, Any]:
    item = {
        "eventId": event_id,
        "type": typ,
        "period": 1,
        "time": "04:33",
        "revision": 1,
        "gameState": "Ongoing",
        "gameUuid": "bdhvuc5tex",
        "realWorldTime": format_local(T - 30_000),
        "updatedTime": "2025-09-13T13:00:00",
        "eventTeam": {"place": "home", "teamCode": "FHC"},
        "player": {
            "playerId": "3770",
            "firstName": "Jacob",
            "familyName": "Peterson",
            "jerseyToday": "40",
        },
        "goalSection": 3,
    }
    item.update(extra)
    return item


def snap(pbp: list[dict[str, Any]] | None, at: int = T, **kwargs: Any) -> Snapshot:
    return Snapshot.at(at, INFO, pbp, **kwargs)


def kinds(changes: list[Any]) -> list[tuple[str, str | None]]:
    return [(c.kind, c.event.key if c.event else None) for c in changes]


def test_game_seconds() -> None:
    assert game_seconds(3, "09:07") == 2947
    assert game_seconds(4, "01:16") == 3676
    assert game_seconds("shootout", "00:00") is None
    assert game_seconds(1, "bad") is None


def test_added_updated_removed_and_first_seen() -> None:
    n = Normalizer()
    changes = n.apply(snap([ev(1)], age_s=4))
    assert kinds(changes) == [("added", "e1")]
    shot = changes[0].event
    assert shot is not None
    assert shot.first_seen_ms == T - 4000 and shot.received_ms == T
    assert shot.event_ms == T - 30_000
    assert shot.type == "shot" and shot.side == "home" and shot.team_code == "FHC"
    assert shot.team_uuid == "087a-087aTQv9u"
    assert shot.player and shot.player.number == "40" and shot.player.last == "Peterson"
    assert shot.data["on_goal"] is True and shot.game_seconds == 273

    # a new list with the same content: nothing
    assert n.apply(snap([ev(1)], at=T + 2000)) == []
    # gameState, attendance, updatedTime and realWorldTime changes are noise
    noisy = ev(
        1,
        gameState="Intermission",
        attendance=9000,
        updatedTime="2025-09-13T14:00:00",
        realWorldTime=format_local(T),
    )
    assert n.apply(snap([noisy], at=T + 4000)) == []
    # a real change keeps first_seen and event_ms
    changes = n.apply(snap([ev(1, revision=2, goalSection=-3)], at=T + 6000))
    assert kinds(changes) == [("updated", "e1")]
    updated = changes[0].event
    assert updated is not None and updated.revision == 2 and updated.data["on_goal"] is False
    assert updated.first_seen_ms == T - 4000 and updated.event_ms == T - 30_000
    assert updated.received_ms == T + 6000
    # removal, then reappearance as a new event
    assert kinds(n.apply(snap([], at=T + 8000))) == [("removed", "e1")]
    again = n.apply(snap([ev(1)], at=T + 10_000))
    assert kinds(again) == [("added", "e1")] and again[0].event
    assert again[0].event.first_seen_ms == T + 10_000


def test_same_list_object_is_skipped_and_none_ignored() -> None:
    n = Normalizer()
    pbp = [ev(1)]
    n.apply(snap(pbp))
    assert n.apply(snap(pbp, at=T + 2000)) == []
    assert n.apply(snap(None, at=T + 4000)) == []
    assert list(n.events) == ["e1"]


def test_goal_precursor_shot_is_removed() -> None:
    """Live pattern: a shot, then a goal (revision 2) by the same player, shot deleted."""
    n = Normalizer()
    n.apply(snap([ev(6)]))
    goal = ev(
        7,
        "goal",
        revision=2,
        homeGoals=1,
        awayGoals=0,
        goalStatus="EQ",
        assists={
            "first": {
                "playerId": "1",
                "firstName": "Max",
                "familyName": "Friberg",
                "jerseyToday": "12",
            }
        },
    )
    changes = n.apply(snap([goal, ev(6)], at=T + 20_000))
    assert kinds(changes) == [("added", "e7")]
    changes = n.apply(snap([goal], at=T + 22_000))
    assert kinds(changes) == [("removed", "e6")]
    g = n.events["e7"]
    assert g.type == "goal" and g.data["score"] == {"home": 1, "away": 0}
    assert g.data["assists"][0]["last"] == "Friberg" and g.data["strength"] == "EQ"


def test_periods_and_game_end() -> None:
    n = Normalizer()
    started = format_local_z(T - 25_000)
    period = {
        "type": "period",
        "period": 1,
        "started": True,
        "startedAt": started,
        "finished": False,
        "gameUuid": "bdhvuc5tex",
    }
    changes = n.apply(snap([ev(1), period]))
    assert kinds(changes) == [("added", "e1"), ("added", "period-1-start")]
    start = n.events["period-1-start"]
    assert start.type == "period_start" and start.event_ms == T - 25_000

    finished = period | {"finished": True, "finishedAt": format_local_z(T + 1_000_000)}
    ended = [ev(1, gameState="GameEnded"), finished]
    changes = n.apply(snap(ended, at=T + 1_020_000))
    assert kinds(changes) == [("added", "period-1-end"), ("added", "game-end")]
    end = n.events["period-1-end"]
    assert end.event_ms == T + 1_000_000
    assert end.data["next_period_estimate_ms"] == T + 1_000_000 + 18 * 60_000
    assert n.events["game-end"].data == {
        "final": {"home": 0, "away": 0},
        "overtime": False,
        "shootout": False,
    }
    assert n.game_state == "GameEnded"


def test_implausible_event_ms_is_dropped() -> None:
    n = Normalizer()
    ahead = ev(1, realWorldTime=format_local(T + 60_000))
    behind = ev(2, realWorldTime=format_local(T - 11 * 60_000))
    missing = ev(3, realWorldTime=None)
    n.apply(snap([ahead, behind, missing]))
    assert [n.events[k].event_ms for k in ("e1", "e2", "e3")] == [None, None, None]


def test_penalty_data() -> None:
    n = Normalizer()
    pen = ev(
        5,
        "penalty",
        offence="FIGHT",
        variant={
            "shortName": "Minor + Major + GM",
            "minorTime": "2",
            "majorTime": "5",
            "gMTime": "20",
            "description": "2 + 5 + GM",
        },
    )
    bench = ev(
        6, "penalty", offence="TOO-M", player=None, variant={"shortName": "Bench", "benchTime": "2"}
    )
    n.apply(snap([pen, bench]))
    data = n.events["e5"].data
    assert data["offence_text"] == "Slagsmål" and data["minutes"] == 27
    assert data["kind"] == "minor+major+game_misconduct" and data["segments_s"] == [120, 300]
    team = n.events["e6"].data
    assert team["kind"] == "bench_minor" and team["team_penalty"] is True
    assert team["offence_text"] == "För många spelare på isen"


def test_unknown_values_are_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    n = Normalizer()
    odd = [  # gameState is the same on every event in the feed
        ev(1, "hologram", gameState="Paused"),
        ev(2, "penalty", offence="ZZTOP", variant={"minorTime": "2"}, gameState="Paused"),
        ev(3, "goal", goalStatus="XX9", homeGoals=1, awayGoals=0, gameState="Paused"),
    ]
    with caplog.at_level(logging.WARNING):
        n.apply(snap(odd))
        n.apply(snap([*odd, ev(4, gameState="Paused")], at=T + 2000))
    messages = [r.getMessage() for r in caplog.records]
    for value in ("'hologram'", "'ZZTOP'", "'XX9'", "'Paused'"):
        assert sum(value in m for m in messages) == 1, value
    assert n.events["e1"].type == "unknown" and n.events["e1"].data["raw_type"] == "hologram"
    assert n.events["e2"].data["offence_text"] == "ZZTOP"


def test_epoch_change_resets() -> None:
    n = Normalizer()
    n.apply(snap([ev(1)]))
    changes = n.apply(snap([ev(2)], at=T + 2000, epoch=1))
    assert kinds(changes) == [("reset", None), ("added", "e2")]
    assert list(n.events) == ["e2"]
