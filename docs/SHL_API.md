# shl.se JSON API: what we know

The SHL website loads its data from JSON endpoints under `https://www.shl.se/api/`.
They are public but undocumented and can change without notice. Everything marked
**verified** below was fetched and inspected on 2026-10-20. Items marked **assumption**
or **unknown** must be checked against a real recording (Phase 0 recorder) and this file
updated.

A wider endpoint list (27 endpoints) is documented by the SportsDataverse project:
https://py.sportsdataverse.org/docs/shl/reference/shl

## Known IDs (verified)

| What | Value |
|---|---|
| Series SHL | `qQ9-bb0bzEWUk` |
| Season 2026/2027 | `ndcf81nlb3` (code `"2026"`) |
| Season 2025/2026 | `xs4m9qupsi` |
| Game type, regular season | `qQ9-af37Ti40B` (only game type listed so far this season) |
| Current ssgt (season+series+gametype) | `qa98unlbd6` |
| Example finished game | `bdhvuc5tex`: Frölunda–Linköping 2–1, 2025-09-13, Scandinavium, 12 044 spectators |
| Overtime example | `m01wkdm2u1`: HV71–Skellefteå 4–3 OT, 2026-09-24 |
| Shootout example | `et9erhx0si`: Frölunda–Skellefteå 3–2 SO, 2026-10-17 |

Never hard-code the season: read it from the filter endpoint's `defaultSsgtFilter`.

## Endpoints

### Season/series/game-type filter (verified)

`GET /api/sports-v2/season-series-game-types-filter`

```json
{
  "series":   [{"uuid": "qQ9-bb0bzEWUk", "code": "SHL", "names": [...]}, {"uuid": "qQ9-9397drVEh", "code": "CHL", ...}],
  "season":   [{"uuid": "ndcf81nlb3", "code": "2026", "names": [{"language": "sv", "translation": "2026/2027"}]}, ...],
  "gameType": [{"uuid": "qQ9-af37Ti40B", "code": "regular", "names": [...]}],
  "defaultSsgtFilter": {"season": "ndcf81nlb3", "series": "qQ9-bb0bzEWUk", "gameType": "qQ9-af37Ti40B"},
  "ssgtUuid": "qa98unlbd6"
}
```

### Game schedule (verified)

`GET /api/sports-v2/game-schedule?seasonUuid=<s>&seriesUuid=<se>&gameTypeUuid=<gt>&gamePlace=all&played=all`

```json
{"gameInfo": [{
  "uuid": "mtn5yq64mp",
  "rawStartDateTime": "2026-10-20T17:00:00.000Z",
  "startDateTime": "2026-10-20 19:00:00",
  "state": "pre-game",
  "overtime": false, "shootout": false,
  "ssgtUuid": "qa98unlbd6",
  "homeTeamInfo": {
    "status": "N/A",
    "uuid": "087a-087aTQv9u", "ownerInstanceId": "fhc1_fhc", "code": "FHC",
    "names": {"code": "FHC", "short": "Frölunda ", "long": "Frölunda HC", "full": "Frölunda Hockey Club",
              "codeSite": "FHC", "shortSite": "Frölunda", "fullSite": "...", "longSite": "Frölunda HC"},
    "score": "N/A",
    "icon": "https://sportality.cdn.s8y.se/team-logos/fhc1_fhc.svg"
  },
  "awayTeamInfo": {"...": "same shape"},
  "venueInfo": {"uuid": "qQ9-f9a9cjS0U", "name": "Scandinavium"},
  "seriesInfo": {"uuid": "qQ9-bb0bzEWUk", "code": "SHL", "displayName": "SHL"},
  "roundNumber": 25, "roundLabel": ""
}]}
```

- `rawStartDateTime` is real UTC. `startDateTime` is local Swedish time without zone.
- `state` seen: `pre-game`, `post-game`. Live value **unknown**.
- `score` is an integer after the game and the **string** `"N/A"` before it.
  (game-info differs: there a pre-game `score` is the empty string `""`, verified 2026-10-20.)
- `status` is `WIN`, `LOSE` or `N/A`.
- `roundNumber` is not reliable for ordering (rescheduled games keep odd round numbers).

### Game info (verified)

`GET /api/sports-v2/game-info/<game_uuid>`

```json
{
  "gameInfo": {"gameUuid": "bdhvuc5tex", "extId": "22003", "startDateTime": "2025-09-13T13:15:00.000Z",
               "arenaName": "Scandinavium", "state": "post_game", "overtime": false, "shootout": false,
               "seriesCode": "SHL", "roundNumber": 1, ...},
  "homeTeam": {"names": {...}, "uuid": "087a-087aTQv9u", "icon": "...svg", "score": 2, ...},
  "awayTeam": {"names": {...}, "uuid": "41c4-41c4BiYZU", "icon": "...svg", "score": 1, ...},
  "ssgtUuid": "iuzqg7dqk9", "seriesUuid": "qQ9-bb0bzEWUk"
}
```

- `state` here uses an **underscore** (`post_game`) while the schedule uses a hyphen
  (`post-game`). Normalise by replacing `_` with `-`.

### Play-by-play (verified)

`GET /api/gameday/play-by-play/<game_uuid>`

A JSON **array**, newest event first, with period objects appended at the end.

Common fields on every event (not on period objects):

```json
{
  "gameSourceId": "20250913-FHC-LHC", "gameId": 22003, "eventId": 96,
  "eventUuid": "e7ba057e-...", "gameUuid": "bdhvuc5tex",
  "round": 1, "gameType": "Elitserien", "arena": "Scandinavium", "attendance": 12044,
  "startDateAndTime": "2025-09-13T15:15:00",
  "period": 3, "time": "09:07", "gameState": "GameEnded", "revision": 3, "type": "goal",
  "realWorldTime": "2025-09-13T17:10:22.536784",
  "updatedTime": "2025-09-13T15:34:22.161003",
  "homeTeam": {"teamId": "FHC", "teamName": "Frölunda HC", "teamCode": "FHC", "score": 2},
  "awayTeam": {"teamId": "LHC", "teamName": "Linköpings HC", "teamCode": "LHC", "score": 1},
  "eventTeam": {"teamId": "FHC", "place": "home", "teamCode": "FHC", "teamName": "Frölunda HC"},
  "player": {"playerId": "6433", "firstName": "Arttu", "familyName": "Ruotsalainen", "jerseyToday": "25"}
}
```

- `time` is elapsed time **in the period**, counting up, `"MM:SS"`.
- `homeTeam.score` / `awayTeam.score` on each event are the score at that moment.
- `eventTeam.place` is `home` or `away`: use it for side, not the codes.
- Team names here can differ from the site's (`Linköpings HC` vs `Linköping HC`).
- `playerId` and `jerseyToday` are strings.
- `eventId` has gaps (10, 15, 22, 58 and 100 are missing in `bdhvuc5tex`). **Assumption:**
  gaps are events deleted before the game ended. Treat a disappearing id as a removal.
- Event order by `eventId` is feed order. Ordering by `time` can disagree slightly
  (a shot at P2 00:22 has a higher id than the goal at P2 00:24). Use (period, time) for timelines.

Types seen: `goal`, `shot`, `penalty`, `goalkeeper`, `timeout`, `period`.

**shot**

```json
{"type": "shot", "locationX": 165, "locationY": -135, "goalSection": -3, "isPenaltyShot": false}
```

- `goalSection` values seen: -3, -1 and 0 to 9 (-1 once: `bdhvuc5tex` event 131, LHC, P3 19:58).
  **Original assumption:** only -3 means missed the net. **Contradicted by the boxscores
  (checked 2026-10-20):** in all three fixture games, counting `shot` + `goal` events with
  `goalSection` **1 to 9** gives exactly the boxscore's per-team skater `SOG` sum
  (`bdhvuc5tex` FHC 31 / LHC 29, `m01wkdm2u1` 24 / 40, `mtn5yq64mp` 44 / 14 at the
  end of the recording; 45 / 14 after the post-game corrections). The "-3 only"
  rule gives 40 / 43 for `bdhvuc5tex`. **Checked against shl.se's game report
  (2026-10-21, `mtn5yq64mp`):**

  | `goalSection` | Site shows | Engine `result` |
  |---|---|---|
  | 1 to 9 | Skott | `on_goal` |
  | 0 | Skott (utanför) | `wide` |
  | -3 | Skott (täckt av spelare) | `blocked` |
  | -1 | not checked (seen once, `bdhvuc5tex` P3 19:58); likely "Ramträff" (post) | `unknown`, logged once |

  (First guess was 0 blocked, -3 missed: the other way round.) **Decided 2026-10-20:**
  the engine uses `ON_GOAL_SECTIONS = 1..9`; goals always count as on goal (all goals in
  the samples have a section 1 to 9).
- What 1 to 9 mean (open). Probably where on the goal the shot went, but **not a clean
  3 × 3 grid**. Observations:
  - 5 and 8 are never goals although they are the most common sections: 5 only in the
    2025/26 fixture, 8 only in 2026/27 games (22–32 per game). Likely "into the goalie";
    the numbering or the scorers' habits seem to have changed between seasons.
  - The user compared all eight `mtn5yq64mp` goals with the video (goalie's perspective):

    | Goal | Section | Where it went in |
    |---|---|---|
    | P1 03:47 Heens | 6 | left post, mid height |
    | P1 10:01 Thorell | 6 | left post, along the ice |
    | P2 05:04 Tömmernes | 1 | right post, along the ice |
    | P2 07:36 Wahlstrom | 2 | right post, along the ice |
    | P2 10:50 Fagemo | 3 | middle, along the ice |
    | P3 07:20 Lindholm | 4 | left post, high |
    | P3 09:21 Westergård | 3 | along the ice, a little towards the left post |
    | P3 17:09 Hudon | 2 | middle, along the ice (deflection) |

    The last two were predicted from the first six (3 = middle, 2 = goalie's right);
    both predictions were off.
    **Conclusion (2026-10-21):** at most a rough side tendency (low numbers towards the
    goalie's right), no reliable height; the scorers' manual entry and slow-motion
    judgement both add noise. Decided: use 1 to 9 only as "on goal"; no goal-zone
    graphic. Shot graphics use `locationX` / `locationY` (where the shot was taken from).
- Shootout and shots: in `et9erhx0si` the home skaters' `SOG` sum is 16, which **includes
  the deciding shootout goal**; the away goalies' `SOGA` is 15, which does not. Regulation
  and overtime shots (period an int) give 15 / 23. The engine leaves the shootout out of
  shot and goal stats.
- The earlier counter-example (event 120 in `bdhvuc5tex`, "FHC, P3 18:01, `goalSection` 5")
  is an **LHC** shot in the feed (Christoffer Ehn, revision 1), i.e. by the team that had
  pulled its goalie. Not a contradiction.
- `locationX` / `locationY` (**verified 2026-10-21** against shl.se's shot plot for
  `mtn5yq64mp`, five shots within about 1.5 m): decimetres on a 60 × 30 m rink.
  `locationX` = distance out from the goal line being attacked; `locationY` = lateral,
  negative on the attacking team's left (the goalie's right). Outliers exist (X 481,
  X -29): skip anything outside 0 to 300 for the shot map.
- shl.se's shot plot: "SKOTT" is all attempts (`shot` + `goal`, regulation and overtime),
  "MÅL%" goals / attempts. Symbols: circle = "Räddat skott", square = "Blockat skott",
  cross = "Skott utanför", G = "Mål"; it also filters on "Ramträff". For `mtn5yq64mp`
  its counts (FHC 6 goals / 67 shots, DIF 2 / 38; DIF 12 saved, 8 blocked, 16 wide) equal
  ours from the final play-by-play.

**goal**

```json
{
  "type": "goal", "locationX": 51, "locationY": 68, "goalSection": 9,
  "homeGoals": 2, "awayGoals": 1,
  "isPenaltyShot": false, "isEmptyNetGoal": false,
  "goalStatus": "PP1",
  "player": {"...": "...", "statistics": [{"key": "G", "value": "1"}, {"key": "A", "value": "0"}]},
  "assists": {"first": {"playerId": "6432", "firstName": "Dominik", "familyName": "Egli", "jerseyToday": "46",
                        "statistics": [{"key": "G", "value": "0"}, {"key": "A", "value": "1"}]},
              "second": {"...": "..."}},
  "pop": [{"playerId": "2427", "firstName": "Lars", "familyName": "Johansson", "jerseyToday": "1"}, "..."],
  "nep": ["... players of the conceding team on the ice ..."]
}
```

- `homeGoals` / `awayGoals`: score after the goal. Use these for the score shown with the goal.
- `goalStatus` seen: `EQ` (even strength), `PP1` (power play). Others **unknown**
  (expect short-handed and empty-net variants). Show unknown values raw and log them.
- `pop` = scoring team's players on the ice (goalie included), `nep` = the other team's.
- `player.statistics` = the scorer's goals and assists **this season** after this goal
  (corrected 2026-10-21: in the 2026-10-20 recording Fagemo's only goal of the game had
  `G` 4). The goals in this game are counted from the play-by-play (`scorer_game_goals`).
- Goals can have high revision numbers (one had revision 5); details get corrected after the fact.

**penalty**

```json
{"type": "penalty",
 "variant": {"shortName": "Minor", "minorTime": "2", "doubleMinorTime": "0", "benchTime": "0",
             "majorTime": "0", "misconductTime": "0", "gMTime": "0", "mPTime": "0", "description": "2 min"},
 "offence": "HOLD", "didRenderInPenaltyShot": false}
```

Offence codes seen and the text to show. The English names are kept on screen, as
Swedish hockey uses them (decided by the user 2026-10-21: "vi översätter inte hooking,
tripping"):

| Code | Shown |
|---|---|
| `TRIP` | Tripping |
| `HOLD` | Holding |
| `CROSS` | Cross-checking |
| `INTRF` | Interference |
| `BOARD` | Boarding |
| `ROUGH` | Roughing |
| `SLASH` | Slashing |
| `FIGHT` | Fighting |
| `HOOK` | Hooking |
| `DELAY` | Delay of game |
| `TOO-M` | Too many men (team penalty: no `player`, variant `Bench`) |
| `P-SHOT` | Penalty shot (penalty shot awarded; empty `variant`, no minutes) |

Unknown codes: show the code and log it. Extend the table as new codes appear. The table
lives in `server/app/engine/offences.py`.

Penalty minutes: the sum of all `variant.*Time` fields matches the boxscore `PIM` sums
(`gMTime` is 20 for a game misconduct). Team (bench) penalties are not in the boxscore's
player sums: `et9erhx0si` SKE has 2 PIM in the boxscore plus a 2 min bench minor.

**goalkeeper**: `{"type": "goalkeeper", "isEntering": true|false}`. `false` mid-game means the
goalie was pulled (or left); the game also ends with `isEntering: false` events at 20:00.
A goalie change is an exit and an entry at the same second, **in either eventId order**:
VLH–FBK 2026-10-31 (P1 12:06, entry 25 before exit 26) and MIF–LHC 2026-10-27 (P2 05:20,
76 before 77). Read in eventId order the exit comes last and the team looks pulled for the
rest of the game. In 14 games (2026-10-24 to 29) exits without an entry came only late in
the third or in overtime (pulls for an extra skater); delayed penalties have no exit
events. So `state.py` takes an exit and an entry at one second as a change, and ignores an
exit in period 1 or 2 until its entry comes.

**timeout**: no player, only `eventTeam`.

**period** (no `eventId`):

```json
{"gameSourceId": "20250913-FHC-LHC", "gameId": 22003, "period": 1, "type": "period",
 "started": true, "startedAt": "2025-09-13T15:14:26.032Z",
 "finished": true, "finishedAt": "2025-09-13T15:46:48.027Z",
 "realWorldTime": "2025-09-13T15:46:48.275351", "gameUuid": "bdhvuc5tex"}
```

### Shootout (verified from `et9erhx0si`)

- A `period` object with `"period": "shootout"` (a **string**, not an int) follows period 4.
- Each attempt is an event of type `shootout-penalty-shot` with `period: "shootout"`,
  `time: "00:00"`, `isPenaltyShot: true`, `isGoal`, `isGameWinningGoal`, `shootoutIndex`
  (1, 2, ... in order) and `shootoutScore: {"homeGoals", "awayGoals"}` (the shootout tally).
- The deciding attempt is **also** a normal `goal` event with `period: "shootout"`,
  `time: "00:00"`, `goalStatus: "EQ"` and `homeGoals`/`awayGoals` set to the final score
  (3–2). Stats code must skip `period == "shootout"` or it counts an extra goal and shot.
- game-info: `shootout: true`, final score includes the shootout goal.
- Overtime (`m01wkdm2u1`): period 4 is an ordinary int period; game-info `overtime: true`.

### Boxscore (verified 2026-10-20)

`GET /api/gameday/boxscore/<game_uuid>`. Returns 200 even for a pre-game game.

```json
{
  "dataColumns": [{"name": "NR", "type": "string", "highlighted": false, "group": ""}, "..."],
  "players":     {"homeTeamValue": {"<playerId>": {"fullName", "firstName", "lastName", "extIds"}}, "awayTeamValue": {}},
  "stats":       {"homeTeamValue": [{"NR": 7, "POS": "LD", "LINE": 1, "G": 0, "A": 0, "PPG": 0, "SW": 2,
                                     "PIM": 0, "SOG": 2, "PPSOG": 0, "+/-": 0, "TOI": "22:21", "Hits": 0,
                                     "FOW": 0, "FOL": 0, "FOPerc": 0,
                                     "info": {"period": 0, "playerId": 1332, "teamId": "FHC", "team": "home"}}],
                  "awayTeamValue": []},
  "gkDataColumns": ["..."],
  "gkStats":     {"homeTeamValue": [{"NR": 1, "POS": "GK", "GA": 1, "SOGA": 29, "SPGA": 14, "SVS": 28,
                                     "SVS%": "0.9655...", "info": {"...": "..."}}], "awayTeamValue": []},
  "goalkeepers": {"homeTeamValue": {"<playerId>": {"...": "..."}}, "awayTeamValue": {}},
  "provider": "statnet"
}
```

- `playerId` is an **int** here (a string in play-by-play).
- **Faceoffs exist only here** (`FOW` / `FOL` per skater); play-by-play has no faceoff
  events. `mtn5yq64mp`: FHC 25, DIF 28 won, equal to shl.se's "Vunna tekningar". The
  pre-game boxscore had all zeros.
- shl.se's final stats for `mtn5yq64mp` ("Skott på mål" 45–14, "Räddningsprocent"
  85.71–86.67, "Publik" 11361) all follow from play-by-play: shots on goal by the 1–9 rule
  plus goals, save % = (opponent shots on goal − goals against) / opponent shots on goal,
  attendance from the `attendance` field on every event.
- `SVS%` is a string. `info.period` 0 = whole game.
- Team shots on goal: sum of skater `SOG`. The opposing goalies' `SOGA` sum agrees in 5 of 6
  team-games; `et9erhx0si` home has SOG 16 vs SOGA 15.

### Standings (verified 2026-10-20)

`GET /api/gameday/team-standings/<ssgt_uuid>`

```json
{"ssgtUuid": "qa98unlbd6", "season": 2026, "gameType": "SHL", "provider": "statnet",
 "leagueStandings": [{"id": "FBK", "rank": 1, "rankDiff": 0, "GP": 10, "W": 8, "T": 2, "L": 0,
                      "OTW": 1, "OTL": 1, "P": 27, "GF": 40, "GA": 11, "Diff": 29,
                      "info": {"code": "Färjestad", "teamId": "FBK",
                               "teamInfo": {"teamUuid": "752c-752c12zB7Z", "teamMedia": "...svg",
                                            "teamNames": {"code", "short", "long", "full", "...": "..."}}}}],
 "groupings": [{"description": "Playoff", "first": 1, "last": 6}, "..."]}
```

- 14 teams. Identify teams by `info.teamInfo.teamUuid`; `id` is a code.
- `groupings` (verified 2026-10-23) are SHL's zones of the table: `Playoff` 1–6 (straight
  to the quarter-finals), `Playin` 7–10, `MissedPlayoff` 11–12, `QualificationDown` 13–14
  (the qualifier against HockeyAllsvenskan). Read them, do not hard-code the ranges: they
  follow the season's format. Each row also has `rankDiff` (not used yet).

### Endpoints used by shl.se itself (found 2026-10-21)

From the site's JavaScript bundle (`/assets/index-*.js`), all under `/api`:
`gameday/` boxscore, game-info, game-overview, gameheader, periodstats, play-by-play,
play-by-play/initial-events, player-stats, post-game-data/promo-bar-stats,
post-game-data/team-stats, team-standings, team-stats, upcoming-live-games(/v2);
`sports-v2/` all-sites, all-teams, athlete-details, athletes/by-team-uuid, game-info,
game-schedule, game-series/by-ssgt, last-game-day, latest-ssgt, next-game-day,
played-games, season-series-game-types-filter, staffs, teams, today-games, upcoming-games,
upcoming-live-games. Only the ones described in this file have been inspected
(`gameday/periodstats/<game>` returned HTTP 500 for `mtn5yq64mp`).

### Earlier seasons and playoffs (verified 2026-10-22)

- `GET /api/sports-v2/season-series-game-types-filter?season=<season uuid>` lists that
  season's game types: for 2025/2026 `regular` (`qQ9-af37Ti40B`), `qualdown`
  (`qRf-347BaDIOc`) and `playoff` (`qQ9-7debq38kX`). With `seasonUuid=` instead, or none,
  only the default (regular) comes back.
- The game schedule takes any of them: playoff games have the same shape as regular ones,
  `roundLabel` "Eight final 1", "Quarter final 3" and so on (44 playoff games in 2025/26).
- Team uuids are the same across seasons (Frölunda `087a-087aTQv9u` in 2025/26 and
  2026/27), so head-to-head meetings are found by uuid over seasons. The filter's
  `season` list is newest first: 2026, 2025, 2024, ...

### Statistics (verified 2026-10-22)

Found in the site's bundle (`STATS_V2` in `/assets/index-*.js`): `statistics-v2/`
overview, stats-info, layout-info, featured/athlete/leaderboard, game-form,
game-center/team-h2h, player-h2h, league-standings and more. Used:

- `GET /api/statistics-v2/stats-info/<module>?ssgtUuid=<ssgt>&provider=statnet&count=<n>&teamUuid=<team>`:
  a list with one object `{dataColumns, defaultSortKey, stats, ...}`; `stats` are the
  rows, best first, each with `info` (the athlete: `uuid` = the athlete uuid of
  `athletes/by-team-uuid`, `firstName`, `lastName`, `number`, `position`, `playerMedia`,
  `team`) and the numbers: `players_point` gives `Rank`, `GP`, `G`, `A`, `TP`, ...;
  `players_goal` gives `Rank`, `G`, `GP`, `GWG`, ... `teamUuid` filters on one team
  (`team=` is ignored and returns the league); `count` limits the rows.
- Modules (from `layout-info?statisticsType=players`): players_summary, players_point,
  players_goal, players_powerplay, players_penalty, players_plusMinus, players_faceoff,
  goalkeepers_summary, teams_result, teams_goal, teams_powerplay, games_games and more;
  filters `location`, `position`, `outcome`, `team`, `vsTeam`. The provider is `statnet`
  (also in the standings response).
- `GET /api/statistics-v2/overview/<ssgt>?provider=statnet`: the league's top ten by goals,
  points, penalty minutes and save %, and the teams' by wins, goals, PP % and PK %.

### Team stats (verified 2026-10-21)

`GET /api/gameday/team-stats/<game_uuid>`: `{"home": {...}, "away": {...}}`, each with
`teamId`, `place` and `statistics`: a list per `period` (0 = whole game) of
`parsedTotalStatistics` `[{"key", "value"}]`. Keys include `G`, `PIM`, `FOW` (faceoffs
won), `SOG`, `Saves`, `GA`, `PPG`, `PPGA`, `SHG`, `SHGA`, `NumPP`, `NumSH`, `PP_perc`,
`SH_perc`, `Hits`, `BkS` (shots this team blocked), `SiBk` (this team's shots that were
blocked), `SPG`, `PPSOG`. For `mtn5yq64mp` it matches our numbers (SOG 45–14, FOW 25–28,
SiBk 10 / 8 = our blocked shots). **Power plays now match too** (FHC 1/3, DIF 0/1; and
FHC 1/3 – LHC 1/2, HV71 0/2 – SAIK 1/4, FHC 0/2 – SAIK 1/2 for the fixtures, tested). That
needed three rules worked out with the user from the 10:26 fight in `mtn5yq64mp` (shl.se
lists FHC: Meijer 5 fighting, Clarke, Cederqvist, Tömmernes 2 roughing; DIF: Grewe 2+5+GM
fighting, Grewe 2 holding, Carlsson, Pettersen #20, Pettersson #37 2 roughing; event 130
was corrected from #37 to #20 after the game, 131 is a real second penalty):
coincidental penalties cancel the same offence first (roughing against roughing, the
fighting majors against each other), one player's remaining penalties are served one
after the other (Grewe: 2 + 2, so FHC 5 on 4 for four minutes, not 5 on 3 for two), and a
chance is counted when a team gains a man advantage it did not have (so Hartmann's minor
at 14:17, during that power play, is not a new one, while 4 on 4 turning into 5 on 4 is).
No timestamps, so it cannot be synced to the TV. (shl.se's event list marks home events with ' and away events with ''.)

### Players and portraits (verified 2026-10-21)

- `GET /api/sports-v2/athletes/by-team-uuid/<team_uuid>`: the current roster grouped by
  position (`positionCode` GK, D, F), each player with `uuid` (athlete uuid), `firstName`,
  `lastName`, `jerseyNumber`, `nationality` and `renderedLatestPortrait.url` (a PNG
  portrait on an imgix CDN; `&w=320` style widths in `srcset`).
- `GET /api/sports-v2/athlete-details/<athlete_uuid>`: `athleteData.playerExtIds`; the
  entry with `extIdType.code == "isa"` is the play-by-play `playerId` (Jacob Peterson:
  athlete `qQ9-adafYNUQw`, isa `3770`). So: roster per team (one request) gives portraits;
  matching to play-by-play is exact via athlete-details (one request per player, cache it)
  or by team + name.
- Confirmed in Phase 3: the imgix URLs are signed (`&s=...`); adding or changing `w`
  breaks the signature, so pick a ready-made `srcset` entry (the service takes the
  smallest at least 480 px wide). The roster is the current one only: players who have
  left the team (Arttu Ruotsalainen, Frölunda's scorer in the 2025 fixture `bdhvuc5tex`)
  have no portrait. The service matches by name (accents ignored), then jersey number,
  instead of one athlete-details request per player.

### Team logos

Use the `icon` field (game-info, schedule, standings `teamMedia`), e.g.
`https://sportality.cdn.s8y.se/team-logos/fhc1_fhc.svg`. Guessing the file name from the
code fails (`oh1_oh.svg` is 403; Örebro is `ohk1_ohk.svg`, from `ownerInstanceId`).

### Site settings (verified, large)

`GET /api/site/settings`: `teamsInSite` / `allTeamsInSite` hold every team with `uuid`,
`teamNames` (`code`, `short`, `long`, `full`), `logo`/`icon` URL and `extIds`. Includes CHL
and HockeyAllsvenskan teams; filter by series `qQ9-bb0bzEWUk`. Use it to build the team directory.

## Time zones: the trap

| Field | Actual meaning |
|---|---|
| schedule `rawStartDateTime` | UTC, correctly marked `Z` |
| schedule `startDateTime` | Local Swedish time, no zone |
| game-info `startDateTime` | UTC, marked `Z` |
| pbp `startDateAndTime` | Local Swedish time, no zone |
| pbp `realWorldTime` | Local Swedish time, no zone |
| pbp `updatedTime` | UTC, no zone |
| period `startedAt` / `finishedAt` | **Local Swedish time, wrongly marked `Z`** |

In `bdhvuc5tex` the game starts 13:15 UTC, and period 1 `startedAt` is `15:14:26Z`: that is
15:14 local time, not UTC. Rule: never use feed timestamps for timing decisions; use our own
`first_seen_ms`. For display and replay, parse each field with the zone in the table.

## Caching (observed 2026-10-20, live game `mtn5yq64mp`)

```
client ──► Cloudflare ──► Varnish ──► Varnish ──► Express (origin)
```

- Responses carry `server: cloudflare`, `cf-cache-status`, `age`, two `x-varnish` headers,
  `via: 1.1 site-service-cached-1 (Varnish/7.3), 1.1 site-service-cached-0 (Varnish/7.3)`
  and `x-powered-by: Express`. No `cache-control` header was seen.
- Play-by-play is cached by Cloudflare for **10 s**: polled once a second, `age` counts
  0 to 9 and resets. Different Cloudflare servers can hold copies of different ages
  (9 followed by 7).
- A cache hit answers in about 50 ms. A refresh from the origin took up to 8.6 s on game
  night, which made the recorder's 5 s timeout fail repeatedly (`ReadTimeout`). DNS and
  connect times were a few ms, so it is not the client's network.
- Consequences: new events become visible in 10 s steps, so receive time alone jitters
  by up to 10 s. Use `received_ms − age × 1000` as the availability time (see CLAUDE.md
  rule 2). Polling every 2 s stays right: almost all polls are cheap cache hits, and
  faster polling gains nothing. Use a 15 s timeout.

## Live behaviour (observed 2026-10-20, `mtn5yq64mp`)

- **game-info is not updated during the game.** In period 3 it still said
  `state: "pre_game"` with `score: ""` for both teams, while play-by-play had the score
  4–1. Take live state and score from play-by-play.
  It was still `pre_game` at 21:36, nine minutes after play-by-play said `GameEnded`.
- Play-by-play `gameState` values: **`Ongoing`** (period running), **`Intermission`**,
  `GameEnded`. The value is copied onto **every** event, so at each period start/end every
  event in the list changes (also `attendance` once, and `updatedTime`). The normalizer
  must ignore `gameState`, `attendance` and `updatedTime` when deciding whether an event
  was updated, or each intermission produces ~100 `updated` events.
- Period objects appear when the period starts (`started: true, finished: false`) and get
  `finished: true` when it ends. Seen 22–31 s after `startedAt`, 14–26 s after `finishedAt`.

- **Corrections continue after the game.** After the recording stopped (5 min after
  `GameEnded`), shot 146 (P3 15:29) was deleted and replaced by 161 (P3 15:29, revision 3)
  and a new shot 162 (P3 15:32), and penalty 130's player name changed. A final refresh
  some time after the game is needed for exact final stats (Phase 5).

Recording in the repo: `data/recordings/mtn5yq64mp/` (FHC–DIF 6–2, `polls.jsonl` and
`report.md`; no `age` header recorded yet).

### How a goal arrives

Every goal followed the same pattern:

1. A **`shot`** by the scorer appears first (revision 1), about 20 s before the goal.
2. A new **`goal`** event appears with a new `eventId`, already at **revision 2**, with
   scorer, assists, `homeGoals`/`awayGoals` and `goalStatus`, but no `pop`/`nep`.
3. The shot from step 1 is **deleted** (same player and game time as the goal).
4. 20–80 s later, revision 3 adds `pop`/`nep` (players on ice).
5. Corrections can come much later. Goal 66 (P2 10:50) first said scorer Hasa, assists
   Johannesson and Tömmernes; 81 s later revision 3 changed it to scorer Fagemo, assists
   Hasa and Johannesson. With a 30 s offset the wrong scorer would already be on screen,
   so goal graphics must accept updates after release.

No goal was deleted (no disallowed goal this game). 27 shots were deleted in total: the
goal precursors above, and other shots, probably duplicates. Event 46 was deleted and
reappeared 1 min later.

### Feed latency (this recording, without `age` correction)

| Event | `realWorldTime` → first seen | `updatedTime` → first seen |
|---|---|---|
| goal (8) | min 19 s, median 48 s, max 78 s | 7–28 s, median 11 s |
| shot (122) | median 35 s | median 18 s |
| penalty (17) | 25–79 s, median 42 s (one fight major 330 s) | median 21 s |
| period start (3) | 22–31 s after `startedAt` | |

**`realWorldTime` is the on-ice moment, not the logging time.** Across all 123 pairs of
consecutive events in a period, `realWorldTime` never advanced less than the game clock
(it would, often, if it were the variable logging time), and each goal's `realWorldTime`
is within 3 s of its precursor shot's. The lag is in the logging and delivery: about 34 s
median from `realWorldTime` to the goal's `updatedTime`, then about 11 s to us. Hence the
sync anchor in CLAUDE.md rule 2. The TV was measured at about 40 s behind the arena. **Goals reach us on average ~48 s after they happen, longer than the
~30 s the TV is assumed to lag the arena.** See the open question in `docs/PLAN.md`.

Also seen: penalty variants `Major` and `Minor + Major + GM` (event 128 changed from
`Major` to `Minor + Major + GM` minutes later); a fight produced ten penalties at P3 10:26.
`goalSection` 1 to 9 matched the boxscore shots on goal again (FHC 44, DIF 14; the
"-3 only" rule gives 56 and 30). 83 of 4465 play-by-play polls (1.9 %) timed out.

## Observed latency

In `bdhvuc5tex`, `updatedTime` (UTC) of first revisions is typically 1 to 2 s after
`realWorldTime` (local) for shots. That suggests events appear in the feed within seconds of
being logged by the scorers. How long after the actual on-ice moment they are logged is
**unknown**; the calibrated offset absorbs it.

## Open questions for the Phase 0 recording

Checked again against `mtn5yq64mp` in Phase 5 (2026-10-21).

1. ~~Game state while live~~: play-by-play `Ongoing`; game-info stays `pre_game`
   (see Live behaviour). game-info was still `pre_game` 1.3 min after `GameEnded`, when
   the recording stopped, so `LiveSource` ends on play-by-play's `GameEnded`, not on
   game-info. When game-info turns `post_game` is still unknown (it was `post_game` for
   finished games fetched later).
2. ~~What `goalSection` means~~: 1 to 9 = on goal, confirmed live (see **shot** and the
   latency section). -1 stays unexplained (seen once, shown as unknown).
3. ~~How shootouts appear~~: answered from the fixtures (see **Shootout**). Whether
   attempts arrive one by one live is still unseen.
4. How a disallowed goal appears: not seen yet. No goal disappeared in `mtn5yq64mp`
   (other events did; see Live behaviour). The engine treats a removed goal as
   disallowed.
5. Other `goalStatus` and `offence` values: logged once at WARNING when they appear
   (CLAUDE.md rule 7); none new in the recording.
6. ~~Delay to our first sight per event type~~: see Feed latency and Observed latency.
7. ~~Whether period objects appear at once~~: no, 22–31 s after `startedAt`
   (P1 22 s, P2 31 s, P3 25 s in `mtn5yq64mp`), the replay source's 25 s period lag.
