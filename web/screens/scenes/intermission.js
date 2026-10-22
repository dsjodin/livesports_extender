// intermission (mockup scene 4, Phase 8): the left screen pages through our game's
// statistics, the right one through the evening's other games; 12 s a slide, the slide
// from the synced clock and the scene start, so both screens and any reload agree. The
// countdown is an estimate: the period's end on TV (the scene's play_at) plus the break,
// scaled by the replay speed.
import { compareRow, shotMap } from "../../shared/components.js";
import { caps, countdown, esc, html, percent, periodWord, raw, score, strengthChip } from "../../shared/format.js";
import { barPage, every, plainLogo, play, shortName, slideshow, statsLine, stopTimers } from "./common.js";
import { gameStatus, ticker } from "./ticker.js";

const BREAK_MS = 18 * 60_000;
const OVERTIME_BREAK_MS = 3 * 60_000; // assumption: a short pause before overtime

export function enter(ctx, data, at) {
  render(ctx);
  const tl = gsap.timeline({ paused: true });
  tl.from(ctx.root.querySelectorAll(".anim"), { y: 30, opacity: 0, duration: 0.45, ease: "power2.out", stagger: 0.07 });
  play(ctx, at, tl);
}

export function update(ctx) {
  render(ctx);
}

export function exit(ctx) {
  stopTimers(ctx);
}

export function ends(ctx) {
  const tv = ctx.tv;
  const start = tv.scene?.since_ms ?? ctx.now();
  const length = typeof tv.period === "number" && tv.period >= 3 ? OVERTIME_BREAK_MS : BREAK_MS;
  return start + length / (ctx.config.speed || 1);
}

function after(n) {
  return n === 1 ? "EFTER EN PERIOD" : `EFTER ${caps(periodWord(n))} PERIODER`;
}

function nextName(n) {
  return n >= 3 ? "FÖRLÄNGNING" : `PERIOD ${n + 1}`;
}

function render(ctx) {
  stopTimers(ctx);
  const tv = ctx.tv;
  const n = typeof tv.period === "number" ? tv.period : 1;
  if (ctx.kind === "bar") {
    const centre = html`<div class="label">PAUS</div><div class="mid">${nextName(n)} OM</div><div class="big-word gold" data-countdown></div>`;
    ctx.root.innerHTML = barPage(tv, { centre, strip: html`${after(n)} • ${statsLine(tv)}` });
    ticker(ctx, ctx.root.querySelector(".strip"), () => `${after(n)} • ${statsLine(ctx.tv)}`);
  } else {
    const slides = ctx.side === "home" ? ourSlides(tv, n) : otherSlides(tv);
    ctx.root.innerHTML = html`<div class="portrait-page inter-page"><div class="rule" style="--c: var(--${ctx.side})"></div>
      <div class="slides">${raw(slides.map((s, i) => `<section class="slide" data-i="${i}">${s}</section>`).join(""))}</div>
      <div class="inter-foot anim"><div class="dots">${raw(slides.map((_, i) => `<span data-dot="${i}"></span>`).join(""))}</div>
        <div class="card alt countdown-card"><div class="label">${nextName(n)} OM</div>
        <div class="big-line gold" data-countdown></div></div></div></div>`;
    slideshow(ctx, ctx.tv.scene?.since_ms ?? 0);
  }
  const els = ctx.root.querySelectorAll("[data-countdown]");
  if (els.length) every(ctx, 250, () => els.forEach((el) => (el.textContent = countdown(ends(ctx) - ctx.now()))));
}

// --- our game -------------------------------------------------------------------------
// Sized for 3 m (docs/SCREENS.md, Type): one subject a slide, nothing under --fs-floor.

export function savePct(g) {
  return g?.shots_against ? g.saves / g.shots_against : null;
}

/** Final statistics rows (postgame): shots, power play, penalty minutes, save %. */
export function comparison(tv, { perPeriod = true } = {}) {
  const h = tv.stats?.home ?? {};
  const a = tv.stats?.away ?? {};
  const rows = [];
  if (perPeriod) rows.push(...shotRows(tv));
  rows.push(compareRow("SKOTT PÅ MÅL", h.shots_on_goal ?? 0, a.shots_on_goal ?? 0));
  rows.push(compareRow("SKOTTFÖRSÖK", h.shot_attempts ?? 0, a.shot_attempts ?? 0));
  rows.push(compareRow("POWERPLAY", h.pp?.goals ?? 0, a.pp?.goals ?? 0, `${h.pp?.goals ?? 0}/${h.pp?.chances ?? 0}`, `${a.pp?.goals ?? 0}/${a.pp?.chances ?? 0}`));
  rows.push(compareRow("UTV.MIN", h.pim ?? 0, a.pim ?? 0));
  const hs = savePct(h.goalie);
  const as = savePct(a.goalie);
  rows.push(compareRow("RÄDDNINGSPROCENT", hs ?? 0, as ?? 0, percent(hs), percent(as)));
  return rows.join("");
}

function shotRows(tv) {
  const h = tv.stats?.home ?? {};
  const a = tv.stats?.away ?? {};
  const periods = Math.max(h.shots_by_period?.length ?? 0, a.shots_by_period?.length ?? 0);
  const rows = [];
  for (let i = 0; i < periods; i++) {
    rows.push(compareRow(i < 3 ? `SKOTT P${i + 1}` : "SKOTT ÖT", h.shots_by_period?.[i] ?? 0, a.shots_by_period?.[i] ?? 0));
  }
  return rows;
}

function head(label, title) {
  return html`<div class="slide-head"><div class="label">${label}</div><div class="slide-title">${title}</div></div>`;
}

function teamLine(tv, side, right = "") {
  return html`<div class="team-line">${raw(plainLogo(tv, side, "sm"))}<span class="tl-name">${caps(shortName(tv, side))}</span>${raw(right ? html`<span class="tl-right">${right}</span>` : "")}</div>`;
}

function duo(tv) {
  return html`<div class="duo3">${raw(teamLine(tv, "home"))}${raw(teamLine(tv, "away"))}</div>`;
}

const lastName = (p) => caps(p?.last ?? "");

function goalLine(tv, g) {
  const p = g.player;
  const chip = strengthChip(g.data?.strength, g.data?.empty_net);
  const who = p ? `#${p.number ?? ""} ${lastName(p)}` : "MÅL";
  const sc = g.data?.score ?? {};
  return html`<div class="row3" style="--c: var(--${g.side})"><div class="r3-main"><span class="r3-name">${who}</span><span class="r3-score">${score(sc.home, sc.away)}</span></div>
    <div class="r3-meta">P${g.period} ${g.time ?? ""} · ${g.team_code ?? ""}${chip ? ` · ${chip}` : ""}</div></div>`;
}

function penaltyLine(pen) {
  const p = pen.player;
  const shot = pen.data?.offence_code === "P-SHOT"; // a penalty shot awarded, no minutes
  const who = shot ? "STRAFFSLAG" : p ? `#${p.number ?? ""} ${lastName(p)}` : "LAGSTRAFF";
  const minutes = pen.data?.minutes ? `${pen.data.minutes} MIN` : "";
  const what = shot ? "" : ` · ${pen.data?.offence_text ?? ""}`;
  return html`<div class="row3" style="--c: var(--${pen.side})"><div class="r3-main"><span class="r3-name">${who}</span><span class="r3-score">${minutes}</span></div>
    <div class="r3-meta">P${pen.period} ${pen.time ?? ""} · ${pen.team_code ?? ""}${what}</div></div>`;
}

function goalsSlide(tv, label) {
  const goals = (tv.goals ?? []).filter((g) => !g.data?.shootout).slice(-6);
  return html`${raw(head(label, "MÅLEN"))}<div class="list3">${raw(goals.length ? goals.map((g) => goalLine(tv, g)).join("") : `<div class="empty3">Inga mål ännu</div>`)}</div>`;
}

function penaltiesSlide(tv, label) {
  const pens = (tv.penalties ?? []).slice(-6);
  return html`${raw(head(label, "UTVISNINGAR"))}<div class="list3">${raw(pens.length ? pens.map(penaltyLine).join("") : `<div class="empty3">Inga utvisningar</div>`)}</div>`;
}

function goalieBlock(tv, side) {
  const g = tv.stats?.[side]?.goalie;
  const pct = savePct(g);
  const name = g?.name ? `#${g.number ?? ""} ${caps((g.name ?? "").split(" ").slice(-1)[0])}` : "–";
  return html`<div class="goalie3">${raw(teamLine(tv, side))}<div class="g3-body"><div><div class="g3-name">${name}</div>
    <div class="r3-meta">${g?.saves ?? 0} räddningar</div></div><div class="g3-pct">${percent(pct)}</div></div></div>`;
}

function ourSlides(tv, n) {
  const h = tv.stats?.home ?? {};
  const a = tv.stats?.away ?? {};
  const label = after(n);
  const maps = ["home", "away"]
    .map((side) => html`<div class="map3">${raw(teamLine(tv, side, `${tv.stats?.[side]?.shots_on_goal ?? 0} SKOTT`))}${raw(shotMap(tv.shots?.[side], side))}</div>`)
    .join("");
  return [
    html`${raw(head(label, "SKOTT"))}${raw(duo(tv))}<div class="cmp-list3">${raw(shotRows(tv).join(""))}
      ${raw(compareRow("PÅ MÅL", h.shots_on_goal ?? 0, a.shots_on_goal ?? 0))}${raw(compareRow("FÖRSÖK", h.shot_attempts ?? 0, a.shot_attempts ?? 0))}</div>`,
    html`${raw(head(label, "SKOTTKARTOR"))}${raw(maps)}`,
    goalsSlide(tv, label),
    penaltiesSlide(tv, label),
    html`${raw(head(label, "MÅLVAKTER OCH SPECIAL TEAMS"))}${raw(goalieBlock(tv, "home"))}${raw(goalieBlock(tv, "away"))}
      <div class="cmp-list3">${raw(compareRow("POWERPLAY", h.pp?.goals ?? 0, a.pp?.goals ?? 0, `${h.pp?.goals ?? 0}/${h.pp?.chances ?? 0}`, `${a.pp?.goals ?? 0}/${a.pp?.chances ?? 0}`))}${raw(compareRow("UTV.MIN", h.pim ?? 0, a.pim ?? 0))}</div>`,
  ];
}

// --- the other games ------------------------------------------------------------------

function logo(t) {
  return t?.logo ? `<img class="logo3" src="${esc(t.logo)}" alt="" onerror="this.remove()">` : `<span class="logo3"></span>`;
}

function otherCard(o) {
  const live = !o.ended && o.phase !== "pregame";
  const status = `${gameStatus(o)}${o.last_game_time && live && o.phase !== "intermission" ? ` ${o.last_game_time}` : ""}`;
  return html`<div class="og3 ${live ? "live" : ""}">
    <div class="og3-team">${raw(logo(o.teams.home))}<span>${o.teams.home.code ?? ""}</span></div>
    <div class="og3-score">${o.phase === "pregame" ? "–" : score(o.score.home, o.score.away)}</div>
    <div class="og3-team away"><span>${o.teams.away.code ?? ""}</span>${raw(logo(o.teams.away))}</div>
    <div class="og3-status">${status}</div></div>`;
}

function tableSlide(rows, title) {
  const body = rows
    .map((r) => {
      const move = r.move > 0 ? `<span class="mv up">▲</span>` : r.move < 0 ? `<span class="mv down">▼</span>` : `<span class="mv"></span>`;
      const tonight = r.live ? `${r.live.for}–${r.live.against}` : "";
      return html`<div class="t3-row ${r.live ? "playing" : ""}"><span class="num">${r.rank}</span>${raw(move)}${raw(logo({ logo: r.logo }))}
        <span class="t3-team">${r.short ?? r.code}</span><span class="num t3-live">${tonight}</span><span class="num t3-pts">${r.points}</span></div>`;
    })
    .join("");
  return html`${raw(head("SHL", title))}<div class="table3"><div class="t3-row t3-head label"><span class="num">#</span><span></span><span></span><span>LAG</span><span class="num">IKVÄLL</span><span class="num">P</span></div>${raw(body)}</div>`;
}

/** Goals in the other games, three games a slide, the last four goals each. */
function goalsElsewhere(others) {
  const played = others.filter((o) => o.goals?.length);
  const slides = [];
  for (let i = 0; i < played.length; i += 3) {
    const cards = played
      .slice(i, i + 3)
      .map(
        (o) => html`<div class="og3-goals"><div class="og3-goals-head">${o.teams.home.code} ${score(o.score.home, o.score.away)} ${o.teams.away.code}</div>
          ${raw(o.goals.slice(-4).map((g) => html`<div class="og3-goal"><span>${typeof g.period === "number" ? `P${g.period} ` : ""}${g.time ?? ""}</span><b>${o.teams[g.side]?.code ?? ""}</b><span class="og3-who">${caps(g.last ?? "")}</span><span class="num">${score(g.score?.home, g.score?.away)}</span></div>`).join(""))}</div>`,
      )
      .join("");
    slides.push(html`${raw(head("KVÄLLENS ANDRA MATCHER", "MÅLSKYTTAR"))}${raw(cards)}`);
  }
  return slides;
}

function otherSlides(tv) {
  const others = tv.others ?? [];
  const slides = [];
  if (others.length) {
    slides.push(html`${raw(head("KVÄLLENS ANDRA MATCHER", "RESULTAT"))}<div class="list3">${raw(others.slice(0, 6).map(otherCard).join(""))}</div>`);
  } else {
    // nobody else plays tonight: our goals and penalties instead
    slides.push(goalsSlide(tv, "MATCHEN"), penaltiesSlide(tv, "MATCHEN"));
  }
  if (tv.live_table) slides.push(tableSlide(tv.live_table, "OM MATCHERNA SLUTADE NU"));
  else if (tv.league?.standings?.length) slides.push(tableSlide(tv.league.standings, "TABELL"));
  slides.push(...goalsElsewhere(others));
  return slides;
}
