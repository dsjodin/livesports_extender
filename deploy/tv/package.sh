#!/bin/sh
# Package the Samsung TV app (SHLlive/) as a signed .wgt and, if TV is set, install it on
# the TV (docs/DEPLOY.md, section 3). Needs the Tizen CLI (tizen and sdb on PATH, from
# Tizen Studio or its CLI-only install) and a Samsung certificate profile made for this TV
# in its Certificate Manager.
#
#   TIZEN_PROFILE=mytv deploy/tv/package.sh                    # SHLlive.wgt in the repo root
#   TIZEN_PROFILE=mytv TV=192.168.1.30 deploy/tv/package.sh    # and install it on the TV
set -eu

profile=${TIZEN_PROFILE:?set TIZEN_PROFILE to your Samsung certificate profile}
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

cp -R "$root/SHLlive/." "$work/"
# the source picture is not part of the app (its icon is icon.png)
rm -f "$work/SHL live! på mörk bakgrund.png"

tizen package -t wgt -s "$profile" -- "$work"
wgt=$(find "$work" -maxdepth 1 -name '*.wgt' | head -n 1)
if [ -z "$wgt" ]; then
  echo "tizen package made no .wgt" >&2
  exit 1
fi
cp "$wgt" "$root/SHLlive.wgt"
echo "packaged: $root/SHLlive.wgt (version $(sed -n 's/.*<widget[^>]* version="\([^"]*\)".*/\1/p' "$root/SHLlive/config.xml"))"

if [ -n "${TV:-}" ]; then
  sdb connect "$TV"
  tizen install -n "$(basename "$wgt")" -s "$TV:26101" -- "$work"
  echo "installed on $TV"
fi
