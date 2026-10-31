// The TV overlay (docs/TV_APP.md): the delayed TV state from the service, drawn over the
// HDMI picture on the Samsung TV. This is its frame (task 9.2): the connection and synced
// clock, scene changes at their play_at, the TV picture placed per scene (full screen in
// play, the L-frame outside it) and the L-frame's backdrop around the picture. The scenes'
// own graphics come in 9.3; until then each scene shows its name and the score.
import * as clock from "../shared/clock.js";
import { html } from "../shared/format.js";
import * as stage from "../shared/stage.js";
import { Store } from "../shared/store.js";
import { connect } from "../shared/ws.js";
import * as host from "./host.js";
import { BAND, COLUMN, H, W, windowFor } from "./layout.js";

const TITLES = {
  idle: "Vila",
  pregame: "Före matchen",
  live: "Live",
  goal: "Mål",
  intermission: "Periodpaus",
  postgame: "Efter matchen",
};
const FADE_S = 0.3;

const store = new Store();
const debug = new URLSearchParams(location.search).get("debug") === "1";
const url = (path) => new URL(path, import.meta.url).href;
let connection = "connecting";
let scene = null; // the scene shown
let full = false; // the viewer asked for the full picture in an L-frame scene (9.4)
let rect; // where the TV picture is: unknown at start (the shell may keep it from before)
let lastBack = 0;
const log = [];

const el = (tag, cls) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
};
const root = el("div", "tv");
const backdrop = el("div", "tv-backdrop"); // paints around the picture, never over it
const column = el("section", "tv-column");
const band = el("section", "tv-band");
const play = el("section", "tv-play");
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

function place(node, [x, y, w, h]) {
  Object.assign(node.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
}

function fit() {
  root.style.transform = `scale(${Math.min(window.innerWidth / W, window.innerHeight / H)})`;
}

function say(text) {
  toast.textContent = text;
  gsap.killTweensOf(toast);
  gsap.fromTo(toast, { opacity: 1 }, { opacity: 0, delay: 2.5, duration: 0.5 });
}

// ---- the TV picture -------------------------------------------------------------------

/** Move the TV picture for the scene now due; the backdrop follows the same moment. */
async function placePicture(animate) {
  const next = windowFor(scene, full);
  const lframe = !!next;
  gsap.killTweensOf([backdrop, column, band]);
  const to = { opacity: lframe ? 1 : 0, duration: animate ? FADE_S : 0 };
  if (lframe) place(backdrop, next);
  // Going to full screen the backdrop must be gone by the time the picture has grown
  // (45–120 ms on the TV): it would cover it.
  gsap.to([backdrop, column, band], lframe ? to : { ...to, duration: animate ? 0.1 : 0 });
  if (JSON.stringify(next) === JSON.stringify(rect)) return;
  rect = next;
  const result = await host.placeWindow(next);
  if (!result.ok) note(`TV-bilden: ${result.error}`);
}

// ---- scenes (placeholders until 9.3) ----------------------------------------------------

function teamName(side) {
  const t = store.tv?.teams?.[side] ?? {};
  return t.short ?? t.code ?? (side === "home" ? "Hemma" : "Borta");
}

function matchLine() {
  const tv = store.tv;
  if (!tv?.teams?.home?.uuid) return "Ingen match vald";
  const s = tv.score;
  return s ? `${teamName("home")}  ${s.home}–${s.away}  ${teamName("away")}` : `${teamName("home")} – ${teamName("away")}`;
}

function render() {
  const title = TITLES[scene] ?? scene ?? "–";
  column.innerHTML = html`<div class="tv-brand">SHL live!</div><h1>${title}</h1>
    <div class="tv-match">${matchLine()}</div>
    <p class="tv-note">Grafiken för den här scenen kommer i nästa steg (9.3).</p>`;
  band.innerHTML = html`<div class="tv-match">${matchLine()}</div>`;
  play.innerHTML = scene === "goal" ? html`<div class="tv-lower"><span class="tv-chip">MÅL!</span> ${matchLine()}</div>` : "";
}

function show(next, at, animate) {
  if (!TITLES[next?.name]) console.warn("tv: unknown scene", next?.name);
  const name = next?.name ?? "idle";
  if (name !== scene) full = false; // a new scene starts in its own layout
  scene = name;
  render();
  placePicture(animate);
  if (animate) note(`${name} start delta=${(clock.now() - at).toFixed(1)}ms`);
}

// ---- keys (the menu comes in 9.4) ---------------------------------------------------------

host.onKey((key) => {
  note(`key ${key}`);
  if (key === "back") {
    if (Date.now() - lastBack < 2000) return host.exit();
    lastBack = Date.now();
    say("Tryck Back igen för att avsluta");
  }
});

// ---- connection and debug ---------------------------------------------------------------

function feedDot() {
  dot.classList.toggle("on", connection !== "open" || store.config.feed_ok === false);
}

function note(text) {
  log.push(text);
  if (log.length > 6) log.shift();
}

function debugLoop() {
  const c = clock.stats();
  debugBox.textContent = [
    `tv  ${host.mode}  ws ${connection}  offset ${c.offset} ms  rtt ${c.rtt ?? "-"} ms`,
    `rev ${store.tv?.rev ?? "-"}  scene ${scene ?? "-"}  window ${rect ? rect.join(",") : "full"}`,
    ...log,
  ].join("\n");
}

store.on("state", (tv) => show(tv.scene, clock.now(), false));
store.on("scene", (next, playAt) => show(next, playAt, true));
store.on("patch", () => render());
store.on("config", (config) => {
  if (config.tv_probe) location.reload(); // the test page was asked for (tv.js)
  feedDot();
});

async function main() {
  await Promise.all([
    include("link", { rel: "stylesheet", href: url("../shared/tokens.css") }),
    include("link", { rel: "stylesheet", href: url("tv.css") }),
    include("script", { src: url("../vendor/gsap/gsap.min.js") }),
  ]);
  await stage.load(host.base);
  root.append(backdrop, column, band, play, dot, toast);
  if (debug) root.append(debugBox);
  document.body.appendChild(root);
  stage.applyType("tv", root);
  place(column, COLUMN);
  place(band, BAND);
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
