#!/usr/bin/env bash
# Checks the display box: the three outputs (active, right size after rotation), one
# SHL Arena window on each, the service reachable and the units running.
# Run as the kiosk user in its sway session, or as root (it finds the session):
#   sudo /opt/shl-arena-display/check.sh
set -uo pipefail

USER_NAME=${KIOSK_USER:-arena}
ENV_FILE=${SHL_DISPLAY_ENV:-/etc/shl-arena/display.env}
# shellcheck source=/dev/null
source "$ENV_FILE"

if [[ $(id -u) == 0 && "${1:-}" != --as-user ]]; then
  uid=$(id -u "$USER_NAME")
  sock=$(compgen -G "/run/user/$uid/sway-ipc.*.sock" | head -n1 || true)
  [[ -n "$sock" ]] || { echo "FAIL  no sway session for $USER_NAME (not logged in?)"; exit 1; }
  exec sudo -u "$USER_NAME" SWAYSOCK="$sock" XDG_RUNTIME_DIR="/run/user/$uid" \
    SHL_DISPLAY_ENV="$ENV_FILE" "$0" --as-user
fi

failed=0
ok() { echo "ok    $*"; }
fail() {
  echo "FAIL  $*"
  failed=1
}

outputs=$(swaymsg -t get_outputs) || { echo "FAIL  swaymsg cannot reach sway"; exit 1; }
echo "outputs: $(jq -r '[.[] | "\(.name) \(.rect.width)x\(.rect.height)"] | join(", ")' <<< "$outputs")"

check_output() {
  local name=$1 w=$2 h=$3 what=$4 info
  info=$(jq -c --arg n "$name" '.[] | select(.name == $n)' <<< "$outputs")
  if [[ -z "$info" ]]; then
    fail "$what: no output $name (set it in $ENV_FILE)"
    return
  fi
  if [[ $(jq -r '.active' <<< "$info") != true ]]; then
    fail "$what: $name is not active"
    return
  fi
  local rw rh
  rw=$(jq -r '.rect.width' <<< "$info")
  rh=$(jq -r '.rect.height' <<< "$info")
  if [[ "$rw" == "$w" && "$rh" == "$h" ]]; then
    ok "$what: $name ${rw}x${rh}"
  else
    fail "$what: $name is ${rw}x${rh}, expected ${w}x${h} (rotation or mode in $ENV_FILE)"
  fi
}
check_output "$OUT_LEFT" 1080 1920 left
check_output "$OUT_BAR" 1920 360 bar
check_output "$OUT_RIGHT" 1080 1920 right

tree=$(swaymsg -t get_tree)
for pair in "left:$OUT_LEFT" "bar:$OUT_BAR" "right:$OUT_RIGHT"; do
  screen=${pair%%:*}
  output=${pair#*:}
  on=$(jq -r --arg t "SHL Arena – $screen" '
    .nodes[] | select(.type == "output") | .name as $o
    | [.. | objects | select(.type? == "con" and ((.name // "") | startswith($t)))]
    | select(length > 0) | "\($o) \(length)"' <<< "$tree")
  if [[ -z "$on" ]]; then
    fail "window $screen: not running"
  elif [[ "$on" == "$output 1" ]]; then
    ok "window $screen on $output"
  else
    fail "window $screen: found on '$on', expected $output"
  fi
done

if curl -fsS --max-time 5 "$ARENA_URL/api/health" > /dev/null; then
  ok "service $ARENA_URL"
else
  fail "service $ARENA_URL does not answer"
fi
for unit in shl-kiosk.service shl-screen-power.timer; do
  if systemctl --user is-active --quiet "$unit"; then ok "$unit running"; else fail "$unit not running"; fi
done

((failed)) && echo "Some checks failed." || echo "All checks passed."
exit "$failed"
