# SHL Arena

Broadcast-style graphics for SHL games at home: a stretched 28" LCD bar
(1920×360) between two portrait 24" screens (1080×1920), driven by shl.se's
live data, delayed to match the TV picture, with goal lights and horns in
Home Assistant.

## Status

Planning done, nothing built yet. The build is split into phases in
[`docs/PLAN.md`](docs/PLAN.md), designed to be implemented by Claude Code one
phase at a time.

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

- `http://<host>:8080/sim`: the whole wall in one browser window, with replay controls
- `http://<host>:8080/app`: phone app (game selection, calibration, scenes)
- `http://<host>:8080/screens/left.html`, `bar.html`, `right.html`: the three screen pages

## Docs

| File | Contents |
|---|---|
| `CLAUDE.md` | Architecture, rules and conventions (loaded by Claude Code every session) |
| `docs/PLAN.md` | Phases, tasks, acceptance criteria, decisions and open questions |
| `docs/SHL_API.md` | Verified shl.se endpoints, field paths and data quirks |
| `docs/PROTOCOL.md` | REST API, WebSocket messages, Home Assistant webhooks |
| `docs/SCREENS.md` | Wall geometry, design tokens, scenes, simulator, phone app |
| `config/wall.json` | Physical screen layout |
