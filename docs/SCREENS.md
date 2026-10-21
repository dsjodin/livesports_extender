# Screens, simulator and phone app

## The wall

Three screens side by side, as seen from the sofa:

```
┌────────┐                              ┌────────┐
│        │                              │        │
│  LEFT  │  ┌────────────────────────┐  │ RIGHT  │
│  24"   │  │          BAR 28"       │  │  24"   │
│ 1080×  │  └────────────────────────┘  │ 1080×  │
│  1920  │                              │  1920  │
│        │                              │        │
└────────┘                              └────────┘
```

| Screen | Id | Resolution (CSS px) | Active area | Pixel pitch | Connection |
|---|---|---|---|---|---|
| Left 24", portrait | `left` | 1080×1920 | 299 × 531 mm | 0.277 mm | DisplayPort |
| Bar, VSDISPLAY VS280ZJ-V823 | `bar` | 1920×360 | 700 × 132 mm | 0.365 mm | HDMI |
| Right 24", portrait | `right` | 1080×1920 | 299 × 531 mm | 0.277 mm | USB-C (DP alt mode) |

- The OS rotates the portrait outputs, so each Chromium window sees a 1080×1920 viewport.
  Author those pages at 1080×1920 and the bar at 1920×360.
- One bar pixel is about 32% larger than a 24" pixel. Anything that moves across screens
  must be positioned in millimetres (the stage), not pixels.
- The physical layout is in `config/wall.json`. Its gaps and the bar's vertical position are
  **assumptions** (40 mm gaps, bar centred vertically) until the user measures the real wall.

### Stage coordinates

- Origin: top-left corner of the left screen's active area. Units: millimetres. X right, Y down.
- `stage.js` gives each page `mmToPx(x, y)` and `pxToMm(x, y)` for its own screen, using
  `position_mm`, `physical_mm` and `resolution` from `wall.json`.
- Cross-screen effects are defined once in stage millimetres and evaluated per screen
  with the shared clock, so they line up at the bezels.

## Visual language

Dark broadcast look, condensed type, team colours as accents, gold for goals and power
plays. Reference mockups: the design canvas "SHL Arena Screens" (four scenes); PNG
exports may be in `docs/mockups/`. The mockup drew the 24" screens at 820 px wide; multiply
its portrait sizes by **1.317** to get native 1080-wide values (already done below). Its bar
was drawn at native size.

### Team colours

The team colour is the jersey the team wears in this game: the home team's home colour,
the away team's away colour (`teams.<side>.color` and `.jersey` in the TV state). Defaults
per team uuid are in `config/teams.json` (set by the user 2026-10-21), overrides from the phone app win. Many teams play in white (vit) away and
some in black (svart): on the dark wall, team-coloured fills need a thin contrasting
outline, and text on a team colour picks black or white by contrast. Unknown colour:
use a neutral grey and show the team code.

### Tokens (`web/shared/tokens.css`)

```css
:root {
  --bg-screen: #070A10;       /* every screen's background */
  --panel: #0F1420;           /* cards, stat tiles */
  --panel-raised: #1A2130;    /* highlighted card, chips */
  --panel-alt: #141A26;       /* bottom info cards */
  --strip: #0E131C;           /* bar bottom strip */
  --text: #F2F4F8;
  --text-secondary: #C9D0DD;
  --text-muted: #A3ACBE;      /* labels; 7:1 on --bg-screen */
  --divider: #4A5366;
  --gold: #F5C542;            /* goals, power play, countdowns */
  --gold-flash: #FFE08A;
  --on-gold: #1A1405;
  --penalty: #FF8A8F;         /* "UTVISNING" label */
  --ice: #0C111B;
  --rink-red: #E5484D;
  --rink-blue: #3F6FE0;
  --rink-board: rgba(255, 255, 255, 0.28);
  --home: #34D399;            /* default; replaced per team */
  --on-home: #06150D;
  --away: #5B8CFF;            /* default; replaced per team */
  --on-away: #08132E;
  --wall: #1B1E24;            /* simulator background only */
}
```

- Team colours come from `config/teams.json` (generated in Phase 1 from the site's team
  directory, with the defaults above; the user edits real colours). Text on a team colour:
  pick `#0B0F17` or `#F2F4F8`, whichever reaches 4.5:1 contrast.
- Home and away must also differ by position and label, never by colour alone.

### Type

- **Barlow Condensed** 600/700/800 for names, numbers, labels. **Barlow** 400–700 for running
  text. Vendored woff2 in `web/vendor/fonts/`.
- All numbers use `font-variant-numeric: tabular-nums`.
- Labels: uppercase, Barlow Condensed 600, letter-spacing 0.16–0.2em, `--text-muted`.

**Sized for 3 m** (decided 2026-10-21, after the user found text hard to read at 2–3 m;
`tools/legibility.py` measured 216 of 293 texts on the left screen under 10 mm cap
height). Rules:

- Sizes are cap heights on the glass, from the viewing distance in `config/wall.json`
  (`viewing`): **floor** 11 mm at 3 m (labels, times, legends), **text** 18 mm (names,
  rows, card text), large numbers 30 mm and up. `stage.applyType` turns them into
  `--fs-floor` and `--fs-text` in CSS pixels for each screen (portrait 55 / 90 px, bar
  42 / 68 px).
- Nothing goes below the floor: text that does not fit is cut or moved to an
  intermission slide, never shrunk. Long team names shrink (`data-fit`) but stay large.
- Fewer things per screen rather than smaller ones. Save % and the goalie are in the
  intermission only (the user's call, 2026-10-21); the live portraits have no rotation.
- Logos without the white badge circle where there is room: large and toned down
  (30 %) behind the team name on the portraits, free-standing on the bar (the user's
  call, 2026-10-21). Badges stay in lists.
- `tools/legibility.py` (service running) measures every text of every scene; a scene
  is done when nothing is under the floor. Done so far: `live`, `intermission` and the
  bar in every scene. Still to do: pregame, goal, postgame and idle portraits.

Native sizes before the 3 m pass (the scenes not yet redone), portrait screens (1080 wide):

| Element | Size |
|---|---|
| Side padding / top padding | 74 px / 66 px |
| Team-colour rule at the top | 13 px |
| Gap between blocks | 45 px |
| Label | 32–34 px |
| Body / secondary text | 29–37 px |
| Card title (player name) | 61 px, 700 |
| Team name | 103 px, 800 |
| Stat tile value | 121 px, 800 |
| Goalie save % | 90 px, 800 |
| "MÅL!" | 250 px, 800 |
| Scorer last name / first name | 137 px 800 / 84 px 700 |
| Outline jersey number (decorative) | 553 px, 4–5 px stroke in team colour, 55% opacity |
| Team badge (header) | 163 px circle |
| Card radius / chip radius | 21 px / pill |

Bar (1920×360), native:

| Element | Size |
|---|---|
| Layout | main row 262 px + bottom strip 98 px (3 m) |
| Columns | home 800 px · centre 320 px · away 800 px |
| Team colour edge | 16 px at the outer ends |
| Logo | 150 px, no circle (code badge when there is no logo) |
| Team name | 80 px, 800 |
| Score box | 200 px wide, digits 220 px, 800, `--panel` background |
| Centre: period digit / label / pill | 130 px / `--fs-floor` / `--fs-floor` |
| Strip text | `--fs-floor` (42 px), 700, letter-spacing 0.06em, `--text-secondary` on `--strip` |

### Components

- **Team badge**: the team logo (`/assets/teams/<uuid>.svg`, the feed's `icon` cached by the
  service) on a light disc ringed in the team colour; without a logo, a circle in team
  colour with the team code (from `names.code`) in the on-colour.
- **Stat tile**: `--panel`, label on top, big value below. Three per row.
- **Goalie card**: label "MÅLVAKT", "#nr Förnamn Efternamn", right-aligned save % with one
  decimal and a comma ("96,2 %") and "N räddningar" below.
- **Shot map**: see below.
- **Power-play banner** (team on the power play, bottom of its screen): solid `--gold`,
  pulsing dot, "POWERPLAY", then "<Lag> #nr Namn · <brott> 2 min · <period> <tid>".
- **Penalty card** (penalised team, bottom of its screen): `--panel-alt`, "UTVISNING" in
  `--penalty`, "#nr Namn", "<brott> · 2 min · <period> <tid>".
- **Goal row**: team-colour edge, "P3 09:07 · FHC · POWERPLAY", scorer, "Assist: …", score at right.
  The newest row uses `--panel-raised`.
- **Comparison row**: home value left, label centre, away value right, split bar below in the
  two team colours, home share = home / (home + away).
- **Form row**: result chip (V = filled light, F = outlined; not colour-coded), date, H/B and
  opponent code, note ("straffar", "övertid"), score.

### Shot map

Drawn for the attacked end, goal at the top, in rink units (decimetres), scaled to the
content width (932 px at native size, so `scale = 932 / 300` px per dm):

- Width 300 dm (30 m). Top edge = end boards. Goal line 40 dm below the top.
- Rounded top corners, radius 85 dm. Board outline in `--rink-board`, ice `--ice`.
- Net: 18.3 dm wide, 11 dm deep, behind the goal line. Crease: half circle, radius 18 dm.
- Faceoff circles: centres 60 dm out from the goal line, ±70 dm lateral, radius 45 dm, red.
- Blue line 180 dm out from the goal line (shots cluster below it).
- Dot at `left = centre_x + y_dm * scale`, `top = goal_line_top + x_dm * scale`.
- Symbols as on shl.se's own shot plot: on goal a filled 24 px dot in team colour, wide
  (`goalSection` 0) a cross, blocked (−3) a filled square, goal a 45 px gold star.
  Legend: "På mål", "Utanför", "Täckt", "Mål". Built with the blue line at 180 dm; skip
  shots with `x_dm` outside 0–180.
- The meaning of `goalSection` and the coordinate origin are **assumptions** (see
  `docs/SHL_API.md`); plot a full replay and check that goals cluster at the net.

## Scenes

The SceneDirector picks one scene for the whole wall. All changes happen at the event's
`play_at`.

| Trigger (released event) | Scene | Ends |
|---|---|---|
| No game selected, or selected game not today | `idle` | when a game is selected |
| Game selected, not started | `pregame` | first `period_start` |
| `period_start` | `live` | `period_end` or `game_end` |
| `goal` | `goal` (hold 20 s) | back to `live`; a new goal restarts it |
| `penalty` | `live` with penalty emphasis for 8 s | automatic |
| `goal_disallowed` | `live` with "MÅLET UNDERKÄNT" overlay for 8 s | automatic |
| `timeout` | `live` with "TIMEOUT <LAG>" in the bar strip for 5 s | automatic |
| `goalie_change` (out) mid-period | `live`, "TOM BUR" badge for that team | goalie back, goal or period end |
| `period_end` (not last) | `intermission` | next `period_start` |
| `game_end` | `postgame` (hold 15 min) | then `idle` |
| Manual override from the phone | chosen scene | cleared or hold time over |

The penalty, disallowed-goal and timeout emphases are sent as scene `live` with
`data.overlay` (`penalty`, `goal_disallowed`, `timeout`), `data.event_key`, `data.side` and
`hold_ms`; the "TOM BUR" badge comes from `stats.<side>.goalie.pulled` in the TV state. A
penalty or timeout during a goal scene does not interrupt it; a disallowed goal does.
Holds are in real time, so in a fast replay a goal scene can span a whole intermission.

### idle

- Bar: centred clock (HH:MM) and "Nästa match: <dag> <tid> <HEMMA>–<BORTA>" for my team.
- Left: standings table (14 teams: placering, lag, matcher, poäng, målskillnad).
- Right: "Kvällens matcher" or "Senaste resultat".

### pregame (mockup scene 1)

- Bar: home and away name with badge; score boxes show league **points** with the label
  "POÄNG"; centre "IKVÄLL" / start time / arena; strip "ÄVEN IKVÄLL: …" other games tonight.
  Less than 60 min to start: centre shows a countdown "NEDSLÄPP OM 42:10".
- Left (home) and right (away): header (badge, "HEMMA"/"BORTA", long name); tiles MATCHER,
  POÄNG, MÅLSKILLNAD; "FORM, SENASTE 5" with five form rows, newest first; tiles
  "GJORDA MÅL / MATCH" and "INSLÄPPTA / MATCH" (one decimal, comma).
  Bottom card left: "SENASTE MÖTET · <datum>" with result and arena. Bottom card right:
  "NEDSLÄPP" with arena and start time.
- Data: schedule (results, points: 3 for a regulation win, 2 for an overtime or shootout win,
  1 for an overtime or shootout loss), standings.

### live (mockup scene 2)

- Bar: badges, short names in capitals, score boxes; centre "PERIOD" + period digit and a
  strength pill ("PP FRÖLUNDA" in gold with a pulsing dot; "5 MOT 3" when relevant; nothing at
  5v5); strip "SKOTT 36–26 • UTV.MIN 2–6 • SCANDINAVIUM · 12 044 ÅSKÅDARE".
- Left (home) and right (away), sized for 3 m: header with the short name in capitals
  (170 px) over the team's logo, large and toned down; tiles SKOTT (on goal), MÅL,
  UTV.MIN (values 200 px); the shot map with its legend under it (symbols about 10 mm);
  a "TOM BUR" card while the goalie is pulled; bottom: power-play banner for the team on
  the power play ("#4 Bergqvist · Slashing 2 min"), penalty card for the penalised team,
  otherwise a "SENASTE" card with the last event. No goalie card (intermission only).

### goal (mockup scene 3)

- Scoring side's screen: gold header flashing between `--gold` and `--gold-flash` (0.9 s
  cycle) with "MÅL!" and the team name; decorative outline jersey number behind the content;
  "MÅLSKYTT", first name, LAST NAME; chips "#25", strength ("EQ" full strength, "PP"
  power play, "SH" short-handed, "TOM BUR"; decided 2026-10-21), "3:E PERIODEN 09:07"; card "ASSIST" with up to two "#nr Namn";
  score row with both badges and "2–1"; "PÅ ISEN" grid with the six players from `on_ice`.
- Other screen: dimmed header (60% opacity); "<LEDANDE LAG> LEDER" or "KVITTERING" with the
  score; "SKOTT a–b"; "MÅLEN" list with the new goal highlighted.
- Bar: scoring side's score box flashes gold with the new number; centre "MÅL" in gold and
  "PP · P3 09:07"; strip turns gold: "#25 ARTTU RUOTSALAINEN • ASSIST #46 EGLI, #41 STENBERG".

Goal sequence, times relative to `play_at`:

| t | What happens |
|---|---|
| 0 ms | Gold band sweeps in stage millimetres from the bar's centre outward over both side screens (600 ms, ease-out). Bar centre "MÅL" scales in. Other side screen starts dimming (400 ms). |
| 300 ms | Score digit flips to the new value. |
| 0–350 ms | Scoring side: "MÅL!" header drops in from above; flashing starts (runs 6 s). |
| 600 ms | Outline number fades in; first and last name slide in, 120 ms apart. |
| 1200 ms | Chips pop in, 80 ms apart. |
| 1800 ms | Assist card, score row, on-ice grid, 60 ms stagger. Other side: goal list highlights the new row at 1500 ms. |
| 20 s | 500 ms cross-fade back to `live`. |

With team videos (Phase 8, below), the stinger plays over the scoring side for the first
2.2 s and the graphics build behind it.

### intermission (mockup scene 4)

Countdown: the intermission scene's `since_ms` (the period end as shown on TV) plus 18 min,
divided by the replay speed (`config.speed`). Before overtime the break is taken as 3 min
(assumption, not checked against SHL). It is an estimate; the next `period_start` ends it.

- Bar: score boxes; centre "PAUS", "PERIOD n OM", countdown in gold (estimate: period end +
  18 min); the strip is the ticker (below).
- Both portrait screens change picture every 12 s (Phase 8, decided with the user
  2026-10-21: "bildbyten mellan olika statistik"). The slide shown is
  `floor((now − since_ms) / 12 s) mod n` on the synced clock, so all screens agree and a
  reload lands on the same slide; the change is a 0.5 s cross-fade. Dots at the bottom show
  where in the cycle it is, and the countdown card "<N>:E PERIODEN STARTAR OM" stays.
- Left: our game, five slides under "EFTER n PERIODER" (sized for 3 m, 2026-10-21):
  SKOTT (both teams, comparison rows: shots per period, on goal, attempts); SKOTTKARTOR
  (both maps, shots on goal per team); MÅLEN (the last six: "#11 FAGEMO 1–0", under it
  "P1 07:11 · FHC · EQ"); UTVISNINGAR (the last six: "#4 BERGQVIST 2 MIN", "P1 15:09 ·
  SKE · Slashing"; a penalty shot reads STRAFFSLAG); MÅLVAKTER OCH SPECIAL TEAMS (goalie
  per team with save % and saves, power play goals/chances, penalty minutes). Assists
  are left out of the lists (the goal scene has them).
- Right: "KVÄLLENS ANDRA MATCHER": RESULTAT (up to six games: logos, codes, score,
  status); the live table "OM MATCHERNA SLUTADE NU" (or plain TABELL when no other game
  has started, see `docs/PROTOCOL.md`, live table): rank, movement arrow, logo, team,
  tonight's score, points; MÅLSKYTTAR (three games a slide, the last four goals each:
  "P2 14:17 LHF JUUSTOVAARA 3–2"). With no other games the right screen shows our goals
  and penalties.
- Bottom of both: the slide dots and "PERIOD n OM" with the countdown.

### Bar ticker (Phase 8)

The bar's bottom strip in `live` and `intermission` pages through our own line (shots,
penalty minutes, arena) and then the evening's other games, three per page
("LHF 2–2 HV71 P2 • …"), 8 s a page by the synced clock. A goal in another game (its score
changing in `tv.others` at its own `play_at`, delayed like ours) takes the strip in gold for
8 s: "MÅL HV71!  LHF 2–2 HV71 P2". Penalty and timeout overlays keep the strip while they run.

### Team videos (Phase 8)

Decided 2026-10-21: the videos are silent (Home Assistant plays the horn and sound), the
service ships a generated default per team, and your own replace them.

- Goal stinger: when the goal scene starts on the scoring side's screen, its team's
  `goal` video plays over the scene from `play_at` (2.2 s; bands in the team colours and
  gold, the logo, "MÅL!", the team name; it ends transparent) and the goal graphics build
  behind it. The gold band (`#fx`) still sweeps above it. The other screens show no video.
- Intro: the left and right screens play their team's `intro` video (4.5 s: the team
  colour, logo, "MATCHSTART", the team name, ending transparent) once per game: in
  `pregame` at the scheduled start on TV time (`start_ms + offset_ms`), or, if that time
  had passed (a replay, or a page opened late), at puck drop, when `live` follows
  `pregame`, over the first seconds of the live scene.
- Power play (asked for by the user 2026-10-21): when **my team's** power play begins
  (`strength.pp_side` turns to my side in a patch, at its `play_at`), the bar plays my
  team's `pp` video over the whole bar (4 s, 1920×360: slashes, the team colour, logo,
  "POWERPLAY" letter by letter, the team name, a light sweep and pulsing arrows, ending
  transparent, so the "PP <LAG>" pill shows after it). Not again when it grows to 5 on 3
  within the same power play, nothing for the other team's power play, nothing without a
  my side for the game, and not for a power play already on when a screen (re)loads.
  Only in `live` and `goal`.
- Testing: `/sim` has "Intro (both)", "Goal video home/away", "PP video (my team)"
  (`POST /api/test/video`, the video alone), a "My team" side for the game and "Test goal home/away" (the whole goal sequence). The debug overlay
  (`?debug=1`) shows whether a screen holds its videos ("video goal ready · intro ready").
- Each portrait screen fetches its own team's two videos (the bar: my team's `pp`) when the teams are known, as
  blobs, so playback never waits on the network. A screen that is late starts the video
  that far in; a team without a video shows none. A fresh state (seek, reconnect) stops a
  running video. Each start logs `[sync] video/<kind> screen=… delta=…ms`.
- Making your own: sizes, format, encoding and installing are in `docs/VIDEOS.md`.
- Files: `GET /media/<goal|intro|pp>/<team uuid>.webm` serves `data/media/<kind>/<uuid>.webm`
  if it exists, else the default in `web/media/`. Your own: WebM VP9 with alpha
  (`yuva420p`), 1080×1920 (`pp`: 1920×360), short, ending transparent; e.g.
  `ffmpeg -i in.mov -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 32 -an out.webm`.
- Defaults: `tools/make_stingers.py` draws every frame in Chromium on a transparent page
  (colours from `config/teams.json`, logos from the logo cache) and encodes them with
  ffmpeg; run it again after changing a team's colours.

### postgame

- Bar: final score, centre "SLUT" (plus "ÖT" or "STR" after overtime or shootout).
- Left: final statistics comparison. Right: goals list and, in Phase 8, top players and the
  updated standings with movement arrows.

## Motion rules

- GSAP timelines, started with `gsap.delayedCall` or `requestAnimationFrame` checks against
  the synced clock so they begin exactly at `play_at`.
- Animate only `transform` and `opacity` (plus background colour for the gold flash). Target 60 fps
  on all three screens at once.
- Entrances 250–600 ms, ease-out; exits 300–500 ms. Staggers 60–120 ms.
- Nothing moves while idle except the clock and slow ambient elements.

## Debug overlay

`?debug=1` on any screen page shows, in a corner: connection state, clock offset and RTT,
TV state `rev`, current scene, and a list of upcoming `play_at` countdowns with event keys.
Every scene change is also logged to the console as
`[sync] goal start screen=left delta=1.2ms`, where `delta` is how late (by the synced
clock) the scene started after its `play_at`; `tools/snapshot.py` collects these lines.

On reconnect (for example after a service restart) a screen gets `hello` and a fresh
`state` and redraws the current scene without animation; no page reload.

## Simulator (`/sim`)

A developer tool; its control panel may be in English.

- Background `--wall`. The three screens laid out from `wall.json` at one millimetre scale
  that fits the window, each an iframe of the real page at native resolution scaled with
  `transform: scale()`, with a 10 mm black bezel drawn around each.
- Control panel (below or beside the wall):
  - Source: replay (fixture list plus any finished game uuid), recording, live (today's
    games from the schedule, or a typed uuid; "Follow live").
  - Replay: play/pause, speed 1/2/5/20/50, "next period", "10 s before next goal", progress
    readout (period, game time, real time).
  - System offset (TV profile) and **fake TV delay** (separate slider).
  - **Fake TV pane**: shows raw events as text at `event_ms + fake TV delay`, with a large
    "TV-klocka" (period and game time), so the calibration button can be tested.
  - Webhook log: each call with time, event, status.
  - Toggles: debug overlay on all screens, show raw events.
  - "Open phone app" link (`/app`) and QR code for the phone (the QR code is not built
    yet: no QR library is vendored).
- Built in Phase 3: the source list comes from `GET /api/replays` plus a field for any
  finished game uuid; "End of game" seeks to just after the game ended. The fake TV pane
  needs the raw events, so the simulator always sends `debug_subscribe`; the
  "Show raw events" toggle only shows the arrival list.

## Phone app (`/app`)

Swedish UI, mobile first, touch targets at least 44 px, dark theme with the same tokens.
Tab bar: **Matcher**, **Live**, **Inställningar**.

- **Matcher**
  - Sections "Idag", "Kommande", "Spelade (repris)". Each row: time, badges, "HEMMA–BORTA", arena.
  - Tap a game: sheet with "Följ matchen" and "Mitt lag": [Hemma] [Borta] [Inget].
    For finished games: "Spela upp som repris" with speed choice.
- **Live**
  - Delayed score as on the bar, period and status.
  - Two large **MÅL!** buttons, one per team (my team first, in team colour). Text under:
    "Tryck när målet syns på TV:n." After a press: "Mål registrerat – väntar på data" until
    the feed goal links, then the scorer; "Inget mål kom från SHL" after 180 s.
  - Offset row: "TV-fördröjning 40,0 s" with "−0,5" and "+0,5", TV profile chip ("IPTV").
  - Sync: large "Synka" button with a picker [Nedsläpp | Mål | Utvisning | Timeout |
    Skott på mål] and optional [Hemma | Borta]. Text: "Tryck när du ser händelsen på
    TV:n." Each press is listed as "Väntar…", "41,3 s", "Hittade ingen händelse" or
    "Flera möjliga – välj lag". Then "Förslag: 41,3 s (3 mätningar)" with "Använd" and
    "Rensa"; each sample can be swiped away.
  - A note when events arrive late: "3 mål kom efter TV:n i kväll – överväg att pausa
    TV:n vid nedsläpp." 
  - Scene buttons: "Auto", "Tabell", "Skottkarta", "Periodstatistik", "Mål igen".
  - "Testa mål" (synthetic goal for my team, triggers lights).
  - Replay controls when the source is a replay.
- **Inställningar**
  - TV-profil (IPTV, TV4 Play) with each offset.
  - Home Assistant: webhook URL, on/off, which events.
  - Lagfärger: home and away jersey colour per team (`GET/PUT /api/teams`), chosen from
    the palette (blå, gul, vit, röd, grön, svart) or any colour.
  - Debug: "Visa råa händelser" with the warning "Kan avslöja mål innan de syns på TV."
  - Om: version, source status, last poll, clock offset.

Built in Phase 4 (`web/app/`):

- Manifest, SVG icon and a pass-through service worker (registered only in a secure
  context, so installing needs https or localhost; over plain http on the LAN it runs as
  a normal page).
- Matcher also lists "Testmatcher" (the fixtures) for replays. "Mitt lag" defaults to the
  side my team plays on, "Inget" when it does not play; "Följ matchen" starts the live
  source, "Spela upp som repris" a replay at the chosen speed (1, 2, 5, 20, 50×).
- Live: the MÅL! button of my side is marked ★; each press shows "Mål registrerat –
  väntar på data", then "Målet hittat hos SHL", then the scorer once the feed goal has
  played on the screens, or "Inget mål kom från SHL". Sync samples are removed with ✕
  (no swipe). "Använd målknapp för synk" is a checkbox, on by default. The side picker is
  [Båda | Hemma | Borta]. The TV profile chip switches to the next profile.
- Scene buttons: Auto (back to automatic), Tabell (`idle`), Skottkarta (`live`),
  Periodstatistik (`intermission`), Mål igen (`goal` with the latest goal, 20 s).
- Inställningar: "Mitt lag" picker; Lagfärger with the palette or "Egen färg…" (#rrggbb)
  and "Återställ"; Home Assistant is a disabled field until Phase 6.
- The app redraws a view only when its HTML changes, so a tap is not lost to the
  once-a-second status update.
