// Team videos (docs/SCREENS.md, Team videos): a goal stinger over the scoring side's
// screen and an intro before puck drop. Silent WebM VP9 with alpha from
// /media/<kind>/<team uuid>.webm; Home Assistant plays the sound. Each portrait screen
// fetches its own team's videos ahead of time (as blobs, so playback never waits on the
// network) and starts one at its play_at on the synced clock; a screen that is late
// starts it that far in, and a team without a video simply shows none.
import { now } from "./clock.js";
import { at } from "./scheduler.js";

const KINDS = ["goal", "intro"];
const fetched = new Set(); // "kind/uuid" asked for
const videos = {}; // kind -> <video>, holding the screen's own team's video
let current = null;

function element(kind) {
  if (!videos[kind]) {
    const video = document.createElement("video");
    video.className = "team-video";
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.addEventListener("ended", () => hide(video));
    video.addEventListener("error", () => hide(video));
    document.body.appendChild(video);
    videos[kind] = video;
  }
  return videos[kind];
}

/** Fetch a team's goal and intro videos and load them, ready to play. */
export function preload(uuid) {
  if (!uuid) return;
  for (const kind of KINDS) {
    const key = `${kind}/${uuid}`;
    if (fetched.has(key)) continue;
    fetched.add(key);
    fetch(`/media/${key}.webm`)
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((blob) => {
        const video = element(kind);
        if (video.dataset.blob) URL.revokeObjectURL(video.dataset.blob);
        video.dataset.blob = URL.createObjectURL(blob);
        video.dataset.team = uuid;
        video.src = video.dataset.blob;
        video.load();
      })
      .catch(() => {}); // no video for this team: nothing is shown
  }
}

/** Play the team's video from play_at ``playAt``; false if it has none (yet). */
export function play(kind, uuid, playAt, log = () => {}) {
  const video = videos[kind];
  if (!video || video.dataset.team !== uuid) return false;
  const token = {};
  current = token;
  const begin = () => {
    if (current !== token) return;
    const late = (now() - playAt) / 1000;
    if (Number.isFinite(video.duration) && late >= video.duration) return hide(video);
    video.currentTime = Math.max(0, late);
    video.style.opacity = "1";
    video.play().catch(() => hide(video));
    log(`[sync] video/${kind} screen=${document.body.dataset.screen} delta=${(late * 1000).toFixed(1)}ms`);
  };
  if (video.readyState >= 2) begin();
  else video.addEventListener("loadeddata", begin, { once: true });
  return true;
}

/** Schedule a video for a later play_at; returns a cancel function. */
export function playLater(kind, uuid, playAt, log) {
  return at(playAt, () => play(kind, uuid, playAt, log));
}

/** Stop and hide one video, or all (a seek or a fresh state). */
export function hide(video) {
  for (const v of video ? [video] : Object.values(videos)) {
    v.pause();
    v.style.opacity = "0";
  }
  if (!video) current = null;
}
