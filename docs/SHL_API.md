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
  (`bdhvuc5tex` FHC 31 / LHC 29, `m01wkdm2u1` 24 / 40, `et9erhx0si` 16 / 23, shootout
  excluded). The "-3 only" rule gives 40 / 43 for `bdhvuc5tex`. So 0 is most likely a
  blocked shot (or similar non-SOG attempt), -3 missed, -1 unknown. The engine still uses
  `MISSED_GOAL_SECTIONS = {-3}` until the user decides (Phase 1); `tools/analyze_recording.py`
  reports both rules.
- The earlier counter-example (event 120 in `bdhvuc5tex`, "FHC, P3 18:01, `goalSection` 5")
  is an **LHC** shot in the feed (Christoffer Ehn, revision 1), i.e. by the team that had
  pulled its goalie. Not a contradiction.
- `locationX` / `locationY`: **assumption** decimetres, X = distance out from the goal line
  being attacked (goals in the sample come from X 29 to 57; most shots are below 180, about
  the blue line), Y = lateral position (about -140 to +130). Outliers exist (X 481, X -29):
  skip anything outside 0 to 200 for the shot map.

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
- `player.statistics` = the scorer's goals and assists **in this game** after this goal.
- Goals can have high revision numbers (one had revision 5); details get corrected after the fact.

**penalty**

```json
{"type": "penalty",
 "variant": {"shortName": "Minor", "minorTime": "2", "doubleMinorTime": "0", "benchTime": "0",
             "majorTime": "0", "misconductTime": "0", "gMTime": "0", "mPTime": "0", "description": "2 min"},
 "offence": "HOLD", "didRenderInPenaltyShot": false}
```

Offence codes seen and the Swedish text to show:

| Code | Swedish |
|---|---|
| `TRIP` | Fällning |
| `HOLD` | Fasthållning |
| `CROSS` | Crosscheck |
| `INTRF` | Obstruktion |
| `BOARD` | Knuff mot sarg |

Unknown codes: show the code and log it. Extend the table as new codes appear.

**goalkeeper**: `{"type": "goalkeeper", "isEntering": true|false}`. `false` mid-game means the
goalie was pulled (or left); the game also ends with `isEntering: false` events at 20:00.

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

## Observed latency

In `bdhvuc5tex`, `updatedTime` (UTC) of first revisions is typically 1 to 2 s after
`realWorldTime` (local) for shots. That suggests events appear in the feed within seconds of
being logged by the scorers. How long after the actual on-ice moment they are logged is
**unknown**; the calibrated offset absorbs it.

## Open questions for the Phase 0 recording

1. Game state value(s) while a game is live, in both endpoints.
2. ~~What `goalSection` means~~: fixtures say 1 to 9 = on goal (see **shot**). Confirm on a
   live recording, and decide what -1 is.
3. ~~How shootouts appear~~: answered from the fixtures (see **Shootout**). A live recording
   would show whether attempts arrive one by one.
4. How a disallowed goal appears (removed event, revision, or a new event type).
5. Other `goalStatus` and `offence` values.
6. Delay from `realWorldTime` / `updatedTime` to our first sight of each event type.
7. Whether period objects appear the moment a period starts.
