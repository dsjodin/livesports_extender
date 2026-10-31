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
| Remote | Sync (puck drop), MÅL! buttons, panels, choosing the game on the TV. |
| Server address | Typed in once in the app (setup screen), stored on the TV. |
| Videos | Team videos remade for 16:9 (1920×1080, VP9 with alpha), if the TV plays VP9 alpha (to be verified). |

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

All text Swedish (hockey terms in English as on the wall). Sized for 3 m on the TV's real
width (the size is still to be given, see Open questions), checked with
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

| Key | In a game | In the menu |
|---|---|---|
| Red | MÅL! for the home team | |
| Blue | MÅL! for the away team | |
| Green | Synka: puck drop now (a `period_start` sample) | |
| Yellow | Next panel: Statistik → Tabell → Kvällens matcher → off | |
| OK | Full-screen TV on/off (L-frame scenes) | Choose |
| Arrows | | Move |
| 0 | Menu: Matcher (today's games, follow or stop), Synk (samples, accept), HDMI, Server | |
| Back | Close panel or menu | Back; at the top level "Avsluta?" |

- The MÅL! keys fire lights and horn in Home Assistant at once, so they need a second
  press within 2 s ("MÅL! HEMMA? Tryck igen") to keep a stray press quiet (to confirm
  with the user). With "Använd målknapp för synk" on, a linked press is also a goal
  sample, as in the phone app.
- Colour and digit keys must be registered with `tizen.tvinputdevice.registerKey`
  (privilege `tv.inputdevice`); the shell does that and passes them on.

## Videos

Separate 16:9 versions next to the wall's (`docs/VIDEOS.md`): `tvgoal`, `tvintro`, `tvpp`,
1920×1080 VP9 with alpha, from `tools/make_stingers.py`. Over a live picture they should
be short sweeps that end transparent, leaving the middle of the ice clear as quickly as
possible. If the TV cannot play VP9 alpha, the GSAP animations stay and the videos are
left out on the TV.

## Development and install

- `/sim` gets a TV view: 1920×1080 scaled, with a still from a broadcast as the HDMI
  picture, the L-frame drawn, and the keyboard standing in for the remote
  (R, G, Y, B, Enter, arrows, 0, Backspace).
- The `.wgt` is built and installed with the Tizen CLI (Tizen Studio or the VS Code
  extension): developer mode on the TV with the PC's IP, `sdb connect <tv>`,
  `tizen package -t wgt -s <certificate profile>`, `tizen install -n SHLlive.wgt -t <tv>`.
  A Samsung certificate from the Certificate Manager is needed for a TV. Steps in
  `docs/DEPLOY.md` once the app exists.
- `config.xml` needs, besides `tv.window`: `internet`, `tv.inputdevice`,
  `<access origin="*" subdomains="true"/>` (the service on the LAN) and the right
  `tizen:content-security-policy` to allow the iframe and WebSocket to the server.

## To verify on the real TV first (task 9.1)

1. A transparent iframe from the service draws over the HDMI picture (else the fallback).
2. The packaged app reaches `http://<server>:8010` (HTTP and WebSocket) on the LAN.
3. ES modules and GSAP run smoothly at 1920×1080 (60 fps for transform and opacity).
4. VP9 with alpha plays transparent in `<video>` over HDMI.
5. Moving the TV picture with `tvwindow.show` (L-frame) works without a black flash, and
   how long the move takes.
6. The synced clock holds within a few ms, as on the display box.
7. The colour and digit keys reach the shell.
8. How much the TV's HDMI path delays the picture compared with the TV's own input
   (the `iptv` TV profile may need a small nudge).

## Open questions

- The TV's size (inches) and the viewing distance, for the type scale.
- MÅL! on the remote: double press to confirm, or a single press like the phone app.
