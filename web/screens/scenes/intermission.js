// intermission (mockup scene 4). The countdown is an estimate: the period's end on TV
// (the scene's play_at) plus the break, scaled by the replay speed.
import { badge, compareRow, goalRow, penaltyRow } from "../../shared/components.js";
import { caps, countdown, html, percent, periodWord, raw, score } from "../../shared/format.js";
import { barPage, every, ordinal, play, statsLine, stopTimers, team } from "./common.js";

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
  } else if (ctx.side === "home") {
    ctx.root.innerHTML = stats(tv, n);
  } else {
    ctx.root.innerHTML = lists(tv, n);
  }
  const els = ctx.root.querySelectorAll("[data-countdown]");
  if (els.length) every(ctx, 250, () => els.forEach((el) => (el.textContent = countdown(ends(ctx) - ctx.now()))));
}

function duo(tv) {
  return html`<div class="duo anim"><div class="team">${raw(badge(team(tv, "home"), "home", "sm"))}${team(tv, "home").short ?? ""}</div>
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
  return rows.map((r) => r.replace('class="cmp"', 'class="cmp anim"')).join("");
}

function stats(tv, n) {
  return html`<div class="portrait-page"><div class="rule" style="--c: var(--home)"></div>
    <div class="anim"><div class="label">${after(n)}</div><div class="section-title">PERIODSTATISTIK</div></div>
    ${raw(duo(tv))}<div class="list cmp-list">${raw(comparison(tv))}</div></div>`;
}

function lists(tv, n) {
  const goals = (tv.goals ?? []).slice(-5);
  const pens = (tv.penalties ?? []).slice(-8);
  return html`<div class="portrait-page"><div class="rule" style="--c: var(--away)"></div>
    <div class="list anim"><div class="label">MÅLEN</div>
      ${raw(goals.length ? goals.map((g) => goalRow(g)).join("") : `<div class="secondary body-text">Inga mål ännu</div>`)}</div>
    <div class="list anim"><div class="label">UTVISNINGAR</div>
      ${raw(pens.length ? pens.map((p) => penaltyRow(p)).join("") : `<div class="secondary body-text">Inga utvisningar</div>`)}</div>
    <div class="card alt anim bottom-card"><div class="label">${n >= 3 ? "FÖRLÄNGNING" : `${caps(ordinal(n + 1))} PERIODEN`} · STARTAR OM</div>
      <div class="big-line gold" data-countdown></div><div class="secondary">Ställning ${score(tv.score?.home, tv.score?.away)}</div></div></div>`;
}
