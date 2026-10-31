// pregame on the TV (L-frame): the column pages through the teams' standings and form,
// each team's scoring leaders and the last meetings, 12 s a slide; the band holds the
// matchup and the time to puck drop (from tv.league, delayed like everything else).
import { caps, countdown, dayLabel, decimal, hhmm, html, raw } from "../../shared/format.js";
import { empty, every, head, lframe, ordinal, play, row, scoreboard, shortName, slideshow, slides, stopTimers } from "./common.js";

const COUNTDOWN_FROM_MS = 60 * 60_000;
const NOTE = { övertid: "ÖT", straffar: "STR" };
const MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];

export function enter(ctx, data, at) {
  render(ctx);
  const tl = gsap.timeline({ paused: true });
  tl.from(ctx.root.querySelectorAll(".tv-col, .tv-band"), { opacity: 0, y: 30, duration: 0.5, ease: "power2.out", stagger: 0.1 });
  play(ctx, at, tl);
}

export function update(ctx) {
  render(ctx);
}

export function exit(ctx) {
  stopTimers(ctx);
}

/** Puck drop as seen on TV: the scheduled start plus the TV's delay. */
export function dropOnTv(ctx) {
  const start = ctx.tv.game?.start_ms;
  return start == null ? null : start + (ctx.config.offset_ms ?? 0);
}

const signed = (n) => (n == null ? "–" : n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0");

function render(ctx) {
  stopTimers(ctx);
  const tv = ctx.tv;
  const league = tv.league ?? {};
  const teams = league.teams ?? {};
  const list = [standing(tv, teams)];
  for (const side of ["home", "away"]) {
    const leaders = teams[side]?.leaders?.points;
    if (leaders?.length) list.push(leaderSlide(tv, side, leaders));
  }
  if (league.head_to_head?.games?.length) list.push(h2h(tv, league.head_to_head));
  const start = tv.game?.start_ms;
  const band = html`${raw(scoreboard(tv, { middle: `<span class="tvb-vs">–</span>` }))}
    <div class="pg-when"><span class="tv-label" data-when>${start ? dayLabel(start, ctx.now()) : ""}</span>
      <span class="pg-time" data-time>${start ? hhmm(start) : "–"}</span><span class="pg-arena">${tv.game?.arena ?? ""}</span></div>`;
  ctx.root.innerHTML = lframe(slides(list), band, "pregame");
  slideshow(ctx, tv.scene?.since_ms ?? 0);
  const when = ctx.root.querySelector("[data-when]");
  const time = ctx.root.querySelector("[data-time]");
  every(ctx, 250, () => {
    const drop = dropOnTv(ctx);
    if (drop == null) return;
    const left = drop - ctx.now();
    if (left < COUNTDOWN_FROM_MS) {
      when.textContent = left > 0 ? "NEDSLÄPP OM" : "NEDSLÄPP";
      time.textContent = left > 0 ? countdown(left) : "STRAX";
      time.classList.add("gold");
    }
  });
}

/** Both teams side by side: place, points, goal difference, goals a game, the last five. */
function standing(tv, teams) {
  const cell = (side) => {
    const b = teams[side] ?? {};
    const form = (b.form ?? []).map((f) => `<span class="form-chip ${f.result === "V" ? "won" : "lost"}">${f.result}</span>`).join("");
    return html`<div class="st-team" style="--c: var(--${side})"><div class="st-name">${caps(shortName(tv, side))}</div>
      <div class="st-big">${b.rank ? caps(ordinal(b.rank)) : "–"}</div>
      <div class="st-line"><span>POÄNG</span><b>${b.points ?? "–"}</b></div>
      <div class="st-line"><span>MÅL +/−</span><b>${signed(b.diff)}</b></div>
      <div class="st-line"><span>MÅL/MATCH</span><b>${decimal(b.gf_per_game)}–${decimal(b.ga_per_game)}</b></div>
      <div class="st-form">${raw(form || "–")}</div></div>`;
  };
  return html`${raw(head("INFÖR MATCHEN", "TABELLÄGET"))}<div class="st-duo">${raw(cell("home"))}${raw(cell("away"))}</div>
    <div class="tvr-meta">Plats i tabellen och de fem senaste matcherna (V vinst, F förlust).</div>`;
}

/** A team's top three by points: the leader with a portrait. */
function leaderSlide(tv, side, rows) {
  const [first, ...rest] = rows;
  const portrait = first.portrait ? html`<img class="ld-img" src="${first.portrait}" alt="" onerror="this.remove()">` : "";
  const detail = (r) => `${r.g ?? 0} MÅL · ${r.a ?? 0} ASSIST`;
  return html`${raw(head(caps(shortName(tv, side)), "POÄNGLIGA"))}
    <div class="ld-card" style="--c: var(--${side})">${raw(portrait)}<div class="ld-text">
      <div class="ld-first">${first.number != null ? `#${first.number} ` : ""}${first.first ?? ""}</div>
      <div class="ld-last" data-fit>${caps(first.last ?? "")}</div>
      <div class="ld-value">${first.tp ?? 0}<span> POÄNG</span></div><div class="tvr-meta">${detail(first)}</div></div></div>
    ${raw(rest.map((r) => row(`${r.number != null ? `#${r.number} ` : ""}${caps(r.last ?? "")}`, r.tp ?? 0, detail(r))).join(""))}`;
}

function h2h(tv, data) {
  const home = tv.teams?.home?.uuid;
  const date = (iso) => {
    const [y, m, d] = (iso ?? "").split("-").map(Number);
    return y ? `${d} ${MONTHS[m - 1]} ${y}` : "";
  };
  const rows = data.games
    .map((g) => {
      const winner = g.winner_uuid === home ? "home" : "away";
      const meta = [date(g.date), g.note ? (NOTE[g.note] ?? g.note) : null, g.playoff ? "SLUTSPEL" : null].filter(Boolean).join(" · ");
      return row(`${g.home} ${g.score} ${g.away}`, "", meta, winner);
    })
    .join("");
  return html`${raw(head(`SENASTE ${data.games.length}`, "INBÖRDES MÖTEN"))}
    <div class="h2h-wins"><span>${caps(shortName(tv, "home"))} <b>${data.wins?.home ?? 0}</b></span><span class="tv-label">VINSTER</span>
      <span><b>${data.wins?.away ?? 0}</b> ${caps(shortName(tv, "away"))}</span></div>
    ${raw(rows || empty("Inga möten"))}`;
}
