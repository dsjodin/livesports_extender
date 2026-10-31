// The TV's team animations (docs/TV_APP.md, Videos): animated WebP with alpha, never a
// <video> (on the TV a video takes the media player from the HDMI picture). Fetched ahead
// as blobs from /media/<kind>/<uuid>.webp; a team without one simply shows none. An
// animated image cannot be started part way, so a late start plays from the beginning,
// and one later than the whole animation is skipped.
import { now } from "../shared/clock.js";
import { at } from "../shared/scheduler.js";

/** The longest each kind may run (docs/VIDEOS.md); the image is hidden after it. Its last
 * frame is transparent anyway. */
const MAX_S = { tvgoal: 3, tvintro: 6, tvpp: 5 };
const blobs = new Map(); // "kind/uuid" -> Blob, or null when the team has none
const shown = {}; // kind -> <img>
let base = "";

export function setBase(origin) {
  base = origin;
}

/** Fetch a team's animations of ``kinds``, once. */
export function preload(uuid, kinds) {
  if (!uuid) return;
  for (const kind of kinds) {
    const key = `${kind}/${uuid}`;
    if (blobs.has(key)) continue;
    blobs.set(key, null);
    fetch(`${base}/media/${key}.webp`)
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => blobs.set(key, blob))
      .catch(() => {});
  }
}

function element(kind, parent) {
  if (!shown[kind]) {
    const img = document.createElement("img");
    img.className = `tv-anim tv-anim-${kind}`;
    img.alt = "";
    parent.appendChild(img);
    shown[kind] = img;
  }
  return shown[kind];
}

/** Show the team's animation at ``playAt`` on the synced clock, in ``parent``. */
export function play(kind, uuid, playAt, parent, log = () => {}) {
  return at(playAt, () => {
    const blob = blobs.get(`${kind}/${uuid}`);
    const late = (now() - playAt) / 1000;
    if (!blob || late >= MAX_S[kind]) return;
    const img = element(kind, parent);
    if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
    img.dataset.url = URL.createObjectURL(blob); // a new URL starts the animation over
    img.src = img.dataset.url;
    img.style.opacity = "1";
    clearTimeout(img.hideTimer);
    img.hideTimer = setTimeout(() => (img.style.opacity = "0"), (MAX_S[kind] - Math.max(0, late)) * 1000);
    log(`anim ${kind} delta=${(late * 1000).toFixed(1)}ms`);
  });
}

/** Hide everything (a seek or a fresh state). */
export function hide() {
  for (const img of Object.values(shown)) img.style.opacity = "0";
}
