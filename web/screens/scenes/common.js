// Pieces shared by the scene modules.
import { badge } from "../../shared/components.js";
import { caps, DASH, html, periodName, raw, score, thousands } from "../../shared/format.js";

export const other = (side) => (side === "home" ? "away" : "home");
export const team = (tv, side) => tv?.teams?.[side] ?? {};
export const shortName = (tv, side) => team(tv, side).short ?? team(tv, side).code ?? (side === "home" ? "Hemma" : "Borta");
export const longName = (tv, side) => team(tv, side).long ?? shortName(tv, side);

/** Start a paused GSAP timeline as if it began at play_at (jumping ahead if we are late).
 * Without animation (a fresh state on connect) it goes straight to its end. */
export function play(ctx, at, tl) {
  if (!ctx.animate) return tl.progress(1);
  tl.time(Math.max(0, ctx.now() - at) / 1000, false); // callbacks we jumped over still run
  return tl.play();
}

/** Re-run fn every ms while the scene is shown (countdowns, the idle clock). */
export function every(ctx, ms, fn) {
  fn();
  const id = setInterval(fn, ms);
  ctx.timers = [...(ctx.timers ?? []), id];
}

export function stopTimers(ctx) {
  (ctx.timers ?? []).forEach(clearInterval);
  ctx.timers = [];
}

/** Portrait header: team-colour rule, badge, "HEMMA"/"BORTA", long name. */
export function teamHead(tv, side, extraClass = "") {
  return html`<div class="rule" style="--c: var(--${side}); --ol: var(--${side}-outline)"></div>
    <div class="team-head ${extraClass}">${raw(badge(team(tv, side), side, "lg"))}
    <div><div class="label">${side === "home" ? "HEMMA" : "BORTA"}</div><div class="team-name">${longName(tv, side)}</div></div></div>`;
}

/** One half of the bar's main row. `value` goes in the score box, `sub` under it. */
export function barTeam(tv, side, value, { sub = "", flash = false, id = "" } = {}) {
  return html`<div class="bar-team ${side}" style="--c: var(--${side})"><div class="edge"></div>
    ${raw(badge(team(tv, side), side, "md"))}<div class="bar-name">${caps(shortName(tv, side))}</div>
    <div class="score-box ${flash ? "flash" : ""}" ${raw(id ? `id="${id}"` : "")}><div class="digits ${String(value).length > 1 ? "narrow" : ""}">${value}</div>${raw(sub ? `<div class="sub label">${sub}</div>` : "")}</div></div>`;
}

export function barPage(tv, { home, away, centre, strip, stripClass = "" }) {
  return html`<div class="bar-page"><div class="bar-main">${raw(home ?? barTeam(tv, "home", tv.score?.home ?? 0))}
    <div class="bar-centre">${raw(centre)}</div>${raw(away ?? barTeam(tv, "away", tv.score?.away ?? 0))}</div>
    <div class="strip ${stripClass}">${raw(strip ?? "")}</div></div>`;
}

/** "SKOTT 36–26 • UTV.MIN 2–6" */
export function statsLine(tv) {
  const s = tv.stats ?? {};
  return `SKOTT ${score(s.home?.shots_on_goal, s.away?.shots_on_goal)} • UTV.MIN ${score(s.home?.pim, s.away?.pim)}`;
}

export function venueLine(tv) {
  const g = tv.game ?? {};
  const parts = [g.arena, g.attendance ? `${thousands(g.attendance)} ÅSKÅDARE` : null].filter(Boolean);
  return parts.join(" · ");
}

export function periodLabel(tv) {
  const p = tv.period;
  if (p === "shootout") return { label: "", big: "STRAFFAR" };
  if (p === 4 || (typeof p === "number" && p > 4)) return { label: "FÖRLÄNGNING", big: "ÖT" };
  return { label: "PERIOD", big: p ?? DASH };
}

export function periodTime(event) {
  return `${caps(periodName(event.period))} ${event.time ?? ""}`.trim();
}

/** "3:e" style ordinals for the copy ("2:a målet"). */
export const ordinal = (n) => `${n}:${n % 10 === 1 || n % 10 === 2 ? "a" : "e"}`;

/** Text of a player: "#25 Arttu Ruotsalainen". */
export const who = (p) => (p ? `#${p.number ?? ""} ${p.first ?? ""} ${p.last ?? ""}`.replace(/\s+/g, " ").trim() : "");
