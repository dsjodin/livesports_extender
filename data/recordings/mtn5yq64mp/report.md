# Recording report: mtn5yq64mp

- Game: `mtn5yq64mp`, FHC–DIF, last score –
- Recorded 12:26:26.0 to 21:28:50.5 (Europe/Stockholm), 9312 rows
- Requests: boxscore 3, game-info 4844, play-by-play 4465
- Statuses: boxscore 200: 3, game-info 200: 4844, play-by-play 200: 4382, play-by-play None: 83
- Errors: play-by-play ReadTimeout: 83
- Age header on play-by-play: not recorded

## Game states

| Source | Value | First seen |
|---|---|---|
| game-info `gameInfo.state` | `pre_game` | 12:26:26.0 |
| play-by-play `gameState` | `Ongoing` | 19:00:34.3 |
| play-by-play `gameState` | `Intermission` | 19:32:17.6 |
| play-by-play `gameState` | `GameEnded` | 21:27:31.5 |

## Delay to first sight, per event type (to `received_ms`)

Seconds from the event's first-seen `realWorldTime` (parsed as Europe/Stockholm) and
`updatedTime` (parsed as UTC) to `received_ms` of the first poll that contained it.

| Type | n | realWorldTime min | median | max | updatedTime min | median | max |
|---|---|---|---|---|---|---|---|
| goal | 8 | +18.7 | +48.0 | +77.6 | +6.5 | +10.6 | +28.3 |
| goalkeeper | 4 | +8.7 | +15.5 | +27.5 | +8.7 | +15.4 | +27.5 |
| penalty | 17 | +25.2 | +41.5 | +329.7 | +10.7 | +21.3 | +32.4 |
| shot | 122 | +17.1 | +35.3 | +2137.3 | +4.0 | +17.6 | +1645.8 |
| timeout | 1 | +36.9 | +36.9 | +36.9 | +36.9 | +36.9 | +36.9 |

## Revisions and changes

| Event | Seen | Revision | Changed fields |
|---|---|---|---|
| 1 goalkeeper P1 00:00 FHC | 19:00:34.3 | 1 (first) | |
| | 21:27:31.5 | 2 | `revision` |
| 1 period P1 | 19:00:34.3 | None (first) | |
| | 19:32:17.6 | None | `finished`, `finishedAt`, `realWorldTime` |
| 2 goalkeeper P1 00:00 DIF | 19:00:54.8 | 1 (first) | |
| | 21:27:31.5 | 2 | `revision` |
| 7 goal P1 03:47 FHC | 19:06:51.9 | 2 (first) | |
| | 19:07:32.8 | 3 | `nep`, `pop`, `revision` |
| 20 penalty P1 08:36 DIF | 19:14:20.0 | 1 (first) | |
| | 19:16:50.8 | 2 | `revision` |
| 22 shot P1 10:01 FHC | 19:16:30.5 | 1 (first) | |
| | 19:16:50.8 | 2 | `revision` |
| 23 goal P1 10:01 FHC | 19:16:50.8 | 2 (first) | |
| | 19:17:31.6 | 3 | `nep`, `pop`, `revision` |
| 31 penalty P1 19:03 FHC | 19:29:52.8 | 1 (first) | |
| | 19:53:15.0 | 2 | `revision` |
| 2 period P2 | 19:50:38.6 | None (first) | |
| | 20:26:54.6 | None | `finished`, `finishedAt`, `realWorldTime` |
| 34 penalty P2 00:28 DIF | 19:52:17.2 | 1 (first) | |
| | 19:54:56.7 | 2 | `revision` |
| 47 goal P2 05:04 FHC | 20:00:30.9 | 2 (first) | |
| | 20:01:11.1 | 3 | `nep`, `pop`, `revision` |
| | 21:27:41.7 | 4 | `revision` |
| 46 shot P2 05:03 FHC | 20:00:30.9 | 1 (first) | |
| | 20:04:12.8 | 3 | `revision` |
| 59 goal P2 07:36 DIF | 20:05:34.4 | 2 (first) | |
| | 20:06:54.6 | 3 | `nep`, `pop`, `revision` |
| 66 goal P2 10:50 FHC | 20:09:58.6 | 2 (first) | |
| | 20:11:19.3 | 3 | `assists.first.familyName`, `assists.first.firstName`, `assists.first.jerseyToday`, `assists.first.playerId`, `assists.first.statistics`, `assists.second.familyName`, `assists.second.firstName`, `assists.second.jerseyToday`, `assists.second.playerId`, `assists.second.statistics`, `player.familyName`, `player.firstName`, `player.jerseyToday`, `player.playerId`, `player.statistics`, `revision` |
| | 20:12:30.5 | 4 | `nep`, `pop`, `revision` |
| 3 period P3 | 20:44:37.8 | None (first) | |
| | 21:27:21.3 | None | `finished`, `finishedAt`, `realWorldTime` |
| 103 goal P3 07:20 FHC | 20:55:54.4 | 2 (first) | |
| | 20:56:35.2 | 3 | `nep`, `pop`, `revision` |
| 114 goal P3 09:21 FHC | 21:01:30.9 | 2 (first) | |
| | 21:02:11.8 | 3 | `nep`, `pop`, `revision` |
| 123 penalty P3 10:26 FHC | 21:11:00.3 | 1 (first) | |
| | 21:13:33.1 | 2 | `revision` |
| 125 penalty P3 10:26 FHC | 21:11:20.7 | 1 (first) | |
| | 21:13:33.1 | 2 | `revision` |
| 124 penalty P3 10:26 FHC | 21:11:20.7 | 1 (first) | |
| | 21:13:12.7 | 2 | `revision` |
| 126 penalty P3 10:26 FHC | 21:11:30.9 | 1 (first) | |
| | 21:13:33.1 | 2 | `revision` |
| 127 penalty P3 10:26 DIF | 21:12:11.6 | 1 (first) | |
| | 21:17:40.4 | 2 | `revision` |
| 128 penalty P3 10:26 DIF | 21:12:32.0 | 1 (first) | |
| | 21:13:53.5 | 2 | `revision`, `variant.description`, `variant.gMTime`, `variant.shortName` |
| | 21:17:20.0 | 3 | `revision`, `variant.description`, `variant.minorTime`, `variant.shortName` |
| | 21:24:51.3 | 4 | `revision` |
| 130 penalty P3 10:26 DIF | 21:12:52.4 | 1 (first) | |
| | 21:13:33.1 | 2 | `revision` |
| 129 penalty P3 10:26 DIF | 21:12:52.4 | 1 (first) | |
| | 21:13:33.1 | 2 | `revision` |
| 131 penalty P3 10:26 DIF | 21:13:12.7 | 1 (first) | |
| | 21:13:33.1 | 2 | `revision` |
| 140 penalty P3 14:17 DIF | 21:19:51.1 | 1 (first) | |
| | 21:22:40.1 | 2 | `revision` |
| 147 shot P3 16:35 DIF | 21:23:00.6 | 1 (first) | |
| | 21:24:51.3 | 2 | `revision` |
| 150 shot P3 17:08 DIF | 21:23:31.3 | 1 (first) | |
| | 21:24:51.3 | 3 | `revision` |
| 149 shot P3 16:46 FHC | 21:23:31.3 | 2 (first) | |
| | 21:24:51.3 | 3 | `revision` |
| 151 goal P3 17:09 DIF | 21:24:32.8 | 2 (first) | |
| | 21:24:51.3 | 3 | `nep`, `pop`, `revision` |

## Disappeared events

| Event | Last seen | Gone at |
|---|---|---|
| 6 shot P1 03:47 FHC | 19:07:30.6 | 19:07:32.8 |
| 13 shot P1 06:08 DIF | 19:10:34.1 | 19:10:36.1 |
| 9 shot P1 04:47 DIF | 19:11:35.1 | 19:11:37.1 |
| 22 shot P1 10:01 FHC | 19:17:29.5 | 19:17:31.6 |
| 29 shot P1 18:07 FHC | 19:28:49.7 | 19:28:51.7 |
| 40 shot P2 04:26 DIF | 19:58:38.0 | 19:58:40.0 |
| 43 shot P2 04:36 DIF | 19:59:28.5 | 19:59:30.6 |
| 46 shot P2 05:03 FHC | 20:01:09.1 | 20:01:11.1 |
| 53 shot P2 06:20 FHC | 20:03:00.9 | 20:03:22.4 |
| 55 shot P2 06:46 FHC | 20:03:30.6 | 20:03:32.6 |
| 45 shot P2 05:03 FHC | 20:03:51.0 | 20:04:12.8 |
| 58 shot P2 07:35 DIF | 20:06:32.8 | 20:06:54.6 |
| 65 shot P2 10:49 FHC | 20:12:48.8 | 20:12:50.8 |
| 49 shot P2 05:41 FHC | 20:19:18.1 | 20:19:20.2 |
| 76 shot P2 15:11 DIF | 20:20:18.7 | 20:21:11.0 |
| 50 shot P2 05:42 FHC | 20:28:34.5 | 20:28:36.5 |
| 51 shot P2 06:03 FHC | 20:28:54.8 | 20:28:56.9 |
| 54 shot P2 06:20 FHC | 20:29:56.4 | 20:30:15.1 |
| 74 shot P2 13:57 FHC | 20:47:33.2 | 20:47:35.3 |
| 102 shot P3 07:19 FHC | 20:59:16.5 | 20:59:18.5 |
| 113 shot P3 09:21 FHC | 21:02:09.8 | 21:02:11.8 |
| 99 shot P3 04:05 FHC | 21:03:31.5 | 21:03:33.6 |
| 112 shot P3 08:54 DIF | 21:08:35.6 | 21:08:37.7 |
| 138 shot P3 13:54 FHC | 21:19:15.4 | 21:19:17.4 |
| 143 shot P3 15:29 FHC | 21:22:38.0 | 21:22:40.1 |
| 148 shot P3 16:46 FHC | 21:23:39.5 | 21:23:41.5 |
| 150 shot P3 17:08 DIF | 21:25:09.9 | 21:25:12.0 |

Reappeared: 46 at 20:04:12.8

## Distinct values (final play-by-play)

| Field | Values (count) |
|---|---|
| `type` | `goal` (8), `goalkeeper` (4), `penalty` (17), `period` (3), `shot` (96), `timeout` (1) |
| `goalStatus` | `EQ` (7), `PP1` (1) |
| `offence` | `FIGHT` (2), `HOLD` (1), `INTRF` (3), `ROUGH` (9), `SLASH` (1), `TRIP` (1) |
| `variant.shortName` | `Major` (1), `Minor` (15), `Minor + Major + GM` (1) |
| `goalSection` | `-3` (18), `0` (28), `1` (10), `2` (9), `3` (11), `4` (1), `6` (2), `8` (25) |

## Shots by `goalSection` (types `shot` and `goal`, shootout excluded)

| Team | `-3` | `0` | `1` | `2` | `3` | `4` | `6` | `8` | all | on goal A | on goal B |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FHC (home) | 10 | 12 | 9 | 4 | 9 | 1 | 2 | 19 | 66 | 56 | 44 |
| DIF (away) | 8 | 16 | 1 | 5 | 2 | 0 | 0 | 6 | 38 | 30 | 14 |

- A: `goalSection` not in [-3] (the current assumption).
- B: `goalSection` 1 to 9 (alternative).

| Team | A | B | boxscore skater SOG sum | boxscore opposing goalie SOGA | matches |
|---|---|---|---|---|---|
| FHC | 56 | 44 | 44 | 44 | B |
| DIF | 30 | 14 | 14 | 14 | B |

## Period objects

`startedAt` / `finishedAt` parsed as local time despite the `Z`. Deltas are the
period object's first-seen time minus the first-seen time of the period's first or
last event (negative: the period object came first).

| Period | Object first seen | Started seen | `startedAt` | First event (rwt / seen) | Δ start | Finished seen | `finishedAt` | Last event (rwt / seen) | Δ end |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 19:00:34.3 | 19:00:34.3 | 19:00:12.0 | 00:00 goalkeeper: 19:00:25.6 / 19:00:34.3 | +0.0 | 19:32:17.6 | 19:31:52.0 | 19:18 shot: 19:30:23.0 / 19:30:53.9 | +83.7 |
| 2 | 19:50:38.6 | 19:50:38.6 | 19:50:07.0 | 00:28 penalty: 19:51:34.8 / 19:52:17.2 | -98.6 | 20:26:54.6 | 20:26:28.0 | 19:57 shot: 20:26:16.6 / 20:26:54.6 | +0.0 |
| 3 | 20:44:37.8 | 20:44:37.8 | 20:44:12.0 | 00:20 shot: 20:45:08.4 / 20:45:45.7 | -67.9 | 21:27:21.3 | 21:27:07.0 | 20:00 goalkeeper: 21:27:21.7 / 21:27:41.7 | -20.4 |
