// The menu on OK (docs/TV_APP.md, Remote): the remote has only arrows, OK and Back, so
// everything the phone app does during a game is here. A list low on the left, over the
// picture: ↑ ↓ move, OK chooses, Back closes. It opens on "MÅL! <my team>" in play, so
// OK, OK is a goal (the two presses decided 2026-10-31); before the game and in the breaks
// on "Synka nedsläpp"; else on "Statistik". Matcher, Synk and Inställningar
// open a sheet to the right of the list. The schedule carries live scores straight from
// shl.se, so the game list shows times and teams only (CLAUDE.md rule 1).
import { caps, decimal, esc, hhmm, html, raw } from "../shared/format.js";

const IDLE_CLOSE_MS = 30_000;
const STATE = { "pre-game": "", live: "PÅGÅR", "post-game": "SLUT" };

let list = null; // the menu's element
let sheet = null; // the open sheet's element
let items = []; // [{id, label, run}]
let at = 0;
let sheetRows = null; // the open sheet's selectable rows [{label, run}], or null
let sheetAt = 0;
let timer = null;
let d = null; // what the overlay lends: tv(), api(), panels, say(), full(), setFull(), lframe(), host

export function create(parent, deps) {
  d = deps;
  list = document.createElement("section");
  list.className = "tv-menu";
  sheet = document.createElement("section");
  sheet.className = "tv-sheet";
  parent.append(list, sheet);
}

export const isOpen = () => list?.classList.contains("on");

function inPlay() {
  return ["live", "goal"].includes(d.scene());
}

function teamName(side) {
  const t = d.tv()?.teams?.[side] ?? {};
  return caps(t.short ?? t.code ?? (side === "home" ? "Hemma" : "Borta"));
}

function build() {
  const tv = d.tv();
  const out = [];
  if (tv?.game?.uuid) {
    const mine = tv.game.my_side;
    const sides = mine === "away" ? ["away", "home"] : ["home", "away"];
    for (const side of sides) out.push({ id: `goal-${side}`, label: `MÅL! ${teamName(side)}`, side, run: () => goal(side) });
    out.push({ id: "sync", label: "Synka nedsläpp", run: syncNow });
  }
  out.push({ id: "stats", label: "Statistik", run: () => d.panels.open("stats") });
  out.push({ id: "shots", label: "Skottkarta", run: () => d.panels.open("shots") });
  out.push({ id: "table", label: "Tabell", run: () => d.panels.open("table") });
  out.push({ id: "games", label: "Kvällens matcher", run: () => d.panels.open("games") });
  if (d.lframe()) out.push({ id: "full", label: d.full() ? "Tillbaka till L-ram" : "Helbild", run: () => d.setFull(!d.full()) });
  out.push({ id: "matcher", label: "Matcher", sheet: matcherSheet });
  out.push({ id: "synk", label: "Synk", sheet: syncSheet });
  out.push({ id: "settings", label: "Inställningar", sheet: settingsSheet });
  return out;
}

export function open() {
  items = build();
  // Where OK, OK lands: a goal in play; the puck-drop sync before the game and in the
  // breaks (the next drop is what comes); the games when nothing is on. Never a change of
  // game by two presses.
  const mine = d.tv()?.game?.my_side;
  const scene = d.scene();
  const first = inPlay() ? `goal-${mine === "away" ? "away" : "home"}` : ["pregame", "intermission"].includes(scene) ? "sync" : "stats";
  at = Math.max(0, items.findIndex((i) => i.id === first));
  closeSheet();
  render();
  list.classList.add("on");
  gsap.fromTo(list, { opacity: 0, x: -40 }, { opacity: 1, x: 0, duration: 0.25, ease: "power2.out" });
  touch();
}

export function close() {
  clearTimeout(timer);
  closeSheet();
  if (!isOpen()) return;
  list.classList.remove("on");
  gsap.to(list, { opacity: 0, x: -40, duration: 0.2 });
}

function touch() {
  clearTimeout(timer);
  timer = setTimeout(close, IDLE_CLOSE_MS);
}

function render() {
  list.innerHTML = items
    .map((item, i) => {
      const side = item.side ? ` style="--c: var(--${item.side}); --on: var(--on-${item.side})"` : "";
      const cls = ["tv-item", i === at ? "on" : "", item.side ? "goal" : "", item.sheet ? "more" : ""].filter(Boolean).join(" ");
      return `<div class="${cls}"${side}>${esc(item.label)}</div>`;
    })
    .join("");
}

/** A key while the menu is open; true when it was used. */
export function key(k) {
  if (!isOpen()) return false;
  touch();
  if (sheetRows) return sheetKey(k);
  if (k === "up" || k === "down") {
    at = (at + (k === "up" ? items.length - 1 : 1)) % items.length;
    render();
  } else if (k === "ok" || k === "right") {
    const item = items[at];
    if (item.sheet) return openSheet(item.sheet), true;
    if (k === "ok") {
      close();
      item.run();
    }
  } else if (k === "back" || k === "left") {
    close();
  }
  return true;
}

// ---- actions ------------------------------------------------------------------------------

async function goal(side) {
  try {
    await d.api("goal", { side });
    d.say(`MÅL! ${teamName(side)}`);
  } catch (err) {
    d.say(`MÅL! gick inte: ${err.message}`);
  }
}

/** A puck-drop sync sample now (the menu, or play/pause straight away). */
export async function syncNow() {
  if (!d.tv()?.game?.uuid) return d.say("Ingen match vald");
  try {
    const r = await d.api("calibrate", { kind: "period_start" });
    const proposal = r.proposal_s != null ? ` · förslag ${decimal(r.proposal_s)} s` : "";
    d.say(`Nedsläpp registrerat${proposal}`);
  } catch (err) {
    d.say(`Synk gick inte: ${err.message}`);
  }
}

// ---- sheets -------------------------------------------------------------------------------

async function openSheet(make) {
  sheetRows = [];
  sheetAt = 0;
  sheet.innerHTML = `<div class="tv-empty">Hämtar…</div>`;
  sheet.classList.add("on");
  try {
    await make();
  } catch (err) {
    sheet.innerHTML = html`<div class="tv-empty">Gick inte att hämta: ${err.message}</div>`;
  }
}

function closeSheet() {
  sheetRows = null;
  sheet?.classList.remove("on");
}

/** Show a sheet: a title, text above the rows, and rows OK can choose. */
function showSheet(title, intro, rows) {
  sheetRows = rows;
  sheetAt = Math.min(sheetAt, Math.max(0, rows.length - 1));
  const body = rows
    .map((r, i) => `<div class="tv-item${i === sheetAt ? " on" : ""}${r.quiet ? " quiet" : ""}">${esc(r.label)}${r.note ? `<small>${esc(r.note)}</small>` : ""}</div>`)
    .join("");
  sheet.innerHTML = html`<div class="tv-sheet-title">${title}</div>${raw(intro)}<div class="tv-sheet-rows">${raw(body)}</div>`;
}

function sheetKey(k) {
  if (k === "up" || k === "down") {
    if (sheetRows.length) sheetAt = (sheetAt + (k === "up" ? sheetRows.length - 1 : 1)) % sheetRows.length;
    sheet.querySelectorAll(".tv-sheet-rows .tv-item").forEach((el, i) => el.classList.toggle("on", i === sheetAt));
  } else if (k === "ok") {
    sheetRows[sheetAt]?.run?.();
  } else if (k === "back" || k === "left") {
    closeSheet();
  }
  return true;
}

async function matcherSheet() {
  const [{ games }, state] = await Promise.all([d.api("schedule?days=0", null, "GET"), d.api("state", null, "GET")]);
  const followed = state.status?.game_uuid;
  const rows = games.map((g) => {
    const live = g.state === "post-game" ? "replay" : "live";
    const what = live === "replay" ? "repris" : "följ";
    return {
      label: `${hhmm(g.start_ms)}  ${g.home.code ?? ""}–${g.away.code ?? ""}`,
      note: [STATE[g.state] ?? "", g.uuid === followed ? "FÖLJS" : what].filter(Boolean).join(" · "),
      run: () => follow(g.uuid, live),
    };
  });
  if (followed) rows.push({ label: "Sluta följa", run: stopFollowing });
  showSheet("MATCHER IDAG", games.length ? "" : `<div class="tv-empty">Inga matcher idag</div>`, rows);
}

async function follow(uuid, mode) {
  close();
  d.say(mode === "live" ? "Följer matchen…" : "Startar repris…");
  try {
    await d.api("source", mode === "live" ? { mode, uuid } : { mode, uuid, speed: 1 });
    await d.api("game", { uuid, my_side: null }); // my side follows my team
  } catch (err) {
    d.say(`Gick inte: ${err.message}`);
  }
}

async function stopFollowing() {
  close();
  try {
    await d.api("source", { mode: "none" });
    await d.api("game", { uuid: null, my_side: null });
    d.say("Följer ingen match");
  } catch (err) {
    d.say(`Gick inte: ${err.message}`);
  }
}

async function syncSheet() {
  const c = await d.api("calibrate", null, "GET");
  const samples = (c.samples ?? []).slice(-4).reverse();
  const lines = samples.map((s) => `${esc(KIND[s.kind] ?? s.kind)}${s.sample_s != null ? ` · ${decimal(s.sample_s)} s` : " · väntar på SHL"}`).join("<br>");
  const intro = html`<div class="tv-sheet-text">TV-profil ${caps(c.profile ?? "")} · fördröjning <b>${decimal(c.current_offset_s)} s</b><br>
    ${c.proposal_s != null ? `Förslag ${decimal(c.proposal_s)} s av ${c.proposal_samples} prov` : "Inget förslag ännu"}</div>
    ${raw(lines ? `<div class="tv-sheet-text quiet">${lines}</div>` : "")}`;
  const again = () => syncSheet().catch((err) => d.say(err.message));
  const rows = [
    { label: "Synka nedsläpp nu", run: () => syncNow().then(again) },
    ...(c.proposal_s != null ? [{ label: `Använd förslaget ${decimal(c.proposal_s)} s`, run: () => d.api("calibrate/accept", {}).then(again) }] : []),
    { label: "+0,5 s", run: () => d.api("offset/nudge", { delta: 0.5 }).then(again) },
    { label: "−0,5 s", run: () => d.api("offset/nudge", { delta: -0.5 }).then(again) },
    ...(samples.length ? [{ label: "Rensa proven", run: () => d.api("calibrate", null, "DELETE").then(again) }] : []),
  ];
  showSheet("SYNK", intro, rows);
}

const KIND = { period_start: "Nedsläpp", goal: "Mål", penalty: "Utvisning", timeout: "Timeout", shot_on_goal: "Skott" };

async function settingsSheet() {
  const state = await d.api("state", null, "GET");
  const profiles = Object.keys(state.config?.profiles ?? {});
  const active = state.config?.active_profile;
  const next = profiles[(profiles.indexOf(active) + 1) % profiles.length];
  const again = () => settingsSheet().catch((err) => d.say(err.message));
  const shell = d.host.info();
  const rows = [
    { label: `TV-profil: ${caps(active ?? "")}`, note: profiles.length > 1 ? `OK byter till ${caps(next)}` : "", run: () => d.api("profile", { profile: next }).then(again) },
    {
      label: `Följ mitt lag automatiskt: ${state.config?.follow_my_team ? "på" : "av"}`,
      note: "mitt lags match idag följs av sig själv",
      run: () => d.api("follow", { enabled: !state.config?.follow_my_team }).then(again),
    },
    {
      label: `Rutor över bilden: ${Math.round(d.cover() * 100)} % täckning`,
      note: "OK byter: 97, 94, 90, 85, 80, 70, 60, 100 %",
      run: () => (d.nextCover(), again()),
    },
    { label: "Server och HDMI", note: "skalets inställningar", run: () => (close(), d.host.openSetup()) },
    { label: "Testsidan", note: "kontroll av TV:n", run: () => d.api("tv/probe-mode", { enabled: true }) },
  ];
  const saver = shell?.screen_saver ? `<br>Skärmsläckare: ${esc(shell.screen_saver)}` : "";
  const n = d.nudges?.();
  const woken = n?.count ? `<br>Väckknappar: ${n.count}, senast ${hhmm(n.at)} (${esc(n.key)})` : "";
  const about = `<div class="tv-sheet-text quiet">SHL live! · skal ${esc(shell?.version ?? "–")}${shell?.model ? ` · ${esc(shell.model)}` : ""}<br>${esc(d.host.base)}${saver}${woken}</div>`;
  showSheet("INSTÄLLNINGAR", about, rows);
}
