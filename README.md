# SHL Arena

Broadcast-style graphics for SHL games at home: a stretched 28" LCD bar
(1920×360) between two portrait 24" screens (1080×1920), driven by shl.se's
live data, delayed to match the TV picture, with goal lights and horns in
Home Assistant.

## Status

Phases 0 to 2 done: a service (`/api/health`, page index), test fixtures from
shl.se, the game recorder and recording analyzer, and the feed client, replay and
recording sources, normalizer, game state and power-play tracker
(`cd server && uv run python -m app.cli replay bdhvuc5tex --instant`), and the delay
queue, TV state, scene director, WebSocket hub and REST API with a `/debug` page. The
build is split into
phases in [`docs/PLAN.md`](docs/PLAN.md), designed to be implemented by Claude
Code one phase at a time.

## Recording a live game

Later phases need a real recording (and it answers the open questions in
`docs/SHL_API.md`). Find the game uuid in the schedule
(`server/tests/fixtures/schedule_2026.json`, or the shl.se game page URL), then
start the recorder any time before puck drop and leave it running:

```
# with uv, from the repo root
uv run --project server python tools/record_game.py <game_uuid>

# or with Docker, writes to ./data like the service
docker compose run --rm arena python /srv/tools/record_game.py <game_uuid>
```

It polls game-info once a minute until 15 min before the start, then game-info
and play-by-play every 2 s, and stops by itself 5 min after the game ends
(Ctrl-C stops it earlier; a restart appends to the same file). Then:

```
uv run --project server python tools/analyze_recording.py data/recordings/<game_uuid>
```

writes `data/recordings/<game_uuid>/report.md`. Keep `polls.jsonl` for later phases.

## Building it with Claude Code

1. Create an empty git repo and copy this folder's contents into it.
2. Optional: export the four mockup scenes from the design canvas
   ("SHL Arena Screens") as PNG files into `docs/mockups/`
   (`pregame.png`, `live.png`, `goal.png`, `intermission.png`).
   Claude Code can look at them; the written spec in `docs/SCREENS.md` is enough without them.
3. Start Claude Code in the repo root and give it this first prompt:

   > Read CLAUDE.md and docs/PLAN.md. Implement Phase 0 only. Verify every
   > acceptance criterion, commit, then stop and summarise what you built,
   > what you verified and anything that differed from the docs.

4. Review, then continue with "Implement Phase 1" and so on. Start a fresh
   session for each phase if the context gets long; everything it needs is in the repo.

## Quick start (once built)

```
docker compose up --build
```

- `http://<host>:8010/sim`: the whole wall in one browser window, with replay controls
- `http://<host>:8010/app`: phone app (game selection, calibration, scenes)
- `http://<host>:8010/screens/left.html`, `bar.html`, `right.html`: the three screen pages

## Docs

| File | Contents |
|---|---|
| `CLAUDE.md` | Architecture, rules and conventions (loaded by Claude Code every session) |
| `docs/PLAN.md` | Phases, tasks, acceptance criteria, decisions and open questions |
| `docs/SHL_API.md` | Verified shl.se endpoints, field paths and data quirks |
| `docs/PROTOCOL.md` | REST API, WebSocket messages, Home Assistant webhooks |
| `docs/SCREENS.md` | Wall geometry, design tokens, scenes, simulator, phone app |
| `config/wall.json` | Physical screen layout |
