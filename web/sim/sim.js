// Simulator: the whole wall at one millimetre scale, replay controls and a fake TV.
import * as clock from "../shared/clock.js";
import { hhmm } from "../shared/format.js";
import * as stage from "../shared/stage.js";
import { Store } from "../shared/store.js";
import { connect } from "../shared/ws.js";

const $ = (id) => document.getElementById(id);
const SPEEDS = [1, 2, 5, 20, 50];
const store = new Store();
let status = null;
let debug = new URLSearchParams(location.search).get("debug") === "1";
const raw = new Map(); // key -> raw entry

async function api(path, body, method = "POST") {
  const r = await fetch(`/api/${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) alert(`${path}: ${data.detail ?? r.status}`);
  return data;
}

function storageGet(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}
function storageSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

// --- wall ---------------------------------------------------------------------------

const frames = [];

function buildWall() {
  const wall = $("wall");
  for (const s of stage.all()) {
    const frame = document.createElement("div");
    frame.className = "frame";
    frame.innerHTML = `<span class="name">${s.id}</span>`;
    const iframe = document.createElement("iframe");
    iframe.width = s.resolution[0];
    iframe.height = s.resolution[1];
    iframe.src = `${s.page}${debug ? "?debug=1" : ""}`;
    iframe.title = s.id;
    frame.appendChild(iframe);
    wall.appendChild(frame);
    frames.push({ s, frame, iframe });
  }
  layout();
  new ResizeObserver(layout).observe(wall);
}

function layout() {
  const wall = $("wall");
  const b = stage.bounds();
  const bezel = Math.max(...stage.all().map((s) => s.bezel_mm ?? 10));
  const margin = 24; // px around the wall
  const wMm = b.x1 - b.x0 + 2 * bezel;
  const hMm = b.y1 - b.y0 + 2 * bezel;
  const scale = Math.min((wall.clientWidth - 2 * margin) / wMm, (wall.clientHeight - 2 * margin) / hMm);
  const left0 = (wall.clientWidth - wMm * scale) / 2;
  const top0 = (wall.clientHeight - hMm * scale) / 2;
  for (const { s, frame, iframe } of frames) {
    const bz = (s.bezel_mm ?? 10) * scale;
    frame.style.left = `${left0 + (s.position_mm[0] - b.x0 + bezel) * scale - bz}px`;
    frame.style.top = `${top0 + (s.position_mm[1] - b.y0 + bezel) * scale - bz}px`;
    frame.style.width = `${s.physical_mm[0] * scale + 2 * bz}px`;
    frame.style.height = `${s.physical_mm[1] * scale + 2 * bz}px`;
    frame.style.borderWidth = `${bz}px`;
    iframe.style.transform = `scale(${(s.physical_mm[0] * scale) / s.resolution[0]})`;
  }
}

function setDebug(on) {
  debug = on;
  for (const { s, iframe } of frames) iframe.src = `${s.page}${on ? "?debug=1" : ""}`;
}

// --- controls -----------------------------------------------------------------------

async function fillGames() {
  const { fixtures, recordings } = await (await fetch("/api/replays")).json();
  const select = $("game");
  const group = (label, items, kind) => {
    if (!items.length) return;
    const g = document.createElement("optgroup");
    g.label = label;
    for (const item of items) g.appendChild(new Option(item, `${kind}:${item}`));
    select.appendChild(g);
  };
  group("Fixtures (replay)", fixtures, "replay");
  group("Recordings", recordings, "recording");
}

async function fillLive() {
  const r = await fetch("/api/schedule?days=0");
  if (!r.ok) {
    $("live-game").options[0].text = "Schedule unavailable";
    return;
  }
  const { games } = await r.json();
  const state = { "pre-game": "not started", "post-game": "finished" };
  for (const g of games) {
    const label = `${hhmm(g.start_ms)} ${g.home.code}–${g.away.code} · ${state[g.state] ?? g.state ?? "?"}`;
    $("live-game").appendChild(new Option(label, g.uuid));
  }
  if (!games.length) $("live-game").options[0].text = "No games today";
}

function bindControls() {
  $("follow-live").onclick = () => {
    const uuid = $("uuid").value.trim() || $("live-game").value;
    if (!uuid) return alert("Pick one of today's games or type a game uuid.");
    api("source", { mode: "live", uuid });
  };
  $("start").onclick = () => {
    const typed = $("uuid").value.trim();
    const [kind, value] = typed ? ["replay", typed] : $("game").value.split(":");
    const speed = Number($("start-speed").value);
    const body = kind === "recording" ? { mode: "recording", path: value, speed } : { mode: "replay", uuid: value, speed };
    api("source", body);
  };
  $("stop").onclick = () => api("source", { mode: "none" });
  $("playpause").onclick = () => api("replay", { action: status?.paused ? "play" : "pause" });
  $("next-period").onclick = () => api("replay", { action: "seek", to: "next_period" });
  $("end").onclick = () => api("replay", { action: "seek", to: "end" });
  $("next-goal").onclick = () => api("replay", { action: "seek", to: "before_next_goal" });
  for (const speed of SPEEDS) {
    const b = document.createElement("button");
    b.textContent = `${speed}×`;
    b.dataset.speed = speed;
    b.onclick = () => api("replay", { action: "speed", speed });
    $("speeds").appendChild(b);
  }
  $("offset").oninput = () => ($("offset-out").value = `${Number($("offset").value).toFixed(1)} s`);
  $("offset").onchange = () => api("offset", { profile: store.config.profile ?? "iptv", seconds: Number($("offset").value) });
  $("fake").value = storageGet("sim.fakeDelay", "40");
  $("fake").oninput = () => {
    $("fake-out").value = `${Number($("fake").value).toFixed(1)} s`;
    storageSet("sim.fakeDelay", $("fake").value);
  };
  $("fake").oninput();
  $("debug").checked = debug;
  $("debug").onchange = () => setDebug($("debug").checked);
  $("show-raw").onchange = () => $("raw-events").classList.toggle("hidden", !$("show-raw").checked);
}

function showConfig(config) {
  if (config.offset_ms == null) return;
  $("profile").textContent = config.profile;
  if (document.activeElement !== $("offset")) {
    $("offset").value = config.offset_ms / 1000;
    $("offset").oninput();
  }
}

function showStatus() {
  if (!status) return;
  const hooks = status.webhooks ?? {};
  $("webhook-state").textContent = hooks.enabled ? `on${hooks.pending ? `, ${hooks.pending} waiting` : ""}` : hooks.url_set ? "off" : "no URL set";
  const src = status.source ?? {};
  $("playpause").textContent = status.paused ? "Play" : "Pause";
  for (const b of $("speeds").children) b.classList.toggle("on", Number(b.dataset.speed) === src.speed);
  const tv = store.tv ?? {};
  const lines = [
    `source  ${src.mode} ${src.uuid ?? src.path ?? ""} ${status.running ? "running" : "stopped"}${status.error ? ` – ${status.error}` : ""}`,
    `arena   ${status.feed_ms ? new Date(status.feed_ms).toLocaleTimeString("sv-SE") : "–"} (replay feed time)`,
    `screens ${tv.phase ?? "–"} · P${tv.period ?? "–"} ${tv.last_game_time ?? ""} · ${tv.score ? `${tv.score.home}–${tv.score.away}` : ""} · scene ${tv.scene?.name ?? "–"}`,
    `real    ${hhmm(clock.now())} · events ${status.released_events}/${status.raw_events} released`,
  ];
  $("progress").textContent = lines.join("\n");
}

// --- webhooks -----------------------------------------------------------------------

function showWebhook(entry) {
  const list = $("webhook-log");
  list.querySelector(".muted")?.remove();
  const li = document.createElement("li");
  const when = new Date(entry.sent_ms ?? entry.play_at_ms).toLocaleTimeString("sv-SE");
  const late = entry.sent_ms != null ? ` +${entry.sent_ms - entry.play_at_ms} ms` : "";
  const flags = [entry.test && "test", entry.source === "manual" && "MÅL! button", entry.attempts > 1 && "retried"].filter(Boolean);
  li.textContent = `${when}${late} ${entry.event} → ${entry.error ?? entry.status}${flags.length ? ` (${flags.join(", ")})` : ""}`;
  if (entry.error) li.style.color = "var(--penalty)";
  list.prepend(li);
  while (list.children.length > 50) list.lastChild.remove();
}

// --- fake TV ------------------------------------------------------------------------

function onRaw(entry) {
  if (entry.change === "reset") {
    raw.clear();
    return;
  }
  if (entry.change === "removed") raw.delete(entry.key);
  else raw.set(entry.key, entry);
  const li = document.createElement("li");
  li.textContent = `${new Date(entry.received_ms).toLocaleTimeString("sv-SE")} ${entry.change} ${entry.label}`;
  if (entry.type === "goal") li.className = "goal";
  $("raw-events").prepend(li);
  while ($("raw-events").children.length > 200) $("raw-events").lastChild.remove();
}

function renderTv() {
  const delay = Number($("fake").value) * 1000;
  const now = clock.now();
  const shown = [...raw.values()]
    .filter((e) => e.event_ms != null && e.event_ms + delay <= now)
    .sort((a, b) => a.event_ms - b.event_ms);
  const withClock = [...shown].reverse().find((e) => /^P\S+ \d\d:\d\d/.test(e.label));
  $("tv-clock").textContent = withClock ? withClock.label.match(/^(P\S+ \d\d:\d\d)/)[1] : "–";
  const list = $("tv-events");
  const items = shown.slice(-14).reverse();
  const html = items
    .map((e) => `<li class="${e.type === "goal" ? "goal" : ""}">${new Date(e.event_ms + delay).toLocaleTimeString("sv-SE")} ${e.label}</li>`)
    .join("");
  if (list.dataset.html !== html) {
    list.innerHTML = html;
    list.dataset.html = html;
  }
}

// --- main ---------------------------------------------------------------------------

async function main() {
  await stage.load();
  buildWall();
  bindControls();
  fillGames();
  fillLive();
  let socket = null;
  store.on("config", showConfig);
  store.on("status", (m) => {
    status = m.status;
    showStatus();
  });
  store.on("state", () => raw.clear()); // a new source or seek; raw_backlog refills on connect
  store.on("raw_backlog", (m) => {
    raw.clear();
    (m.raw ?? []).forEach(onRaw);
  });
  store.on("raw", (m) => onRaw(m.entry));
  store.on("webhook", (m) => showWebhook(m.entry));
  fetch("/api/webhooks/log")
    .then((r) => r.json())
    .then((d) => d.log.forEach(showWebhook))
    .catch(() => {});
  socket = connect({
    role: "sim",
    id: "sim",
    onMessage: (m) => store.handle(m),
    onStatus: (s) => {
      $("conn").textContent = `websocket ${s}`;
      if (s === "open") socket?.send({ t: "debug_subscribe" });
    },
  });
  setInterval(renderTv, 200);
  setInterval(showStatus, 1000);
}

main();
