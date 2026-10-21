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
             "jersey": "röd", "color": "#c8102e",
             "icon": "https://sportality.cdn.s8y.se/team-logos/fhc1_fhc.svg",
             "logo": "/assets/teams/087a-087aTQv9u.svg"},
    "away": {"uuid": "41c4-41c4BiYZU", "code": "LHC", "short": "Linköping", "long": "Linköping HC",
             "jersey": "vit", "color": "#f4f6f8",
             "icon": "https://sportality.cdn.s8y.se/team-logos/lhc1_lhc.svg"}
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
  "league": {"... standings, form and games, see below; null until fetched ..."},
  "scene": {"name": "live", "since_ms": 1757775000000, "hold_ms": null, "data": {},
            "override": false}
}
```

`phase`: `idle`, `pregame`, `live`, `intermission`, `postgame`.

Notes: `strength` also has `label` (`"5v4"`; a pulled goalie adds a skater). `stats.*.goalie`
is per team (the goalie on the ice now, the team's saves and shots against; empty-net
goals excluded) and has `pulled`. `shots` skips coordinates outside 0–300 dm. `GET
/api/state` returns `{"tv": <this>, "config": <persisted settings>, "status": {...}}`.

### League block

`league` holds what the pregame and idle scenes show. It is fetched (standings cached
1 h, schedule 1 h) only while the applied phase is `idle` or `pregame` and every 10 min
then, so tonight's results cannot reach a screen during or after the game; it stays as it
was from puck drop on.

```json
{"updated_ms": 1792567865804,
 "standings": [{"rank": 1, "uuid": "752c-752c12zB7Z", "code": "FBK", "short": "Färjestad",
                "gp": 10, "w": 8, "l": 0, "otw": 1, "otl": 1, "points": 27, "gf": 40, "ga": 11,
                "diff": 29, "logo": "/assets/teams/752c-752c12zB7Z.svg"}, "..."],
 "teams": {"home": {"rank": 2, "points": 25, "gp": 11, "diff": 14, "gf_per_game": 3.5,
                    "ga_per_game": 2.2,
                    "form": [{"uuid": "mtn5yq64mp", "date": "2026-10-20", "result": "V",
                              "home_away": "H", "opponent": "DIF", "opponent_uuid": "...",
                              "note": null, "score": "6–2"}, "... newest first, 5 ..."]},
           "away": {"...": "same shape"}},
 "last_meeting": {"uuid": "pdllryhpd8", "date": "2026-10-15", "home": "LHC", "away": "FHC",
                  "home_uuid": "...", "score": "0–3", "arena": "Saab Arena", "note": null},
 "my_team": {"uuid": "82eb-82ebmgaJ8", "next_game": {"uuid": "...", "start_ms": 1792688400000,
             "home": "ÖRE", "away": "BIF", "arena": "Behrn Arena", "...": "..."}},
 "tonight": ["... today's games without scores ..."],
 "recent": ["... latest finished games with score and note (straffar, övertid) ..."]}
```

`result` is `V` (won) or `F` (lost) from that team's view, `home_away` `H` or `B`; the
score is always home–away of that game.

### Other games and the live table (Phase 8)

`others`: the evening's other SHL games (same day as ours, from the schedule), each
delayed by the same offset as ours through its own DelayQueue, sorted by start time:

```json
{"uuid": "pmch0rrshr", "start_ms": 1792242900000,
 "teams": {"home": {"uuid": "...", "code": "DIF", "short": "Djurgården", "long": "Djurgården Hockey",
                    "logo": "/assets/teams/<uuid>.svg", "color": "#1f4fbf"}, "away": {"...": "..."}},
 "phase": "live", "period": 2, "period_running": true, "last_game_time": "07:12",
 "score": {"home": 1, "away": 0}, "ended": false, "overtime": false, "went_to_shootout": false,
 "stats": {"home": {"shots_on_goal": 14, "pim": 2, "pp": {"goals": 0, "chances": 1}}, "away": {"...": "..."}},
 "goals": [{"key": "e41", "side": "home", "period": 1, "time": "12:03", "number": "17",
            "last": "Bergström", "score": {"home": 1, "away": 0}, "strength": "EQ"}]}
```

Live they are polled every 30 s (play-by-play only) and saved as recordings under their
own uuid; in a replay they replay in step with ours (fixtures, or fetched when finished).
Their events send no event, scene or webhook messages: only state patches at play_at.

`live_table`: null, or the standings "om matcherna slutade nu": the rows of
`league.standings` (fetched before tonight) with tonight's started games applied as they
stand on the wall (ours and `others`, only games in `league.tonight`, so a game already
in the fetched standings is not counted twice). Points 3 / 2–1 after overtime or a
shootout / 1 each for a tie still on. Each row adds `prev_rank`, `move` and `live`
(`{"for", "against", "ended", "home_away", "opponent"}` or null). Replays of past evenings
have no `league.tonight`, so no live table.

### Starting and seeking

The first snapshot after a source starts (or a replay seeks) brings everything that has
already happened. Events that are already late at that moment, so the TV has shown them,
are applied at once as the starting state: no `event` or `scene` messages for them, then a
fresh `state` to everyone. The scene is what the director would show at that moment (a
goal shown 5 s ago is still the goal scene, with 15 s left). Events still ahead of the TV
play normally.

## WebSocket

Endpoint: `/ws?role=screen|sim|phone|debug&id=<screen id or client name>`

### Server to client

```json
{"t": "hello", "server_ms": 1760000000000, "role": "screen", "id": "left",
 "config": {"offset_ms": 40000, "lead_ms": 1500, "profile": "iptv", "speed": 1.0, "debug": false}}

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
- `{"t": "config", "config": {...}}` when the offset, TV profile, source or replay speed
  changes. `speed` is the replay speed (1 for live); the intermission countdown divides
  the break by it.
- Non-screen clients (sim, phone, debug) get `{"t": "status", "status": {...}}` about once
  a second: source mode, uuid, speed, running, paused, replay position (`feed_ms`), error,
  selected game, my side (`my_side`, and `my_side_choice` as set), profile, offset,
  counts, `last_snapshot_ms`, `late_goals` (goals that reached us after the TV),
  `manual` (MÅL! presses), `calibration` (as `GET /api/calibrate`), `goal_button_sync`,
  `follow_my_team`.
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
| `POST /api/game` | `{"uuid", "my_side": "home"\|"away"\|"none"\|null}` | Select a game to follow; `"none"`: no side is mine, `null`: my side follows my team |
| `POST /api/source` | `{"mode": "live"\|"replay"\|"recording"\|"none", "uuid"?, "path"?, "speed"?}` | Choose the data source. `live` needs `uuid` and polls shl.se for that game (CLAUDE.md rule 5); a game that is already over is read once. Every live poll is also saved to `data/recordings/<uuid>/polls.jsonl` (the `tools/record_game.py` format, plus boxscore and team-stats at the final refresh), so it can be replayed as `recording` and analysed |
| `POST /api/replay` | `{"action": "play"\|"pause"\|"speed"\|"seek", "speed"?, "to"?: "next_period"\|"before_next_goal"\|"period:N"\|"end"}` | Replay and recording control (live: 400, nothing to pause or seek). A recording seeks to the on-ice times in its last play-by-play and shows what had been received by then; a seek after the end reads on from the new position |
| `POST /api/offset` | `{"profile": "iptv", "seconds": 40.0}` | Set a TV profile's delay behind the arena |
| `POST /api/offset/nudge` | `{"delta": 0.5}` | Adjust the active profile's offset |
| `POST /api/profile` | `{"profile": "iptv"\|"tv4play"}` | Switch TV profile |
| `POST /api/calibrate` | `{"kind": "period_start"\|"goal"\|"penalty"\|"timeout"\|"shot_on_goal", "side"?: "home"\|"away"}` | Register a "Synka" press (server stamps the time) |
| `GET /api/calibrate` | | Samples and current proposal |
| `POST /api/calibrate/accept` | | Store the proposal as the active profile's offset |
| `POST /api/calibrate/goal-button` | `{"enabled": true}` | "Använd målknapp för synk": a linked MÅL! press is a `goal` sample |
| `DELETE /api/calibrate` | | Clear samples |
| `DELETE /api/calibrate/{id}` | | Remove one sample |
| `POST /api/follow` | `{"enabled": true}` | "Följ mitt lag": follow my team's game of the day live when nothing else runs (checked every 10 min) |
| `POST /api/goal` | `{"side": "home"\|"away"}` | MÅL! button: celebrate now (webhook in Phase 6); returns `{"press", "status"}` |
| `POST /api/scene` | `{"name", "hold_s"?}` | Manual scene override |
| `DELETE /api/scene` | | Back to automatic |
| `POST /api/test/goal` | `{"side"?: "home"\|"away"}` | Synthetic goal (default my side), offset 0, `test: true` |
| `GET /api/webhooks` | | `{"settings": {"url", "enabled", "events"}, "events": [all event names]}` |
| `GET /api/webhooks/log` | | Recent webhook calls and results |
| `POST /api/webhooks` | `{"url", "enabled", "events": [...]}` | Webhook settings |
| `GET /api/wall` | | Contents of `config/wall.json` |
| `GET /api/replays` | | `{"fixtures": [uuid, ...], "recordings": [dir, ...]}`: games that replay without the network, and saved recordings |
| `POST /api/my-team` | `{"uuid": "<team uuid>"\|null}` | My team (default Örebro); my side follows it unless set per game |
| `GET /api/teams` | | Palette and every team's home/away jersey colour (`config/teams.json` plus overrides) |
| `PUT /api/teams/{uuid}` | `{"home"?: "röd"\|"#rrggbb", "away"?: ...}` | Override a team's colours (saved in `data/state.json`) |
| `DELETE /api/teams/{uuid}` | | Back to the defaults from `config/teams.json` |

### Calibration response

```json
{"profile": "iptv", "current_offset_s": 40.0,
 "samples": [{"id": "s1", "kind": "period_start", "pressed_ms": 1760000050000,
              "event_key": "period-3-start", "sample_s": 41.3, "status": "matched"},
             {"id": "s2", "kind": "goal", "side": "home", "pressed_ms": 1760000950000,
              "status": "pending"}],
 "proposal_s": 41.3, "reaction_ms": 300}
```

`POST /api/calibrate` returns this plus `press` (the new sample). Samples also carry
`source` (`sync` or `goal_button`), `event_ms` and `side`; `proposal_samples` is how many
samples the proposal used (at most 5). Samples are saved in `data/state.json`. A matched
sample stays matched if its event later goes away (a replay seek).

A press matches the raw event of that kind (and side) whose `event_ms` lies 5 to 150 s
before the press. `shot_on_goal` matches shots with result `on_goal` (not goals). A press without a match stays `pending` for up to 150 s, because the
feed can be slower than the TV, then becomes `unmatched`. Two or more candidates make it
`ambiguous`. Only `matched` samples count towards the proposal.

### MÅL! button (built in Phase 4)

A press plays a goal event (key `manual-<n>`, `raw_type` `manual`, no player,
`data.manual`, `data.score` = the score on screen +1) and the goal scene 300 ms later,
with scene data `{"event_key", "side", "manual": true, "score"}`. It does not change the
TV state's score. The press links to the feed goal for that side whose `event_ms` lies
150 s before to 5 s after the press: one already waiting for its `play_at`, or the next to
arrive within 180 s. When the linked goal plays, the running goal scene (if it is still
that press's) is sent again with `{"event_key": <feed key>, "side", "linked_from":
"manual-<n>"}`; screens fill in scorer and score without starting over. No goal in 180 s:
the press is `unconfirmed`. A test goal (`test-<n>`) links to nothing. The presses are in
`status.manual`: `id`, `side`, `test`, `pressed_ms`, `status` (`waiting`, `linked`,
`unconfirmed`, `test`) and `scorer` once the linked goal has played.

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

Entity ids and the horn file are placeholders for the user's own. The full set of
examples is in `docs/HA.md`.

### Dispatcher (built in Phase 6)

- Sent at `play_at_ms` by the server clock, never before (checked against a fake clock:
  within 50 ms; 1 ms on the real service). Timeout 3 s, one retry after 1 s.
- Only events in the settings' `events` list, only when `enabled` and a `url` is set.
- A replay seek or a new source cancels calls not sent yet. Events applied in a catch-up
  (`Starting and seeking`) send nothing.
- A test goal (`POST /api/test/goal`) always has `is_my_team: true`; when my team is not
  in the selected game it carries my team's name and home colour.
- `GET /api/webhooks/log`: the last 100 calls, `{"id", "event", "test", "source",
  "play_at_ms", "sent_ms", "status", "error", "attempts"}`. Each call is also sent to
  sim and phone clients as `{"t": "webhook", "entry": {...}}`. `status.webhooks` has
  `enabled`, `url_set` and `pending`.

## Assets

Not under `/api`. Fetched from shl.se once, stored under `data/cache/`, served locally
with `Cache-Control: max-age=86400`; 404 when the feed has none.

| Path | Source |
|---|---|
| `GET /assets/teams/<team uuid>.svg` | the team's `icon` URL from game-info or the schedule |
| `GET /assets/players/<isa id>.png` | the portrait in `athletes/by-team-uuid` (team roster cached 24 h), matched by name, then jersey number; the smallest signed `srcset` entry at least 480 px wide |

| `GET /media/<goal\|intro>/<team uuid>.webm` | not from shl.se: `data/media/<kind>/<uuid>.webm` (your own) or the default in `web/media/` (`tools/make_stingers.py`); see `docs/SCREENS.md`, Team videos |

A player is known once an event names them (scorer, assists, players on the ice). A
player who has left the team since the game (old fixtures) has no portrait.
