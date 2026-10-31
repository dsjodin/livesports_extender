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

- **At start the defaults, not where it was left** (the user, 2026-10-31): the first load
  of the graphics after the app starts (not their own reloads: `sessionStorage`) calls
  `POST /api/tv/start`. With "follow my team" on (the default) and my team playing today,
  the service follows that game live (pregame, live or intermission as it stands);
  otherwise a replay, a recording or an old game is closed and the TV shows idle. A live
  game the user chose today that still runs is kept. `/sim`'s TV view skips this
  (`?sim=1`).
- **Between games (idle)** the column pages through the standings, my team's next game
  (time, arena, both teams' place), my team's place, form and points leaders (with a
  portrait), and the latest results when the band shows tonight's games.
- **At start** a note shows for 6 s what the app does ("SHL live! · Följer FHC–SKE · live ·
  OK öppnar menyn", or "Ingen match vald"), so a quiet full picture in play is not taken
  for a dead app (the user, 2026-10-31).
- **Power-play clock:** the service knows when each penalty runs out in game time
  (`expires_game_seconds`), not how much of it is left now (the game clock only reaches
  us with events), so the TV says "till P1 17:09" rather than a ticking countdown.
- **Lower thirds** sit 120–130 px above the bottom, clear of the broadcaster's tickers,
  and from the left edge, clear of its bug top left.
- **L-frame:** the TV picture moves to the top left at 60 % (1152×648, 40 px from the
  edges), our graphics fill the column right of it (648×1000) and the band below it
  (1152×312); a backdrop in `--bg-screen` paints everything around the picture
  (`web/tv/layout.js`). The overlay asks the shell to move the picture at the scene's
  `play_at`, so the change lands with the broadcast; going back to full screen the
  backdrop fades out in 0.1 s, before the picture has grown (45–120 ms on the TV).
  The viewer can ask for the full picture in any L-frame scene (9.4); the next scene
  change resets it.
- **Panels** (on ↑ ↓ or from the menu, `web/tv/panels.js`): Statistik (shots per period,
  power plays, penalty minutes, save %), Skottkarta (both teams' shot maps with their
  shots on goal, asked for by the user 2026-10-31), Tabell (the live table or the
  standings), Kvällens matcher. In play they lie in the right third over the full picture, half see-through;
  in an L-frame scene they take the column's place, opaque, so nothing lies on top of the
  column's own graphics (the user, 2026-10-31: "overlay på overlay"), and the column's
  slideshow is back when they close. Past the last (or first) they close, as do Back and
  20 s without a key; a change between full picture and L-frame closes them too. An open
  panel follows the delayed patches.
- Kept out of the broadcast's own graphics: the top left (the broadcaster's score bug)
  and the bottom 8 % (its tickers) stay free in `live` and `goal`.

## Remote

The remote (Samsung, 2026) has arrows, OK, Back, play/pause, volume and channel keys;
digits and colour keys only on a virtual pad on screen. So the app works with **arrows,
OK and Back** alone (2026-10-31). Of the remote's other physical keys, **play/pause**
reaches the app (key code 10252, the test page's report 2026-10-31) and is the shortcut
for Synka nedsläpp: one press at the moment the drop shows on TV. The channel rocker did
not show in the report: the TV may pass it on to the box over HDMI (CEC), so nothing
depends on it.

| Key | No menu open | Menu open |
|---|---|---|
| OK | Opens the menu | Choose; on Matcher, Synk, Inställningar opens its sheet |
| ↑ ↓ | Next / previous panel (Statistik → Skottkarta → Tabell → Kvällens matcher → off) | Move |
| → | | Opens a sheet, like OK |
| ← / Back | Back: closes a panel, or the full picture back to the L-frame; twice in 2 s: exit | Closes the sheet, then the menu |
| ⏯ play/pause | Synka nedsläpp at once (a `period_start` sample, with a selected game) | The same |

The menu (`web/tv/menu.js`, task 9.4) is a list low on the left over the picture, 38 px
text (nine items in a row along the bottom would not fit at a readable size):
MÅL! <my team>, MÅL! <the other team>, Synka nedsläpp, Statistik, Skottkarta, Tabell,
Kvällens matcher, Helbild (in an L-frame scene; "Tillbaka till L-ram" when on), Matcher ›,
Synk ›, Inställningar › (TV profile, "Följ mitt lag automatiskt" on/off, server and
HDMI, the test page). The goal and sync items only while a game is selected. It closes
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

## Dimming and the OLED

Boxes over the full picture (penalty, power-play pill, goal, panels, menu): with a
88–94 % background they looked see-through and hard to read on the S95HF, though a
browser draws them nearly solid, and at 100 % too solid (the user 2026-10-31). The TV
blends our layer over its picture its own way, so the cover (the whole box, text included, as `filter: opacity()`) is a choice in the menu
(Inställningar → "Rutor över bilden": 97 % by default, then 94, 90, 85, 80, 70, 60 and 100 %), kept in the TV
browser's storage (`shllive.cover`); `--ov-bg` in `tv.css`.

The TV is an OLED (S95HF), so graphics that stand still for hours can burn in (the user,
2026-10-31). `web/tv/overlay.js`:

- **Quiet** is idle, or pregame while puck drop on TV is more than an hour away (a followed
  game makes the whole game day pregame; the dimming did not show for it, 2026-10-31).
  Dimming and rest apply when quiet; an hour before the drop the graphics come back to
  full brightness by themselves.
- **Dimming in idle**, the wall's setting (`idle_dim`, "Dimning i vila" in the phone app,
  `docs/SCREENS.md`): our graphics fade to `1 − idle_dim` over 1.5 s when idle starts and
  come back in 0.4 s; the TV picture is never dimmed. Panels opened by hand are not.
- **Rest in idle:** after 10 min in idle without a key the graphics step aside and the TV
  gets the whole picture (as "Helbild"); the first key brings the L-frame back and does
  nothing else, and the next game brings the graphics back by itself.
- **Pixel shift:** every 2 min our graphics (not the backdrop, which lines up with the TV
  picture) move to the next of eight offsets within ±3 px, over 3 s, so no edge stays on
  the same pixels. Invisible at 4 m.
- In play little stands still: panels close after 20 s, lower thirds after seconds, the
  power-play pill after the power play.
- The TV's own care helps too: Samsung's pixel shift and logo-luminance settings
  (Settings → General / Picture → panel care, names vary by model) are worth leaving on.

For trying them: `/tv/?rest=<s>&shift=<s>` shortens the rest and the shift.

## Sound (tried on the TV 2026-10-31)

- The app's own sound plays, through Web Audio and through `<audio>`, and reaches the
  soundbar with the broadcast's sound (the user's sound goes to a soundbar over HDMI
  eARC).
- The TV's volume and mute (`tvaudiocontrol`, shell 1.1.0) do nothing to it: they act on
  the TV's own speakers, not on a soundbar over eARC. So the app cannot lower or mute the
  broadcast. That would go through Home Assistant, which already gets the goal webhook
  at `play_at` and can turn the soundbar down and back.
- The remote's volume keys do reach the soundbar (the TV passes them on over HDMI-CEC).
  So the shell (1.2.0) can also step the volume as those keys do (`setVolumeUp`,
  `setVolumeDown`); the test page's "Ljud: volym 3 steg ner och upp (som fjärren)" shows
  whether that reaches the soundbar too.
- The soundbar is a Sonos Arc (2026-10-31). A Sonos announcement switches its input away
  from the TV (lag, trouble getting back), so sound comes from the TV app: mixed into the
  TV's own sound before eARC, the Arc stays on the TV input. The mix also means nothing
  can lower the broadcast under our sound: the Arc's volume (HA, or the remote's steps)
  turns both down alike. Our sound plays over the broadcast at its own level.
- What the app does with sound is still open (the user has ideas, 2026-10-31).

## Screen saver

The TV counts an app nobody presses keys in as idle and starts its screen saver after a
while, which it never does on a TV input (the user, 2026-10-31). The shell turns it off
while the app is shown and on again when the app is hidden or exits:
`webapis.appcommon.setScreenSaver(SCREEN_SAVER_OFF)` (Samsung's AppCommon API, from
`$WEBAPIS/webapis/webapis.js`). Samsung's guide: the saver comes "after a defined amount
of time with no activity" (the TV's setting "Auto Protection Time"; with that setting off
the API has no effect), and it says nothing about how long one "off" holds.

On the S95HF one "off" did not hold: Samsung's saver came after about 4 min with shell
1.0.0 (one call at start) and with 1.3.0 (the same call every minute and on keys),
2026-10-31. Shell 1.4.0 switches it on and straight off again every minute and on keys,
a change the TV should notice and count from anew. The menu (Inställningar) shows
"Skärmsläckare: av · växlad 12 gånger, senast 20:41", and the test page's report
`shell.screen_saver`. If that does not hold it either, the fallback is the TV's own
setting (Auto Protection Time longer, or off: our graphics dim and rest by themselves,
see Dimming and the OLED).

Shell 1.3.0 still let it come after about 2 min, and what the user found about Samsung's
OLED TVs says the saver cannot be turned off there (2026-10-31). A key press does reset
it, so the next test (before anything is built in) is a key sent over the network:
`tools/tv_keepawake.py <TV's IP>` sends KEY_RED every 60 s through the TV's own network
remote (the remote-control WebSocket on port 8002 that phone remote apps use; the first
time the TV asks to allow "SHL Arena", and the token is kept in
`data/tv_remote_token.txt`). The remote has no red key and the graphics ignore "red"
(not even waking the resting L-frame), so nothing shows on screen. If the saver stays
away, the service can do the same while the TV app is shown.

**Result (2026-10-31): a network key works.** Samsung's saver comes only while the TV
picture is shrunk (the L-frame), never over a full-screen game. KEY_RED sent every 60 s
over the TV's network remote kept it away for 5 min in the L-frame, and the graphics
counted the keys ("Väckknappar: 10, senast 17:46 (red)" in the menu, two senders) with
nothing on screen. The TV let the user's Windows PC on its own subnet (10.1.30.x) in at
once, giving a token, while the Docker host on another subnet (10.1.40.x) got
`ms.channel.timeOut` with and without that token; after the token was issued, the PC too
needed `&token=…` in the URL. So the sender must be on the TV's own network (or be the
TV app itself, if its local remote channel can be reached).

1.3.0 also tried `tizen.power.request("SCREEN", "SCREEN_NORMAL")`, but the TV has no
`tizen.power` (S95HF, Tizen 9.0: "skärmlås fel: cannot read properties of undefined
(reading 'request')"); 1.4.0 dropped it and its privilege.

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
- The `.wgt` is built and installed with `deploy/tv/package.sh` (the Tizen CLI and a
  Samsung certificate for the TV); the steps are in `docs/DEPLOY.md`, section 3.
- `config.xml` (shell 1.4.0): privileges `internet`, `tv.window`, `tv.inputdevice`,
  `tv.audio` (volume and mute for the graphics, which ask
  with `{t: "audio", op: "get"|"volume"|"mute"}`) and Samsung's `productinfo`; `<access origin="*"
  subdomains="true"/>` for the service on the LAN (no content security policy is needed:
  the iframe, HTTP and WebSocket to the server work as is); `icon.png` 512×423.
- **Recovery** (shell 1.0.0): the graphics say "ready" every 10 s; silent for 30 s (an
  error page while the service was down, a hang), the shell waits for `/api/health` and
  loads them again. HDMI that went away (the box off) is looked for again when the TV
  reports a change of its sources and every 10 s; meanwhile the graphics say "Ingen bild
  från HDMI 1 · är boxen på?". The service's hello carries a `boot` id new at each start;
  the graphics reload themselves when it changes, so an update needs no reinstall.

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
   own. Arrows, OK, Back and play/pause reach the app; the channel rocker did not (or was
   not pressed) in the report of 2026-10-31.
8. How much the TV's HDMI path delays the picture compared with the TV's own input
   (the `iptv` TV profile may need a small nudge). Open: shows with Synka on a live game.

The TV: S95HF, Tizen 9.0, firmware T-RSMFDEUC-0090-1301.0, Chromium 120, page
1920×1080 at dpr 1. Its clock is about 150 ms off; the synced clock absorbs it.

## The test build (task 9.1)

The test page (`web/tv/probe.js`) checks the list above and reports to the service. It
was the whole of `/tv/` in task 9.1; now it shows instead of the graphics while
`tv_probe` is set (menu → Inställningar → Testsidan, or `/sim`).

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
   - **sound** (shell 1.1.0 for the last two; 2026-10-31, before deciding what the app
     does with sound): "Ljud: horn via Web Audio" (the page's own mixer: heard, and the
     broadcast's sound and picture still there?), "Ljud: horn via <audio>" (may take the
     media player from HDMI as `<video>` did; HDMI is restored after it), "Ljud: sänk
     TV:ns volym en stund" (5 steps for 3 s through the shell's `tvaudiocontrol`), "Ljud:
     tysta TV:n och spela horn" (does the TV's mute silence the app too?). The report has
     `sound` (the AudioContext state, `suspended` meaning the TV wants a user gesture, and
     the volume before, lowered and restored);
   - **highlights** (2026-10-31, a test before anything is built): "Video: målklipp FHC–SKE
     (22 s)" and "Video: höjdpunkter FHC–SKE (5 min)" play shl.se's clips in the video
     provider's public embed (`https://embed.staylive.tv/video/<id>?autoplay=1`, the URL
     shl.se's `/api/media/videos-for-game?gameUuid=…` gives) in a full-screen iframe;
     Back or the clip's length closes it and HDMI is asked back; then: did it start by
     itself, was its sound heard, did the TV picture and sound come back;
   - "Dölj testbilden" hides the page (any key brings it back); Back twice exits;
   - "Tillbaka till grafiken" turns the test page off (`tv_probe`) and the TV reloads
     into the graphics.

To check which of the remote's own keys reach the app (play/pause, the channel rocker,
…): menu (OK) → Inställningar → Testsidan, press the keys, and read the "Fjärrkontroll"
row ("andra: …") or `keys` in the report; then "Tillbaka till grafiken". The shell must be
0.3.1 or later (it registers every key the TV lets an app have).
4. The page sends its report every 30 s (and at once on "Skicka rapport"). Read it at
   `http://<server>:8010/api/tv/probe` (kept in `data/tv_probe.json`) and send it on.
5. If the picture does not show through (or the page stays empty), choose Läge
   "Direkt (reserv)" in the settings and run it again: the same page, imported into the
   shell itself.

On a computer the shell runs as a preview at `http://<server>:8010/tvapp/` (striped
stand-in for the TV picture; the keyboard is the remote: Enter, arrows, Backspace). Opening `SHLlive/index.html` from disk tries the fallback mode the
way the TV does (Origin `null`, CORS). Both were run in Chromium on 2026-10-31.
