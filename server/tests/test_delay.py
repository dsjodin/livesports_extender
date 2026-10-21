from typing import Any

from app.engine.delay import DelayQueue
from app.engine.events import Change, NormalizedEvent

T = 1_760_000_000_000
S = 1000


def goal(key: str = "e7", event_ms: int | None = T, received: int = T + 48 * S, **kw: Any):
    data = {"score": {"home": 1, "away": 0}}
    fields: dict[str, Any] = {
        "key": key,
        "type": "goal",
        "raw_type": "goal",
        "period": 1,
        "time": "03:47",
        "game_seconds": 227,
        "event_id": int(key[1:]) if key[1:].isdigit() else 0,
        "data": data,
        "event_ms": event_ms,
        "first_seen_ms": received - 4 * S,
        "received_ms": received,
    }
    fields.update(kw)
    return NormalizedEvent(**fields)


def add(q: DelayQueue, e: NormalizedEvent) -> None:
    assert q.apply([Change("added", e)], e.received_ms) == []


def test_in_time_goal_plays_at_event_ms_plus_offset() -> None:
    q = DelayQueue(offset_ms=80 * S)
    e = goal()
    add(q, e)
    assert q.next_due_ms() == T + 80 * S - 1500
    assert q.due(T + 80 * S - 1501) == []
    [out] = q.due(T + 80 * S - 1500)
    assert out.kind == "release" and out.play_at == T + 80 * S and not out.late


def test_late_goal_plays_after_arrival_plus_lead() -> None:
    q = DelayQueue(offset_ms=40 * S)
    e = goal()  # seen 48 s after the on-ice moment, the TV showed it at 40 s
    add(q, e)
    [out] = q.due(e.received_ms)
    assert out.play_at == e.received_ms + 1500
    assert out.late and out.late_by_ms == 48 * S + 1500 - 40 * S


def test_formula_and_never_before_arrival() -> None:
    for offset in (0, 20, 40, 47, 49, 60, 90):
        for lag in (5, 19, 48, 78):
            q = DelayQueue(offset_ms=offset * S)
            e = goal(received=T + lag * S)
            add(q, e)
            now = e.received_ms
            outs = []
            while not outs:
                outs = q.due(now)
                now += 100
            [out] = outs
            expected = max(T + offset * S, e.received_ms + 1500)
            assert out.play_at == expected
            assert out.late == (e.received_ms + 1500 > T + offset * S)
            assert out.play_at - 1500 >= e.received_ms  # handed out no earlier than arrival


def test_missing_event_ms_is_late() -> None:
    q = DelayQueue(offset_ms=40 * S)
    e = goal(event_ms=None)
    add(q, e)
    [out] = q.due(e.received_ms)
    assert out.late and out.late_by_ms is None and out.play_at == e.received_ms + 1500


def test_removed_before_play_at_is_never_released() -> None:
    q = DelayQueue(offset_ms=80 * S)
    e = goal()
    add(q, e)
    assert q.apply([Change("removed", e)], e.received_ms + 10 * S) == []
    assert q.due(T + 200 * S) == [] and q.next_due_ms() is None


def test_update_before_release_keeps_play_at() -> None:
    q = DelayQueue(offset_ms=80 * S)
    e = goal()
    add(q, e)
    fixed = e.model_copy(update={"revision": 3, "received_ms": e.received_ms + 20 * S})
    assert q.apply([Change("updated", fixed)], fixed.received_ms) == []
    [out] = q.due(T + 80 * S)
    assert out.play_at == T + 80 * S and out.event is not None and out.event.revision == 3


def test_update_and_removal_after_release() -> None:
    q = DelayQueue(offset_ms=40 * S)
    e = goal()
    add(q, e)
    q.due(e.received_ms)
    now = e.received_ms + 80 * S
    fixed = e.model_copy(update={"player": None, "revision": 3})
    [upd] = q.apply([Change("updated", fixed)], now)
    assert upd.kind == "update" and upd.play_at == now + 1500 and upd.event == fixed
    [rem] = q.apply([Change("removed", fixed)], now + S)
    assert rem.kind == "remove" and rem.event == fixed
    assert q.released() == []


def test_offset_change_replans_pending_only() -> None:
    q = DelayQueue(offset_ms=60 * S)
    first = goal("e1", event_ms=T, received=T + 20 * S)
    second = goal("e2", event_ms=T + 30 * S, received=T + 50 * S)
    add(q, first)
    add(q, second)
    [out] = q.due(T + 60 * S)
    assert out.event == first and out.play_at == T + 60 * S
    q.set_offset(90 * S)
    assert q.released()[0].play_at == T + 60 * S  # untouched
    assert q.pending()[0].play_at == T + 120 * S
    q.set_offset(10 * S)  # now too late for the TV: plays after arrival
    p = q.pending()[0]
    assert p.play_at == second.received_ms + 1500 and p.late


def test_release_order_and_reset() -> None:
    q = DelayQueue(offset_ms=40 * S)
    a = goal("e5", event_ms=T, received=T + 10 * S)
    b = goal("e3", event_ms=T, received=T + 10 * S, game_seconds=100)
    add(q, a)
    add(q, b)
    outs = q.due(T + 40 * S)
    assert [o.event.key for o in outs if o.event] == ["e3", "e5"]
    [reset] = q.apply([Change("reset")], T + 50 * S)
    assert reset.kind == "reset" and q.items == {}
