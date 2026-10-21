// Phone app (docs/SCREENS.md, Phone app): Matcher, Live and Inställningar. Swedish UI.
// The score comes from the delayed TV state (applied at play_at, like the screens); raw
// events only behind the debug toggle (CLAUDE.md rule 1).
import * as clock from "../shared/clock.js";
import { caps, decimal, esc, hhmm, html, onColor, periodName, raw, score } from "../shared/format.js";
import { Store } from "../shared/store.js";
import { connect } from "../shared/ws.js";

const $ = (id) => document.getElementById(id);
const KINDS = [
  ["period_start", "Nedsläpp"],
  ["goal", "Mål"],
  ["penalty", "Utvisning"],
  ["timeout", "Timeout"],
  ["shot_on_goal", "Skott på mål"],
];
const SCENES = [
  [null, "Auto"],
  ["idle", "Tabell"],
  ["live", "Skottkarta"],
  ["intermission", "Periodstatistik"],
  ["goal", "Mål igen"],
];
const SPEEDS = [1, 2, 5, 20, 50];
const PROFILE_NAMES = { iptv: "IPTV", tv4play: "TV4 Play" };
const WEBHOOK_EVENTS = [
  ["shl_goal", "Mål"],
  ["shl_goal_disallowed", "Underkänt mål"],
  ["shl_penalty", "Utvisning"],
  ["shl_period_start", "Periodstart"],
  ["shl_period_end", "Periodslut"],
  ["shl_game_end", "Matchslut"],
];

const store = new Store();
const ui = {
  view: "live",
  kind: "period_start",
  side: null,
  status: null,
  connection: "connecting",
  rawOn: false,
  raw: [],
  games: null, // {today, upcoming, played, fixtures}
  teams: null, // GET /api/teams
  webhooks: null, // GET /api/webhooks settings
  webhookLog: [],
  version: null,
};
let socket = null;

// --- helpers --------------------------------------------------------------------------

async function api(path, body, method = "POST") {
  try {
    const r = await fetch(`/api/${path}`, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      toast(`Fel: ${data.detail ?? r.status}`);
      return null;
    }
    if (data.status) ui.status = data.status;
    return data;
  } catch {
    toast("Ingen kontakt med servern");
    return null;
  }
}

let toastTimer = null;
function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 2600);
}

/** Replace a container's HTML only when it changed, so a tap is not lost to a re-render. */
function put(el, markup) {
  if (el.dataset.html !== markup) {
    el.innerHTML = markup;
    el.dataset.html = markup;
  }
}

const team = (side) => store.tv?.teams?.[side] ?? {};

function logo(t, size = "") {
  const img = t?.logo ? `<img src="${esc(t.logo)}" alt="" onerror="this.remove()">` : esc(t?.code ?? "");
  return `<span class="logo ${size}" style="--c:${esc(t?.color ?? "var(--divider)")}">${img}</span>`;
}

function logoFor(uuid, code) {
  return logo({ logo: uuid ? `/assets/teams/${uuid}.svg` : null, code }, "sm");
}

// --- Live -----------------------------------------------------------------------------

function statusLine(tv) {
  const phase = tv.phase;
  if (phase === "pregame") return tv.game?.start_ms ? `Före matchen · nedsläpp ${hhmm(tv.game.start_ms)}` : "Före matchen";
  if (phase === "live") return `${periodName(tv.period)}${tv.last_game_time ? ` · ${tv.last_game_time}` : ""}`;
  if (phase === "intermission") return `Paus efter ${periodName(tv.period).toLowerCase()}`;
  if (phase === "postgame") return `Slut${tv.went_to_shootout ? " efter straffar" : tv.overtime ? " efter förlängning" : ""}`;
  return "Ingen match vald";
}

function pressText(p) {
  if (p.status === "test") return ["Testmål", ""];
  if (p.status === "waiting") return ["Mål registrerat – väntar på data", ""];
  if (p.status === "unconfirmed") return ["Inget mål kom från SHL", "bad"];
  if (p.scorer) return [`#${p.scorer.number} ${p.scorer.first} ${p.scorer.last}`, "ok"];
  return ["Målet hittat hos SHL", "ok"];
}

function sampleText(s) {
  if (s.status === "matched") return [`${decimal(s.sample_s)} s`, "ok"];
  if (s.status === "pending") return ["Väntar…", ""];
  if (s.status === "ambiguous") return ["Flera möjliga – välj lag", "bad"];
  return ["Hittade ingen händelse", "bad"];
}

function renderLive() {
  const tv = store.tv;
  const st = ui.status ?? {};
  if (!tv) return put($("view-live"), `<div class="card muted">Ansluter…</div>`);
  const my = st.my_side;
  const sides = my === "away" ? ["away", "home"] : ["home", "away"];
  const selected = tv.phase !== "idle";

  const scoreCard = html`<div class="card"><div class="score">
      <div class="team">${raw(logo(team("home")))}${team("home").short ?? "Hemma"}</div>
      <div class="digits">${selected ? score(tv.score?.home, tv.score?.away) : "–"}</div>
      <div class="team">${raw(logo(team("away")))}${team("away").short ?? "Borta"}</div>
      <div class="status">${statusLine(tv)}</div></div></div>`;

  const goalButtons = sides
    .map((side) => {
      const t = team(side);
      const color = t.color ?? "#8A93A6";
      return html`<button class="goal-btn" data-act="goal" data-side="${side}" style="--c:${color};--on:${onColor(color)}" ${selected ? "" : "disabled"}>
        <b>MÅL!</b><span>${t.short ?? (side === "home" ? "Hemma" : "Borta")}${side === my ? " ★" : ""}</span></button>`;
    })
    .join("");
  const presses = [...(st.manual ?? [])].reverse().slice(0, 4);
  const pressList = presses.length
    ? `<ul class="press-list">${presses
        .map((p) => {
          const [text, cls] = pressText(p);
          return html`<li><span>${hhmm(p.pressed_ms)} ${team(p.side).code ?? ""}</span><span class="${cls}">${text}</span></li>`;
        })
        .join("")}</ul>`
    : "";
  const goalCard = html`<div class="card"><div class="goal-buttons">${raw(goalButtons)}</div>
    <div class="muted">Tryck när målet syns på TV:n.</div>${raw(pressList)}</div>`;

  const offsetCard = html`<div class="card"><div class="row split">
      <div><div class="label">TV-fördröjning</div><div class="offset">${decimal(st.offset_s)} s</div></div>
      <button class="chip" data-act="profile">${PROFILE_NAMES[st.profile] ?? caps(st.profile ?? "")}</button></div>
    <div class="row"><button class="grow" data-act="nudge" data-delta="-0.5">−0,5</button><button class="grow" data-act="nudge" data-delta="0.5">+0,5</button></div></div>`;

  const cal = st.calibration ?? { samples: [] };
  const samples = [...cal.samples].reverse().slice(0, 8);
  const kindName = Object.fromEntries(KINDS);
  const sampleList = samples.length
    ? `<ul class="press-list">${samples
        .map((s) => {
          const [text, cls] = sampleText(s);
          const side = s.side ? ` ${team(s.side).code ?? ""}` : "";
          const src = s.source === "goal_button" ? " (målknapp)" : "";
          return html`<li><span>${hhmm(s.pressed_ms)} ${kindName[s.kind] ?? s.kind}${side}${src}</span><span class="${cls}">${text}</span>
            <button class="ghost" data-act="del-sample" data-id="${s.id}" aria-label="Ta bort">✕</button></li>`;
        })
        .join("")}</ul>`
    : "";
  const proposal = cal.proposal_s != null
    ? html`<div class="row split"><div class="proposal">Förslag: ${decimal(cal.proposal_s)} s <span class="muted">(${cal.proposal_samples} ${cal.proposal_samples === 1 ? "mätning" : "mätningar"})</span></div>
        <div class="row"><button class="primary" data-act="accept">Använd</button><button data-act="clear-samples">Rensa</button></div></div>`
    : cal.samples.length
      ? `<div class="row split"><span class="muted">Inget förslag ännu</span><button data-act="clear-samples">Rensa</button></div>`
      : "";
  const syncCard = html`<div class="card"><div class="label">Synka</div>
    <div class="seg">${raw(KINDS.map(([k, name]) => html`<button class="${ui.kind === k ? "on" : ""}" data-act="kind" data-kind="${k}">${name}</button>`).join(""))}</div>
    <div class="seg">${raw(
      [[null, "Båda"], ["home", team("home").short ?? "Hemma"], ["away", team("away").short ?? "Borta"]]
        .map(([s, name]) => html`<button class="${ui.side === s ? "on" : ""}" data-act="side" data-side="${s ?? ""}">${name}</button>`)
        .join(""),
    )}</div>
    <button class="primary sync-btn" data-act="sync">Synka</button>
    <div class="muted">Tryck när du ser händelsen på TV:n.</div>
    ${raw(sampleList)}${raw(proposal)}
    <label class="row"><input type="checkbox" data-act="goal-sync" ${st.goal_button_sync ? "checked" : ""}> Använd målknapp för synk</label></div>`;

  const late = st.late_goals
    ? html`<div class="note">${st.late_goals} mål kom efter TV:n i kväll – överväg att pausa TV:n vid nedsläpp.</div>`
    : "";

  const sceneNow = tv.scene?.override ? tv.scene.name : null;
  const sceneCard = html`<div class="card"><div class="label">Scen</div><div class="scene-buttons">${raw(
    SCENES.map(([name, label]) => html`<button class="${(name ?? null) === sceneNow ? "on" : ""}" data-act="scene" data-scene="${name ?? ""}">${label}</button>`).join(""),
  )}</div><button data-act="test-goal">Testa mål</button></div>`;

  let replayCard = "";
  if (st.source?.mode === "replay") {
    replayCard = html`<div class="card"><div class="label">Repris</div>
      <div class="row"><button class="grow" data-act="playpause">${st.paused ? "Spela" : "Paus"}</button>
        <button class="grow" data-act="seek" data-to="next_period">Nästa period</button>
        <button class="grow" data-act="seek" data-to="before_next_goal">10 s före nästa mål</button></div>
      <div class="seg">${raw(SPEEDS.map((s) => html`<button class="${st.source.speed === s ? "on" : ""}" data-act="speed" data-speed="${s}">${s}×</button>`).join(""))}</div></div>`;
  }

  put($("view-live"), scoreCard + goalCard + late + offsetCard + syncCard + sceneCard + replayCard);
}

// --- Matcher --------------------------------------------------------------------------

async function loadGames() {
  const [upcoming, recent, replays] = await Promise.all([
    fetch("/api/schedule?days=7").then((r) => (r.ok ? r.json() : { games: [] })),
    fetch("/api/schedule/recent?days=30").then((r) => (r.ok ? r.json() : { games: [] })),
    fetch("/api/replays").then((r) => (r.ok ? r.json() : { fixtures: [] })),
  ]).catch(() => [{ games: [] }, { games: [] }, { fixtures: [] }]);
  const today = new Intl.DateTimeFormat("sv-SE", { dateStyle: "short", timeZone: "Europe/Stockholm" }).format(clock.now());
  const day = (ms) => new Intl.DateTimeFormat("sv-SE", { dateStyle: "short", timeZone: "Europe/Stockholm" }).format(ms);
  const notOver = upcoming.games.filter((g) => g.state !== "post-game");
  ui.games = {
    today: upcoming.games.filter((g) => day(g.start_ms) === today),
    upcoming: notOver.filter((g) => day(g.start_ms) !== today),
    played: recent.games.slice(0, 20),
    fixtures: replays.fixtures ?? [],
  };
  renderMatcher();
}

function gameRow(g, when) {
  const sel = ui.status?.game_uuid === g.uuid ? "selected" : "";
  return html`<button class="game ${sel}" data-act="open-game" data-uuid="${g.uuid}">
    <span class="when">${when}</span>
    <span class="pair">${raw(logoFor(g.home.uuid, g.home.code))}${raw(logoFor(g.away.uuid, g.away.code))}</span>
    <span class="names"><b>${g.home.code}–${g.away.code}${g.home.score != null && g.state === "post-game" ? `  ${g.home.score}–${g.away.score}` : ""}</b><small>${g.arena ?? ""}</small></span></button>`;
}

function dayShort(ms) {
  return new Intl.DateTimeFormat("sv-SE", { weekday: "short", day: "numeric", month: "numeric", timeZone: "Europe/Stockholm" }).format(ms);
}

function renderMatcher() {
  const g = ui.games;
  if (!g) return put($("view-matcher"), `<div class="card muted">Hämtar matcher…</div>`);
  const section = (title, rows) => html`<div class="label">${title}</div><div class="games">${raw(rows || `<div class="muted">Inga matcher</div>`)}</div>`;
  const fixtures = g.fixtures
    .map((uuid) => {
      const sel = ui.status?.game_uuid === uuid ? "selected" : "";
      return html`<button class="game ${sel}" data-act="open-fixture" data-uuid="${uuid}"><span class="when">Test</span><span></span>
        <span class="names"><b>${uuid}</b><small>Sparad match (fixtur)</small></span></button>`;
    })
    .join("");
  put(
    $("view-matcher"),
    section("Idag", g.today.map((x) => gameRow(x, hhmm(x.start_ms))).join("")) +
      section("Kommande", g.upcoming.map((x) => gameRow(x, dayShort(x.start_ms))).join("")) +
      section("Spelade (repris)", g.played.map((x) => gameRow(x, dayShort(x.start_ms))).join("")) +
      section("Testmatcher", fixtures),
  );
}

function findGame(uuid) {
  const g = ui.games ?? {};
  return [...(g.today ?? []), ...(g.upcoming ?? []), ...(g.played ?? [])].find((x) => x.uuid === uuid);
}

function openSheet(markup) {
  $("sheet").innerHTML = markup;
  $("sheet").hidden = false;
  $("sheet-backdrop").hidden = false;
}

function closeSheet() {
  $("sheet").hidden = true;
  $("sheet-backdrop").hidden = true;
}

let sheetGame = null; // {uuid, finished, mySide}

function gameSheet(uuid, fixture = false) {
  const g = findGame(uuid);
  const myTeam = ui.status?.my_team_uuid;
  const current = ui.status?.game_uuid === uuid ? ui.status?.my_side_choice : null;
  const mySide = current ?? (g?.home.uuid === myTeam ? "home" : g?.away.uuid === myTeam ? "away" : "none");
  sheetGame = { uuid, finished: fixture || g?.state === "post-game", mySide, speed: 5 };
  renderSheet(g);
}

function renderSheet(g) {
  const s = sheetGame;
  const title = g ? `${g.home.short ?? g.home.code}–${g.away.short ?? g.away.code}` : `Testmatch ${s.uuid}`;
  const sub = g ? `${dayShort(g.start_ms)} ${hhmm(g.start_ms)} · ${g.arena ?? ""}` : "Spelas upp från sparad data";
  const sides = [
    ["home", g?.home.short ?? "Hemma"],
    ["away", g?.away.short ?? "Borta"],
    ["none", "Inget"],
  ];
  const action = s.finished
    ? html`<div class="label">Hastighet</div><div class="seg">${raw(SPEEDS.map((x) => html`<button class="${s.speed === x ? "on" : ""}" data-act="sheet-speed" data-speed="${x}">${x}×</button>`).join(""))}</div>
      <button class="primary" data-act="replay-game">Spela upp som repris</button>`
    : html`<button class="primary" data-act="follow-game">Följ matchen</button>`;
  openSheet(html`<h2>${title}</h2><div class="muted">${sub}</div>
    <div class="label">Mitt lag</div>
    <div class="seg">${raw(sides.map(([side, name]) => html`<button class="${s.mySide === side ? "on" : ""}" data-act="sheet-side" data-side="${side}">${name}</button>`).join(""))}</div>
    ${raw(action)}<button class="ghost" data-act="close-sheet">Stäng</button>`);
}

async function startGame(mode) {
  const s = sheetGame;
  const body = mode === "live" ? { mode, uuid: s.uuid } : { mode: "replay", uuid: s.uuid, speed: s.speed };
  closeSheet();
  toast(mode === "live" ? "Följer matchen" : "Startar repris…");
  if (!(await api("source", body))) return;
  await api("game", { uuid: s.uuid, my_side: s.mySide });
  setView("live");
}

// --- Inställningar --------------------------------------------------------------------

async function loadSettings() {
  const [teams, health, hooks, hookLog] = await Promise.all([
    fetch("/api/teams").then((r) => r.json()),
    fetch("/api/health").then((r) => r.json()),
    fetch("/api/webhooks").then((r) => r.json()),
    fetch("/api/webhooks/log").then((r) => r.json()),
  ]).catch(() => [null, null, null, null]);
  ui.teams = teams;
  ui.version = health?.version;
  ui.webhooks = hooks?.settings ?? null;
  ui.webhookLog = hookLog?.log ?? [];
  renderSettings();
}

function renderSettings() {
  const st = ui.status ?? {};
  const cfgProfiles = ui.profiles ?? {};
  const profiles = Object.entries(cfgProfiles)
    .map(
      ([name, seconds]) => html`<div class="profile-row">
        <button class="${st.profile === name ? "on" : ""}" data-act="use-profile" data-profile="${name}">${st.profile === name ? "Aktiv" : "Välj"}</button>
        <span>${PROFILE_NAMES[name] ?? name}</span>
        <input type="number" inputmode="decimal" step="0.5" min="0" max="600" value="${seconds}" data-act="profile-offset" data-profile="${name}" aria-label="Fördröjning i sekunder"></div>`,
    )
    .join("");
  const t = ui.teams;
  const palette = t ? Object.entries(t.colors) : [];
  const picker = (team, where) => {
    const jersey = team[where].jersey;
    const color = team[where].color;
    const opts = palette.map(([name]) => `<option value="${esc(name)}" ${jersey === name ? "selected" : ""}>${esc(name)}</option>`).join("");
    const custom = jersey && !t.colors[jersey] ? `<option value="${esc(jersey)}" selected>${esc(jersey)}</option>` : "";
    return html`<label>${where === "home" ? "Hemma" : "Borta"} <span class="swatch" style="background:${color ?? "transparent"}"></span>
      <select data-act="team-color" data-uuid="${team.uuid}" data-where="${where}">${raw(custom + opts)}<option value="custom">Egen färg…</option></select></label>`;
  };
  const teamRows = t
    ? t.teams
        .map(
          (team) => html`<div class="team-row">${raw(logoFor(team.uuid, ""))}<div class="row split"><b>${team.name}</b>${raw(
            team.overridden ? html`<button class="ghost" data-act="team-reset" data-uuid="${team.uuid}">Återställ</button>` : "",
          )}</div><div class="pickers">${raw(picker(team, "home"))}${raw(picker(team, "away"))}</div></div>`,
        )
        .join("")
    : `<div class="muted">Hämtar lag…</div>`;
  const myTeam = t
    ? html`<select data-act="my-team"><option value="">Inget lag</option>${raw(
        t.teams.map((x) => `<option value="${esc(x.uuid)}" ${st.my_team_uuid === x.uuid ? "selected" : ""}>${esc(x.name)}</option>`).join(""),
      )}</select>`
    : "";
  put(
    $("view-installningar"),
    html`<div class="card"><div class="label">TV-profil</div>${raw(profiles || `<div class="muted">Ansluter…</div>`)}
      <div class="muted">Hur många sekunder TV:n ligger efter arenan.</div></div>
    <div class="card"><div class="label">Mitt lag</div>${raw(myTeam)}<div class="muted">Mitt lags mål tänder lamporna. Kan ändras per match under Matcher.</div>
      <label class="row"><input type="checkbox" data-act="follow" ${st.follow_my_team ? "checked" : ""}> Följ mitt lag automatiskt</label>
      <div class="muted">Följer mitt lags match live när den spelas idag, om ingen annan match eller repris är igång. Stäng av för att sluta följa.</div></div>
    ${raw(haCard())}
    <div class="card"><div class="label">Lagfärger</div>${raw(teamRows)}</div>
    <div class="card"><div class="label">Felsökning</div>
      <label class="row"><input type="checkbox" data-act="raw" ${ui.rawOn ? "checked" : ""}> Visa råa händelser</label>
      <div class="warn">Kan avslöja mål innan de syns på TV.</div><ul class="raw" id="raw-list"></ul></div>
    <div class="card"><div class="label">Om</div><dl id="about"></dl></div>`,
  );
  renderAbout();
  renderRaw();
  renderHaLog();
}

function haCard() {
  const w = ui.webhooks;
  if (!w) return `<div class="card"><div class="label">Home Assistant</div><div class="muted">Hämtar…</div></div>`;
  const events = WEBHOOK_EVENTS.map(
    ([id, name]) => html`<label class="row"><input type="checkbox" data-ha-event="${id}" ${w.events.includes(id) ? "checked" : ""}> ${name}</label>`,
  ).join("");
  return html`<div class="card" id="ha-card"><div class="label">Home Assistant</div>
    <input id="ha-url" type="url" inputmode="url" placeholder="http://homeassistant.local:8123/api/webhook/shl-arena" value="${w.url ?? ""}">
    <label class="row"><input type="checkbox" id="ha-enabled" ${w.enabled ? "checked" : ""}> Skicka till Home Assistant</label>
    <div class="label">Händelser</div>${raw(events)}
    <button class="primary" data-act="save-ha">Spara</button>
    <div class="muted">Anropen skickas när händelsen syns på TV:n. Prova med "Testa mål" under Live.</div>
    <ul class="press-list" id="ha-log"></ul></div>`;
}

function renderHaLog() {
  const el = $("ha-log");
  if (!el) return;
  const names = Object.fromEntries(WEBHOOK_EVENTS);
  put(
    el,
    ui.webhookLog
      .slice(-5)
      .reverse()
      .map((e) => {
        const ok = !e.error;
        const what = `${names[e.event] ?? e.event}${e.test ? " (test)" : e.source === "manual" ? " (MÅL!-knapp)" : ""}`;
        return html`<li><span>${new Date(e.sent_ms ?? e.play_at_ms).toLocaleTimeString("sv-SE")} ${what}</span><span class="${ok ? "ok" : "bad"}">${ok ? "Skickat" : `Fel: ${e.error}`}</span></li>`;
      })
      .join(""),
  );
}

function renderAbout() {
  const el = $("about");
  if (!el) return;
  const st = ui.status ?? {};
  const c = clock.stats();
  const src = st.source ?? {};
  const mode = { live: "Live", replay: "Repris", recording: "Inspelning", none: "Ingen" }[src.mode] ?? src.mode ?? "–";
  put(
    el,
    html`<dt>Version</dt><dd>${ui.version ?? "–"}</dd>
      <dt>Källa</dt><dd>${mode}${src.uuid ? ` ${src.uuid}` : ""}${st.running ? " · igång" : ""}${st.error ? ` · ${st.error}` : ""}</dd>
      <dt>Senaste hämtning</dt><dd>${st.last_snapshot_ms ? new Date(st.last_snapshot_ms).toLocaleTimeString("sv-SE") : "–"}</dd>
      <dt>Klocka</dt><dd>${c.offset} ms mot servern (rtt ${c.rtt ?? "–"} ms)</dd>`,
  );
}

function renderRaw() {
  const el = $("raw-list");
  if (!el) return;
  put(el, ui.rawOn ? ui.raw.slice(-60).reverse().map((e) => html`<li>${new Date(e.received_ms ?? e.at_ms).toLocaleTimeString("sv-SE")} ${e.change} ${e.label ?? ""}</li>`).join("") : "");
}

// --- actions --------------------------------------------------------------------------

const actions = {
  goal: (d) => api("goal", { side: d.side }).then((r) => r && toast("Mål registrerat")),
  nudge: (d) => api("offset/nudge", { delta: Number(d.delta) }),
  profile: () => {
    const names = Object.keys(ui.profiles ?? {});
    const next = names[(names.indexOf(ui.status?.profile) + 1) % names.length];
    if (next) api("profile", { profile: next });
  },
  kind: (d) => ((ui.kind = d.kind), renderLive()),
  side: (d) => ((ui.side = d.side || null), renderLive()),
  sync: () =>
    api("calibrate", { kind: ui.kind, side: ui.side }).then((r) => {
      if (!r) return;
      if (ui.status) ui.status.calibration = r;
      renderLive();
    }),
  "del-sample": (d) => api(`calibrate/${d.id}`, undefined, "DELETE").then((r) => r && ui.status && (ui.status.calibration = r) && renderLive()),
  "clear-samples": () => api("calibrate", undefined, "DELETE").then((r) => r && ui.status && (ui.status.calibration = r) && renderLive()),
  accept: () => api("calibrate/accept").then((r) => r && toast(`TV-fördröjning ${decimal(r.current_offset_s)} s`)),
  scene: (d) => (d.scene ? api("scene", { name: d.scene, hold_s: d.scene === "goal" ? 20 : null }) : api("scene", undefined, "DELETE")),
  "test-goal": () => api("test/goal", {}).then((r) => r && toast("Testmål skickat")),
  playpause: () => api("replay", { action: ui.status?.paused ? "play" : "pause" }),
  seek: (d) => api("replay", { action: "seek", to: d.to }),
  speed: (d) => api("replay", { action: "speed", speed: Number(d.speed) }),
  "open-game": (d) => gameSheet(d.uuid),
  "open-fixture": (d) => gameSheet(d.uuid, true),
  "close-sheet": closeSheet,
  "sheet-side": (d) => ((sheetGame.mySide = d.side), renderSheet(findGame(sheetGame.uuid))),
  "sheet-speed": (d) => ((sheetGame.speed = Number(d.speed)), renderSheet(findGame(sheetGame.uuid))),
  "follow-game": () => startGame("live"),
  "replay-game": () => startGame("replay"),
  "use-profile": (d) => api("profile", { profile: d.profile }).then(() => renderSettings()),
  "team-reset": (d) => api(`teams/${d.uuid}`, undefined, "DELETE").then(loadSettings),
  "save-ha": () => {
    const events = [...document.querySelectorAll("[data-ha-event]")].filter((el) => el.checked).map((el) => el.dataset.haEvent);
    const url = $("ha-url").value.trim() || null;
    api("webhooks", { url, enabled: $("ha-enabled").checked, events }).then((r) => {
      if (!r) return;
      ui.webhooks = r.settings;
      toast("Home Assistant sparat");
    });
  },
};

const changes = {
  "goal-sync": (el) => api("calibrate/goal-button", { enabled: el.checked }),
  "profile-offset": (el) => api("offset", { profile: el.dataset.profile, seconds: Number(el.value) }),
  "my-team": (el) => api("my-team", { uuid: el.value || null }),
  follow: (el) => api("follow", { enabled: el.checked }).then((r) => r && toast(el.checked ? "Följer mitt lag" : "Följer inte mitt lag automatiskt")),
  "team-color": (el) => {
    let value = el.value;
    if (value === "custom") {
      value = prompt("Färg som #rrggbb", "#") ?? "";
      if (!/^#[0-9a-f]{6}$/i.test(value)) return loadSettings();
    }
    api(`teams/${el.dataset.uuid}`, { [el.dataset.where]: value }, "PUT").then(loadSettings);
  },
  raw: (el) => {
    ui.rawOn = el.checked;
    socket?.send({ t: el.checked ? "debug_subscribe" : "debug_unsubscribe" });
    if (!el.checked) ui.raw = [];
    renderRaw();
  },
};

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el || el.tagName === "INPUT" || el.tagName === "SELECT") return;
  actions[el.dataset.act]?.(el.dataset);
});
document.addEventListener("change", (e) => {
  const el = e.target.closest("[data-act]");
  if (el) changes[el.dataset.act]?.(el);
});
$("sheet-backdrop").addEventListener("click", closeSheet);

function setView(view) {
  ui.view = view;
  for (const b of document.querySelectorAll(".tabs button")) b.classList.toggle("on", b.dataset.view === view);
  for (const v of ["matcher", "live", "installningar"]) $(`view-${v}`).hidden = v !== view;
  if (view === "matcher") (ui.games ? renderMatcher() : null, loadGames());
  if (view === "installningar") loadSettings();
  if (view === "live") renderLive();
}
for (const b of document.querySelectorAll(".tabs button")) b.addEventListener("click", () => setView(b.dataset.view));

// --- connection -----------------------------------------------------------------------

function renderConn() {
  const st = ui.status;
  const el = $("conn");
  el.classList.toggle("bad", ui.connection !== "open");
  if (ui.connection !== "open") return (el.textContent = "Ingen kontakt – försöker igen");
  const src = st?.source ?? {};
  const mode = { live: "Live", replay: `Repris ${src.speed}×`, recording: "Inspelning", none: "Ingen källa" }[src.mode] ?? "";
  el.textContent = `${mode}${st?.error ? " · fel" : ""}`;
}

async function loadProfiles() {
  const r = await fetch("/api/state").then((x) => x.json()).catch(() => null);
  if (r) ui.profiles = r.config.profiles;
}

store.on("state", renderLive);
store.on("patch", renderLive);
store.on("scene", renderLive);
store.on("config", () => loadProfiles().then(() => ui.view === "installningar" && renderSettings()));
store.on("status", (m) => {
  ui.status = m.status;
  renderConn();
  if (ui.view === "live") renderLive();
  if (ui.view === "installningar") renderAbout();
});
store.on("webhook", (m) => {
  ui.webhookLog.push(m.entry);
  if (ui.webhookLog.length > 50) ui.webhookLog.shift();
  renderHaLog();
});
store.on("raw_backlog", (m) => {
  ui.raw = [...(m.raw ?? [])];
  renderRaw();
});
store.on("raw", (m) => {
  ui.raw.push(m.entry);
  if (ui.raw.length > 300) ui.raw.shift();
  renderRaw();
});

socket = connect({
  role: "phone",
  id: "app",
  onMessage: (m) => store.handle(m),
  onStatus: (s) => {
    ui.connection = s;
    renderConn();
    if (s === "open" && ui.rawOn) socket?.send({ t: "debug_subscribe" });
  },
});
loadProfiles();
renderLive();
if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("sw.js").catch(() => {});
