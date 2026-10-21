# Protocol: REST, WebSocket and webhooks

All times are integers in **milliseconds since the Unix epoch, server clock** (`*_ms`),
unless a field is a game time (`"MM:SS"` within a period) or a display string.

## Normalized event

The engine's internal event shape, also sent to clients inside `event` messages.

```json
{
  "key": "e96",
  "type": "goal",
  "game_uuid": "bdhvuc5tex",
  "period": 3,
  "time": "09:07",
  "game_seconds": 2947,
  "side": "home",
  "team_uuid": "087a-087aTQv9u",
  "team_code": "FHC",
  "player": {"id": "6433", "number": "25", "first": "Arttu", "last": "Ruotsalainen"},
  "data": {
    "score": {"home": 2, "away": 1},
    "strength": "PP1",
    "empty_net": false,
    "penalty_shot": false,
    "assists": [{"number": "46", "first": "Dominik", "last": "Egli"},
                {"number": "41", "first": "Ivar", "last": "Stenberg"}],
    "on_ice": [{"number": "1", "first": "Lars", "last": "Johansson"}, "..."],
    "scorer_game_goals": 1
  },
  "revision": 3,
  "event_ms": 1757776222536,
  "first_seen_ms": 1757776270100,
  "received_ms": 1757776275100,
  "late": false,
  "test": false
}
```

`type` values: `goal`, `shot`, `penalty`, `goalie_change`, `timeout`, `period_start`,
`period_end`, `game_end`, `shootout_attempt`, `unknown` (an unrecognised raw type, logged
once, `data.raw_type` holds it), plus the correction `goal_disallowed`. `raw_type` is the
feed's type. Keys: `e<eventId>`, `period-<n>-start`, `period-<n>-end`, `game-end`.
`period` is an int, or `"shootout"`.

- `event_ms`: the on-ice moment from the feed (`realWorldTime`, or `startedAt` /
  `finishedAt` for periods), parsed as Europe/Stockholm. `null` if missing or implausible.
- `first_seen_ms`: `received_ms − Age × 1000` of the first poll containing the event.
- `late`: the event arrived too late to play at `event_ms + offset` (see CLAUDE.md rule 2);
  `late_by_ms` says by how much.
- A goal linked to a MÅL! press carries `"manual_key": "m3"`.

Type-specific `data`:

| type | data |
|---|---|
| `goal` | as in the example, plus `opponents_on_ice`, `shootout`, `x_dm`, `y_dm`, `goal_section` |
| `shot` | `x_dm`, `y_dm`, `goal_section`, `on_goal` (bool), `result` (`on_goal`, `wide` = "utanför", `blocked` = "täckt", `unknown`; see `docs/SHL_API.md`), `penalty_shot` |
| `penalty` | `offence_code`, `offence_text` (Swedish), `minutes` (PIM), `kind` (minor, bench_minor, double_minor, major, match, misconduct, game_misconduct, penalty_shot, joined with `+`), `segments_s` (shorthanded parts in order), `variant`, `description`, `penalty_shot_awarded`, `team_penalty`. Expiry is in the state, not the event. |
| `shootout_attempt` | `scored`, `index`, `shootout_score`, `game_winning` |
| `goalie_change` | `entering` (bool) |
| `period_end` | `next_period_estimate_ms` (period end + 18 min, labelled as an estimate) |
| `game_end` | `final` score, `overtime`, `shootout` |
| `goal_disallowed` | `original_key`, `score` after correction |

## TV state

The delayed state every client renders. Sent in full on connect, then as patches.

```json
{
  "rev": 412,
  "game": {"uuid": "bdhvuc5tex", "arena": "Scandinavium", "attendance": 12044,
           "start_ms": 1757769300000, "my_side": "home"},
  "teams": {
    "home": {"uuid": "087a-087aTQv9u", "code": "FHC", "short": "Frölunda", "long": "Frölunda HC",
             "color": "#34D399", "icon": "https://sportality.cdn.s8y.se/team-logos/fhc1_fhc.svg"},
    "away": {"uuid": "41c4-41c4BiYZU", "code": "LHC", "short": "Linköping", "long": "Linköping HC",
             "color": "#5B8CFF", "icon": "https://sportality.cdn.s8y.se/team-logos/lhc1_lhc.svg"}
  },
  "phase": "live",
  "period": 3,
  "period_running": true,
  "last_game_time": "08:16",
  "score": {"home": 1, "away": 1},
  "strength": {"home": 5, "away": 4, "pp_side": "home"},
  "penalties_active": [{"key": "e94", "side": "away", "number": "8", "name": "Jonathan Myrenberg",
                        "offence_text": "Fasthållning", "minutes": 2, "started": "P3 07:39",
                        "expires_game_seconds": 2979}],
  "stats": {
    "home": {"shots_on_goal": 36, "shots_wide": 5, "shots_blocked": 7, "shot_attempts": 48, "shots_by_period": [16, 15, 5], "pim": 2,
             "pp": {"goals": 0, "chances": 3}, "goalie": {"number": "1", "name": "Lars Johansson",
             "saves": 25, "shots_against": 26, "on_ice": true}},
    "away": {"...": "same shape"}
  },
  "shots": {"home": [{"x_dm": 50, "y_dm": -74, "result": "on_goal", "goal": false, "period": 1}, "..."],
            "away": ["..."]},
  "goals": ["... normalized goal events in order ..."],
  "penalties": ["... normalized penalty events in order ..."],
  "shootout": ["... shootout attempts ..."],
  "recent": ["... last 10 played events (not shots): key, type, period, time, side, label, play_at_ms ..."],
  "ended": false, "overtime": false, "went_to_shootout": false,
  "scene": {"name": "live", "since_ms": 1757775000000, "hold_ms": null, "data": {},
            "override": false}
}
```

`phase`: `idle`, `pregame`, `live`, `intermission`, `postgame`.

Notes: `strength` also has `label` (`"5v4"`; a pulled goalie adds a skater). `stats.*.goalie`
is per team (the goalie on the ice now, the team's saves and shots against; empty-net
goals excluded) and has `pulled`. `shots` skips coordinates outside 0–300 dm. `GET
/api/state` returns `{"tv": <this>, "config": <persisted settings>, "status": {...}}`.

## WebSocket

Endpoint: `/ws?role=screen|sim|phone|debug&id=<screen id or client name>`

### Server to client

```json
{"t": "hello", "server_ms": 1760000000000, "role": "screen", "id": "left",
 "config": {"offset_ms": 40000, "lead_ms": 1500, "profile": "iptv", "debug": false}}

{"t": "state", "state": { "... full TV state ..." }}

{"t": "state_patch", "rev": 413, "play_at_ms": 1760000031500,
 "patch": {"score": {"home": 2, "away": 1}, "strength": {"home": 5, "away": 5, "pp_side": null}}}

{"t": "event", "play_at_ms": 1760000031500, "event": { "... normalized event ..." }}

{"t": "event_update", "play_at_ms": 1760000033000, "event": { "... corrected event ..." }}

{"t": "scene", "play_at_ms": 1760000031500,
 "scene": {"name": "goal", "hold_ms": 20000, "data": {"event_key": "e96", "side": "home"}}}

{"t": "clock_pong", "t0": 1760000000000, "server_ms": 1760000000012}

{"t": "heartbeat", "server_ms": 1760000010000}
```

- Every visible change carries `play_at_ms`. Clients apply it at that moment, never on receipt.
- `config.offset_ms` is the TV's delay behind the arena (the on-ice moment), not behind
  our receive time.
- `event_update` corrects an event that has already played (for example a goal's scorer);
  clients update the visible text without replaying the animation.
- Messages are sent `lead_ms` before `play_at_ms` (default 1500 ms) so clients can preload.
- `event` and `event_update` bodies carry `late` and `late_by_ms` (null when not late or
  when `event_ms` was missing).
- A goal removed after it played becomes an `event` of type `goal_disallowed` (key
  `<key>-disallowed`); any other event removed after it played only changes the state
  (`state_patch`), for example a precursor shot that turned into a goal.
- On connect a client gets `hello`, then `state` (only what has reached its `play_at`),
  then every message still waiting for its `play_at`, in order. A replay seek or a new
  source sends a fresh `state` to everyone.
- `{"t": "config", "config": {...}}` when the offset or TV profile changes.
- Non-screen clients (sim, phone, debug) get `{"t": "status", "status": {...}}` about once
  a second: source mode, uuid, speed, running, paused, replay position (`feed_ms`), error,
  selected game, my side, profile, offset, counts.
- Raw (undelayed) normalizer changes go only to sim, phone and debug clients that sent
  `debug_subscribe` (CLAUDE.md rule 1): first `{"t": "raw_backlog", "raw": [...],
  "released": [...]}`, then `{"t": "raw", "entry": {"change", "key", "type", "label",
  "event_ms", "first_seen_ms", "received_ms", "at_ms"}}` per change.

### Client to server

```json
{"t": "clock_ping", "t0": 1760000000000}
{"t": "debug_subscribe"}
{"t": "debug_unsubscribe"}
```

Clock sync: the client sends `clock_ping` every 2 s for the first 10 s, then every 30 s.
For each pong, `rtt = now - t0` and `offset = server_ms - (t0 + now) / 2`. Use the median
offset of the 5 samples with the lowest RTT.

## REST

All under `/api`. JSON in and out. No authentication (LAN only; put a reverse proxy with
auth in front if it is ever exposed).

| Method and path | Body / query | Purpose |
|---|---|---|
| `GET /api/health` | | `{"status":"ok","version":...}` |
| `GET /api/state` | | Full TV state plus config and source status |
| `GET /api/schedule?days=7` | | Games from today and the next N days, from cache |
| `GET /api/schedule/recent?days=30` | | Finished games (for replay selection) |
| `POST /api/game` | `{"uuid", "my_side": "home"\|"away"\|null}` | Select a game to follow |
| `POST /api/source` | `{"mode": "live"\|"replay"\|"recording", "uuid"?, "path"?, "speed"?}` | Choose the data source |
| `POST /api/replay` | `{"action": "play"\|"pause"\|"speed"\|"seek", "speed"?, "to"?: "next_period"\|"before_next_goal"\|"period:N"}` | Replay control |
| `POST /api/offset` | `{"profile": "iptv", "seconds": 40.0}` | Set a TV profile's delay behind the arena |
| `POST /api/offset/nudge` | `{"delta": 0.5}` | Adjust the active profile's offset |
| `POST /api/profile` | `{"profile": "iptv"\|"tv4play"}` | Switch TV profile |
| `POST /api/calibrate` | `{"kind": "period_start"\|"goal"\|"penalty"\|"timeout"\|"shot_on_goal", "side"?: "home"\|"away"}` | Register a "Synka" press (server stamps the time) |
| `GET /api/calibrate` | | Samples and current proposal |
| `POST /api/calibrate/accept` | | Store the proposal as the active profile's offset |
| `DELETE /api/calibrate` | | Clear samples |
| `DELETE /api/calibrate/{id}` | | Remove one sample |
| `POST /api/goal` | `{"side": "home"\|"away"}` | MÅL! button: celebrate and fire the webhook now |
| `POST /api/scene` | `{"name", "hold_s"?}` | Manual scene override |
| `DELETE /api/scene` | | Back to automatic |
| `POST /api/test/goal` | `{"side": "home"\|"away"}` | Synthetic goal, offset 0, `test: true` |
| `GET /api/webhooks/log` | | Recent webhook calls and results |
| `POST /api/webhooks` | `{"url", "enabled", "events": [...]}` | Webhook settings |
| `GET /api/wall` | | Contents of `config/wall.json` |

### Calibration response

```json
{"profile": "iptv", "current_offset_s": 40.0,
 "samples": [{"id": "s1", "kind": "period_start", "pressed_ms": 1760000050000,
              "event_key": "period-3-start", "sample_s": 41.3, "status": "matched"},
             {"id": "s2", "kind": "goal", "side": "home", "pressed_ms": 1760000950000,
              "status": "pending"}],
 "proposal_s": 41.3, "reaction_ms": 300}
```

A press matches the raw event of that kind (and side) whose `event_ms` lies 5 to 150 s
before the press. A press without a match stays `pending` for up to 150 s, because the
feed can be slower than the TV, then becomes `unmatched`. Two or more candidates make it
`ambiguous`. Only `matched` samples count towards the proposal.

## Webhooks to Home Assistant

One URL (an HA webhook trigger), POST with JSON, sent at `play_at_ms`. Every payload has
`event`, `game_uuid`, `test` and `sent_ms`.

```json
{"event": "shl_goal", "game_uuid": "bdhvuc5tex", "test": false, "sent_ms": 1760000031500,
 "side": "home", "is_my_team": true, "team_code": "FHC", "team_name": "Frölunda HC",
 "team_color": "#34D399", "team_rgb": [52, 211, 153],
 "scorer": "Arttu Ruotsalainen", "scorer_number": "25", "assists": ["Dominik Egli", "Ivar Stenberg"],
 "strength": "PP1", "empty_net": false,
 "score_home": 2, "score_away": 1, "period": 3, "time": "09:07",
 "tts_sv": "Mål för Frölunda! Nummer 25, Arttu Ruotsalainen, i powerplay. Två–ett."}
```

`source` is `"feed"` or `"manual"` (MÅL! button). A manual goal has `side`,
`is_my_team`, team fields and `score_*` as known at the press (+1 for that side); scorer
fields are empty. The feed goal linked to it sends no second `shl_goal`.

Other events and their extra fields:

| event | Extra fields |
|---|---|
| `shl_goal_disallowed` | `side`, `is_my_team`, `score_home`, `score_away` |
| `shl_penalty` | `side`, `is_my_team`, `player`, `number`, `offence_text`, `minutes` |
| `shl_period_start` | `period` |
| `shl_period_end` | `period`, `score_home`, `score_away` |
| `shl_game_end` | `score_home`, `score_away`, `winner_side`, `my_team_won`, `overtime`, `shootout` |

### Example Home Assistant automation

```yaml
- alias: "SHL: mål för mitt lag"
  triggers:
    - trigger: webhook
      webhook_id: shl-arena
      allowed_methods: [POST]
      local_only: true
  conditions:
    - condition: template
      value_template: "{{ trigger.json.event == 'shl_goal' and trigger.json.is_my_team }}"
  actions:
    - action: light.turn_on
      target:
        entity_id: light.vardagsrum
      data:
        rgb_color: "{{ trigger.json.team_rgb }}"
        flash: long
    - action: media_player.play_media
      target:
        entity_id: media_player.vardagsrum
      data:
        media_content_id: "media-source://media_source/local/malhorn.mp3"
        media_content_type: music
```

Entity ids and the horn file are placeholders for the user's own. Put the full set of
examples in `docs/HA.md` (Phase 6).
