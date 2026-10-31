# TV app: SHL live! on a Samsung TV (Tizen)

The system's graphics drawn straight on top of the TV picture, by an app on the Samsung
TV itself (a 2026 model, Tizen). The Telia IPTV box stays on HDMI 1; the app shows that
HDMI picture behind its own transparent web page and draws our graphics over it. The
demo the user built (`SHLlive/`, 2026-10-31) proves the base: `tizen.tvwindow` shows
HDMI 1 `BEHIND` the page, and transparent and half-transparent graphics work over it.

## Decisions (the user, 2026-10-31)

| Area | Decision |
|---|---|
| Data | The app is a client of our service on the LAN, like the screens: same WebSocket, DelayQueue, sync, Home Assistant and phone app. No engine in the TV. |
| Delivery | A thin shell in the `.wgt` package (HDMI, remote, settings) with a transparent iframe that loads the overlay page `/tv/` from the service. Graphics change without reinstalling the app. |
| Role | The TV app **replaces the wall**: it must work without the three screens, so it shows more than the minimum (pauses, standings, tonight's games). The wall keeps working for whoever has one. |
| Over the broadcast | Goal celebration, penalties and power play, a statistics panel on a key, intermissions in an L-frame (TV picture shrunk, our graphics around it). Our own score bug is not shown: the broadcast has its own. |
| Outside a game | L-frame: the TV picture shrunk, pregame or idle graphics around it; one key gives full-screen TV. |
| Remote | Sync (puck drop), MÅL! buttons, panels, choosing the game on the TV. The remote has only arrows, OK and Back (digits and colours are on a virtual pad, too awkward, 2026-10-31), so everything goes through a menu on OK. |
| Server address | Typed in once in the app (setup screen), stored on the TV. |
| Videos | Team videos remade for 16:9. Not as `<video>`: on the TV it takes the player from HDMI (picture and sound go, seen 2026-10-31). As animated WebP with alpha instead (an image): transparent and smooth on the TV (2026-10-31). |
| TV and distance | 77" (16:9, 1705×959 mm), watched from 4 m (the user, 2026-10-31). |
| MÅL! on the remote | Two presses within 2 s, to be tried (the user, 2026-10-31). |

## How it fits together

```
 Samsung TV
 ┌──────────────────────────────────────────────────────────────┐
 │ video plane: HDMI 1 (Telia box), placed by tvwindow.show()   │ full screen, or a
 │                                                              │ rectangle (L-frame)
 │ web layer, transparent:                                      │
 │   shell (SHLlive/, in the .wgt)                              │
 │     ├─ HDMI source + tvwindow rectangle                      │
 │     ├─ remote keys (registered with tvinputdevice)           │
 │     ├─ setup: server address, HDMI number                    │
 │     └─ iframe http://<server>:8010/tv/  ◄─ postMessage ─►    │
 │          overlay page: ES modules + GSAP, synced clock,      │
 │          WebSocket role=screen id=tv, scenes for 16:9        │
 └──────────────────────────────────────────────────────────────┘
```

- **The overlay page** (`web/tv/`) is a screen like `left`, `bar` and `right`: it
  connects as `role=screen&id=tv`, gets the same delayed state and scene messages, and
  schedules everything from `play_at` on the synced clock (CLAUDE.md, rule 1 and
  conventions). It reuses `web/shared/` (clock, store, scheduler, format, media, tokens)
  and has its own scene modules, laid out for 1920×1080 over a live picture.
- **The shell** owns everything that needs Tizen APIs: it selects HDMI, places the TV
  picture, registers the remote's keys and passes them to the overlay. The overlay
  never calls Tizen; it asks the shell.
- **Fallback** if the TV will not draw a transparent iframe over the video plane: the
  shell imports the overlay modules from the service itself
  (`<script type="module" src="http://<server>/tv/tv.js">`, needs CORS headers on `/tv/`
  and `/shared/`). Same code, still no reinstall.

### Shell and overlay messages (postMessage)

| Direction | Message | Meaning |
|---|---|---|
| shell → overlay | `{"t": "key", "key": "red"}` | A remote key: `red`, `green`, `yellow`, `blue`, `ok`, `back`, `up`, `down`, `left`, `right`, `0`–`9`, `playpause` |
| shell → overlay | `{"t": "source", "hdmi": 1, "ok": true}` | HDMI picture state (shown in the menu, and a warning if it fails) |
| overlay → shell | `{"t": "window", "rect": [x, y, w, h]}` | Place the TV picture, in 1920×1080 pixels; `null` is full screen |
| overlay → shell | `{"t": "exit"}` | Leave the app (Back at the top level, confirmed) |
| overlay → shell | `{"t": "ready"}` | The overlay runs; the shell hides its loading text |

The shell checks the origin of every message against the server address it was given.

## Scenes on the TV

All text Swedish (hockey terms in English as on the wall). Sized for the TV: 77" at 4 m.
The page is 1920×1080 CSS pixels over 1705 mm, so 0.888 mm a pixel. With the wall's
rule (`config/wall.json` `viewing`: cap height 3.67 mm per metre at least, 6 mm per metre
for text meant to be read) that is a cap height of 14.7 mm (16.5 px, a **23 px** font)
at the least and 24 mm (27 px, a **38 px** font) for reading. Checked with
`tools/legibility.py`.

One module per scene in `web/tv/scenes/` (task 9.3, 2026-10-31); they reuse the wall's
helpers (`web/screens/scenes/common.js`: slideshow, standings table, names) with their own
layout (`web/tv/tv.css`). Every number comes from the delayed state (CLAUDE.md rule 1).

| Scene | TV picture | Our graphics |
|---|---|---|
| `idle` | L-frame | Column: the standings with zones (my team in gold). Band: clock, my team's next game, tonight's games (or the latest results) |
| `pregame` | L-frame | Column, 12 s a slide: both teams' place, points, goal difference, goals a game and form; each team's points leaders (the leader with a portrait); the last meetings. Band: the matchup, the start time, then "NEDSLÄPP OM" counting down the last hour on TV time. My team's intro (`tvintro`) at puck drop |
| `live` | full screen | Nothing by default (the broadcast has its own bug). A penalty: a lower third for the director's overlay (who, offence, minutes, "till P1 17:09", the power play it gives); then a pill bottom right while the power play runs ("POWERPLAY FRÖLUNDA · 5 MOT 4 · TILL P1 17:09"). Timeout and a disallowed goal: short banners. My team's power play: its animation (`tvpp`). Panels on ↑ ↓ |
| `goal` | full screen | A gold sweep, then the lower third: "MÅL!" and the team on a gold band, the scorer large with portrait, EQ/PP/SH, the time, "2:A MÅLET IKVÄLL" or "HATTRICK", assists, the score with logos. The scoring team's animation (`tvgoal`). A MÅL! press shows the team and "Väntar på SHL" until the feed's goal is linked |
| `intermission` | L-frame | Column, 12 s a slide: shots per period, both shot maps, goals, penalties, goalies and special teams (save % here only), the (live) table, the other games. Band: the score and "PERIOD 3 OM 14:22" |
| `postgame` | L-frame | Column: final statistics, the goals (and the shootout), the table. Band: the final score, "SLUT", after overtime or a shootout |

- **Power-play clock:** the service knows when each penalty runs out in game time
  (`expires_game_seconds`), not how much of it is left now (the game clock only reaches
  us with events), so the TV says "till P1 17:09" rather than a ticking countdown.
- **Lower thirds** sit 120–130 px above the bottom, clear of the broadcaster's tickers,
  and from the left edge, clear of its bug top left.
- **L-frame:** the TV picture moves to the top left at 60 % (1152×648, 40 px from the
  edges), our graphics fill the column right of it (608×1000) and the band below it
  (1152×312); a backdrop in `--bg-screen` paints everything around the picture
  (`web/tv/layout.js`). The overlay asks the shell to move the picture at the scene's
  `play_at`, so the change lands with the broadcast; going back to full screen the
  backdrop fades out in 0.1 s, before the picture has grown (45–120 ms on the TV).
  The viewer can ask for the full picture in any L-frame scene (9.4); the next scene
  change resets it.
- **Panels** (live and goal, on ↑ ↓, `web/tv/panels.js`): Statistik (shots per period,
  power plays, penalty minutes, save %), Tabell (the live table or the standings),
  Kvällens matcher. The right third, half see-through, over the full picture; past the
  last (or first) they close, as do Back and 20 s without a key. An open panel follows
  the delayed patches.
- Kept out of the broadcast's own graphics: the top left (the broadcaster's score bug)
  and the bottom 8 % (its tickers) stay free in `live` and `goal`.

## Remote

The remote (Samsung, 2026) has arrows, OK, Back, play/pause, volume and channel keys;
digits and colour keys only on a virtual pad on screen. So the app works with **arrows,
OK and Back** alone (2026-10-31). The remote also has a physical play/pause key
and a channel rocker; whether they reach the app (registered by the shell) is still to be
seen in the key log, and if they do they can become shortcuts.

| Key | No menu open | Menu open |
|---|---|---|
| OK | Opens the menu | Choose; on Matcher, Synk, Inställningar opens its sheet |
| ↑ ↓ | In play: next / previous panel (Statistik → Tabell → Kvällens matcher → off) | Move |
| → | | Opens a sheet, like OK |
| ← / Back | Back: closes a panel, or the full picture back to the L-frame; twice in 2 s: exit | Closes the sheet, then the menu |

The menu (`web/tv/menu.js`, task 9.4) is a list low on the left over the picture, 38 px
text (nine items in a row along the bottom would not fit at a readable size):
MÅL! <my team>, MÅL! <the other team>, Synka nedsläpp, Statistik, Tabell, Kvällens
matcher, Helbild (in an L-frame scene; "Tillbaka till L-ram" when on), Matcher ›,
Synk ›, Inställningar ›. The goal and sync items only while a game is selected. It closes
after 30 s without a key, and when the scene changes.

- **Where it opens**, so that OK, OK is always the useful thing and never a change of
  game: on "MÅL! <my team>" in play (`live`, `goal`; the home team when no side is mine),
  on "Synka nedsläpp" before the game and in the breaks (the next puck drop is what
  comes), else on "Statistik".
- **MÅL!** is OK, OK in play: the first opens the menu on my team's goal, the second
  fires it (`POST /api/goal`), the two presses decided on 2026-10-31. The press time
  is the second. The other team: OK, ↓, OK. Lights and horn fire in Home Assistant at
  once; with "Använd målknapp för synk" on, a linked press is also a goal sample.
- **Synka nedsläpp** registers a `period_start` sample at the moment of OK
  (`POST /api/calibrate`) and says the proposal, if there is one.
- **Matcher ›**: today's games with their start time, teams and PÅGÅR / SLUT, never a
  score (the schedule's scores are live, CLAUDE.md rule 1). OK follows a game live
  (`POST /api/source` live, then `POST /api/game` with my side following my team), a
  finished one as a replay; "Sluta följa" stops.
- **Synk ›**: the profile and its delay, the proposal and the last four samples; Synka
  nedsläpp nu, Använd förslaget, +0,5 s, −0,5 s, Rensa proven.
- **Inställningar ›**: the TV profile (OK switches to the next), Server och HDMI (the
  shell's own settings screen), Testsidan (`tv_probe`), and the shell's version and model.
- An active scene override (from the phone or `/sim`) wins over the goal scene, as on
  the wall: the MÅL! press still fires, but the TV keeps the forced scene.
- The shell registers every key the TV lets an app have (`tvinputdevice`, privilege
  `tv.inputdevice`) except volume, power, source and home, and passes them on by name.

## Videos

Not as `<video>`: on this TV (S95HF, Tizen 9.0) an HTML video takes the media player
from the HDMI input, so the TV picture and its sound go while it plays (2026-10-31). The
TV versions are **animated WebP with alpha** instead: an image, decoded without the
media player. Tried on the TV with the 1920×360 power-play video (895 kB, 4 s): ready in
155 ms, transparent and smooth to the eye (one 67 ms frame in the measurement), HDMI
picture and sound stay.

`tools/make_stingers.py` makes them from the same drawing as the wall's (task 9.5,
2026-10-31), in `web/media/<kind>/<team uuid>.webp`, 0.5–0.9 MB each:

| Kind | Size | Length | What |
|---|---|---|---|
| `tvgoal` | 1920×1080 | 2.0 s | Bands sweep over the picture, logo, "MÅL!" and the team; all gone by 1.8 s, the goal's lower third underneath |
| `tvintro` | 1920×360 | 3.0 s | The band with logo and "MATCHSTART" at puck drop, low in the picture: never over the whole of it, the drop itself is on the TV |
| `tvpp` | 1920×360 | 4.0 s | The bar's power-play band, for my team's power play |

`web/tv/anim.js` fetches them ahead as blobs and shows one at its `play_at`: `tvgoal`
over the whole frame, `tvintro` and `tvpp` as a band at y 600. An animated image cannot be
started part way, so a late one plays from its start, and one later than its length
(goal 3 s, intro 6 s, power play 5 s) is skipped; it is hidden after that length, and
its last frame is empty anyway (checked in Chromium for the defaults). They play once
(WebP loop count 1). Your own go in `data/media/<kind>/<uuid>.webp` (`docs/VIDEOS.md`).

## Development and install

- `/sim` has a TV view ("View: TV app"): `/tv/` in a 16:9 frame over a stand-in for the
  HDMI picture (a rink, with the Fake TV clock as the broadcast's bug). `/sim` plays the
  shell (`web/sim/tvview.js`): it answers the overlay's messages, moves the stand-in
  picture 60 ms after a window request, as the TV does, and sends the remote's keys
  (buttons, or arrows, Enter, Backspace, space for play/pause, PgUp/PgDn for the
  channel rocker). "Test page on the TV" switches the TV to the test page and back
  (`POST /api/tv/probe-mode`, setting `tv_probe`); the TV reloads itself, no reinstall.
- The TV's size and distance are in `config/wall.json` under `tv` (the TV is not part of
  the wall's geometry); `stage.applyType("tv")` gives `--fs-floor` 23 px and
  `--fs-text` 38 px.
- The `.wgt` is built and installed with the Tizen CLI (Tizen Studio or the VS Code
  extension): developer mode on the TV with the PC's IP, `sdb connect <tv>`,
  `tizen package -t wgt -s <certificate profile>`, `tizen install -n SHLlive.wgt -t <tv>`.
  A Samsung certificate from the Certificate Manager is needed for a TV. Steps in
  `docs/DEPLOY.md` once the app exists.
- `config.xml` needs, besides `tv.window`: `internet`, `tv.inputdevice`,
  `<access origin="*" subdomains="true"/>` (the service on the LAN) and the right
  `tizen:content-security-policy` to allow the iframe and WebSocket to the server.

## To verify on the real TV first (task 9.1)

Results from the user's TV (Samsung S95HF, Tizen 9.0, 2026-10-31) after each item.

1. A transparent iframe from the service draws over the HDMI picture (else the fallback).
   **Yes**: iframe mode works, half-transparent panels show the picture through.
2. The packaged app reaches `http://<server>:8010` (HTTP and WebSocket) on the LAN.
   **Yes** (119 ms for the first HTTP request, WebSocket connected).
3. ES modules and GSAP run smoothly at 1920×1080 (60 fps for transform and opacity).
   **Yes**: 60 frames a second, longest pause 17 ms.
4. VP9 with alpha plays transparent in `<video>` over HDMI. **No**: the video plays, but
   it takes the media player from HDMI (picture and sound go, and come back only when the
shell shows HDMI again). Animated WebP works instead (see Videos).
5. Moving the TV picture with `tvwindow.show` (L-frame) works without a black flash, and
   how long the move takes. **Yes**: no flash, 45–120 ms a move (6 of 6 moves).
6. The synced clock holds within a few ms, as on the display box. **Yes**: round trip
   1 ms, drift 1 ms (the TV's own clock is 130 ms off, which the sync takes care of).
7. The colour and digit keys reach the shell. **Moot**: the remote has no such keys of its
   own. Arrows, OK and Back reach the app; the remote's play/pause key and channel rocker
   were not pressed in the test, so still open.
8. How much the TV's HDMI path delays the picture compared with the TV's own input
   (the `iptv` TV profile may need a small nudge). Open: shows with Synka on a live game.

The TV: S95HF, Tizen 9.0, firmware T-RSMFDEUC-0090-1301.0, Chromium 120, page
1920×1080 at dpr 1. Its clock is about 150 ms off; the synced clock absorbs it.

## The test build (task 9.1)

`SHLlive/` is the shell (version 0.3.1); its overlay `/tv/` is, for now, the test page
`web/tv/probe.js`. It checks the list above and reports to the service.

1. Build and install `SHLlive/` on the TV as with the demo (Tizen Studio or the Tizen
   CLI, see Development and install). New privileges: `internet`, `tv.inputdevice`,
   `productinfo`, and `<access origin="*">`.
2. First start: "Inställningar". Type the Docker host's address, e.g.
   `192.168.1.20:8010` (OK opens the TV's keyboard), keep HDMI 1 and Läge "Iframe",
   choose Anslut. The settings stay on the TV; "Inställningar" in the menu opens them again.
3. The test page lies over the TV picture. A green dot means the check passed, red that it
   failed, yellow that it waits for an answer. Questions in the gold box: ← nej, → ja.
   The menu on the right: ↑ ↓ to choose, OK to run.
   - "Spela animerad bild (WebP)" plays the power-play animation as an image;
   - "Spela video" plays it as a video (takes HDMI away; the page asks the shell to
     show HDMI again afterwards, and asks whether picture and sound came back);
   - "Flytta TV-bilden" moves the picture: L-frame, small, full screen in turn;
   - "Återställ HDMI-bilden" shows HDMI again if it is gone;
   - press every key the remote has (play/pause, channel, …): the page lists them;
   - "Dölj testbilden" hides the page (any key brings it back); Back twice exits.
4. The page sends its report every 30 s (and at once on "Skicka rapport"). Read it at
   `http://<server>:8010/api/tv/probe` (kept in `data/tv_probe.json`) and send it on.
5. If the picture does not show through (or the page stays empty), choose Läge
   "Direkt (reserv)" in the settings and run it again: the same page, imported into the
   shell itself.

On a computer the shell runs as a preview at `http://<server>:8010/tvapp/` (striped
stand-in for the TV picture; the keyboard is the remote: Enter, arrows, Backspace). Opening `SHLlive/index.html` from disk tries the fallback mode the
way the TV does (Origin `null`, CORS). Both were run in Chromium on 2026-10-31.
