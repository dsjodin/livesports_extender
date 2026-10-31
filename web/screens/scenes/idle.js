// idle: clock and my team's next game on the bar, standings left, tonight's games or the
// latest results right. Nothing moves except the clock.
import { dayTime, hhmm, html, raw, shortDate } from "../../shared/format.js";
import { every, play, standingsTable, stopTimers } from "./common.js";

export function enter(ctx, data, at) {
  render(ctx);
  const tl = gsap.timeline({ paused: true });
  tl.from(ctx.root.querySelectorAll(".anim"), { opacity: 0, duration: 0.6, ease: "power1.out", stagger: 0.05 });
  play(ctx, at, tl);
}

export function update(ctx) {
  render(ctx);
}

export function exit(ctx) {
  stopTimers(ctx);
}

const logo = (url) => (url ? `<img class="logo3" src="${url}" alt="" onerror="this.remove()">` : `<span class="logo3"></span>`);
const teamLogo = (uuid) => `/assets/teams/${encodeURIComponent(uuid)}.svg`;
const signed = (n) => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0");

function render(ctx) {
  stopTimers(ctx);
  const league = ctx.tv?.league ?? {};
  if (ctx.kind === "bar") {
    const next = league.my_team?.next_game;
    const line = next ? `Nästa match: ${dayTime(next.start_ms)} ${next.home}–${next.away}` : "SHL Arena";
    ctx.root.innerHTML = html`<div class="idle-bar anim"><div class="bar-clock" data-clock></div><div class="idle-next">${line}</div></div>`;
    const el = ctx.root.querySelector("[data-clock]");
    every(ctx, 1000, () => (el.textContent = hhmm(ctx.now())));
    return;
  }
  ctx.root.innerHTML = ctx.side === "home" ? standings(league) : games(league);
}

function standings(league) {
  const rows = league.standings ?? [];
  const table = rows.length
    ? standingsTable(rows, league.groupings ?? [], { mine: league.my_team?.uuid ?? null })
    : `<div class="empty3">Tabellen hämtas…</div>`;
  return html`<div class="portrait-page idle-page"><div class="slide-head anim"><div class="label">SHL</div><div class="slide-title">TABELL</div></div>
    <div class="anim">${raw(table)}</div></div>`;
}

function games(league) {
  // sized for 3 m (docs/SCREENS.md, Type)
  const tonight = league.tonight ?? [];
  const list = tonight.length ? tonight : (league.recent ?? []).slice(0, 7);
  const title = tonight.length ? "KVÄLLENS MATCHER" : "SENASTE RESULTAT";
  const note = (n) => (n === "straffar" ? "STR" : n === "övertid" ? "ÖT" : n);
  const rows = list
    .map((g) => {
      const when = tonight.length ? hhmm(g.start_ms) : shortDate(new Date(g.start_ms).toISOString().slice(0, 10));
      const res = tonight.length ? "" : `${g.score ?? ""}`;
      return html`<div class="ig-row anim"><span class="ig-when">${when}</span>
        <span class="ig-teams">${raw(logo(teamLogo(g.home_uuid)))}<b>${g.home}–${g.away}</b>${raw(logo(teamLogo(g.away_uuid)))}</span>
        <span class="ig-res">${res}${raw(g.note ? `<small> ${note(g.note)}</small>` : "")}</span></div>`;
    })
    .join("");
  return html`<div class="portrait-page idle-page"><div class="slide-head anim"><div class="label">SHL</div><div class="slide-title">${title}</div></div>
    <div class="list3">${raw(rows || `<div class="empty3">Inga matcher</div>`)}</div>
  </div>`;
}
