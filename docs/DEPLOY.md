# Deployment

Two machines:

- **The Docker host** (here `lnx01`) runs the SHL Arena service: it polls shl.se, keeps
  the state, serves the pages and calls Home Assistant.
- **The display box** (a mini PC with Debian 13, planned: Beelink SER8) drives the three
  screens: sway with three Chromium kiosk windows that open the service's screen pages.

The phone app and `/sim` are just pages on the service: open `http://lnx01:8010/app`.

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

## 3. Where things were verified (2026-10-21)

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
