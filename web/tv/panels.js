// Panels (docs/TV_APP.md, Scenes on the TV): Statistik, Tabell, Kvällens matcher. Over the
// full picture in play they lie in the right third, half see-through; in an L-frame scene
// they take the column's place, opaque, so nothing lies on top of the column's own
// graphics (asked for by the user 2026-10-31). ↑ ↓ page through them and off; Back or 20 s
// without a key closes them. Every number comes from the delayed
// state (CLAUDE.md rule 1), and an open panel follows its patches.
import { caps, html, raw } from "../shared/format.js";
import { empty, head, logo, shortName } from "./scenes/common.js";
import { othersSlide, shotsCompare, specialTeams, tableSlide } from "./scenes/intermission.js";

const ORDER = ["stats", "table", "games"];
const CLOSE_MS = 20_000;

let el = null;
let shown = null; // the panel shown, or null
let timer = null;
let getTv = () => null;
let inColumn = () => false;

/** ``columnGetter``: true while the scene is an L-frame (the panel goes in the column). */
export function create(parent, tvGetter, columnGetter) {
  getTv = tvGetter;
  inColumn = columnGetter;
  el = document.createElement("section");
  el.className = "tv-panel";
  parent.appendChild(el);
}

export const isOpen = () => shown != null;

/** Next (+1) or previous (−1) panel; past the last (or first) closes them. */
export function step(dir) {
  const i = shown == null ? (dir > 0 ? 0 : ORDER.length - 1) : ORDER.indexOf(shown) + dir;
  show(i >= 0 && i < ORDER.length ? ORDER[i] : null);
}

export function close() {
  show(null);
}

/** Open one panel by name (from the menu). */
export function open(name) {
  show(ORDER.includes(name) ? name : null);
}

/** Redraw the open panel (a patch arrived). */
export function refresh() {
  if (shown) render();
}

function show(name) {
  clearTimeout(timer);
  const was = shown;
  shown = name;
  if (!name) {
    gsap.to(el, { opacity: 0, x: 40, duration: 0.25, ease: "power1.in" });
    return;
  }
  el.classList.toggle("in-column", inColumn());
  render();
  if (!was) gsap.fromTo(el, { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.3, ease: "power2.out" });
  timer = setTimeout(close, CLOSE_MS);
}

function render() {
  const tv = getTv();
  if (!tv) return;
  const dots = ORDER.map((n) => `<span class="${n === shown ? "on" : ""}"></span>`).join("");
  el.innerHTML = `${body(tv, shown)}<div class="dots">${dots}</div>`;
}

function teams(tv) {
  return html`<div class="cmp-teams"><span>${raw(logo(tv, "home", "tv-logo-sm"))}${caps(shortName(tv, "home"))}</span>
    <span>${caps(shortName(tv, "away"))}${raw(logo(tv, "away", "tv-logo-sm"))}</span></div>`;
}

function body(tv, name) {
  if (name === "stats") return html`${raw(head("MATCHEN", "STATISTIK"))}${raw(teams(tv))}<div class="cmp-list">${raw(shotsCompare(tv))}${raw(specialTeams(tv))}</div>`;
  if (name === "table") return tableSlide(tv) ?? html`${raw(head("SHL", "TABELL"))}${raw(empty("Tabellen hämtas…"))}`;
  return othersSlide(tv) ?? html`${raw(head("IKVÄLL", "KVÄLLENS MATCHER"))}${raw(empty("Inga andra matcher ikväll"))}`;
}
