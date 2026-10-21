#!/usr/bin/env bash
# Turns the screens on or off: on during SCREENS_ON_FROM–SCREENS_ON_UNTIL and whenever the
# service has a game going (phase not idle), off otherwise. Run every minute by the
# shl-screen-power timer. SCREEN_POWER=dpms uses sway, =ha a Home Assistant switch.
set -euo pipefail

ENV_FILE=${SHL_DISPLAY_ENV:-/etc/shl-arena/display.env}
# shellcheck source=/dev/null
source "$ENV_FILE"
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/shl-arena
mkdir -p "$STATE"
LAST="$STATE/screen-power"

[[ "${SCREEN_POWER:-dpms}" == none ]] && exit 0

minutes() { # "17:30" -> 1050
  local h=${1%%:*} m=${1##*:}
  echo $((10#$h * 60 + 10#$m))
}

in_window() {
  [[ -n "${SCREENS_ON_FROM:-}" && -n "${SCREENS_ON_UNTIL:-}" ]] || return 1
  local now from until
  now=$(minutes "$(date +%H:%M)")
  from=$(minutes "$SCREENS_ON_FROM")
  until=$(minutes "$SCREENS_ON_UNTIL")
  if ((from <= until)); then
    ((now >= from && now < until))
  else # past midnight, e.g. 17:00–01:00
    ((now >= from || now < until))
  fi
}

game_on() {
  local phase
  phase=$(curl -fsS --max-time 5 "$ARENA_URL/api/state" | jq -r '.tv.phase' 2> /dev/null) || return 1
  [[ -n "$phase" && "$phase" != idle && "$phase" != null ]]
}

want=off
if in_window || game_on; then
  want=on
fi
[[ -f "$LAST" && "$(cat "$LAST")" == "$want" ]] && exit 0

case "${SCREEN_POWER:-dpms}" in
  dpms)
    swaymsg "output * power $want" > /dev/null
    ;;
  ha)
    curl -fsS --max-time 5 -X POST \
      -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
      -d "{\"entity_id\": \"$HA_SWITCH\"}" \
      "$HA_URL/api/services/switch/turn_$want" > /dev/null
    ;;
  *)
    echo "screen-power: unknown SCREEN_POWER=$SCREEN_POWER" >&2
    exit 1
    ;;
esac
echo "$want" > "$LAST"
echo "screen-power: screens $want"
