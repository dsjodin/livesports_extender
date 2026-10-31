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

| Scene | TV picture | Our graphics |
|---|---|---|
| `idle` | L-frame | Standings with zones, tonight's games or latest results, next game, clock |
| `pregame` | L-frame | The pregame slideshow (team form, leaders, head-to-head), countdown to puck drop; intro video at puck drop |
| `live` | full screen | Nothing by default. Penalty card with power-play countdown (lower third, small), power-play video for my team, panels on a key |
| `goal` | full screen | Goal video, the MÅL! band, then a lower third: scorer with portrait, assists, EQ/PP/SH, score |
| `intermission` | L-frame | The intermission slides (period stats, shots, special teams, save %, live table, other games) |
| `postgame` | L-frame | Final, top players, standings movement |

- **L-frame:** the TV picture moves to the top left at about 60 % (1152×648), our
  graphics fill the right column and the band below. The overlay asks the shell to
  move the picture at the scene's `play_at`, so the change lands with the broadcast.
  OK toggles full-screen TV in any L-frame scene; the next scene change resets it.
- **Panels** (live, on a key): Statistik (shots, power plays, special teams, shot map),
  Tabell (live table), Kvällens matcher. Lower half or right third, semi-transparent,
  over the full picture; they close themselves after 20 s or on Back. Every number in
  them comes from the delayed state, never raw.
- Kept out of the broadcast's own graphics: the top left (the broadcaster's score bug)
  and the bottom 8 % (its tickers) stay free in `live` and `goal`.

## Remote

The remote (Samsung, 2026) has arrows, OK, Back, play/pause, volume and channel keys;
digits and colour keys only on a virtual pad on screen. So the app works with **arrows,
OK and Back** alone (proposal, 2026-10-31). The remote also has a physical play/pause key
and a channel rocker; whether they reach the app (registered by the shell) is still to be
seen in the key log, and if they do they can become shortcuts.

| Key | No menu open | Menu open |
|---|---|---|
| OK | Opens the menu with "MÅL! <my team>" chosen | Choose |
| ← → | | Move along the menu |
| ↑ ↓ | Next / previous panel: Statistik → Tabell → Kvällens matcher → off | |
| Back | Close the panel; in an L-frame scene: full-screen TV on/off | Close the menu |
| Back twice | "Avsluta?" at the top level | |

The menu is a row along the bottom: MÅL! <my team>, MÅL! <the other team>, Synka
nedsläpp, Statistik, Tabell, Kvällens matcher, Helbild, Matcher, Inställningar.

- **MÅL!** is OK, OK: the first opens the menu on my team's goal, the second fires it. That
  is the two presses decided on 2026-10-31, and the press time (for the celebration and
  the goal sample) is the second. The other team: OK, →, OK. A menu left alone closes
  after 5 s.
- The MÅL! press fires lights and horn in Home Assistant at once. With "Använd målknapp
  för synk" on, a linked press is also a goal sample, as in the phone app.
- **Synka nedsläpp** in the menu registers a `period_start` sample at the moment of OK.
- The shell registers every key the TV lets an app have (`tvinputdevice`, privilege
  `tv.inputdevice`) except volume, power, source and home, and passes them on by name.

## Videos

Not as `<video>`: on this TV (S95HF, Tizen 9.0) an HTML video takes the media player
from the HDMI input, so the TV picture and its sound go while it plays (2026-10-31). The
TV versions are **animated WebP with alpha** instead: an image, decoded without the
media player. Tried on the TV with the 1920×360 power-play video (895 kB, 4 s): ready in
155 ms, transparent and smooth to the eye (one 67 ms frame in the measurement), HDMI
picture and sound stay. `tools/make_stingers.py` makes them from the same frames (`tvgoal`,
`tvintro`, `tvpp`, 1920×1080 or a band of it, about 1 MB for 4 s). Over a live picture
they should be short sweeps that end transparent, leaving the middle of the ice clear
as quickly as possible. If WebP stutters on the TV, the GSAP animations stay alone.

## Development and install

- `/sim` gets a TV view: 1920×1080 scaled, with a still from a broadcast as the HDMI
  picture, the L-frame drawn, and the keyboard standing in for the remote
  (Enter, arrows, Backspace).
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
