// The TV app in /sim (docs/TV_APP.md): the overlay /tv/ in a 16:9 frame over a stand-in
// for the HDMI picture. The simulator plays the shell: it answers the overlay's messages
// ({to: "shell"}), moves the stand-in picture where the overlay asks, a moment later as on
// the TV (45–120 ms), and sends the remote's keys.
import { H, W } from "../tv/layout.js";

const MOVE_MS = 60;
const KEYS = [
  ["up", "↑"], ["down", "↓"], ["left", "←"], ["right", "→"], ["ok", "OK"], ["back", "Back"],
  ["playpause", "⏯"], ["ChannelUp", "CH+"], ["ChannelDown", "CH−"],
];
const KEYBOARD = {
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "ok",
  Backspace: "back", Escape: "back", " ": "playpause", PageUp: "ChannelUp", PageDown: "ChannelDown",
};

let view = null;
let iframe = null;
let picture = null;
let stageEl = null;
let screenEl = null;
let debug = false;

const send = (message) => iframe?.contentWindow?.postMessage({ ...message, to: "overlay" }, location.origin);

export function build(container, debugOn) {
  debug = debugOn;
  view = document.createElement("div");
  view.id = "tvview";
  view.className = "hidden";
  view.innerHTML = `<div class="tv-screen"><div class="tv-stage">
      <div class="tv-picture"><div class="tv-bug">TV <b class="tv-bug-clock">–</b></div>
        <span class="tv-picture-label">TV-BILD · HDMI 1</span></div>
      <iframe title="tv" width="${W}" height="${H}"></iframe>
    </div></div>
    <div class="tv-remote">${KEYS.map(([k, label]) => `<button data-key="${k}">${label}</button>`).join("")}
      <span class="muted">Keyboard: arrows, Enter, Backspace, space, PgUp/PgDn</span></div>`;
  container.appendChild(view);
  stageEl = view.querySelector(".tv-stage");
  screenEl = view.querySelector(".tv-screen");
  picture = view.querySelector(".tv-picture");
  iframe = view.querySelector("iframe");
  view.querySelector(".tv-remote").onclick = (e) => {
    const key = e.target.closest("[data-key]")?.dataset.key;
    if (key) send({ t: "key", key });
  };
  window.addEventListener("message", onMessage);
  window.addEventListener("keydown", (e) => {
    if (view.classList.contains("hidden") || e.target.closest("input, select, textarea")) return;
    const key = KEYBOARD[e.key];
    if (!key || e.repeat) return;
    e.preventDefault();
    send({ t: "key", key });
  });
  new ResizeObserver(layout).observe(container);
  setInterval(() => {
    // the stand-in broadcast's clock: the Fake TV pane's (raw events at the fake delay)
    view.querySelector(".tv-bug-clock").textContent = document.getElementById("tv-clock")?.textContent ?? "–";
  }, 250);
}

function onMessage(event) {
  const m = event.data;
  if (!m || m.to !== "shell" || event.source !== iframe?.contentWindow) return;
  if (m.t === "hello") {
    send({ t: "info", version: "sim", tv: false, sim: true, mode: "iframe", hdmi: 1, source: { hdmi: 1, ok: true, error: null } });
  } else if (m.t === "window") {
    setTimeout(() => {
      placePicture(m.rect);
      send({ t: "window_done", id: m.id, ok: true, ms: MOVE_MS, error: null, preview: true });
    }, MOVE_MS);
  } else if (m.t === "exit") {
    flash("The app would exit now (Back twice).");
  } else if (m.t === "setup") {
    flash("The app would open its settings now.");
  } else if (m.t === "hdmi") {
    flash("The app would show HDMI again now.");
  }
}

function placePicture(rect) {
  const [x, y, w, h] = rect ?? [0, 0, W, H];
  Object.assign(picture.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
}

function flash(text) {
  const note = view.querySelector(".tv-remote .muted");
  note.textContent = text;
  setTimeout(() => (note.textContent = "Keyboard: arrows, Enter, Backspace, space, PgUp/PgDn"), 3000);
}

function layout() {
  if (!view || view.classList.contains("hidden")) return;
  const remote = view.querySelector(".tv-remote").offsetHeight + 16;
  const scale = Math.min((view.clientWidth - 48) / W, (view.clientHeight - remote - 48) / H);
  screenEl.style.width = `${W * scale}px`;
  screenEl.style.height = `${H * scale}px`;
  stageEl.style.transform = `scale(${scale})`;
}

/** Show the TV (true) or the wall (false). The TV page loads when first shown. */
export function show(on) {
  view.classList.toggle("hidden", !on);
  if (on && !iframe.src) reload();
  layout();
}

export function reload(debugOn = debug) {
  debug = debugOn;
  placePicture(null);
  iframe.src = `/tv/${debug ? "?debug=1" : ""}`;
}

export const visible = () => view && !view.classList.contains("hidden");
