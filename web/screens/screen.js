// Screen bootstrap: connects, keeps the TV state and switches scenes at their play_at.
// left = home team, right = away team, bar = both (docs/SCREENS.md).
import * as clock from "../shared/clock.js";
import * as media from "../shared/media.js";
import { at } from "../shared/scheduler.js";
import { needsOutline, onColor } from "../shared/format.js";
import { teamVars } from "../shared/components.js";
import * as stage from "../shared/stage.js";
import { Store } from "../shared/store.js";
import { connect } from "../shared/ws.js";
import * as idle from "./scenes/idle.js";
import * as pregame from "./scenes/pregame.js";
import * as live from "./scenes/live.js";
import * as goal from "./scenes/goal.js";
import * as intermission from "./scenes/intermission.js";
import * as postgame from "./scenes/postgame.js";

const SCENES = { idle, pregame, live, goal, intermission, postgame };
const FADE_OUT_S = 0.4;

const screenId = document.body.dataset.screen;
const params = new URLSearchParams(location.search);
const debug = params.get("debug") === "1";
const app = document.getElementById("app");
const fx = document.getElementById("fx");
const store = new Store();
const syncLog = [];
let connection = "connecting";
let current = null; // {name, mod, root, ctx}
const goalEvents = new Map(); // goals seen as events at play_at, MÅL! presses included
const introsPlayed = new Set(); // game uuids whose intro has run here (once per game)

gsap.ticker.lagSmoothing(0); // keep GSAP time equal to wall time, so timelines stay in sync
gsap.config({ nullTargetWarn: false }); // scenes animate ".anim" lists that may be empty

function log(line) {
  console.log(line);
  syncLog.push(line);
  if (syncLog.length > 6) syncLog.shift();
}

function decorate(tv) {
  for (const side of ["home", "away"]) {
    const t = tv.teams?.[side];
    if (!t) continue;
    t.on = onColor(t.color);
    t.outline = needsOutline(t.color);
  }
  teamVars(document.documentElement, tv.teams);
  // each portrait screen shows its own team's goal stinger and intro; the bar my team's
  // power-play video
  if (screenId === "bar") media.preload(myTeam(tv)?.uuid, ["pp"]);
  else media.preload(tv.teams?.[screenId === "left" ? "home" : "away"]?.uuid, ["goal", "intro"]);
}

function myTeam(tv) {
  const side = tv?.game?.my_side;
  return side ? tv.teams?.[side] : null;
}

/** My team's power play has just begun (at this patch's play_at): play the bar's video.
 * Not again when it grows to 5 on 3, nothing for the other team's (docs/SCREENS.md). */
let ppSide = null;
function powerPlay(tv, playAt) {
  const side = tv?.strength?.pp_side ?? null;
  const started = side && side !== ppSide;
  ppSide = side;
  if (!started || screenId !== "bar" || side !== tv.game?.my_side) return;
  if (!["live", "goal"].includes(current?.name)) return;
  media.play("pp", myTeam(tv)?.uuid, playAt, log);
}

function makeCtx(root) {
  return {
    screen: screenId,
    kind: screenId === "bar" ? "bar" : "portrait",
    side: screenId === "left" ? "home" : screenId === "right" ? "away" : null,
    root,
    fx,
    get tv() {
      return store.tv;
    },
    get config() {
      return store.config;
    },
    goalEvent: (key) => goalEvents.get(key),
    /** Play this screen's team video (goal or intro) from play_at; false if none. */
    video(kind, playAt, later = false) {
      const uuid = this.side ? store.tv.teams?.[this.side]?.uuid : null;
      if (!uuid) return false;
      if (kind !== "intro") return later ? media.playLater(kind, uuid, playAt, log) : media.play(kind, uuid, playAt, log);
      // the intro runs once per game: at the scheduled start on TV time, or at puck drop
      const game = store.tv.game?.uuid;
      const go = () => !introsPlayed.has(game) && media.play(kind, uuid, playAt, log) && introsPlayed.add(game);
      if (introsPlayed.has(game)) return false;
      if (later) return at(playAt, go);
      go();
      return true;
    },
    now: clock.now,
    log,
  };
}

function show(scene, at, animate) {
  const name = SCENES[scene?.name] ? scene.name : "idle";
  if (!SCENES[scene?.name]) console.warn("unknown scene", scene?.name);
  const late = clock.now() - at;
  if (current?.name === "goal" && name === "goal" && scene.data?.linked_from === current.ctx.data?.event_key) {
    // the feed goal behind a MÅL! press: fill in the scorer, keep the running scene
    current.mod.relink(current.ctx, scene.data);
    log(`[sync] goal/linked screen=${screenId} delta=${late.toFixed(1)}ms`);
    return;
  }
  if (current && current.name === name && current.mod.overlay && animate) {
    current.mod.overlay(current.ctx, scene.data ?? {}, at);
    log(`[sync] ${name}${scene.data?.overlay ? `/${scene.data.overlay}` : ""} screen=${screenId} delta=${late.toFixed(1)}ms`);
    return;
  }
  const old = current;
  const root = document.createElement("div");
  root.className = `scene scene-${name}`;
  app.appendChild(root);
  const ctx = makeCtx(root);
  ctx.animate = animate;
  const mod = SCENES[name];
  ctx.previous = old?.name ?? null;
  current = { name, mod, root, ctx };
  mod.enter(ctx, scene?.data ?? {}, at);
  if (old) {
    old.mod.exit?.(old.ctx, at);
    if (animate) {
      gsap.to(old.root, { opacity: 0, duration: FADE_OUT_S, ease: "power1.out", onComplete: () => old.root.remove() });
      gsap.fromTo(root, { opacity: 0 }, { opacity: 1, duration: FADE_OUT_S, ease: "power1.out" });
    } else {
      old.root.remove();
    }
  }
  if (animate) log(`[sync] ${name} start screen=${screenId} delta=${late.toFixed(1)}ms`);
}

store.on("state", (tv) => {
  media.hide(); // a seek or a reconnect: whatever was playing is no longer due
  introsPlayed.clear();
  ppSide = tv.strength?.pp_side ?? null; // a power play already on is not announced
  decorate(tv);
  show(tv.scene, clock.now(), false);
});
store.on("patch", (patch, playAt) => {
  if (patch.teams || patch.game) decorate(store.tv);
  if (patch.strength) powerPlay(store.tv, playAt);
  current?.mod.update?.(current.ctx, store.tv, patch);
});
store.on("scene", (scene, playAt) => show(scene, playAt, true));
store.on("event", (event, playAt, late) => {
  if (event.type === "goal") goalEvents.set(event.key, event);
  current?.mod.onEvent?.(current.ctx, event, playAt, late);
});
store.on("event_update", (event) => current?.mod.onEventUpdate?.(current.ctx, event));
store.on("preload", (event) => {
  // Fetch the scorer's portrait before play_at so the goal scene has it at once.
  if (event.type === "goal" && event.player?.id) new Image().src = `/assets/players/${event.player.id}.png`;
});
store.on("video", (m) => {
  // a test from /sim or the phone: only the video, on one side or both
  if (m.kind === "pp") {
    // the bar holds my team's video only
    const uuid = myTeam(store.tv)?.uuid;
    if (screenId === "bar" && uuid) at(m.play_at_ms, () => media.play("pp", uuid, m.play_at_ms, log));
    return;
  }
  const side = screenId === "left" ? "home" : screenId === "right" ? "away" : null;
  const uuid = side ? store.tv?.teams?.[side]?.uuid : null;
  if (uuid && (!m.side || m.side === side)) at(m.play_at_ms, () => media.play(m.kind, uuid, m.play_at_ms, log));
});
store.on("config", () => current?.mod.update?.(current.ctx, store.tv, {}));

function debugOverlay() {
  const el = document.createElement("div");
  el.id = "debug";
  document.body.appendChild(el);
  setInterval(() => {
    const c = clock.stats();
    const now = clock.now();
    const upcoming = [...store.upcoming.values()]
      .sort((a, b) => a.playAt - b.playAt)
      .slice(0, 6)
      .map((u) => `  ${((u.playAt - now) / 1000).toFixed(1).padStart(6)} s  ${u.key}`);
    el.textContent = [
      `${screenId}  ws ${connection}  offset ${c.offset} ms  rtt ${c.rtt ?? "-"} ms`,
      `rev ${store.tv?.rev ?? "-"}  scene ${current?.name ?? "-"}  tv offset ${(store.config.offset_ms ?? 0) / 1000} s`,
      ...(screenId === "bar" ? [] : [`video ${media.status()}`]),
      ...upcoming,
      ...syncLog,
    ].join("\n");
  }, 200);
}

async function main() {
  await stage.load();
  await document.fonts.ready;
  if (debug) debugOverlay();
  connect({
    role: "screen",
    id: screenId,
    onMessage: (m) => store.handle(m),
    onStatus: (s) => {
      connection = s;
    },
  });
}

main();
