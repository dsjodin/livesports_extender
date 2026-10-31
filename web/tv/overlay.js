// The TV overlay (docs/TV_APP.md): the delayed TV state from the service, drawn over the
// HDMI picture on the Samsung TV. It switches scenes at their play_at (one module per
// scene in scenes/), places the TV picture per scene (full screen in play, the L-frame
// outside it, with a backdrop around the picture), plays the team animations (WebP), opens
// the panels on ↑ ↓ in play and the menu on OK (menu.js: MÅL!, Synka, games, settings).
import * as clock from "../shared/clock.js";
import { teamVars } from "../shared/components.js";
import { needsOutline, onColor } from "../shared/format.js";
import * as stage from "../shared/stage.js";
import { Store } from "../shared/store.js";
import { connect } from "../shared/ws.js";
import * as anim from "./anim.js";
import * as host from "./host.js";
import { H, W, windowFor } from "./layout.js";
import * as menu from "./menu.js";
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
const params = new URLSearchParams(location.search);
const debug = params.get("debug") === "1";
const url = (path) => new URL(path, import.meta.url).href;
let connection = "connecting";
let current = null; // {name, mod, root, ctx}
let full = false; // the viewer asked for the full picture in an L-frame scene (menu)
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
const notice = el("div", "tv-notice"); // the shell's own trouble: no HDMI picture
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

function say(text, seconds = 2.5) {
  toast.textContent = text;
  gsap.killTweensOf(toast);
  gsap.fromTo(toast, { opacity: 1 }, { opacity: 0, delay: seconds, duration: 0.5 });
}

/** Once the app has started: what it is doing, so a quiet full picture (in play there is
 * nothing of ours on it) is not taken for a dead app (the user, 2026-10-31). */
const NOW = { pregame: "före matchen", live: "live", goal: "live", intermission: "paus", postgame: "slut", idle: "vila" };
let welcomed = false;
function welcome(tv) {
  if (welcomed) return;
  welcomed = true;
  const t = tv.teams ?? {};
  const game = tv.game?.uuid && t.home ? `Följer ${t.home.code ?? ""}–${t.away?.code ?? ""} · ${NOW[tv.scene?.name] ?? ""}` : "Ingen match vald";
  say(`SHL live! · ${game} · OK öppnar menyn`, 6);
}

/** The service's REST API (docs/PROTOCOL.md); throws with its error detail. */
async function api(path, body, method = "POST") {
  const r = await fetch(`${host.base}/api/${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ?? `HTTP ${r.status}`);
  return data;
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
  if (name !== current?.name) {
    full = false; // a new scene starts in its own layout
    resting = false;
    root.classList.remove("full");
  }
  // a panel lies over the picture in play and in the column in an L-frame: not across that
  if ((windowFor(name) == null) !== (windowFor(current?.name) == null)) panels.close();
  menu.close();
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
  look();
  restLater();
  placePicture(animate);
  if (animate) note(`${name} start delta=${late.toFixed(1)}ms`);
}

// ---- keys: the menu on OK, panels on ↑ ↓, Back (docs/TV_APP.md, Remote) -----------------

host.onKey((key) => {
  note(`key ${key}`);
  restLater();
  if (resting) {
    // the first key only wakes the resting idle L-frame
    resting = false;
    return setFull(false);
  }
  // play/pause is the remote's one free physical key (2026-10-31): a puck-drop sync on one
  // press, at the moment the drop shows on TV
  if (key === "playpause") return menu.syncNow();
  if (menu.key(key)) return;
  if (key === "ok") return menu.open();
  if (key === "up" || key === "down") return panels.step(key === "down" ? 1 : -1);
  if (key === "back") {
    if (panels.isOpen()) return panels.close();
    if (full) return setFull(false);
    if (Date.now() - lastBack < 2000) return host.exit();
    lastBack = Date.now();
    say("Tryck Back igen för att avsluta");
  }
});

/** The full picture in an L-frame scene (the menu's "Helbild"), until Back or the next scene. */
function setFull(on) {
  full = on;
  root.classList.toggle("full", on);
  panels.close(); // it sat in the column, or over the picture: neither holds now
  look();
  placePicture(true);
}

// ---- dimming and the OLED (docs/TV_APP.md, Dimming and the OLED) -------------------------

/** How bright our graphics are, never the TV picture: hidden with the full picture in an
 * L-frame scene, dimmed in idle (config idle_dim, the wall's setting), else full. */
function look() {
  const dim = current?.name === "idle" ? Math.min(Math.max(store.config.idle_dim ?? 0.5, 0), 0.9) : 0;
  const to = full ? 0 : 1 - dim;
  const from = Number(getComputedStyle(scenes).opacity);
  gsap.killTweensOf(scenes);
  gsap.to(scenes, { opacity: to, duration: full ? 0.25 : to < from ? 1.5 : 0.4, ease: "power1.inOut" });
}

/** Idle on an OLED: after 10 min without a key the graphics step aside and the TV gets the
 * whole picture; any key brings the L-frame back (asked for by the user 2026-10-31). */
const REST_MS = (Number(params.get("rest")) || 600) * 1000; // ?rest=<s> to try it
let restTimer = null;
let resting = false;
function restLater() {
  clearTimeout(restTimer);
  if (current?.name !== "idle") return;
  restTimer = setTimeout(() => {
    resting = true;
    setFull(true);
    note("vila: helbild (OLED)");
  }, REST_MS);
}

/** Our graphics move a few pixels every 2 min, so no edge sits on the same pixels for hours. */
const SHIFT = [[0, 0], [3, 0], [3, 3], [0, 3], [-3, 3], [-3, 0], [-3, -3], [0, -3]];
let shiftAt = 0;
function pixelShift() {
  shiftAt = (shiftAt + 1) % SHIFT.length;
  root.style.setProperty("--sx", `${SHIFT[shiftAt][0]}px`);
  root.style.setProperty("--sy", `${SHIFT[shiftAt][1]}px`);
}

// ---- connection and debug ---------------------------------------------------------------

/** No HDMI picture (the box is off, the cable out): say so; the shell keeps looking. */
function hdmi(s) {
  const lost = host.info()?.tv && s && !s.ok;
  notice.textContent = lost ? `Ingen bild från HDMI ${s.hdmi ?? ""} · är boxen på?` : "";
  notice.classList.toggle("on", !!lost);
}

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
  welcome(tv);
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
let boot = null;
store.on("hello", (m) => {
  // the service started again (an update, a restart): load the newest pages
  if (boot && m.boot && m.boot !== boot) location.reload();
  boot = m.boot ?? boot;
});
store.on("config", (config) => {
  if (config.tv_probe) location.reload(); // the test page was asked for (tv.js)
  if (store.tv) current?.mod.update?.(current.ctx, store.tv, {});
  if (current) look(); // a new idle_dim
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
  root.append(backdrop, scenes, fx, dot, toast, notice);
  panels.create(root, () => store.tv, () => windowFor(current?.name, full) != null);
  menu.create(root, {
    tv: () => store.tv,
    scene: () => current?.name,
    api,
    panels,
    say,
    host,
    full: () => full,
    setFull,
    lframe: () => windowFor(current?.name) != null,
  });
  if (debug) root.append(debugBox);
  document.body.appendChild(root);
  stage.applyType("tv", root);
  fit();
  window.addEventListener("resize", fit);
  host.onInfo((info) => {
    host.ready();
    if (info?.source) hdmi(info.source);
  });
  host.onSource(hdmi);
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
  setInterval(pixelShift, (Number(params.get("shift")) || 120) * 1000); // ?shift=<s> to try it
  if (debug) setInterval(debugLoop, 200);
}

main().catch((err) => {
  document.body.textContent = `TV-grafiken kunde inte starta: ${err}`;
  document.body.style.cssText = "color:#fff;background:#300;font:32px sans-serif;padding:60px";
});
