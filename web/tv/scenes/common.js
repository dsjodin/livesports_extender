// Pieces shared by the TV scenes (docs/TV_APP.md, Scenes on the TV). The wall's helpers
// are reused where the markup fits (slideshow, standings, names); the layout is the TV's
// own: the L-frame's column and band (layout.js, tv.css), lower thirds over the picture.
import { caps, esc, html, raw, score } from "../../shared/format.js";
import { shortName, team } from "../../screens/scenes/common.js";

export {
  every,
  fitText,
  longName,
  ordinal,
  other,
  periodTime,
  play,
  shortName,
  slideshow,
  standingsTable,
  stopTimers,
  team,
  who,
} from "../../screens/scenes/common.js";

/** The team's logo, or its code on its colour when there is none. */
export function logo(tv, side, cls = "tv-logo") {
  const t = team(tv, side);
  if (t.logo) return `<img class="${cls}" src="${esc(t.logo)}" alt="" onerror="this.remove()">`;
  return `<span class="${cls} tv-code" style="--c: var(--${side}); --on: var(--on-${side})">${esc(t.code ?? "")}</span>`;
}

export const logoUrl = (uuid) => `/assets/teams/${encodeURIComponent(uuid)}.svg`;

/** "[logo] ÖREBRO  2–1  FRÖLUNDA [logo]"; ``middle`` replaces the score (pregame). */
export function scoreboard(tv, { sc = tv.score, middle = null, cls = "" } = {}) {
  const mid = middle ?? score(sc?.home, sc?.away);
  return html`<div class="tv-board ${cls}">
    <div class="tvb-team">${raw(logo(tv, "home"))}<span class="tvb-name" data-fit>${caps(shortName(tv, "home"))}</span></div>
    <div class="tvb-mid">${raw(mid)}</div>
    <div class="tvb-team away"><span class="tvb-name" data-fit>${caps(shortName(tv, "away"))}</span>${raw(logo(tv, "away"))}</div></div>`;
}

/** The L-frame's column (right of the picture) and band (below it). */
export function lframe(column, band, cls = "") {
  return `<section class="tv-col ${cls}">${column}</section><section class="tv-band ${cls}">${band}</section>`;
}

export function head(label, title) {
  return html`<div class="tv-head"><div class="tv-label">${label}</div><div class="tv-title">${title}</div></div>`;
}

/** Slides for the column, shown one at a time by slideshow() with dots under them. */
export function slides(list) {
  const body = list.map((s, i) => `<section class="slide" data-i="${i}">${s}</section>`).join("");
  const dots = list.length > 1 ? list.map((_, i) => `<span data-dot="${i}"></span>`).join("") : "";
  return `<div class="slides">${body}</div><div class="dots">${dots}</div>`;
}

/** A line of a list: main text, a value on the right, a quieter line under it. */
export function row(main, value = "", meta = "", side = null) {
  const edge = side ? ` style="--c: var(--${side})"` : "";
  return html`<div class="tv-row${side ? " edged" : ""}"${raw(edge)}><div class="tvr-main"><span class="tvr-name">${main}</span><span class="tvr-value">${value}</span></div>
    ${raw(meta ? html`<div class="tvr-meta">${meta}</div>` : "")}</div>`;
}

export const empty = (text) => html`<div class="tv-empty">${text}</div>`;

/** Game seconds (from the start of the game) as the period and its clock: "P2 14:23". */
export function gameClock(seconds) {
  if (seconds == null) return "";
  const period = Math.floor(seconds / 1200) + 1;
  const within = seconds - (period - 1) * 1200;
  const mm = String(Math.floor(within / 60)).padStart(2, "0");
  const ss = String(within % 60).padStart(2, "0");
  return `${period > 3 ? "ÖT" : `P${period}`} ${mm}:${ss}`;
}
