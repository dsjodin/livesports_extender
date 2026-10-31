# Deployment

Two machines:

- **The Docker host** (here `lnx01`) runs the SHL Arena service: it polls shl.se, keeps
  the state, serves the pages and calls Home Assistant.
- **The display box** (a mini PC with Debian 13, planned: Beelink SER8) drives the three
  screens: sway with three Chromium kiosk windows that open the service's screen pages.

The phone app and `/sim` are just pages on the service: open `http://lnx01:8010/app`.

Instead of (or as well as) the wall, **the Samsung TV app** (`SHLlive/`, section 3) draws the
graphics over the TV picture itself; it needs only the Docker host.

## 1. Docker host

Needs Docker with the compose plugin, and an NTP-synced clock (CLAUDE.md rule 2: the
sync to the TV is only as good as the clock). Check with `timedatectl` ("System clock
synchronized: yes"); on Fedora/RHEL `chronyd` does it.

```
git clone <repo> livesports_extender && cd livesports_extender
docker compose up -d --build
docker compose ps            # "Up ... (healthy)" after about 20 s
curl http://localhost:8010/api/health
```

`compose.yaml` restarts the service unless you stopped it, checks `/api/health` every
30 s, and rotates the logs (5 × 10 MB). Everything that must survive is in `./data`:

| Path | What |
|---|---|
| `data/state.json` | settings: TV profiles, calibration, my team, team colours, Home Assistant |
| `data/recordings/<game>/polls.jsonl` | every game followed live (about 11 MB each) |
| `data/cache/` | team logos and player portraits (fetched again if deleted) |

Open the port for the display box and the phone if the host has a firewall:

```
sudo firewall-cmd --permanent --add-port=8010/tcp && sudo firewall-cmd --reload   # Fedora/RHEL
```

Update: `git pull && docker compose up -d --build`. Logs: `docker compose logs -f`.
The pages are served with `Cache-Control: no-cache` (since 2026-10-22), so a reload picks
up an update; a browser that loaded them before that may need one hard reload
(Ctrl+Shift+R) to drop its old copies.

## 2. Display box

### Install Debian 13

A minimal install: in "Software selection" untick the desktop environments, keep "SSH
server" and "standard system utilities". Any user name for yourself; the installer
script creates the kiosk user `arena` on its own. In the BIOS, set "power on after AC
loss" so the box starts when the screens' power comes on.

### Run the installer

As your own user, over SSH:

```
sudo apt install -y git
git clone <repo> livesports_extender && cd livesports_extender
sudo deploy/display-box/install.sh --url http://lnx01:8010
sudo reboot
```

Use the host's IP address instead of `lnx01` if the box cannot resolve the name
(`curl http://lnx01:8010/api/health` from the box tells you).

`install.sh` installs sway, greetd, Chromium, jq and curl; creates `arena`; copies the
scripts to `/opt/shl-arena-display/`; writes `/etc/shl-arena/display.env` (only the
first time); renders `~arena/.config/sway/config`; and sets greetd to log `arena` into
sway at boot. sway then starts two systemd user units: `shl-kiosk` (the three windows,
restarted if one exits) and `shl-screen-power.timer` (screens on and off). The windows
wait until the service answers, so the order in which the two machines boot does not
matter.

### First boot: name the outputs

The output names depend on the hardware. After the first boot:

```
sudo /opt/shl-arena-display/check.sh
```

It lists the outputs (`outputs: DP-1 1920x1080, HDMI-A-1 1920x360, ...`) and checks
each screen. If a screen is on the wrong output or the wrong size, edit
`/etc/shl-arena/display.env`:

| Setting | Meaning |
|---|---|
| `OUT_LEFT`, `OUT_BAR`, `OUT_RIGHT` | which output is which screen (left = home team) |
| `ROTATE_LEFT`, `ROTATE_RIGHT` | `90` or `270`, whichever puts the top of the picture up |
| `BAR_MODE`, `BAR_CUSTOM_MODE` | the bar's mode; set `BAR_CUSTOM_MODE=1` if its EDID has no 1920×360 mode |
| `SCREEN_POWER` | `dpms` (sway turns the outputs off), `ha` (a Home Assistant switch such as a smart plug) or `none` |
| `SCREENS_ON_FROM`, `SCREENS_ON_UNTIL` | hours the screens are on; they are also on whenever a game is selected on the service |
| `HA_URL`, `HA_TOKEN`, `HA_SWITCH` | only for `SCREEN_POWER=ha` (token: HA profile → Security → long-lived token) |
| `CHROMIUM_EXTRA_FLAGS` | e.g. `--disable-gpu` if the GPU misbehaves |

Then apply it and check again:

```
sudo /opt/shl-arena-display/render.sh     # rewrites the sway config and reloads sway
sudo reboot                               # simplest way to restart the windows too
sudo /opt/shl-arena-display/check.sh      # "All checks passed."
```

`render.sh` refuses a config that sway does not accept and keeps the old one.

### Update

```
cd livesports_extender && git pull && sudo deploy/display-box/install.sh && sudo reboot
```

`display.env` is kept.

### Troubleshooting

| Symptom | Look at |
|---|---|
| Black screens after boot | `sudo /opt/shl-arena-display/check.sh` |
| A window is missing or on the wrong screen | `check.sh`, then the output names in `display.env` |
| A window shows a browser error page | the service: `curl $ARENA_URL/api/health` from the box |
| Kiosk log | `sudo -u arena XDG_RUNTIME_DIR=/run/user/$(id -u arena) journalctl --user -u shl-kiosk -f` |
| Screens never sleep or never wake | `SCREEN_POWER` and the hours; the log of `shl-screen-power` (as above) |
| Picture upside down | `ROTATE_LEFT` / `ROTATE_RIGHT` 90 ↔ 270 |
| Bar black or wrong size | `BAR_CUSTOM_MODE=1`; `swaymsg -t get_outputs` lists the modes the bar offers |

A keyboard on the box: sway has no key bindings in this config; log in over SSH instead.

## 3. Samsung TV app

The app (`SHLlive/`, `docs/TV_APP.md`) is a thin shell: it shows HDMI 1 (the Telia box)
behind its page, takes the remote's keys and loads the graphics from the service
(`http://lnx01:8010/tv/`). Tried on a Samsung S95HF (77", Tizen 9.0, 2026).

### Once: developer mode, Tizen tools, certificate

1. **Developer mode on the TV:** Apps, then type `1 2 3 4 5` (the remote's on-screen
   number pad), Developer mode **On**, Host PC IP = the computer you build on; restart the
   TV as it asks.
2. **Tizen Studio** (or its CLI-only installer) on that computer. In its Package Manager,
   under Extension SDK: *Samsung Certificate Extension* and *TV Extensions*. `tizen` and
   `sdb` must be on `PATH` for the script below
   (`~/tizen-studio/tools/ide/bin` and `~/tizen-studio/tools`).
3. **Connect:** `sdb connect <TV's IP>`; `sdb devices` should list the TV.
4. **Certificate:** Tizen Studio, Tools → Certificate Manager → `+` → **Samsung** → TV →
   a profile name (e.g. `mytv`) → author certificate (a Samsung account sign-in) →
   distributor certificate with the TV's DUID (it is filled in while the TV is connected).
   An app signed with it installs on that TV only.

### Package and install

```
TIZEN_PROFILE=mytv TV=<TV's IP> deploy/tv/package.sh
```

It copies `SHLlive/` aside (without the source picture), signs it as `SHLlive.wgt` in
the repo root and installs it on the TV. Without `TV` it only packages; install later
with `tizen install -n SHLlive.wgt -s <TV's IP>:26101 -- <dir>`, or from Tizen Studio
(import `SHLlive/` as a web project, Run As → Tizen Web Application). The app is then in
the TV's Apps as **SHLlive**; it stays when developer mode is turned off again.

### First start

"Inställningar": the Docker host's address with port (`192.168.1.20:8010`; OK opens the
TV's keyboard), HDMI 1, Läge **Iframe**, Anslut. The settings stay on the TV; later they
are in the menu (OK) → Inställningar → Server och HDMI.

### Updates

- **Graphics** (everything under `web/`, the server): `git pull` and
  `docker compose up -d --build` on the Docker host. The TV notices the restarted
  service and loads the new pages by itself (no reinstall).
- **The shell** (`SHLlive/`, its version in `config.xml`): package and install again.
  Only needed when a change says so. Build from the updated repo's `SHLlive/` (a copy
  imported into Tizen Studio or VS Code earlier stays at its old version). When the
  installed shell is older than the server's `SHLlive/config.xml`, the graphics say so
  for 30 s at start: "TV-appen är 1.0.0, servern har 1.3.0 · bygg och installera om
  appen". Menu → Inställningar shows the installed version ("skal 1.3.0").

### Troubleshooting

| On the TV | What it means |
|---|---|
| "Ingen kontakt med <server>" | The address or port is wrong, the service is down, or the TV is on another network. It retries every 5 s; OK opens the settings. |
| "Grafiken svarar inte" | The graphics stopped answering (the service went away). The shell waits for the service and loads them again by itself. |
| "Ingen bild från HDMI 1 · är boxen på?" | The box is off or on another input. The shell looks again when the TV's sources change, and every 10 s. |
| Black picture, graphics fine | Menu → Inställningar → Server och HDMI: the right HDMI number. |
| The screen saver starts | Menu → Inställningar shows "Skärmsläckare: av · växlad N gånger, senast hh:mm" from shell 1.4.0 (it switches the saver on and off again every minute). Only "av" or "av · skärmlås …" means an older shell. If it still starts, set the TV's Auto Protection Time longer (`docs/TV_APP.md`, Screen saver). |
| Something else | Menu → Inställningar → Testsidan: checks the TV and reports to `http://<server>:8010/api/tv/probe`. |

## 4. Where things were verified (2026-10-21)

- `compose.yaml`: built and started; the container became `healthy`, with the restart
  policy and log rotation in place.
- `install.sh`: ran to the end on Debian 13 (in a `debian:trixie` container, twice):
  all packages exist (sway 1.10.1, Chromium 155, greetd 0.10.3), the sway config
  validates, a second run keeps `display.env`.
- `render.sh`, `kiosk.sh`, `check.sh`, `screen-power.sh`: under a headless sway with
  three virtual outputs, as a normal user, against the running service: the outputs came
  out 1080×1920, 1920×360 and 1080×1920, each page opened on its own output, a killed
  window came back on its output, and `check.sh` passed (except the systemd units, which
  that test did not run).
- Not verified yet: the real box, with real outputs, greetd and the systemd units at
  boot. That is the Phase 7 acceptance ("a fresh Debian 13 box shows the right pages
  after boot with no manual steps") and needs the hardware.
