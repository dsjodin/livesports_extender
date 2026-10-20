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
| Sync to TV | Fixed offset per TV profile, default 30 s, calibrated with a button in the phone app. |
| Server | One Python 3.12 FastAPI service, run with Docker Compose on the home Docker host. |
| Clients | Screens, simulator and phone app are static pages from the same service. Plain HTML/CSS/ES modules + GSAP. No bundler. |
| Transport | WebSocket to all clients. No MQTT. |
| Home Assistant | Webhook POSTs from the service, sent at `play_at`. |
| Display hardware | One mini PC (planned: Beelink SER8, Ryzen 7 8745HS, Radeon 780M), Debian 13, sway, three Chromium kiosk windows. Bar on HDMI, portrait screens on DP and USB-C. |
| Language | Code and docs English. All on-screen and phone-app text Swedish. |

## Open questions (ask the user when the phase needs the answer)

- Physical layout: the bar's vertical position relative to the 24" screens and the gaps
  between screens. `config/wall.json` has assumed values (bar vertically centred, 40 mm gaps).
- Default "my team" (whose goals trigger the celebration and lights).
- Team logos: use the `icon` URLs from the feed (cached locally) or keep code badges.
- Sound for video stingers: local speaker on the mini PC or none (Phase 8).

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
   `standings(ssgt)`, `site_settings()`. Async httpx, 5 s timeout, User-Agent per
   CLAUDE.md, typed errors. Raw responses stay plain dicts; parse defensively.
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
4. **Normalizer** (`server/app/engine/normalizer.py`): diff successive pbp lists. Key events
   by `eventId`; period objects have no `eventId`, key them `("period", n)`. Emit
   `added`, `updated` (revision or content changed) and `removed`. Stamp `first_seen_ms`
   on first appearance and keep it on updates. Map to normalized types: `goal`, `shot`,
   `penalty`, `goalie_change`, `timeout`, `period_start`, `period_end`, `game_end`.
   Compute `game_seconds = (period - 1) * 1200 + mm * 60 + ss` from `time`.
5. **RawState reducer** (`engine/state.py`): score (from goal events' `homeGoals`/`awayGoals`,
   game-info score as fallback), period and whether it is running, latest game time seen,
   goalies on ice (including pulled goalie), penalties, shots per team and period split by
   on goal / missed (`MISSED_GOAL_SECTIONS = {-3}` as a named constant, marked as an
   assumption), penalty minutes, timeouts.
6. **Power-play tracker** (`engine/powerplay.py`): from penalties and game time. Minor = 2
   min, double minor = two consecutive 2 min, major = 5 min. A minor ends early when the
   other team scores. A penalty is over when the latest known game time passes its end or
   the period/game ends. Output: strength per team (5v5, 5v4, 5v3, 4v4) and which team is on
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
- Shot counts under the current assumption (`goalSection == -3` = missed), goals included:
  - on goal: FHC 16 / 15 / 10 (41), LHC 7 / 14 / 21 (42)
  - all attempts: FHC 19 / 20 / 17 (56), LHC 10 / 21 / 31 (62)
  If boxscore shots on goal differ, report it; do not silently change the rule.
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
   `play_at = first_seen_ms + offset_ms`. Broadcast at `play_at - lead_ms` (lead 1500 ms) so
   clients can preload and schedule. Updates before release replace the payload and keep
   `play_at`. Removals before release drop the item. Removal of an already released goal
   emits a correction event `goal_disallowed`. Changing the offset re-plans everything not
   yet released; released events stay.
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
8. **`/debug` page**: two text columns, raw events (with `first_seen`) and released events
   (with `play_at`), to eyeball the delay.

Acceptance (fake-clock tests unless noted):

- No broadcast `event` has `play_at < first_seen_ms + offset_ms`.
- A goal removed 10 s after first seen (offset 30 s) is never broadcast.
- A goal removed after release produces exactly one `goal_disallowed` and the TV score goes back.
- Changing the offset re-plans pending events; released ones are untouched.
- WebSocket integration test: `hello`, then `state`, then events in order.
- Manual: replay `bdhvuc5tex` at 5× with offset 5 s and watch `/debug`: released events
  trail raw events by about 5 s.

---

## Phase 3: Screens and simulator

Goal: the three screen pages with the scenes from `docs/SCREENS.md`, and the `/sim` page
that shows the whole wall with replay controls and a fake TV.

Tasks:

1. **Shared front-end modules** in `web/shared/`: `clock.js` (server time via WebSocket
   ping/pong, `now()`), `ws.js` (reconnect with backoff, dispatch by message type),
   `stage.js` (loads `config/wall.json`, converts stage millimetres to this screen's pixels),
   `tokens.css` (design tokens from `docs/SCREENS.md`), `scheduler.js` (run a callback at a
   server-time `play_at`). Vendor GSAP and the Barlow / Barlow Condensed fonts (woff2) into
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
   `first_seen + fake_tv_delay`, with a large period/time readout, so calibration can be
   practised.
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
2. **Calibration** (`engine/calibration.py`, endpoints in `docs/PROTOCOL.md`): a press of
   "Nu!" with kind `faceoff` or `goal` is matched to the most recent raw event of that kind
   first seen 5–120 s before the press. Sample = press time − `first_seen_ms` − reaction
   time (300 ms). Proposal = median of the last 5 samples in this session. The user accepts
   it explicitly; it is stored per TV profile.
3. **Scene override** and **test goal** (a synthetic goal for "my team" with offset 0, marked
   `test: true`, so lights can be tested without a game).
4. **My team**: chosen per game in Matcher; decides `is_my_team` in webhooks and which side
   celebrates.

Acceptance:

- In `/sim` with fake TV delay 27 s and system offset 20 s, three presses at the fake TV's
  period start propose 27 ± 0.5 s; after accepting, the screens line up with the fake TV.
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
