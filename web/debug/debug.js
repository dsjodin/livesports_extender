// Debug page: raw events (behind a toggle) next to released events with play_at.
const $ = (id) => document.getElementById(id);
const MAX_ROWS = 400;
let ws;
let clockOffset = 0; // server_ms - local ms
const pings = [];
let config = {};

const serverNow = () => Date.now() + clockOffset;

function time(ms) {
  if (ms == null) return "–";
  const d = new Date(ms);
  return d.toLocaleTimeString("sv-SE") + "," + Math.floor((ms % 1000) / 100);
}

function seconds(ms) {
  if (ms == null) return "–";
  return (ms >= 0 ? "+" : "−") + Math.abs(ms / 1000).toFixed(1).replace(".", ",") + " s";
}

function row(cells, cls) {
  const tr = document.createElement("tr");
  if (cls) tr.className = cls;
  for (const [text, cellCls] of cells) {
    const td = document.createElement("td");
    td.textContent = text;
    if (cellCls) td.className = cellCls;
    tr.appendChild(td);
  }
  return tr;
}

function prepend(body, tr) {
  const hint = body.querySelector(".hint");
  if (hint) hint.remove();
  body.prepend(tr);
  while (body.rows.length > MAX_ROWS) body.deleteRow(-1);
}

function addRaw(entry) {
  if (!entry.key) return;
  const lag = entry.event_ms != null ? entry.first_seen_ms - entry.event_ms : null;
  const cls = [entry.type === "goal" ? "goal" : "", entry.change === "removed" ? "removed" : ""]
    .join(" ").trim();
  prepend($("raw-rows"), row([
    [time(entry.received_ms ?? entry.at_ms)],
    [entry.change],
    [entry.label, "label"],
    [time(entry.event_ms)],
    [seconds(lag)],
  ], cls));
}

const released = [];

function addReleased(message) {
  const e = message.event;
  const tr = row([
    [time(message.play_at_ms)],
    ["", "countdown"],
    [`${message.t === "event_update" ? "rättad: " : ""}${labelOf(e)}`, "label"],
    [time(e.event_ms)],
    [e.event_ms != null ? seconds(message.play_at_ms - e.event_ms) : "–"],
    [e.late ? `sen ${seconds(e.late_by_ms)}` : "", e.late ? "late" : ""],
  ], e.type === "goal" || e.type === "goal_disallowed" ? "goal" : "");
  released.push({ tr, playAt: message.play_at_ms });
  prepend($("released-rows"), tr);
}

function labelOf(e) {
  const where = [e.period != null ? `P${e.period}` : "", e.time || ""].join(" ").trim();
  const who = e.player ? ` #${e.player.number} ${e.player.first ?? ""} ${e.player.last ?? ""}` : "";
  return `${where} ${e.type}${e.team_code ? " " + e.team_code : ""}${who}`.trim();
}

function tick() {
  const now = serverNow();
  for (const item of released.slice(-60)) {
    const left = item.playAt - now;
    item.tr.classList.toggle("pending", left > 0);
    item.tr.querySelector(".countdown").textContent = left > 0 ? seconds(left) : "";
  }
  requestAnimationFrame(tick);
}

function showStatus(s) {
  const src = s.source || {};
  const parts = [
    `källa ${src.mode}${src.uuid ? " " + src.uuid : ""}${src.mode !== "none" ? ` ${src.speed}×` : ""}`,
    s.paused ? "pausad" : "",
    s.feed_ms ? `matchtid ${time(s.feed_ms)}` : "",
    `TV-fördröjning ${String(s.offset_s).replace(".", ",")} s (${s.profile})`,
    `råa ${s.raw_events}, släppta ${s.released_events}, väntande ${s.pending_messages}`,
    s.error ? `fel: ${s.error}` : "",
  ];
  $("status").textContent = parts.filter(Boolean).join(" · ");
  if (document.activeElement !== $("offset")) $("offset").value = s.offset_s;
}

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?role=debug&id=debug`);
  ws.onopen = () => {
    for (let i = 0; i < 5; i++) setTimeout(() => ping(), i * 300);
    if ($("raw").checked) ws.send(JSON.stringify({ t: "debug_subscribe" }));
  };
  ws.onclose = () => {
    $("status").textContent = "Frånkopplad, försöker igen…";
    setTimeout(connect, 2000);
  };
  ws.onmessage = (msg) => {
    const m = JSON.parse(msg.data);
    switch (m.t) {
      case "hello": config = m.config; break;
      case "config": config = m.config; break;
      case "status": showStatus(m.status); break;
      case "clock_pong": pong(m); break;
      case "raw": addRaw(m.entry); break;
      case "raw_backlog": m.raw.forEach(addRaw); break;
      case "event":
      case "event_update": addReleased(m); break;
      case "state":
        if (m.state.rev && !m.state.goals?.length) {
          $("released-rows").replaceChildren();
          released.length = 0;
        }
        break;
    }
  };
}

function ping() {
  if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ t: "clock_ping", t0: Date.now() }));
}

function pong(m) {
  const now = Date.now();
  pings.push({ rtt: now - m.t0, offset: m.server_ms - (m.t0 + now) / 2 });
  const best = [...pings].sort((a, b) => a.rtt - b.rtt).slice(0, 5).map((p) => p.offset).sort((a, b) => a - b);
  clockOffset = best[Math.floor(best.length / 2)];
}

async function post(path, body, method = "POST") {
  const r = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) alert(`${path}: ${(await r.json()).detail ?? r.status}`);
}

$("start").onclick = () => {
  $("raw-rows").replaceChildren();
  $("released-rows").replaceChildren();
  released.length = 0;
  post("/api/source", { mode: "replay", uuid: $("uuid").value.trim(), speed: Number($("speed").value) });
};
$("pause").onclick = () => post("/api/replay", { action: "pause" });
$("play").onclick = () => post("/api/replay", { action: "play" });
$("next-goal").onclick = () => post("/api/replay", { action: "seek", to: "before_next_goal" });
$("set-offset").onclick = () =>
  post("/api/offset", { profile: config.profile || "iptv", seconds: Number($("offset").value) });
$("raw").onchange = () =>
  ws?.send(JSON.stringify({ t: $("raw").checked ? "debug_subscribe" : "debug_unsubscribe" }));

setInterval(ping, 30000);
connect();
requestAnimationFrame(tick);
