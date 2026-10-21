#!/usr/bin/env bash
# Sets up a fresh Debian 13 box as the SHL Arena display box (docs/DEPLOY.md):
# packages, the kiosk user "arena", greetd autologin into sway, the kiosk and
# screen-power units. Safe to run again (an update keeps /etc/shl-arena/display.env).
# Usage: sudo ./install.sh [--url http://lnx01:8010]
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
PREFIX=/opt/shl-arena-display
ETC=/etc/shl-arena
USER_NAME=arena
URL=""

while (($#)); do
  case $1 in
    --url) URL=$2; shift 2 ;;
    *) echo "usage: sudo $0 [--url http://host:8010]" >&2; exit 2 ;;
  esac
done

[[ $(id -u) == 0 ]] || { echo "run as root (sudo $0)" >&2; exit 1; }
if ! grep -q '^VERSION_CODENAME=trixie' /etc/os-release; then
  echo "warning: written for Debian 13 (trixie); this is $(grep '^PRETTY_NAME=' /etc/os-release)" >&2
fi

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends \
  sway swaybg greetd chromium jq curl gettext-base dbus-user-session \
  fonts-dejavu-core ca-certificates sudo

echo "== kiosk user $USER_NAME"
if ! id "$USER_NAME" > /dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$USER_NAME"
fi
for group in video render input; do # GPU and input access for sway
  if getent group "$group" > /dev/null; then usermod -aG "$group" "$USER_NAME"; fi
done

echo "== files to $PREFIX"
install -d "$PREFIX"
install -m 755 "$HERE"/kiosk.sh "$HERE"/screen-power.sh "$HERE"/render.sh "$HERE"/check.sh "$PREFIX"/
install -m 644 "$HERE"/sway.config.template "$HERE"/display.env.example "$PREFIX"/
install -m 644 "$HERE"/systemd/shl-kiosk.service "$HERE"/systemd/shl-screen-power.service \
  "$HERE"/systemd/shl-screen-power.timer /etc/systemd/user/

echo "== settings $ETC/display.env"
install -d "$ETC"
if [[ ! -f "$ETC/display.env" ]]; then
  install -m 644 "$HERE/display.env.example" "$ETC/display.env"
  echo "   new file: edit the output names after the first boot (check.sh lists them)"
fi
if [[ -n "$URL" ]]; then
  sed -i "s|^ARENA_URL=.*|ARENA_URL=$URL|" "$ETC/display.env"
fi
grep '^ARENA_URL=' "$ETC/display.env"

echo "== sway config"
"$PREFIX/render.sh" "$USER_NAME"

echo "== greetd autologin"
install -m 644 "$HERE/greetd.toml" /etc/greetd/config.toml
systemctl enable greetd.service
systemctl set-default graphical.target

echo
echo "Done. Reboot: the box logs $USER_NAME into sway and opens the three screens."
echo "Then check:  sudo $PREFIX/check.sh"
