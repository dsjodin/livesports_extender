// The TV app's test page (docs/TV_APP.md, task 9.1): checks on the real TV what the
// overlay needs (transparency over HDMI, the service over HTTP and WebSocket, the synced
// clock, smooth animation, VP9 with alpha, moving the TV picture, the remote's keys) and
// reports it to the service (POST /api/tv/probe; read it at GET /api/tv/probe). Run with
// the arrows, OK and Back only (the remote has no digits, 2026-10-31): ↑ ↓ and OK in the
// menu, ← nej / → ja to the questions only a person can answer.
import * as clock from "../shared/clock.js";
import { connect } from "../shared/ws.js";
import * as host from "./host.js";

const W = 1920;
const H = 1080;
const MY_TEAM = "82eb-82ebmgaJ8"; // the video's team when no game is selected
const RECTS = {
  full: null,
  lframe: [0, 0, 1152, 648], // 60 % top left, the L-frame of docs/TV_APP.md
  small: [1220, 60, 640, 360],
};
const RECT_NAMES = { full: "helbild", lframe: "L-ram", small: "liten bild" };
const RECT_ORDER = ["lframe", "small", "full"];
const QUESTIONS = {
  clip_started: "Startade videon av sig själv och syntes i helbild?",
  clip_sound: "Hördes videons ljud (i soundbaren)?",
  volume_steps: "Sänktes soundbarens volym tre steg och kom sedan tillbaka?",
  sound_heard: "Hördes hornet (Web Audio)?",
  sound_hdmi: "Hördes TV-sändningens ljud samtidigt, och låg bilden kvar?",
  audio_heard: "Hördes hornet (<audio>)?",
  volume: "Sänktes TV:ns volym en stund och kom sedan tillbaka?",
  mute_heard: "Med TV:n tystad: hördes hornet ändå?",
  transparent: "Syns TV-bilden genom rutorna 0–75 % till höger?",
  smooth: "Glider pucken mjukt, utan hack?",
  webp: "Var animationen genomskinlig och mjuk, med TV-bilden kvar runt den?",
  video: "Var videon genomskinlig, syntes TV-bilden runt den?",
  hdmi_back: "Kom TV-bilden och ljudet tillbaka efter videon?",
  flash: "Blev bilden svart eller blinkade den när den flyttades?",
};
const REPEATABLE = ["clip_started", "clip_sound", "volume_steps", "webp", "video", "hdmi_back", "flash", "sound_heard", "sound_hdmi", "audio_heard", "volume", "mute_heard"];

const url = (path) => new URL(path, import.meta.url).href;
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

const report = {
  probe: 1,
  started_ms: null,
  mode: null,
  shell: null,
  source: null,
  env: {},
  http: null,
  ws: { state: "connecting", opens: 0, closes: 0 },
  clock: null,
  fps: null,
  video: { can_play_vp9: null, runs: [] },
  webp: { runs: [] },
  sound: {},
  moves: [],
  answers: {},
  keys: {},
  errors: [],
};
let state = null; // the TV state from the service, for a team uuid
const asked = [];
let question = null;
let lastBack = 0;
let menuAt = 0;
let nextRect = 0;

window.addEventListener("error", (e) => report.errors.push(String(e.message).slice(0, 200)));

function load(tag, attrs) {
  return new Promise((resolve, reject) => {
    const node = Object.assign(document.createElement(tag), attrs);
    node.onload = resolve;
    node.onerror = () => reject(new Error(`kunde inte ladda ${attrs.href ?? attrs.src}`));
    document.head.appendChild(node);
  });
}

// ---- layout ----------------------------------------------------------------------------

const root = el("div", "tvp");
root.id = "tv-root";
const outline = el("div", "tvp-outline");
const panel = el("section", "tvp-panel");
const rows = el("div", "tvp-rows");
const keylog = el("div", "tvp-keys");
const side = el("section", "tvp-side");
const bottom = el("section", "tvp-bottom");
const prompt = el("div", "tvp-question");
const legend = el("div", "tvp-legend", "↑ ↓ välj · OK kör · ← → svara på frågan · Back två gånger avslutar");
const menu = el("div", "tvp-menu");
const anim = el("img", "tvp-anim");
const toast = el("div", "tvp-toast");
const video = el("video", "tvp-video");
video.muted = true;
video.playsInline = true;

const ROWS = [
  ["shell", "Skal"],
  ["source", "HDMI"],
  ["http", "Server (HTTP)"],
  ["ws", "WebSocket"],
  ["clock", "Klocka"],
  ["fps", "Animation"],
  ["webp", "Animerad bild"],
  ["sound", "Ljud"],
  ["clip", "Höjdpunkt (video)"],
  ["video", "Video VP9 alfa"],
  ["move", "Flytta TV-bilden"],
  ["keys", "Fjärrkontroll"],
  ["env", "Skärm"],
];
const cells = {};
const MENU = [
  ["webp", "Spela animerad bild (WebP)"],
  ["video", "Spela video (kan bryta HDMI)"],
  ["move", "Flytta TV-bilden"],
  ["hdmi", "Återställ HDMI-bilden"],
  ["sound_web", "Ljud: horn via Web Audio"],
  ["sound_el", "Ljud: horn via <audio> (kan bryta HDMI)"],
  ["sound_vol", "Ljud: sänk TV:ns volym en stund"],
  ["sound_mute", "Ljud: tysta TV:n och spela horn"],
  ["sound_steps", "Ljud: volym 3 steg ner och upp (som fjärren)"],
  ["clip_goal", "Video: målklipp FHC–SKE (22 s)"],
  ["clip_long", "Video: höjdpunkter FHC–SKE (5 min)"],
  ["send", "Skicka rapport"],
  ["setup", "Inställningar"],
  ["hide", "Dölj testbilden"],
  ["graphics", "Tillbaka till grafiken"],
];

function renderMenu() {
  [...menu.children].forEach((item, i) => item.classList.toggle("on", i === menuAt));
  menu.children[menuAt]?.scrollIntoView({ block: "nearest" });
  const move = menu.querySelector('[data-id="move"]');
  if (move) move.textContent = `Flytta TV-bilden: ${RECT_NAMES[RECT_ORDER[nextRect]]}`;
}

function build() {
  panel.append(el("h1", null, "SHL live! · Test av TV:n"));
  for (const [key, label] of ROWS) {
    const row = el("div", "tvp-row");
    const dot = el("span", "tvp-dot");
    const value = el("span", "tvp-value", "…");
    row.append(dot, el("span", "tvp-label", label), value);
    rows.append(row);
    cells[key] = { row, value };
  }
  panel.append(rows, el("h2", null, "Senaste knappar"), keylog);

  // transparency: white, black and gold at 0–100 %
  const alpha = el("div", "tvp-alpha");
  alpha.append(el("div", "tvp-alpha-head", "Genomskinlighet"));
  for (const [name, rgb] of [["Vit", "255,255,255"], ["Svart", "0,0,0"], ["Guld", "245,197,66"]]) {
    const line = el("div", "tvp-alpha-line");
    line.append(el("span", "tvp-alpha-name", name));
    for (const a of [0, 25, 50, 75, 100]) {
      const cell = el("span", "tvp-alpha-cell", `${a} %`);
      cell.style.background = `rgba(${rgb},${a / 100})`;
      if (name !== "Svart" && a >= 50) cell.style.color = "#111";
      line.append(cell);
    }
    alpha.append(line);
  }

  const lane = el("div", "tvp-lane");
  lane.append(el("div", "tvp-puck"));
  const time = el("div", "tvp-clock");
  time.append(el("span", "tvp-time", "--:--:--.---"), el("span", "tvp-second"));
  for (const [id, label] of MENU) {
    const item = el("div", "tvp-item", label);
    item.dataset.id = id;
    menu.append(item);
  }
  side.append(alpha, lane, time, menu);
  renderMenu();

  bottom.append(prompt, legend);
  root.append(outline, video, anim, panel, side, bottom, toast);
  document.body.appendChild(root);
}

function fit() {
  const scale = Math.min(window.innerWidth / W, window.innerHeight / H);
  root.style.transform = `scale(${scale})`;
}

function set(key, text, status = "ok") {
  cells[key].value.textContent = text;
  cells[key].row.dataset.status = status; // ok | bad | wait | ask
}

function say(text) {
  toast.textContent = text;
  gsap.killTweensOf(toast);
  gsap.fromTo(toast, { opacity: 1 }, { opacity: 0, delay: 3, duration: 0.6 });
}

// ---- questions (← nej, → ja) -------------------------------------------------------------

function ask(id) {
  if (report.answers[id] !== undefined && !REPEATABLE.includes(id)) return;
  if (!asked.includes(id)) asked.push(id);
  next();
}

function next() {
  question = asked.find((id) => report.answers[id] === undefined) ?? null;
  prompt.textContent = question ? `${QUESTIONS[question]}   ← Nej · Ja →` : "";
  prompt.classList.toggle("on", !!question);
}

function answer(yes) {
  if (!question) return;
  report.answers[question] = yes;
  say(`Svar sparat: ${yes ? "ja" : "nej"}`);
  next();
  send();
}

// ---- checks ---------------------------------------------------------------------------

/** "Chrome 141.0…"; Tizen writes its Chromium version bare ("… 120.0.6099.5/9.0 TV …"). */
function browserName(ua) {
  const named = ua.match(/(SamsungBrowser|Chrome|Chromium)\/([\d.]+)/);
  if (named) return `${named[1]} ${named[2]}`;
  const tizen = ua.match(/\b(\d{2,3}\.\d+\.\d+\.\d+)\/[\d.]+ TV\b/);
  return tizen ? `Chromium ${tizen[1]}` : null;
}

function env() {
  const ua = navigator.userAgent;
  report.env = {
    user_agent: ua,
    browser: browserName(ua),
    inner: [window.innerWidth, window.innerHeight],
    screen: [screen.width, screen.height],
    dpr: window.devicePixelRatio,
  };
  set("env", `${window.innerWidth}×${window.innerHeight}, dpr ${window.devicePixelRatio}, ${report.env.browser ?? "okänd webbläsare"}`);
}

async function http() {
  const t0 = performance.now();
  try {
    const r = await fetch(`${host.base}/api/health`, { cache: "no-store" });
    const body = await r.json();
    const ms = Math.round(performance.now() - t0);
    report.http = { ok: r.ok, ms, version: body.version };
    set("http", `${host.base} svarar på ${ms} ms (version ${body.version})`);
  } catch (err) {
    report.http = { ok: false, error: String(err) };
    set("http", `${host.base}: ${err}`, "bad");
  }
}

function socket() {
  connect({
    role: "screen",
    id: "tv",
    base: host.base,
    onMessage: (m) => {
      if (m.t === "state") state = m.state;
      // the graphics were asked for again (tv.js picks the page)
      if ((m.t === "hello" || m.t === "config") && m.config.tv_probe === false) location.reload();
    },
    onStatus: (s) => {
      report.ws.state = s;
      if (s === "open") report.ws.opens++;
      else report.ws.closes++;
      set("ws", s === "open" ? `ansluten (${report.ws.opens} gånger)` : "frånkopplad, försöker igen", s === "open" ? "ok" : "bad");
    },
  });
}

const offsets = [];
function clockCheck() {
  const s = clock.stats();
  if (s.samples) offsets.push(s.offset);
  if (offsets.length > 30) offsets.shift();
  const drift = offsets.length ? Math.max(...offsets) - Math.min(...offsets) : null;
  report.clock = { ...s, drift_ms: drift };
  if (!s.samples) return set("clock", "väntar på svar", "wait");
  const good = s.rtt != null && s.rtt < 60 && (drift ?? 0) < 20;
  set("clock", `avvikelse ${s.offset} ms · rtt ${s.rtt} ms · drift ${drift} ms (${s.samples} prov)`, good ? "ok" : "bad");
}

// frame times over the last 5 s while the puck glides
const frames = [];
let lastFrame = null;
function frame(t) {
  if (lastFrame != null) frames.push([t, t - lastFrame]);
  lastFrame = t;
  while (frames.length && frames[0][0] < t - 5000) frames.shift();
  const now = clock.now();
  const d = new Date(now);
  const pad = (n, w = 2) => String(n).padStart(w, "0");
  root.querySelector(".tvp-time").textContent =
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
  root.querySelector(".tvp-second").style.opacity = now % 1000 < 120 ? "1" : "0";
  requestAnimationFrame(frame);
}
function fpsCheck() {
  if (frames.length < 10) return set("fps", "mäter…", "wait");
  const deltas = frames.map((f) => f[1]);
  const fps = (deltas.length / deltas.reduce((a, b) => a + b, 0)) * 1000;
  const worst = Math.max(...deltas);
  report.fps = { fps: Math.round(fps * 10) / 10, worst_ms: Math.round(worst) };
  set("fps", `${report.fps.fps} bilder/s, längsta paus ${report.fps.worst_ms} ms`, fps >= 55 && worst < 50 ? "ok" : "bad");
}

const NAV = ["up", "down", "left", "right", "ok", "back"];
function keysCheck(key, code) {
  report.keys[key] = code ?? true;
  const line = el("div", null, `${key}${code ? ` (${code})` : ""}`);
  keylog.prepend(line);
  while (keylog.children.length > 6) keylog.lastChild.remove();
  const nav = NAV.filter((k) => report.keys[k]).length;
  const other = Object.keys(report.keys).filter((k) => !NAV.includes(k));
  set("keys", `pilar, OK, Back ${nav}/6 · andra: ${other.join(", ") || "inga än"}`, nav === 6 ? "ok" : "wait");
}

async function playVideo() {
  const uuid = state?.teams?.home?.uuid ?? MY_TEAM;
  const run = { team: uuid, kind: "pp" };
  report.video.runs.push(run);
  set("video", "hämtar video…", "wait");
  try {
    const r = await fetch(`${host.base}/media/pp/${uuid}.webm`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const blob = await r.blob();
    if (video.dataset.blob) URL.revokeObjectURL(video.dataset.blob);
    video.dataset.blob = URL.createObjectURL(blob);
    video.src = video.dataset.blob;
    video.style.opacity = "1";
    await video.play();
    run.started = true;
    set("video", "spelar…", "wait");
  } catch (err) {
    run.error = String(err);
    video.style.opacity = "0";
    set("video", `fel: ${err}`, "bad");
    send();
  }
}

video.addEventListener("ended", () => {
  const run = report.video.runs.at(-1);
  const q = video.getVideoPlaybackQuality?.();
  if (q) Object.assign(run, { frames: q.totalVideoFrames, dropped: q.droppedVideoFrames });
  run.duration_s = Math.round(video.duration * 100) / 100;
  video.style.opacity = "0";
  set("video", `spelad: ${run.frames ?? "?"} bilder, ${run.dropped ?? "?"} tappade`, (run.dropped ?? 0) < 5 ? "ask" : "bad");
  report.answers.video = undefined;
  ask("video");
  restoreHdmi();
  send();
});
video.addEventListener("error", () => {
  const run = report.video.runs.at(-1);
  if (run) run.error = `media error ${video.error?.code}`;
  video.style.opacity = "0";
  set("video", `kan inte spela: fel ${video.error?.code}`, "bad");
  restoreHdmi();
});

/** A <video> took the TV's player from HDMI (seen 2026-10-31): ask the shell to show
 * HDMI again, then ask whether picture and sound came back. */
function restoreHdmi() {
  video.removeAttribute("src");
  video.load();
  host.restoreHdmi();
  report.answers.hdmi_back = undefined;
  ask("hdmi_back");
}

// ---- sound (2026-10-31): what the TV allows decides the user's ideas for sound ----------

const askAgain = (...ids) => ids.forEach((id) => ((report.answers[id] = undefined), ask(id)));
let audioCtx = null;

/** The horn through Web Audio (the page's own mixer, perhaps beside the HDMI sound). */
async function playWebAudio(label, questions) {
  const run = { at_ms: Date.now() };
  report.sound[label] = run;
  try {
    audioCtx ??= new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") await audioCtx.resume().catch(() => {});
    run.state = audioCtx.state; // "suspended": the TV wants a user gesture first
    const data = await (await fetch(url("test/horn.wav"))).arrayBuffer();
    const buffer = await audioCtx.decodeAudioData(data);
    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(audioCtx.destination);
    source.start();
    run.started = true;
    set("sound", `Web Audio spelar (${audioCtx.state})`, "ask");
    await new Promise((resolve) => setTimeout(resolve, buffer.duration * 1000 + 300));
    run.state_after = audioCtx.state;
    if (questions) askAgain(...questions);
  } catch (err) {
    run.error = String(err);
    set("sound", `Web Audio: ${err}`, "bad");
  }
  send();
  return run;
}

/** The horn through an <audio> element: may take the media player from HDMI, as <video>. */
async function playAudioElement() {
  const run = { at_ms: Date.now() };
  report.sound.element = run;
  const audio = new Audio(url("test/horn.wav"));
  try {
    await audio.play();
    run.started = true;
    set("sound", "<audio> spelar", "ask");
    await new Promise((resolve) => audio.addEventListener("ended", resolve, { once: true }));
  } catch (err) {
    run.error = String(err);
    set("sound", `<audio>: ${err}`, "bad");
  }
  audio.removeAttribute("src");
  audio.load();
  askAgain("audio_heard");
  restoreHdmi(); // and asks whether picture and sound came back
  send();
}

/** The TV's volume down 5 steps for 3 s, then back (the shell, 1.1.0). */
async function volumeTest() {
  const run = {};
  report.sound.volume = run;
  const before = await host.audio("get");
  run.before = before;
  if (!before.ok) {
    set("sound", `Volym: ${before.error}`, "bad");
    return send();
  }
  run.lowered = await host.audio("volume", Math.max(0, before.volume - 5));
  set("sound", `Volym ${before.volume} → ${run.lowered.volume ?? "?"} i 3 s`, "ask");
  await new Promise((resolve) => setTimeout(resolve, 3000));
  run.restored = await host.audio("volume", before.volume);
  askAgain("volume");
  send();
}

// ---- highlights (2026-10-31): a test before anything is built ------------------------------
// shl.se lists each game's clips (/api/media/videos-for-game) with a public embed of the
// video provider's own player; these two are from Frölunda–Skellefteå (2026-10-17). The
// player plays in an iframe over everything; its end cannot be seen from here, so it
// closes after the clip's length (or on Back), and HDMI is asked back.
const CLIPS = {
  clip_goal: { id: "661877", seconds: 22, name: "målklipp" },
  clip_long: { id: "661916", seconds: 307, name: "höjdpunkter" },
};
let clipFrame = null;
let clipTimer = null;

function playClip(key) {
  const c = CLIPS[key];
  closeClip(false);
  const run = { id: c.id, at_ms: Date.now() };
  (report.clips ??= []).push(run);
  clipFrame = document.createElement("iframe");
  clipFrame.className = "tvp-clip";
  clipFrame.allow = "autoplay; fullscreen; encrypted-media";
  clipFrame.src = `https://embed.staylive.tv/video/${c.id}?autoplay=1`;
  clipFrame.onload = () => (run.loaded_ms = Date.now() - run.at_ms);
  root.appendChild(clipFrame);
  set("clip", `spelar ${c.name} · Back stänger`, "ask");
  clipTimer = setTimeout(() => closeClip(true), (c.seconds + 3) * 1000);
}

function closeClip(asked) {
  clearTimeout(clipTimer);
  if (!clipFrame) return;
  clipFrame.remove();
  clipFrame = null;
  set("clip", "spelad", "ask");
  host.restoreHdmi(); // the video took the TV's player from HDMI
  if (asked !== false) askAgain("clip_started", "clip_sound", "hdmi_back");
  send();
}

/** Three steps down, 3 s, three steps up, as the remote's volume keys (shell 1.2.0): the
 * remote reaches the soundbar over HDMI-CEC; perhaps these do too. */
async function stepsTest() {
  const run = { down: [], up: [] };
  report.sound.steps = run;
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  for (let i = 0; i < 3; i++) {
    run.down.push(await host.audio("down"));
    await pause(400);
  }
  const first = run.down[0];
  if (!first?.ok) {
    set("sound", `Volymsteg: ${first?.error ?? "inget svar"}`, "bad");
    return send();
  }
  set("sound", `Volym 3 steg ner (${first.volume} → ${run.down.at(-1).volume}), upp om 3 s`, "ask");
  await pause(3000);
  for (let i = 0; i < 3; i++) {
    run.up.push(await host.audio("up"));
    await pause(400);
  }
  askAgain("volume_steps");
  send();
}

/** The TV muted, the horn through Web Audio, then the mute back as it was. */
async function muteTest() {
  const run = {};
  report.sound.mute = run;
  const before = await host.audio("get");
  run.before = before;
  if (!before.ok) {
    set("sound", `Tysta: ${before.error}`, "bad");
    return send();
  }
  run.muted = await host.audio("mute", true);
  await playWebAudio("muted", null);
  run.restored = await host.audio("mute", before.muted);
  askAgain("mute_heard");
  send();
}

// Animated WebP: an image, so it should not need the TV's video player.
async function playWebp() {
  const run = { file: "test/pp.webp" };
  report.webp.runs.push(run);
  set("webp", "hämtar…", "wait");
  const t0 = performance.now();
  try {
    const r = await fetch(url("test/pp.webp"));
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const blob = await r.blob();
    run.kb = Math.round(blob.size / 1024);
    if (anim.dataset.blob) URL.revokeObjectURL(anim.dataset.blob);
    anim.dataset.blob = URL.createObjectURL(blob); // a new URL starts the animation over
    anim.src = anim.dataset.blob;
    await anim.decode();
    run.decode_ms = Math.round(performance.now() - t0);
    const start = performance.now();
    anim.style.opacity = "1";
    set("webp", `spelar (${run.kb} kB, klar på ${run.decode_ms} ms)…`, "wait");
    setTimeout(() => {
      anim.style.opacity = "0";
      const deltas = frames.filter((f) => f[0] >= start).map((f) => f[1]);
      run.worst_ms = deltas.length ? Math.round(Math.max(...deltas)) : null;
      set("webp", `spelad: ${run.kb} kB, längsta paus ${run.worst_ms} ms`, "ask");
      report.answers.webp = undefined;
      ask("webp");
      send();
    }, 4200);
  } catch (err) {
    run.error = String(err);
    set("webp", `fel: ${err}`, "bad");
    send();
  }
}

async function move(name) {
  const rect = RECTS[name];
  set("move", `flyttar till ${RECT_NAMES[name]}…`, "wait");
  drawOutline(rect);
  const result = await host.placeWindow(rect);
  report.moves.push({ to: name, ok: result.ok, ms: Math.round(result.ms ?? 0), error: result.error ?? null });
  if (!result.ok) set("move", `${RECT_NAMES[name]}: ${result.error}`, "bad");
  else set("move", `${RECT_NAMES[name]} på ${Math.round(result.ms)} ms${result.preview ? " (förhandsvisning)" : ""}`, "ask");
  if (result.ok && name !== "full") {
    report.answers.flash = undefined;
    ask("flash");
  }
  send();
}

function drawOutline(rect) {
  const [x, y, w, h] = rect ?? [0, 0, W, H];
  Object.assign(outline.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
  outline.classList.toggle("full", !rect);
}

// ---- report ---------------------------------------------------------------------------

let sendTimer = null;
function send(now = false) {
  clearTimeout(sendTimer);
  sendTimer = setTimeout(async () => {
    try {
      const r = await fetch(`${host.base}/api/tv/probe`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...report, sent_ms: clock.now() }),
      });
      if (now) say(r.ok ? "Rapport skickad till servern" : `Rapporten gick inte fram: HTTP ${r.status}`);
    } catch (err) {
      if (now) say(`Rapporten gick inte fram: ${err}`);
    }
  }, now ? 0 : 500);
}

/** Back to the graphics: the service's setting; the page reloads on its config message. */
async function leave() {
  send(true);
  try {
    const r = await fetch(`${host.base}/api/tv/probe-mode`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
    if (!r.ok) say(`Gick inte: HTTP ${r.status}`);
  } catch (err) {
    say(`Gick inte: ${err}`);
  }
}

// ---- keys -----------------------------------------------------------------------------

function run(id) {
  if (id === "webp") return playWebp();
  if (id === "video") return playVideo();
  if (id === "move") {
    const name = RECT_ORDER[nextRect];
    nextRect = (nextRect + 1) % RECT_ORDER.length;
    renderMenu();
    return move(name);
  }
  if (id === "hdmi") return host.restoreHdmi();
  if (id === "sound_web") return playWebAudio("webaudio", ["sound_heard", "sound_hdmi"]);
  if (id === "sound_el") return playAudioElement();
  if (id === "sound_vol") return volumeTest();
  if (id === "sound_mute") return muteTest();
  if (id === "sound_steps") return stepsTest();
  if (id === "clip_goal" || id === "clip_long") return playClip(id);
  if (id === "send") return send(true);
  if (id === "setup") return host.openSetup();
  if (id === "graphics") return leave();
  if (id === "hide") root.classList.add("hidden");
}

host.onKey((key, code) => {
  keysCheck(key, code);
  if (clipFrame) return key === "back" ? closeClip(true) : undefined; // the video has the screen
  if (root.classList.contains("hidden")) return root.classList.remove("hidden");
  if (key === "left") return answer(false);
  if (key === "right") return answer(true);
  if (key === "up" || key === "down") {
    menuAt = (menuAt + (key === "up" ? MENU.length - 1 : 1)) % MENU.length;
    return renderMenu();
  }
  if (key === "ok") return run(MENU[menuAt][0]);
  if (key === "back") {
    if (Date.now() - lastBack < 2000) return host.exit();
    lastBack = Date.now();
    say("Tryck Back igen för att avsluta");
  }
});

host.onInfo((info) => {
  report.mode = host.mode;
  report.shell = info;
  const names = { iframe: "iframe", direct: "direkt (reservläge)", browser: "webbläsare utan skal" };
  if (!info) set("shell", names.browser, "wait");
  else set("shell", `${names[host.mode]} · skal ${info.version} · ${info.tv ? `TV ${info.model ?? ""} Tizen ${info.platform ?? "?"}` : "förhandsvisning på dator"}`);
  if (!info?.tv) set("source", info ? "ingen HDMI på dator" : "-", "wait");
  if (info?.source) showSource(info.source);
  if (info) host.placeWindow(null); // the full picture, wherever the graphics had put it
  host.ready();
  send();
});

function showSource(s) {
  report.source = s;
  if (s.ok) set("source", `HDMI ${s.hdmi} visas`);
  else set("source", `HDMI ${s.hdmi ?? "?"}: ${s.error ?? "ingen bild"}`, "bad");
}
host.onSource(showSource);

// ---- start ----------------------------------------------------------------------------

async function main() {
  await Promise.all([
    load("link", { rel: "stylesheet", href: url("../shared/tokens.css") }),
    load("link", { rel: "stylesheet", href: url("probe.css") }),
    load("script", { src: url("../vendor/gsap/gsap.min.js") }),
  ]);
  report.started_ms = Date.now();
  build();
  fit();
  window.addEventListener("resize", fit);
  drawOutline(null);
  env();
  host.start();
  report.video.can_play_vp9 = video.canPlayType('video/webm; codecs="vp9"') || "nej";
  set("webp", "välj i menyn till höger", "wait");
  set("sound", "välj i menyn (Ljud: …)", "wait");
  set("clip", "välj i menyn (Video: …)", "wait");
  set("video", `stöd: ${report.video.can_play_vp9} · välj i menyn (kan bryta HDMI)`, "wait");
  set("move", "välj i menyn", "wait");
  set("keys", "tryck på alla knappar fjärrkontrollen har", "wait");
  gsap.to(".tvp-puck", { x: 700, duration: 2, ease: "sine.inOut", repeat: -1, yoyo: true });
  requestAnimationFrame(frame);
  await http();
  socket();
  setInterval(() => {
    clockCheck();
    fpsCheck();
  }, 1000);
  setInterval(send, 30000);
  ask("transparent");
  ask("smooth");
}

main().catch((err) => {
  document.body.textContent = `Testsidan kunde inte starta: ${err}`;
  document.body.style.cssText = "color:#fff;background:#300;font:32px sans-serif;padding:60px";
});
