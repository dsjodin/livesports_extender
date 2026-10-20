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

Native sizes, portrait screens (1080 wide):

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
| Layout | main row 284 px + bottom strip 76 px |
| Columns | home 800 px · centre 320 px · away 800 px |
| Team colour edge | 16 px at the outer ends |
| Badge | 130 px circle |
| Team name | 80 px, 800 |
| Score box | 200 px wide, digits 220 px, 800, `--panel` background |
| Centre: period digit / label / pill | 130 px / 26 px / 30 px |
| Strip text | 30 px, 600, letter-spacing 0.12em, `--text-secondary` on `--strip` |

### Components

- **Team badge**: circle in team colour with the team code (from `names.code`) in the
  on-colour. Later: the team logo from the feed's `icon` URL, cached (Phase 8).
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
- Blue line about 175 to 190 dm out from the goal line (tune visually; shots cluster below 180).
- Dot at `left = centre_x + y_dm * scale`, `top = goal_line_top + x_dm * scale`.
- On goal: filled 24 px dot in team colour. Missed: 24 px ring, 4 px. Goal: 45 px gold star.
  Legend: "På mål", "Utanför", "Mål". Skip shots with `x_dm` outside 0–200.
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
- Left (home) and right (away): header; tiles SKOTT (on goal), MÅL, UTV.MIN; goalie card;
  "SKOTTKARTA" with legend and the shot map; bottom: power-play banner for the team on the
  power play, penalty card for the penalised team, otherwise a "SENASTE" card with the last
  event.

### goal (mockup scene 3)

- Scoring side's screen: gold header flashing between `--gold` and `--gold-flash` (0.9 s
  cycle) with "MÅL!" and the team name; decorative outline jersey number behind the content;
  "MÅLSKYTT", first name, LAST NAME; chips "#25", strength ("POWERPLAY", "FULLT LAG",
  "BOXPLAY", "TOM BUR"), "3:E PERIODEN 09:07"; card "ASSIST" with up to two "#nr Namn";
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

With video stingers (Phase 8), the stinger plays over the scoring side for the first 2.5 s
and the graphics build behind it.

### intermission (mockup scene 4)

- Bar: score boxes; centre "PAUS", "PERIOD n OM", countdown in gold (estimate: period end +
  18 min); strip "EFTER n PERIODER • SKOTT a–b • UTV.MIN c–d".
- Left: "EFTER TVÅ PERIODER" / "PERIODSTATISTIK", both teams named with badges, comparison rows:
  shots per period played, shots total, power play (goals/chances), penalty minutes, save %.
- Right: "MÅLEN" list, "UTVISNINGAR" list (period time, team, player, offence text, minutes),
  bottom card "<N>:E PERIODEN · Startar om" with the countdown.

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

## Simulator (`/sim`)

A developer tool; its control panel may be in English.

- Background `--wall`. The three screens laid out from `wall.json` at one millimetre scale
  that fits the window, each an iframe of the real page at native resolution scaled with
  `transform: scale()`, with a 10 mm black bezel drawn around each.
- Control panel (below or beside the wall):
  - Source: replay (fixture list plus any finished game uuid), recording, live.
  - Replay: play/pause, speed 1/2/5/20/50, "next period", "10 s before next goal", progress
    readout (period, game time, real time).
  - System offset (TV profile) and **fake TV delay** (separate slider).
  - **Fake TV pane**: shows raw events as text at `first_seen + fake TV delay`, with a large
    "TV-klocka" (period and game time), so the calibration button can be tested.
  - Webhook log: each call with time, event, status.
  - Toggles: debug overlay on all screens, show raw events.
  - "Open phone app" link (`/app`) and QR code for the phone.

## Phone app (`/app`)

Swedish UI, mobile first, touch targets at least 44 px, dark theme with the same tokens.
Tab bar: **Matcher**, **Live**, **Inställningar**.

- **Matcher**
  - Sections "Idag", "Kommande", "Spelade (repris)". Each row: time, badges, "HEMMA–BORTA", arena.
  - Tap a game: sheet with "Följ matchen" and "Mitt lag": [Hemma] [Borta] [Inget].
    For finished games: "Spela upp som repris" with speed choice.
- **Live**
  - Delayed score as on the bar, period and status.
  - Offset row: "Fördröjning 30,0 s" with "−0,5" and "+0,5", TV profile chip ("IPTV").
  - Calibration: large "Nu!" button with a segmented control [Nedsläpp | Mål]. Text:
    "Tryck när du ser nedsläppet/målet på TV:n." After presses:
    "Förslag: 27,1 s (3 mätningar)" with buttons "Använd" and "Rensa".
  - Scene buttons: "Auto", "Tabell", "Skottkarta", "Periodstatistik", "Mål igen".
  - "Testa mål" (synthetic goal for my team, triggers lights).
  - Replay controls when the source is a replay.
- **Inställningar**
  - TV-profil (IPTV, TV4 Play) with each offset.
  - Home Assistant: webhook URL, on/off, which events.
  - Lagfärger: colour per team.
  - Debug: "Visa råa händelser" with the warning "Kan avslöja mål innan de syns på TV."
  - Om: version, source status, last poll, clock offset.
