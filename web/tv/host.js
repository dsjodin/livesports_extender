// Bridge between the TV overlay and the TV app's shell (docs/TV_APP.md, Shell and overlay
// messages). In an iframe the shell is the parent window; imported into the shell itself
// (the fallback mode) it is this same window. Opened in a browser without the shell, the
// keyboard stands in for the remote and moving the TV picture is only pretended.

export const base = new URL(import.meta.url).origin; // the service, in every mode
const inFrame = window.parent !== window;
const peer = inFrame ? window.parent : window;
const handlers = { key: [], info: [], source: [] };
const pending = new Map();
let seq = 0;
let shell = null; // the shell's info once it has answered

/** "iframe", "direct" (imported into the shell) or "browser" (no shell). */
export let mode = "browser";

function send(message) {
  if (mode === "browser") return;
  peer.postMessage({ ...message, to: "shell" }, "*");
}

window.addEventListener("message", (event) => {
  const m = event.data;
  if (!m || m.to !== "overlay" || event.source !== peer) return;
  if (m.t === "info") {
    const first = !shell;
    shell = m;
    mode = m.mode === "direct" ? "direct" : "iframe";
    if (first) handlers.info.forEach((f) => f(m));
  } else if (m.t === "key") handlers.key.forEach((f) => f(m.key, m.code));
  else if (m.t === "source") handlers.source.forEach((f) => f(m));
  else if (m.t === "window_done") {
    pending.get(m.id)?.(m);
    pending.delete(m.id);
  }
});

// The remote on a keyboard, for the browser without the shell.
const KEYBOARD = {
  r: "red", g: "green", y: "yellow", b: "blue", Enter: "ok", Backspace: "back", Escape: "back",
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", " ": "playpause",
};

function browserMode() {
  mode = "browser";
  window.addEventListener("keydown", (event) => {
    const key = KEYBOARD[event.key] ?? (/^[0-9]$/.test(event.key) ? event.key : null);
    if (!key || event.repeat) return;
    event.preventDefault();
    handlers.key.forEach((f) => f(key, event.keyCode));
  });
  handlers.info.forEach((f) => f(null));
}

/** Say hello to the shell; without an answer in 2 s there is none (a plain browser). */
export function start() {
  let tries = 0;
  const hello = () => {
    if (shell) return;
    if (++tries > 8) return browserMode();
    peer.postMessage({ t: "hello", to: "shell" }, "*");
    setTimeout(hello, 250);
  };
  hello();
}

export const onKey = (f) => handlers.key.push(f);
export const onInfo = (f) => handlers.info.push(f);
export const onSource = (f) => handlers.source.push(f);
export const info = () => shell;
let heartbeat = null;
/** "ready" now and every 10 s after: the shell reloads graphics that fall silent. */
export function ready() {
  send({ t: "ready" });
  heartbeat ??= setInterval(() => send({ t: "ready" }), 10_000);
}
export const exit = () => send({ t: "exit" });
export const openSetup = () => send({ t: "setup" });
/** Show the HDMI picture again (a <video> on the TV takes its player from HDMI). */
export const restoreHdmi = () => send({ t: "hdmi" });

/** Place the TV picture: [x, y, w, h] in 1920×1080 pixels, or null for full screen.
 * Resolves with {ok, ms, error?} once the shell has moved it. */
export function placeWindow(rect) {
  if (mode === "browser") return Promise.resolve({ ok: true, ms: 0, preview: true });
  const id = ++seq;
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      resolve({ ok: false, ms: 10000, error: "inget svar från skalet på 10 s" });
    }, 10000);
    pending.set(id, (m) => {
      clearTimeout(timer);
      resolve(m);
    });
    send({ t: "window", id, rect });
  });
}
