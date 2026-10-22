# Test fixtures

Fetched from shl.se on 2026-10-21 07:05 UTC by `tools/fetch_fixtures.py` (User-Agent
`shl-arena/0.1.0 (private home display)`). Responses are saved unchanged apart from pretty-printing.
Refresh with `uv run --project server python tools/fetch_fixtures.py`.

Games:

- `bdhvuc5tex`: Frölunda–Linköping 2–1, 2025-09-13
- `m01wkdm2u1`: HV71–Skellefteå 4–3 after overtime, 2026-09-24
- `et9erhx0si`: Frölunda–Skellefteå 3–2 after shootout, 2026-10-17

Played at the same time as `et9erhx0si` (game-info and play-by-play only, fetched
2026-10-21 with `tools/fetch_fixtures.py --evening-only`):

- `pmch0rrshr`: Djurgården–Malmö, 2026-10-17 15:15
- `ux4bplsxbh`: Luleå–HV71, 2026-10-17 15:15
- `wffn21lxeb`: Rögle–Örebro, 2026-10-17 15:15
- `yklkh1aqmw`: Linköping–Färjestad, 2026-10-17 15:15

Pregame slides (Phase 8), fetched 2026-10-22 with `tools/fetch_fixtures.py --history-only`:
Frölunda's and Skellefteå's top three by points and by goals this season, and the
2025/2026 schedules (regular season, playoffs) for head-to-head meetings.

| File | Source URL |
|---|---|
| `filter.json` | https://www.shl.se/api/sports-v2/season-series-game-types-filter |
| `schedule_2026.json` | https://www.shl.se/api/sports-v2/game-schedule?seasonUuid=ndcf81nlb3&seriesUuid=qQ9-bb0bzEWUk&gameTypeUuid=qQ9-af37Ti40B&gamePlace=all&played=all |
| `site_settings.json` | https://www.shl.se/api/site/settings |
| `standings_qa98unlbd6.json` | https://www.shl.se/api/gameday/team-standings/qa98unlbd6 |
| `game_info_bdhvuc5tex.json` | https://www.shl.se/api/sports-v2/game-info/bdhvuc5tex |
| `pbp_bdhvuc5tex.json` | https://www.shl.se/api/gameday/play-by-play/bdhvuc5tex |
| `boxscore_bdhvuc5tex.json` | https://www.shl.se/api/gameday/boxscore/bdhvuc5tex |
| `team_stats_bdhvuc5tex.json` | https://www.shl.se/api/gameday/team-stats/bdhvuc5tex |
| `game_info_m01wkdm2u1.json` | https://www.shl.se/api/sports-v2/game-info/m01wkdm2u1 |
| `pbp_m01wkdm2u1.json` | https://www.shl.se/api/gameday/play-by-play/m01wkdm2u1 |
| `boxscore_m01wkdm2u1.json` | https://www.shl.se/api/gameday/boxscore/m01wkdm2u1 |
| `team_stats_m01wkdm2u1.json` | https://www.shl.se/api/gameday/team-stats/m01wkdm2u1 |
| `game_info_et9erhx0si.json` | https://www.shl.se/api/sports-v2/game-info/et9erhx0si |
| `pbp_et9erhx0si.json` | https://www.shl.se/api/gameday/play-by-play/et9erhx0si |
| `boxscore_et9erhx0si.json` | https://www.shl.se/api/gameday/boxscore/et9erhx0si |
| `team_stats_et9erhx0si.json` | https://www.shl.se/api/gameday/team-stats/et9erhx0si |
| `leaders_points_fhc.json` | https://www.shl.se/api/statistics-v2/stats-info/players_point?ssgtUuid=qa98unlbd6&provider=statnet&count=3&teamUuid=087a-087aTQv9u |
| `leaders_goals_fhc.json` | https://www.shl.se/api/statistics-v2/stats-info/players_goal?ssgtUuid=qa98unlbd6&provider=statnet&count=3&teamUuid=087a-087aTQv9u |
| `leaders_points_ske.json` | https://www.shl.se/api/statistics-v2/stats-info/players_point?ssgtUuid=qa98unlbd6&provider=statnet&count=3&teamUuid=50e6-50e6DYeWM |
| `leaders_goals_ske.json` | https://www.shl.se/api/statistics-v2/stats-info/players_goal?ssgtUuid=qa98unlbd6&provider=statnet&count=3&teamUuid=50e6-50e6DYeWM |
| `filter_2025.json` | https://www.shl.se/api/sports-v2/season-series-game-types-filter?season=xs4m9qupsi |
| `schedule_2025_regular.json` | https://www.shl.se/api/sports-v2/game-schedule?seasonUuid=xs4m9qupsi&seriesUuid=qQ9-bb0bzEWUk&gameTypeUuid=qQ9-af37Ti40B&gamePlace=all&played=all |
| `schedule_2025_playoff.json` | https://www.shl.se/api/sports-v2/game-schedule?seasonUuid=xs4m9qupsi&seriesUuid=qQ9-bb0bzEWUk&gameTypeUuid=qQ9-7debq38kX&gamePlace=all&played=all |
