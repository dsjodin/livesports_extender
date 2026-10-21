# Build plan

Implement one phase at a time. Each phase ends with its acceptance criteria verified,
tests and lint clean, a commit, and a short summary back to the user. Do not start the
next phase without being asked.

The order is simulator-first: everything up to Phase 4 runs on a laptop with replayed
games, without the real screens and without a live game.

## Decisions (already made)

| Area | Decision |
|---|---|
| Data | shl.se's own JSON API (unofficial, undocumented). See `docs/SHL_API.md`. |
| Sync to TV | `play_at = event_ms + offset`, where `event_ms` is the feed's on-ice time (`realWorldTime` / `startedAt` / `finishedAt`, Europe/Stockholm) and `offset` is the TV's delay behind the arena, per TV profile, calibrated with a sync button in the phone app. Never before `first_seen_ms`; late events play at once, marked `late`. Decided 2026-10-20 (see CLAUDE.md rule 2). |
| Receive time | `first_seen_ms = received_ms − Age header × 1000` of the first poll containing the event (fallback `received_ms`). Used for the never-early bound, analysis and as fallback anchor. Decided 2026-10-20. |
| Goal button | A manual "MÅL!" button in the phone app fires the celebration and Home Assistant at once; the feed's goal is linked to it later and does not fire twice. Complements the automatic sync for goals that arrive after the TV shows them. Decided 2026-10-20. |
| Server | One Python 3.12 FastAPI service, run with Docker Compose on the home Docker host. |
| Clients | Screens, simulator and phone app are static pages from the same service. Plain HTML/CSS/ES modules + GSAP. No bundler. |
| Transport | WebSocket to all clients. No MQTT. |
| Home Assistant | Webhook POSTs from the service, sent at `play_at`. |
| Display hardware | One mini PC (planned: Beelink SER8, Ryzen 7 8745HS, Radeon 780M), Debian 13, sway, three Chromium kiosk windows. Bar on HDMI, portrait screens on DP and USB-C. |
| Language | Code and docs English. All on-screen and phone-app text Swedish. |

## Open questions (ask the user when the phase needs the answer)

- **Feed latency vs TV delay (found 2026-10-20).** Goals reach us 19–78 s (median 48 s)
  after the on-ice moment. The TV (Telia IPTV box, linear channel over UDP multicast) was
  measured at about 40 s behind the arena (one rough measurement: puck drop reported from
  the arena by phone). So roughly a third of goals arrive before the TV shows them. The
  design handles both cases (sync on `event_ms`, late events at once, the MÅL! button).
  Still open: whether the Telia box can pause the SHL channel; pausing ~40 s at puck drop
  would put almost every goal in time. Verify with the sync button once Phase 4 exists.
- Physical layout: the wall is not built yet (2026-10-21), so the bar's vertical position
  and the gaps stay assumed in `config/wall.json` (bar vertically centred, 40 mm gaps).
  Everything reads the geometry from that file; measure and edit it once the wall exists.
- ~~Default "my team"~~: Örebro Hockey (`82eb-82ebmgaJ8`), decided 2026-10-21
  (`my_team_uuid`, `POST /api/my-team`); the side follows the team unless set per game.
- ~~Team logos~~: decided 2026-10-21: the feed's `icon` URLs (SVG), cached locally, code
  badge as fallback. **Player portraits** are also available (`athletes/by-team-uuid`,
  see `docs/SHL_API.md`); use them in the goal scene, cached locally, number as fallback.
- Sound for video stingers: local speaker on the mini PC or none (Phase 8).
- Faceoffs (found 2026-10-21): not in play-by-play. `gameday/team-stats` has them per
  period (plus hits, blocked shots and SHL's own power-play counts), without timestamps.
  Recommended: poll it every 60 s during the game and show it in intermissions and after
  the game only. Needed by Phase 3 (intermission scene).

---

## Phase 0: Skeleton, fixtures and the game recorder

Goal: a running empty service, real test data on disk, and a tool that records a live
game so later phases can be verified against reality.

Tasks:

1. **Repo skeleton.** `server/pyproject.toml` (uv, FastAPI, uvicorn, httpx, pydantic v2,
   pytest, pytest-asyncio, ruff), `server/app/main.py` with `GET /api/health` and a static
   mount of `web/`, `Dockerfile` (python:3.12-slim), `compose.yaml` (port 8080, volume
   `./data:/data`, env file), `.gitignore`, ruff and pytest config.
2. **`tools/fetch_fixtures.py`.** Fetch and save pretty-printed JSON into
   `server/tests/fixtures/` (file names as listed):
   - `filter.json`: season/series/game-type filter
   - `schedule_2026.json`: full 2026/27 regular-season schedule
   - `site_settings.json`: team directory
   - `standings_qa98unlbd6.json`: current standings
   - For game `bdhvuc5tex` (Frölunda–Linköping 2–1, 2025-09-13):
     `game_info_bdhvuc5tex.json`, `pbp_bdhvuc5tex.json`, `boxscore_bdhvuc5tex.json`
   - The same three files for `m01wkdm2u1` (HV71–Skellefteå 4–3 after overtime,
     2026-09-24) and `et9erhx0si` (Frölunda–Skellefteå 3–2 after shootout, 2026-10-17)
   - Write `server/tests/fixtures/README.md` with fetch date and source URLs.
3. **`tools/record_game.py <game_uuid>`.** Polls `game-info` and `play-by-play` for one game
   and appends one JSON line per poll to `data/recordings/<uuid>/polls.jsonl`:
   `{"received_ms", "endpoint", "status", "sha1", "body"}`, storing `body` only when the
   hash changed (otherwise `null`). Polling: every 60 s while `pre-game` and more than
   15 min before start, every 2 s otherwise. Stops 5 min after a post-game state, or on Ctrl-C.
   Prints a one-line status per change (state, score, number of events).
4. **`tools/analyze_recording.py <dir>`.** Writes `report.md` next to the recording:
   - every distinct `gameInfo.state` and pbp `gameState` value with first-seen times
   - per event type: delay from `realWorldTime` (parsed as Europe/Stockholm) and from
     `updatedTime` (parsed as UTC) to our `received_ms`: min/median/max
   - events that changed revision (which fields changed) and events that disappeared
   - distinct `goalStatus`, `offence`, `variant.shortName`, `goalSection` values
   - shots per team by `goalSection` value, compared with boxscore shots on goal
     (fetch the boxscore at the end of the run)
   - period objects: started/finished timing versus the events around them
5. A smoke test that loads every fixture file.

Acceptance:

- `docker compose up --build` serves `GET /api/health` → `{"status":"ok"}` and `/` lists the pages that exist.
- All fixture files exist and the smoke test passes.
- `record_game.py` on a finished game makes one poll, sees the post-game state and exits
  cleanly; on an upcoming game it polls at the slow interval.
- `analyze_recording.py` produces a report from a short real recording (or from a
  synthetic recording built from the `bdhvuc5tex` fixtures).
- Tell the user how to run the recorder during the next live game. A real recording is
  needed by Phase 5 and resolves the open data questions in `docs/SHL_API.md`.

---

## Phase 1: Feed client, sources, normalizer and game state

Goal: turn feed snapshots into a clean stream of game events and a correct raw game state,
tested against real fixtures. No delay, no clients yet.

Tasks:

1. **`ShlClient`** (`server/app/feed/client.py`): `filter()`, `schedule(season, series,
   game_type)`, `game_info(uuid)`, `play_by_play(uuid)`, `boxscore(uuid)`,
   `standings(ssgt)`, `site_settings()`. Async httpx, 15 s timeout (raised from 5 s after
   the 2026-10-20 timeouts), User-Agent per CLAUDE.md, typed errors, Age and
   cf-cache-status returned with the data. Raw responses stay plain dicts; parse defensively.
2. **Snapshot model**: `Snapshot(received_ms, game_info: dict | None, pbp: list | None)`.
3. **Sources** (`server/app/feed/sources.py`), all async iterators of snapshots driven by
   the injectable `Clock`:
   - `ReplaySource(pbp_full, game_info_final, speed)`: reveals events progressively by
     their `realWorldTime` (Europe/Stockholm) relative to the first event, emits a snapshot
     every 2 s of replay time, and synthesises `game_info` (state `pre-game` before the
     first period starts, `live` while periods run, `post-game` after the last one; score
     from the latest visible goal). Controls: play, pause, speed (1/2/5/20/50), seek to a
     period start or to N seconds before a given goal.
   - `RecordingSource(polls.jsonl, speed)`: replays recorded polls with their original spacing.
   - `LiveSource` is Phase 5; define the interface now.
0. **Carry-over from the first live recording (2026-10-20, see `docs/SHL_API.md`).**
   - `tools/record_game.py`: store the response's `age` and `cf-cache-status` on every
     row; timeout 15 s; take state and score from play-by-play (`gameState`, latest goal),
     not game-info, which stayed `pre_game` with an empty score during the live game;
     stop 5 min after play-by-play `GameEnded` (or game-info `post-game`, whichever first).
   - `tools/analyze_recording.py`: report delays from `received_ms − age` when `age` is
     present; report error/timeout counts.
   - The snapshot carries `available_ms` (= `received_ms − age`), and the normalizer stamps
     `first_seen_ms` from it (see the Event timing decision).
   - `ReplaySource` synthesises the play-by-play `gameState` (`Ongoing` while live) and
     leaves game-info alone; state comes from play-by-play everywhere.
   - Normalized events carry `event_ms` (see CLAUDE.md rule 2) next to `first_seen_ms`.
   - `ReplaySource` reveals each event at its `realWorldTime` **plus a simulated feed lag**
     (per type, default from the recording: goal 48 s, shot 35 s, penalty 42 s, period
     25 s; configurable, 0 allowed). Replay and recording sources shift the feed's
     timestamps (`realWorldTime`, `startedAt`, `finishedAt`, `updatedTime`) onto the replay
     timeline, scaled by speed, so `event_ms` stays consistent with the clock.
   - Period keys can be strings (`("period", "shootout")`).
   - The normalizer and `analyze_recording.py` ignore `gameState`, `attendance` and
     `updatedTime` when comparing event content (they change on every event at each
     period boundary).
   - A goal arrives as a shot that is then deleted and replaced by a new `goal` event at
     revision 2, and can be corrected later (scorer and assists). Treat the deleted
     precursor shot as a normal removal; never derive a goal from a shot.
4. **Normalizer** (`server/app/engine/normalizer.py`): diff successive pbp lists. Key events
   by `eventId`; period objects have no `eventId`, key them `("period", n)`. Emit
   `added`, `updated` (revision or content changed) and `removed`. Stamp `first_seen_ms`
   on first appearance and keep it on updates. Map to normalized types: `goal`, `shot`,
   `penalty`, `goalie_change`, `timeout`, `period_start`, `period_end`, `game_end`, plus
   `shootout_attempt` (raw `shootout-penalty-shot`) and `unknown` (logged once, shown raw).
   Compute `game_seconds = (period - 1) * 1200 + mm * 60 + ss` from `time`.
5. **RawState reducer** (`engine/state.py`): score (from goal events' `homeGoals`/`awayGoals`,
   game-info score as fallback), period and whether it is running, latest game time seen,
   goalies on ice (including pulled goalie), penalties, shots per team and period split by
   on goal / not on goal (`ON_GOAL_SECTIONS = 1..9` as a named constant, decided
   2026-10-20 from four boxscores; goals always count as on goal), penalty minutes,
   timeouts.
6. **Power-play tracker** (`engine/powerplay.py`): from penalties and game time. Minor = 2
   min, double minor = two consecutive 2 min, major = 5 min. A minor ends early when the
   other team scores. A penalty is over when the latest known game time passes its end or
   the game ends (penalties carry over between periods, as in hockey; see the module
   docstring for coincidental penalties, waiting penalties and 3-on-3 overtime). Output: strength per team (5v5, 5v4, 5v3, 4v4) and which team is on
   the power play, plus each penalty's expiry in game seconds.
7. **CLI**: `python -m app.cli replay <fixture-uuid> --speed 50` prints the event timeline and
   final state.

Acceptance (from `bdhvuc5tex`; verify these exact values in tests):

- Goals in order:
  - P1 04:33 FHC #40 Jacob Peterson, assists #12 Max Friberg and #21 Jere Innala, `EQ`, 1–0
  - P2 00:24 LHC #70 Fredrik Karlström, assists #73 Nick Shore and #39 Ty Rattie, `PP1`, 1–1
  - P3 09:07 FHC #25 Arttu Ruotsalainen, assists #46 Dominik Egli and #41 Ivar Stenberg, `PP1`, 2–1
- Penalties: P1 01:42 LHC #9 Erik Norén `BOARD`; P1 18:35 FHC #46 Dominik Egli `TRIP`;
  P2 11:20 LHC #81 Theodor Lennström `INTRF`; P3 07:39 LHC #8 Jonathan Myrenberg `HOLD`;
  P3 11:10 FHC #46 Dominik Egli `CROSS`. All minors. Penalty minutes FHC 4, LHC 6.
- Power play: LHC on the power play at P2 00:24 (Egli's minor runs to P2 00:35) and the goal
  ends that minor; FHC on the power play at P3 09:07 and the goal ends Myrenberg's minor
  early. FHC 1/3 and LHC 1/2 on the power play at the end.
- LHC timeout and goalie #31 Jesper Myrenberg pulled at P3 17:13.
- Shot counts with `goalSection` 1–9 = on goal (decided 2026-10-20), goals included:
  - on goal: FHC 15 / 11 / 5 (31), LHC 4 / 10 / 15 (29), equal to the boxscore
  - all attempts: FHC 19 / 20 / 16 (55), LHC 10 / 21 / 32 (63)
  (The original numbers, 41/42 on goal and 56/62 attempts, used the old "-3 only" rule and
  counted event 120 for FHC; it is an LHC shot.)
- Final state 2–1, game ended, three period start/end pairs.
- Overtime and shootout fixtures replay to their known results (4–3 OT, 3–2 SO) and the
  shootout does not inflate goal or shot stats (report how the feed represents it).

---

## Phase 2: Clock sync, delay queue, TV state, director and WebSocket

Goal: the delayed "TV state" the clients render, delivered over WebSocket with timestamps
the clients can schedule animations against.

Tasks:

1. **Clock**: `RealClock` and `FakeClock(advance)`. Everything time-based takes a clock.
2. **DelayQueue** (`engine/delay.py`): each normalized event gets
   `play_at = max(event_ms + offset_ms, received_ms + lead_ms)`; when the second term
   wins the event is marked `late: true` (and `late_by_ms`). Without a plausible
   `event_ms` (CLAUDE.md rule 2) it is `received_ms + lead_ms`, also `late`, logged once
   at WARNING. Broadcast at `play_at - lead_ms` (lead 1500 ms) so clients can preload and
   schedule. Updates before release replace the payload and keep `play_at`. Updates after
   release (a goal's scorer or assists corrected) go out as `event_update` at once.
   Removals before release drop the item. Removal of an already released goal emits a
   correction event `goal_disallowed`. Changing the offset re-plans everything not yet
   released; released events stay.
3. **TvState** (`engine/tvstate.py`): reducer over released events only: score, period,
   strength, stats, recent events, current scene, monotonic `rev`.
4. **SceneDirector** (`engine/director.py`): rules in `docs/SCREENS.md` (Scenes) plus a
   manual override with optional hold time.
5. **WebSocket hub** (`api/ws.py`): `/ws?role=screen|sim|phone&id=…`. On connect: `hello`
   with server time and config, then a full `state`. Then `event`, `scene`, `state_patch`
   messages as in `docs/PROTOCOL.md`. Clock sync ping/pong. Heartbeat every 10 s.
6. **REST**: `GET /api/state`, `GET /api/schedule`, `POST /api/game`, `POST /api/source`,
   `POST /api/replay`, `POST /api/offset`, `POST /api/offset/nudge` (see `docs/PROTOCOL.md`).
7. **Persistence**: runtime state in `data/state.json` (selected game, my team, TV profile and
   offsets, calibration samples, webhook settings), loaded at start.
8. **`/debug` page**: two text columns, raw events (with `event_ms` and `first_seen`) and
   released events (with `play_at` and `late`), to eyeball the delay.

Acceptance (fake-clock tests unless noted):

- Every broadcast `event` has `play_at == max(event_ms + offset_ms, received_ms + lead_ms)`
  and is never broadcast before it reached us; `late` is set exactly when the second term
  wins. (`received_ms` replaced `first_seen_ms` here on 2026-10-21, see CLAUDE.md rule 2.)
- With offset 80 s, a goal first seen 48 s after its `event_ms` plays at `event_ms + 80 s`;
  with offset 40 s it plays at `received + lead` and is `late`.
- A goal removed before its `play_at` is never broadcast.
- A scorer correction after release produces one `event_update`; the TV state shows the
  corrected scorer.
- A goal removed after release produces exactly one `goal_disallowed` and the TV score goes back.
- Changing the offset re-plans pending events; released ones are untouched.
- WebSocket integration test: `hello`, then `state`, then events in order.
- Manual: replay `bdhvuc5tex` at 5× with offset 60 s and watch `/debug`: released events
  sit 60 s after their `event_ms`, goals with a simulated lag over 60 s are `late`.

---

## Phase 3: Screens and simulator

Goal: the three screen pages with the scenes from `docs/SCREENS.md`, and the `/sim` page
that shows the whole wall with replay controls and a fake TV.

Tasks:

1. **Shared front-end modules** in `web/shared/`: `clock.js` (server time via WebSocket
   ping/pong, `now()`), `ws.js` (reconnect with backoff, dispatch by message type),
   `stage.js` (loads `config/wall.json`, converts stage millimetres to this screen's pixels),
   `tokens.css` (design tokens from `docs/SCREENS.md`), `scheduler.js` (run a callback at a
   server-time `play_at`). An asset cache in the service (`/assets/teams/<uuid>.svg`,
   `/assets/players/<isa id>.jpg`) fetches team logos and player portraits from shl.se once,
   stores them under `data/cache/` and serves them locally. Vendor GSAP and the Barlow /
   Barlow Condensed fonts (woff2) into
   `web/vendor/`.
2. **Screen pages** `web/screens/{left,bar,right}.html`, each loading scene modules from
   `web/screens/scenes/`. A scene module exports `enter(ctx, data, at)`, `update(ctx, tv)`,
   `exit(ctx, at)`. Build in this order: live, goal, intermission, pregame, then idle,
   penalty overlay, postgame and goal-disallowed.
3. **Cross-screen goal effect**: a gold band defined in stage millimetres sweeps from the
   bar's centre outward across both side screens, starting at the goal's `play_at`; each
   screen renders only its own part. Because positions are in millimetres, the band keeps
   its size and speed across the different pixel densities.
4. **Simulator** `web/sim/index.html`: wall laid out from `wall.json` at a common
   millimetre scale, one iframe per screen at native resolution scaled with CSS transform,
   bezels drawn. Control panel: replay game (fixtures, or any finished game uuid),
   play/pause, speed, seek (next period, 10 s before next goal), system offset, fake TV
   delay (independent), webhook log, debug toggle (`?debug=1` on the screens shows event
   ids and `play_at` countdowns). **Fake TV pane**: shows raw events as text at
   `event_ms + fake_tv_delay` (the simulated TV's lag behind the arena), with a large
   period/time readout, so the sync and MÅL! buttons can be practised.
5. **`tools/snapshot.py`** (Playwright): opens `/sim`, seeks the `bdhvuc5tex` replay to fixed
   moments and saves each screen at native size to `artifacts/snapshots/`:
   pregame, live at P3 08:20 (FHC power play), goal at P3 09:07 + 2 s, intermission after P2.

Acceptance:

- Replaying `bdhvuc5tex` at 5× in `/sim` runs pregame → live → goals → intermissions → postgame.
- The goal sequence starts on all three screens within 20 ms of `play_at` (debug log shows it).
- Snapshots exist and follow the layouts in `docs/SCREENS.md` (and `docs/mockups/` if present).
- Restarting the service: screens reconnect and restore state without a page reload.

---

## Phase 4: Phone app and calibration

Goal: control the system from a phone, and calibrate the delay against the TV.

Tasks:

1. **`/app`** PWA (manifest, simple icon, installable): views Matcher, Live and
   Inställningar as in `docs/SCREENS.md` (Phone app). Swedish UI. Large touch targets.
2. **Sync button** (`engine/calibration.py`, endpoints in `docs/PROTOCOL.md`): the user
   presses "Synka" when an event is seen on TV and picks its kind: `period_start`
   (Nedsläpp), `goal` (Mål), `penalty` (Utvisning), `timeout` (Timeout) or
   `shot_on_goal` (Skott på mål), optionally with the side. The feed has no offside or
   icing events, so those kinds do not exist. A press is matched to the raw event of that
   kind (and side, if given) whose `event_ms` lies 5–150 s before the press. Because the
   feed can be slower than the TV, a press with no match yet stays **pending for up to
   150 s** and is matched when the event arrives. If more than one event matches (common
   for shots) the sample is rejected as ambiguous. Sample = press time − `event_ms` −
   reaction time (300 ms). Proposal = median of the last 5 samples in this session; each
   sample is listed with its kind and can be removed. The user accepts the proposal
   explicitly; it is stored per TV profile.
3. **MÅL! button**: one large button per team (my team first). A press fires the goal
   scene with team only ("MÅL!" without scorer) and the `shl_goal` webhook at once, with
   `source: "manual"`. The next feed goal for that side whose `event_ms` lies at most 150 s
   before the press is **linked** to it: no second celebration or webhook; the scorer,
   assists and score fill in when it plays (or at once if it is late). If no goal arrives
   within 180 s the press is marked unconfirmed in the app and nothing else happens. A
   linked press also counts as a `goal` sync sample if "Använd målknapp för synk" is on.
4. **Scene override** and **test goal** (a synthetic goal for "my team" with offset 0, marked
   `test: true`, so lights can be tested without a game).
5. **My team**: chosen per game in Matcher; decides `is_my_team` in webhooks and which side
   celebrates.

Acceptance:

- In `/sim` with fake TV delay 75 s and system offset 60 s, three sync presses at the fake
  TV's period starts propose 75 ± 0.5 s; after accepting, the screens line up with the fake
  TV.
- A sync press for a goal made before the goal reaches the feed is matched once it arrives.
- With fake TV delay 40 s, pressing MÅL! when the fake TV shows a late goal celebrates at
  once, and the feed goal arriving afterwards links to it without a second celebration or
  webhook.
- The app works from a phone browser on the LAN; every action is reflected in `/sim`.

---

## Phase 5: Live source

Goal: follow real games.

Tasks:

1. **`LiveSource`**: driven by the schedule. More than 15 min before start: `game-info`
   every 60 s. From 15 min before: `game-info` and `play-by-play` every 2 s. Stop 2 min
   after a post-game state. Backoff on errors. Log unknown state strings once.
2. Update state normalisation and `docs/SHL_API.md` with what the Phase 0 recording showed
   (live state value, `goalSection` meaning, revision behaviour, shootout representation).
3. Test: run a real recording through `RecordingSource` and assert the goal timeline
   against the official result.
4. Optional "follow my team": select my team's next game automatically each day.
5. Final refresh: fetch play-by-play once more about 30 min after `GameEnded` (and the
   boxscore), since shl.se keeps correcting events after the game (docs/SHL_API.md).

Acceptance:

- A recorded live game replays through `RecordingSource` with the correct goal timeline.
- Dry run: `LiveSource` on an upcoming game polls at 60 s; on a finished game it stops cleanly.

---

## Phase 6: Home Assistant

Tasks:

1. **Webhook dispatcher**: POST at `play_at` (not at broadcast time), 3 s timeout, one retry,
   every call logged and shown in `/sim`. Settings: URL, enabled, which event types.
2. **`docs/HA.md`** with example automations (see `docs/PROTOCOL.md`) for lights in team
   colour, a goal horn on a media player, TTS for the scorer, and period/game-end events.

Acceptance:

- Fake-clock test: webhooks fire at `play_at` ± 50 ms, never before.
- Manual: the test-goal button in the app triggers the user's HA automation.

---

## Phase 7: Deployment

Tasks:

1. Production compose for the Docker host: restart policy, healthcheck, `/data` volume, log rotation.
2. `deploy/display-box/`: install notes for Debian 13; sway config template with the three
   outputs (portrait transform for the 24" screens, custom 1920×360 mode for the bar if its
   EDID is wrong, positions matching `wall.json`); greetd autologin; `kiosk.sh` starting three
   Chromium windows (`--kiosk`, separate `--user-data-dir` per window, Wayland, autoplay
   allowed, no error dialogs) on workspaces bound to each output; systemd user unit;
   screen power handling (DPMS or HA smart plug).
3. `deploy/display-box/check.sh`: verifies outputs, modes and that three windows run.
4. `docs/DEPLOY.md`.

Acceptance: following `docs/DEPLOY.md` on a fresh Debian 13 box gives three screens showing
the right pages after boot, with no manual steps.

---

## Phase 8: Extras (prioritise with the user)

- Video stingers per team (WebM VP9 with alpha) for goals, and intro videos before puck drop.
  Preload, start at `play_at`. Decide audio routing first.
- Live standings table ("om matcherna slutade nu") using standings + live scores of the evening.
- Other games ticker on the bar.
- Post-game: top players by points from the boxscore, final stats, standings movement.
- Team logos from the feed's `icon` URLs, cached locally, badges as fallback.
- Momentum graph: shots per team over the last 5 minutes.
- Power-play countdown that ticks between events (estimated, clearly marked).
