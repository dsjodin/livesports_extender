#!/usr/bin/env bash
# Writes the sway config for the kiosk user from sway.config.template and display.env,
# and reloads sway if it is running.
# Usage: sudo /opt/shl-arena-display/render.sh [user]   (default user: arena)
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
USER_NAME=${1:-arena}
ENV_FILE=${SHL_DISPLAY_ENV:-/etc/shl-arena/display.env}
TARGET=${SWAY_CONFIG_OUT:-$(getent passwd "$USER_NAME" | cut -d: -f6)/.config/sway/config}

# shellcheck source=/dev/null
source "$ENV_FILE"
if [[ "${BAR_CUSTOM_MODE:-0}" == 1 ]]; then
  BAR_MODE_LINE="mode --custom ${BAR_MODE}"
else
  BAR_MODE_LINE="mode ${BAR_MODE}"
fi
export OUT_LEFT OUT_BAR OUT_RIGHT ROTATE_LEFT ROTATE_RIGHT BAR_MODE_LINE

mkdir -p "$(dirname "$TARGET")"
# shellcheck disable=SC2016  # envsubst gets the variable names, not their values
envsubst '${OUT_LEFT} ${OUT_BAR} ${OUT_RIGHT} ${ROTATE_LEFT} ${ROTATE_RIGHT} ${BAR_MODE_LINE}' \
  < "$HERE/sway.config.template" > "$TARGET.new"
if command -v sway > /dev/null; then
  # sway -C starts a backend: headless needs no GPU or session; the runtime dir is
  # missing under sudo
  runtime=${XDG_RUNTIME_DIR:-$(mktemp -d)}
  if ! XDG_RUNTIME_DIR=$runtime WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 sway -C -c "$TARGET.new" > /dev/null 2>&1; then
    echo "render.sh: the generated config does not validate:" >&2
    XDG_RUNTIME_DIR=$runtime WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 sway -C -c "$TARGET.new" >&2 || true
    rm -f "$TARGET.new"
    exit 1
  fi
  [[ -n "${XDG_RUNTIME_DIR:-}" ]] || rm -rf "$runtime"
fi
mv "$TARGET.new" "$TARGET"
if [[ $(id -u) == 0 ]] && id "$USER_NAME" > /dev/null 2>&1; then
  chown -R "$USER_NAME:" "$(dirname "$TARGET")"
fi
echo "render.sh: wrote $TARGET"

# reload a running sway of that user
uid=$(id -u "$USER_NAME" 2> /dev/null || true)
for sock in /run/user/"$uid"/sway-ipc.*.sock; do
  [[ -S "$sock" ]] || continue
  if [[ $(id -u) == 0 ]]; then
    sudo -u "$USER_NAME" SWAYSOCK="$sock" swaymsg reload > /dev/null && echo "render.sh: sway reloaded"
  else
    SWAYSOCK="$sock" swaymsg reload > /dev/null && echo "render.sh: sway reloaded"
  fi
done
