"""One poll's worth of raw feed data."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Raw game-info and play-by-play as received, plus our own timing.

    ``available_ms`` is our estimate of when the play-by-play data became available:
    ``received_ms − Age × 1000`` (Cloudflare caches for 10 s), or ``received_ms`` when
    there is no Age header. New events take their ``first_seen_ms`` from it.
    ``epoch`` changes when a replay seeks; consumers then start over.
    ``feed_ms`` is the replay position on the original feed timeline (None when live).
    """

    received_ms: int
    game_info: dict[str, Any] | None
    pbp: list[dict[str, Any]] | None
    available_ms: int
    age_s: int | None = None
    epoch: int = 0
    feed_ms: int | None = None

    @classmethod
    def at(
        cls,
        received_ms: int,
        game_info: dict[str, Any] | None,
        pbp: list[dict[str, Any]] | None,
        *,
        age_s: int | None = None,
        epoch: int = 0,
        feed_ms: int | None = None,
    ) -> "Snapshot":
        available = received_ms - age_s * 1000 if age_s is not None else received_ms
        return cls(received_ms, game_info, pbp, available, age_s, epoch, feed_ms)
