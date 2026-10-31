// The TV overlay (docs/TV_APP.md): the delayed TV state from the service, drawn over the
// HDMI picture on the Samsung TV. It switches scenes at their play_at (one module per
// scene in scenes/), places the TV picture per scene (full screen in play, the L-frame
// outside it, with a backdrop around the picture), plays the team animations (WebP), and
// in play opens the panels on ↑ ↓. The menu on OK comes in 9.4.
import * as clock from "../shared/clock.js";
import { teamVars } from "../shared/components.js";
import { needsOutline, onColor } from "../shared/format.js";
import * as stage from "../shared/stage.js";
import { Store } from "../shared/store.js";
import { connect } from "../shared/ws.js";
import * as anim from "./anim.js";
import * as host from "./host.js";
import { H, W, windowFor } from "./layout.js";
import * as panels from "./panels.js";
import { fitText } from "./scenes/common.js";
import * as goal from "./scenes/goal.js";
import * as idle from "./scenes/idle.js";
import * as intermission from "./scenes/intermission.js";
import * as live from "./scenes/live.js";
import * as postgame from "./scenes/postgame.js";
import * as pregame from "./scenes/pregame.js";

const SCENES = { idle, pregame, live, goal, intermission, postgame };
const FADE_S = 0.3;
const SCENE_FADE_S = 0.4;

const store = new Store();
const debug = new URLSearchParams(location.search).get("debug") === "1";
const url = (path) => new URL(path, import.meta.url).href;
let connection = "connecting";
let current = null; // {name, mod, root, ctx}
let full = false; // the viewer asked for the full picture in an L-frame scene (9.4)
let rect; // where the TV picture is: unknown at start (the shell may keep it from before)
let lastBack = 0;
let ppSide = null;
const goalEvents = new Map(); // goals seen as events at play_at, MÅL! presses included
const introsPlayed = new Set(); // game uuids whose intro has run (once per game)
const log = [];

const el = (tag, cls) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
};
const root = el("div", "tv");
root.id = "app"; // tools/legibility.py measures the text under #app
const backdrop = el("div", "tv-backdrop"); // paints around the picture, never over it
const scenes = el("div", "tv-scenes");
const fx = el("div", "tv-fx"); // the team animations, over the scenes
const dot = el("div", "tv-feed-dot");
const toast = el("div", "tv-toast");
const debugBox = el("pre", "tv-debug");

function include(tag, attrs) {
  return new Promise((resolve, reject) => {
    const node = Object.assign(document.createElement(tag), attrs);
    node.onload = resolve;
    node.onerror = () => reject(new Error(`kunde inte ladda ${attrs.href ?? attrs.src}`));
    document.head.appendChild(node);
  });
}

function fit() {
  root.style.transform = `scale(${Math.min(window.innerWidth / W, window.innerHeight / H)})`;
}

function say(text) {
  toast.textContent = text;
  gsap.killTweensOf(toast);
  gsap.fromTo(toast, { opacity: 1 }, { opacity: 0, delay: 2.5, duration: 0.5 });
}

function note(text) {
  log.push(text);
  if (log.length > 6) log.shift();
}

// ---- teams and animations ---------------------------------------------------------------

const myTeam = (tv) => (tv?.game?.my_side ? tv.teams?.[tv.game.my_side] : null);

function decorate(tv) {
  for (const side of ["home", "away"]) {
    const t = tv.teams?.[side];
    if (!t) continue;
    t.on = onColor(t.color);
    t.outline = needsOutline(t.color);
  }
  teamVars(root, tv.teams);
  for (const side of ["home", "away"]) anim.preload(tv.teams?.[side]?.uuid, ["tvgoal", "tvintro"]);
  anim.preload(myTeam(tv)?.uuid, ["tvpp"]);
}

/** My team's power play has just begun: its animation, in play only (as the wall's bar). */
function powerPlay(tv, playAt) {
  const side = tv?.strength?.pp_side ?? null;
  const started = side && side !== ppSide;
  ppSide = side;
  if (started && side === tv.game?.my_side && ["live", "goal"].includes(current?.name)) {
    anim.play("tvpp", myTeam(tv)?.uuid, playAt, fx, note);
  }
}

/** Puck drop (pregame → live): my team's intro, or the home team's, once per game. */
function intro(tv, playAt) {
  const game = tv.game?.uuid;
  if (!game || introsPlayed.has(game)) return;
  introsPlayed.add(game);
  anim.play("tvintro", (myTeam(tv) ?? tv.teams?.home)?.uuid, playAt, fx, note);
}

// ---- the TV picture -------------------------------------------------------------------

/** Move the TV picture for the scene now due; the backdrop follows the same moment. */
async function placePicture(animate) {
  const next = windowFor(current?.name, full);
  const lframe = !!next;
  gsap.killTweensOf(backdrop);
  if (lframe) Object.assign(backdrop.style, { left: `${next[0]}px`, top: `${next[1]}px`, width: `${next[2]}px`, height: `${next[3]}px` });
  // Going to full screen the backdrop must be gone by the time the picture has grown
  // (45–120 ms on the TV), or it would cover it.
  gsap.to(backdrop, { opacity: lframe ? 1 : 0, duration: animate ? (lframe ? FADE_S : 0.1) : 0 });
  if (rect !== undefined && JSON.stringify(next) === JSON.stringify(rect)) return;
  rect = next;
  const result = await host.placeWindow(next);
  if (!result.ok) note(`TV-bilden: ${result.error}`);
}

// ---- scenes -------------------------------------------------------------------------------

function makeCtx(sceneRoot) {
  return {
    kind: "tv",
    root: sceneRoot,
    get tv() {
      return store.tv;
    },
    get config() {
      return store.config;
    },
    now: clock.now,
    goalEvent: (key) => goalEvents.get(key),
    anim: (kind, side, playAt) => anim.play(kind, store.tv?.teams?.[side]?.uuid, playAt, fx, note),
  };
}

function show(scene, at, animate) {
  const name = SCENES[scene?.name] ? scene.name : "idle";
  if (!SCENES[scene?.name]) console.warn("tv: unknown scene", scene?.name);
  const late = clock.now() - at;
  if (current?.name === "goal" && name === "goal" && scene.data?.linked_from === current.ctx.data?.event_key) {
    current.mod.relink(current.ctx, scene.data); // the feed goal behind a MÅL! press
    return;
  }
  if (current && current.name === name && current.mod.overlay && animate) {
    current.mod.overlay(current.ctx, scene.data ?? {}, at); // a penalty, timeout, …
    note(`${name}/${scene.data?.overlay ?? "-"} delta=${late.toFixed(1)}ms`);
    return;
  }
  if (animate && current?.name === "pregame" && name === "live") intro(store.tv, at);
  if (name !== current?.name) full = false; // a new scene starts in its own layout
  if (!["live", "goal"].includes(name)) panels.close();
  const old = current;
  const sceneRoot = el("div", `tv-scene scene-${name}`);
  scenes.appendChild(sceneRoot);
  const ctx = makeCtx(sceneRoot);
  ctx.animate = animate;
  ctx.previous = old?.name ?? null;
  current = { name, mod: SCENES[name], root: sceneRoot, ctx };
  current.mod.enter(ctx, scene?.data ?? {}, at);
  fitText(sceneRoot);
  if (old) {
    old.mod.exit?.(old.ctx, at);
    if (animate) {
      gsap.to(old.root, { opacity: 0, duration: SCENE_FADE_S, onComplete: () => old.root.remove() });
      gsap.fromTo(sceneRoot, { opacity: 0 }, { opacity: 1, duration: SCENE_FADE_S });
    } else {
      old.root.remove();
    }
  }
  placePicture(animate);
  if (animate) note(`${name} start delta=${late.toFixed(1)}ms`);
}

// ---- keys (the menu on OK comes in 9.4) ----------------------------------------------------

host.onKey((key) => {
  note(`key ${key}`);
  const inPlay = ["live", "goal"].includes(current?.name);
  if ((key === "up" || key === "down") && inPlay) return panels.step(key === "down" ? 1 : -1);
  if (key === "back") {
    if (panels.isOpen()) return panels.close();
    if (Date.now() - lastBack < 2000) return host.exit();
    lastBack = Date.now();
    say("Tryck Back igen för att avsluta");
  }
});

// ---- connection and debug ---------------------------------------------------------------

function feedDot() {
  dot.classList.toggle("on", connection !== "open" || store.config.feed_ok === false);
}

function debugLoop() {
  const c = clock.stats();
  debugBox.textContent = [
    `tv  ${host.mode}  ws ${connection}  offset ${c.offset} ms  rtt ${c.rtt ?? "-"} ms`,
    `rev ${store.tv?.rev ?? "-"}  scene ${current?.name ?? "-"}  window ${rect ? rect.join(",") : "full"}`,
    ...log,
  ].join("\n");
}

store.on("state", (tv) => {
  anim.hide(); // a seek or a reconnect: whatever was playing is no longer due
  introsPlayed.clear();
  ppSide = tv.strength?.pp_side ?? null; // a power play already on is not announced
  decorate(tv);
  show(tv.scene, clock.now(), false);
});
store.on("patch", (patch, playAt) => {
  if (patch.teams || patch.game) decorate(store.tv);
  if (patch.strength) powerPlay(store.tv, playAt);
  current?.mod.update?.(current.ctx, store.tv, patch);
  if (current) fitText(current.root);
  panels.refresh();
});
store.on("scene", (scene, playAt) => show(scene, playAt, true));
store.on("event", (event, playAt, late) => {
  if (event.type === "goal") goalEvents.set(event.key, event);
  current?.mod.onEvent?.(current.ctx, event, playAt, late);
});
store.on("event_update", (event) => current?.mod.onEventUpdate?.(current.ctx, event));
store.on("preload", (event) => {
  // the scorer's portrait before play_at, so the goal scene has it at once
  if (event.type === "goal" && event.player?.id) new Image().src = `${host.base}/assets/players/${event.player.id}.png`;
});
store.on("config", (config) => {
  if (config.tv_probe) location.reload(); // the test page was asked for (tv.js)
  if (store.tv) current?.mod.update?.(current.ctx, store.tv, {});
  feedDot();
});

async function main() {
  await Promise.all([
    include("link", { rel: "stylesheet", href: url("../shared/tokens.css") }),
    include("link", { rel: "stylesheet", href: url("tv.css") }),
    include("script", { src: url("../vendor/gsap/gsap.min.js") }),
  ]);
  gsap.ticker.lagSmoothing(0); // GSAP time equal to wall time, so timelines stay in sync
  gsap.config({ nullTargetWarn: false });
  await stage.load(host.base);
  anim.setBase(host.base);
  root.append(backdrop, scenes, fx, dot, toast);
  panels.create(root, () => store.tv);
  if (debug) root.append(debugBox);
  document.body.appendChild(root);
  stage.applyType("tv", root);
  fit();
  window.addEventListener("resize", fit);
  host.onInfo(() => host.ready());
  host.start();
  setTimeout(feedDot, 5000); // the service may not answer at all
  connect({
    role: "screen",
    id: "tv",
    base: host.base,
    onMessage: (m) => store.handle(m),
    onStatus: (s) => {
      connection = s;
      feedDot();
    },
  });
  if (debug) setInterval(debugLoop, 200);
}

main().catch((err) => {
  document.body.textContent = `TV-grafiken kunde inte starta: ${err}`;
  document.body.style.cssText = "color:#fff;background:#300;font:32px sans-serif;padding:60px";
});
