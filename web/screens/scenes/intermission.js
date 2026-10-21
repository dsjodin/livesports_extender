// intermission (mockup scene 4, Phase 8): the left screen pages through our game's
// statistics, the right one through the evening's other games; 12 s a slide, the slide
// from the synced clock and the scene start, so both screens and any reload agree. The
// countdown is an estimate: the period's end on TV (the scene's play_at) plus the break,
// scaled by the replay speed.
import { badge, compareRow, goalieCard, goalRow, penaltyRow, shotMap } from "../../shared/components.js";
import { caps, countdown, esc, html, percent, periodWord, raw, score } from "../../shared/format.js";
import { barPage, every, ordinal, play, statsLine, stopTimers, team } from "./common.js";
import { gameStatus, ticker } from "./ticker.js";

const BREAK_MS = 18 * 60_000;
const OVERTIME_BREAK_MS = 3 * 60_000; // assumption: a short pause before overtime
const SLIDE_MS = 12_000;

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
        <div class="card alt countdown-card"><div class="label">${n >= 3 ? "FÖRLÄNGNING" : `${caps(ordinal(n + 1))} PERIODEN`} STARTAR OM</div>
        <div class="big-line gold" data-countdown></div></div></div></div>`;
    rotate(ctx, slides.length);
  }
  const els = ctx.root.querySelectorAll("[data-countdown]");
  if (els.length) every(ctx, 250, () => els.forEach((el) => (el.textContent = countdown(ends(ctx) - ctx.now()))));
}

/** Show one slide at a time; cross-fade when the clock says the next one is due. */
function rotate(ctx, count) {
  const slides = [...ctx.root.querySelectorAll(".slide")];
  const dots = [...ctx.root.querySelectorAll("[data-dot]")];
  const start = ctx.tv.scene?.since_ms ?? 0;
  let current = null;
  const pick = () => Math.floor(Math.max(0, ctx.now() - start) / SLIDE_MS) % count;
  const show = (i, animate) => {
    slides.forEach((el, j) => {
      gsap.killTweensOf(el);
      if (j === i) {
        if (animate) gsap.fromTo(el, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" });
        else gsap.set(el, { opacity: 1, y: 0 });
      } else if (j === current && animate) {
        gsap.to(el, { opacity: 0, duration: 0.35, ease: "power1.out" });
      } else {
        gsap.set(el, { opacity: 0 });
      }
    });
    dots.forEach((d, j) => d.classList.toggle("on", j === i));
    current = i;
  };
  show(pick(), false);
  every(ctx, 250, () => {
    const i = pick();
    if (i !== current) show(i, true);
  });
}

// --- our game -------------------------------------------------------------------------

function duo(tv) {
  return html`<div class="duo"><div class="team">${raw(badge(team(tv, "home"), "home", "sm"))}${team(tv, "home").short ?? ""}</div>
    <div class="team">${team(tv, "away").short ?? ""}${raw(badge(team(tv, "away"), "away", "sm"))}</div></div>`;
}

export function savePct(g) {
  return g?.shots_against ? g.saves / g.shots_against : null;
}

export function comparison(tv, { perPeriod = true } = {}) {
  const h = tv.stats?.home ?? {};
  const a = tv.stats?.away ?? {};
  const rows = [];
  if (perPeriod) {
    const periods = Math.max(h.shots_by_period?.length ?? 0, a.shots_by_period?.length ?? 0);
    for (let i = 0; i < periods; i++) {
      rows.push(compareRow(`SKOTT P${i + 1}`, h.shots_by_period?.[i] ?? 0, a.shots_by_period?.[i] ?? 0));
    }
  }
  rows.push(compareRow("SKOTT PÅ MÅL", h.shots_on_goal ?? 0, a.shots_on_goal ?? 0));
  rows.push(compareRow("SKOTTFÖRSÖK", h.shot_attempts ?? 0, a.shot_attempts ?? 0));
  rows.push(compareRow("POWERPLAY", h.pp?.goals ?? 0, a.pp?.goals ?? 0, `${h.pp?.goals ?? 0}/${h.pp?.chances ?? 0}`, `${a.pp?.goals ?? 0}/${a.pp?.chances ?? 0}`));
  rows.push(compareRow("UTV.MIN", h.pim ?? 0, a.pim ?? 0));
  const hs = savePct(h.goalie);
  const as = savePct(a.goalie);
  rows.push(compareRow("RÄDDNINGSPROCENT", hs ?? 0, as ?? 0, percent(hs), percent(as)));
  return rows.join("");
}

function head(label, title) {
  return html`<div><div class="label">${label}</div><div class="section-title">${title}</div></div>`;
}

function goalsAndPenalties(tv) {
  const goals = (tv.goals ?? []).slice(-5);
  const pens = (tv.penalties ?? []).slice(-7);
  return html`<div class="list">${raw(goals.length ? goals.map((g) => goalRow(g)).join("") : `<div class="secondary body-text">Inga mål ännu</div>`)}</div>
    <div class="list"><div class="label">UTVISNINGAR</div>${raw(pens.length ? pens.map((p) => penaltyRow(p)).join("") : `<div class="secondary body-text">Inga utvisningar</div>`)}</div>`;
}

function ourSlides(tv, n) {
  const h = tv.stats?.home ?? {};
  const a = tv.stats?.away ?? {};
  const maps = ["home", "away"]
    .map(
      (side) => html`<div class="map-pair"><div class="map-title">${raw(badge(team(tv, side), side, "sm"))}<span>${team(tv, side).short ?? ""}</span>
        <span class="muted">${tv.stats?.[side]?.shots_on_goal ?? 0} skott på mål</span></div>${raw(shotMap(tv.shots?.[side], side))}</div>`,
    )
    .join("");
  const goalies = ["home", "away"]
    .map(
      (side) => html`<div class="goalie-pair"><div class="map-title">${raw(badge(team(tv, side), side, "sm"))}<span>${team(tv, side).short ?? ""}</span></div>
        ${raw(goalieCard(tv.stats?.[side]?.goalie))}</div>`,
    )
    .join("");
  return [
    html`${raw(head(after(n), "PERIODSTATISTIK"))}${raw(duo(tv))}<div class="list cmp-list">${raw(comparison(tv))}</div>`,
    html`${raw(head(after(n), "SKOTTKARTOR"))}${raw(maps)}`,
    html`${raw(head(after(n), "MÅL OCH UTVISNINGAR"))}${raw(goalsAndPenalties(tv))}`,
    html`${raw(head(after(n), "MÅLVAKTER OCH SPECIALLAG"))}${raw(goalies)}
      <div class="list cmp-list">${raw(compareRow("POWERPLAYMÅL", h.pp?.goals ?? 0, a.pp?.goals ?? 0))}${raw(compareRow("POWERPLAYCHANSER", h.pp?.chances ?? 0, a.pp?.chances ?? 0))}${raw(compareRow("UTVISNINGSMINUTER", h.pim ?? 0, a.pim ?? 0))}</div>`,
  ];
}

// --- the other games ------------------------------------------------------------------

function logo(t) {
  return t?.logo ? `<img class="logo-xs" src="${esc(t.logo)}" alt="" onerror="this.remove()">` : `<span class="logo-xs"></span>`;
}

function otherCard(o) {
  const live = !o.ended && o.phase !== "pregame";
  const sh = o.stats?.home?.shots_on_goal ?? 0;
  const sa = o.stats?.away?.shots_on_goal ?? 0;
  return html`<div class="other-game ${live ? "live" : ""}">
    <div class="og-team">${raw(logo(o.teams.home))}<span>${o.teams.home.short ?? o.teams.home.code}</span></div>
    <div class="og-score">${o.phase === "pregame" ? "–" : score(o.score.home, o.score.away)}</div>
    <div class="og-team away"><span>${o.teams.away.short ?? o.teams.away.code}</span>${raw(logo(o.teams.away))}</div>
    <div class="og-meta"><span class="og-status">${gameStatus(o)}${o.last_game_time && live ? ` ${o.last_game_time}` : ""}</span>${raw(o.phase === "pregame" ? "" : html`<span class="muted">Skott ${score(sh, sa)}</span>`)}</div></div>`;
}

function tableSlide(rows, title) {
  const body = rows
    .map((r) => {
      const move = r.move > 0 ? `<span class="mv up">▲${r.move}</span>` : r.move < 0 ? `<span class="mv down">▼${-r.move}</span>` : `<span class="mv"></span>`;
      const tonight = r.live ? `${r.live.for}–${r.live.against}${r.live.ended ? "" : " •"}` : "";
      return html`<div class="table-row ${r.live ? "playing" : ""}"><span class="num">${r.rank}</span>${raw(move)}${raw(logo({ logo: r.logo }))}
        <span class="team-cell">${r.short ?? r.code}</span><span class="num live-score">${tonight}</span><span class="num">${r.gp}</span><span class="num strong">${r.points}</span></div>`;
    })
    .join("");
  return html`${raw(head("SHL", title))}<div class="list table-live"><div class="table-row head label"><span class="num">#</span><span></span><span></span><span>LAG</span><span class="num">IKVÄLL</span><span class="num">M</span><span class="num">P</span></div>${raw(body)}</div>`;
}

function goalsElsewhere(others) {
  const played = others.filter((o) => o.goals?.length);
  if (!played.length) return "";
  const cards = played
    .slice(0, 4)
    .map(
      (o) => html`<div class="og-goals"><div class="og-goals-head">${o.teams.home.code} ${score(o.score.home, o.score.away)} ${o.teams.away.code}</div>
        ${raw(o.goals.slice(-4).map((g) => html`<div class="og-goal"><span class="muted">P${g.period} ${g.time ?? ""}</span><b>${o.teams[g.side]?.code ?? ""}</b><span>${g.number ? `#${g.number} ` : ""}${g.last ?? ""}</span><span class="og-goal-score">${score(g.score?.home, g.score?.away)}</span></div>`).join(""))}</div>`,
    )
    .join("");
  return html`${raw(head("KVÄLLENS ANDRA MATCHER", "MÅLSKYTTAR"))}${raw(cards)}`;
}

function otherSlides(tv) {
  const others = tv.others ?? [];
  const slides = [];
  if (others.length) {
    slides.push(html`${raw(head("KVÄLLENS ANDRA MATCHER", "RESULTAT"))}<div class="list">${raw(others.map(otherCard).join(""))}</div>`);
  } else {
    // nobody else plays tonight: our goals and penalties instead
    slides.push(html`${raw(head("MATCHEN", "MÅL OCH UTVISNINGAR"))}${raw(goalsAndPenalties(tv))}`);
  }
  if (tv.live_table) slides.push(tableSlide(tv.live_table, "OM MATCHERNA SLUTADE NU"));
  else if (tv.league?.standings?.length) slides.push(tableSlide(tv.league.standings, "TABELL"));
  const scorers = goalsElsewhere(others);
  if (scorers) slides.push(scorers);
  return slides;
}
