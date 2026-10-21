#!/usr/bin/env bash
# Starts the three SHL Arena screen pages as Chromium kiosk windows, one per output, and
# restarts any window that exits. Run by the shl-kiosk systemd user unit from sway.
set -euo pipefail

ENV_FILE=${SHL_DISPLAY_ENV:-/etc/shl-arena/display.env}
# shellcheck source=/dev/null
source "$ENV_FILE"
CHROMIUM=${CHROMIUM:-chromium}
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/shl-arena
SCREENS=(left bar right) # workspaces 1, 2, 3 (sway config)

log() { echo "kiosk: $*"; }

window_on() {
  # true if a window titled "SHL Arena – <screen>" exists
  swaymsg -t get_tree | jq -e --arg t "SHL Arena – $1" \
    '[.. | objects | select(.type? == "con" and ((.name // "") | startswith($t)))] | length > 0' \
    > /dev/null
}

wait_for_service() {
  # the pages reconnect on their own, but Chromium shows an error page (and stays on it)
  # if the first load fails
  until curl -fsS --max-time 3 "$ARENA_URL/api/health" > /dev/null 2>&1; do
    log "waiting for $ARENA_URL"
    sleep 5
  done
}

clean_exit_flag() {
  # no "restore pages?" bubble after a crash or power cut
  local prefs="$1/Default/Preferences"
  [[ -f "$prefs" ]] || return 0
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$prefs"
}

run_window() {
  local screen=$1 workspace=$2 dir="$STATE/chromium-$1"
  mkdir -p "$dir"
  clean_exit_flag "$dir"
  swaymsg "workspace number $workspace" > /dev/null # a new window opens on the focused one
  # shellcheck disable=SC2086  # CHROMIUM_EXTRA_FLAGS is a list of flags
  exec "$CHROMIUM" \
    --kiosk \
    --ozone-platform=wayland \
    --user-data-dir="$dir" \
    --no-first-run \
    --no-default-browser-check \
    --noerrdialogs \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --disable-features=Translate,TranslateUI,MediaRouter \
    --autoplay-policy=no-user-gesture-required \
    --check-for-update-interval=31536000 \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --password-store=basic \
    --hide-scrollbars \
    ${CHROMIUM_EXTRA_FLAGS:-} \
    "$ARENA_URL/screens/$screen.html"
}

supervise() {
  local screen=$1 workspace=$2
  while true; do
    (run_window "$screen" "$workspace") || true
    log "$screen exited, restarting in 3 s"
    sleep 3
    wait_for_service
  done
}

wait_for_service
for i in "${!SCREENS[@]}"; do
  screen=${SCREENS[$i]}
  supervise "$screen" $((i + 1)) &
  # start the next one only when this window is up, so each opens on its own workspace
  for _ in $(seq 60); do
    window_on "$screen" && break
    sleep 0.5
  done
  if window_on "$screen"; then log "$screen up"; else log "$screen: no window after 30 s"; fi
done
wait
