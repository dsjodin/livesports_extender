# SHL Arena: project guide for Claude Code

A home "arena" for Swedish Hockey League (SHL) games. A stretched LCD bar (1920×360)
sits between two portrait 24" screens (1080×1920 each). The system follows a chosen
game using shl.se's own JSON API, delays everything to match the TV broadcast
(about 30 s behind the arena on our IPTV feed), drives broadcast-style graphics on
the three screens and fires goal lights and horns in Home Assistant via webhook.

Read these before working on a phase:

- `docs/PLAN.md`: phases, tasks and acceptance criteria. Work one phase at a time.
- `docs/SHL_API.md`: the verified shl.se endpoints, field paths and data quirks.
- `docs/PROTOCOL.md`: REST API, WebSocket messages and webhook payloads.
- `docs/SCREENS.md`: wall geometry, design tokens, scenes per screen, simulator and phone app.
- `config/wall.json`: physical screen layout (single source of truth for geometry).

## Architecture

```
shl.se JSON API ──poll 2 s──► FeedSource (live | replay | recording)
                                   │ raw snapshots (play-by-play + game-info)
                                   ▼
                         Normalizer (diff by event id + revision)
                                   │ normalized events, first_seen_ms
                                   ▼
                    RawState + DerivedStats (shots, PP, saves, penalties)
                                   │
                                   ▼
               DelayQueue (release at first_seen + offset, minus lead)
                                   │ events with play_at
                                   ▼
                  TvState reducer + SceneDirector (pregame/live/goal/…)
                 │                    │                         │
           WebSocket hub        Webhook dispatcher        REST API
     (screens, sim, phone)    (Home Assistant, at play_at)  (config, control)
```

- One FastAPI service (Python 3.12) runs everything server side.
- Screens, simulator and phone app are static pages served by the same service:
  plain HTML, CSS and ES modules, GSAP for animation, no bundler, no framework.
- The screens are opened by a display box (mini PC, Debian 13, sway, three Chromium
  kiosk windows). During development the simulator page (`/sim`) shows all three.

## Repo layout (target)

```
server/app/            FastAPI app
  feed/                ShlClient, sources (live, replay, recording)
  engine/              normalizer, state, stats, powerplay, delay, director, calibration
  api/                 REST routes, websocket hub, webhook dispatcher
  clock.py             injectable Clock (real + fake for tests)
  config.py            settings (env vars) and persisted runtime state
server/tests/          pytest; fixtures in server/tests/fixtures/
web/screens/           left.html, bar.html, right.html + shared js/css
web/sim/               simulator page
web/app/               phone web app (PWA)
web/vendor/            gsap, fonts (vendored, no CDN at runtime)
config/wall.json       screen geometry
tools/                 fetch_fixtures.py, record_game.py, analyze_recording.py,
                       synth_recording.py, snapshot.py (shared: shl_http.py)
deploy/                display box files (sway config, kiosk script, systemd units)
docs/                  plan and specs
```

## Commands

```
docker compose up --build            # service on http://localhost:8080
cd server && uv run pytest           # tests (use uv; fall back to pip + venv if missing)
cd server && uv run pytest -m "not live"      # offline tests only
cd server && uv run ruff check . ../tools     # lint (server and tools)
uv run --project server python tools/fetch_fixtures.py        # refresh test fixtures
uv run --project server python tools/record_game.py <uuid>    # record a live game
uv run --project server python tools/analyze_recording.py data/recordings/<uuid>
uv run --project server python tools/synth_recording.py bdhvuc5tex   # fake recording
```

Pages once built: `/sim`, `/app`, `/screens/left.html`, `/screens/bar.html`, `/screens/right.html`.

## Hard rules

1. **Nothing reaches a screen, the phone or Home Assistant before its `play_at`.**
   Every derived number (score, shots, shot-map dots, standings) goes through the
   DelayQueue. A raw value leaking early spoils a goal 30 s before the TV shows it.
   Raw data may only appear in the phone app's debug view, behind an explicit toggle.
2. **Time comes from our own clock.** Use `first_seen_ms` for all timing. It is our
   estimate of when the data became available, on our clock: `received_ms − age × 1000`
   of the first poll that contained the event, where `age` is the HTTP `Age` header from
   Cloudflare (0–9 s, see `docs/SHL_API.md`, Caching). Without a usable `Age` header it
   falls back to `received_ms`. Decided 2026-10-20: this removes up to 10 s of cache
   jitter from the TV sync. Feed timestamps are inconsistent about time zones (see `docs/SHL_API.md`)
   and are only used for display and for ordering within a period.
3. **All timing code takes an injectable `Clock`.** Tests use a fake clock and run
   instantly. No `time.sleep` or `asyncio.sleep` on the real clock in engine code.
4. **Engine tests use fixtures; live API tests call shl.se by default.** Engine logic is
   tested against the fixtures in `server/tests/fixtures/`. Tests marked `live` (decided
   2026-10-20) call the real shl.se in the default `pytest` run to catch API changes; run
   offline with `pytest -m "not live"`. Live tests fetch each URL at most once per session.
   Outside tests, only `tools/` scripts and `LiveSource` touch the network.
5. **Be polite to shl.se.** Poll only the selected game: `game-info` every 60 s until
   15 min before puck drop, then `game-info` and `play-by-play` every 2 s until the game is
   over. Never poll when no game is selected. Cache the schedule for one hour. Exponential backoff on errors (2 s doubling to 30 s). Send a
   `User-Agent: shl-arena/<version> (private home display)` header.
6. **Teams are identified by uuid**, never by code. Codes differ between endpoints
   (Skellefteå is `SAIK` and `SKE`, Örebro is `OHK` and `ÖRE`).
7. **Unknown values are logged, not guessed.** An unknown game state, goal status or
   offence code is logged once at WARNING with the raw value and shown raw on screen.

## Conventions

- Code, comments, logs and docs in English. **All text on screens and in the phone app
  is Swedish.** Use the en dash (–) for scores and ranges ("2–1", "19:00–21:30");
  never use the em dash (—) in Swedish copy.
- Python: type hints everywhere, pydantic v2 models for API payloads, `httpx.AsyncClient`
  for HTTP, `ruff` clean, small modules. Engine code is pure and synchronous where it can
  be; I/O lives in `feed/` and `api/`.
- Front end: ES modules, no build step. One module per scene. Animate only `transform`
  and `opacity`. Every animation is scheduled from a `play_at` timestamp using the
  synced clock, never from "message received".
- Screens are authored at native pixels (1080×1920 portrait, 1920×360 bar).
- Commit at the end of each task with a message naming the phase and task.

## Definition of done for a task

- The phase's acceptance criteria in `docs/PLAN.md` pass.
- `pytest` and `ruff` are clean.
- New behaviour has tests (engine) or is visible in `/sim` (front end).
- `docs/` updated if an assumption was confirmed or changed (especially `docs/SHL_API.md`).
- Stop after the phase and summarise what was built, what was verified and what is still open.
