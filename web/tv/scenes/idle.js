// idle on the TV (L-frame): the standings in the column; the clock, my team's next game
// and tonight's games (or the latest results) in the band. Nothing moves but the clock.
import { dayTime, hhmm, html, raw, shortDate } from "../../shared/format.js";
import { empty, every, head, lframe, logoUrl, play, standingsTable, stopTimers } from "./common.js";

const NOTE = { straffar: "STR", övertid: "ÖT" };

export function enter(ctx, data, at) {
  render(ctx);
  const tl = gsap.timeline({ paused: true });
  tl.from(ctx.root.querySelectorAll(".tv-col, .tv-band"), { opacity: 0, duration: 0.6, ease: "power1.out", stagger: 0.1 });
  play(ctx, at, tl);
}

export function update(ctx) {
  render(ctx);
}

export function exit(ctx) {
  stopTimers(ctx);
}

function render(ctx) {
  stopTimers(ctx);
  const league = ctx.tv?.league ?? {};
  const rows = league.standings ?? [];
  const table = rows.length ? standingsTable(rows, league.groupings ?? [], { mine: league.my_team?.uuid ?? null }) : empty("Tabellen hämtas…");
  const column = html`${raw(head("SHL", "TABELL"))}${raw(table)}`;
  ctx.root.innerHTML = lframe(column, band(league), "idle");
  const clock = ctx.root.querySelector("[data-clock]");
  every(ctx, 1000, () => (clock.textContent = hhmm(ctx.now())));
}

function band(league) {
  const next = league.my_team?.next_game;
  const tonight = league.tonight ?? [];
  const list = tonight.length ? tonight : (league.recent ?? []).slice(0, 4);
  const games = list
    .slice(0, 4)
    .map((g) => {
      const when = tonight.length ? hhmm(g.start_ms) : shortDate(new Date(g.start_ms).toISOString().slice(0, 10));
      const res = tonight.length ? "" : (g.score ?? "");
      const logo = (uuid) => (uuid ? `<img class="tv-logo-sm" src="${logoUrl(uuid)}" alt="" onerror="this.remove()">` : "");
      return html`<div class="ib-game"><span class="ib-when">${when}</span>${raw(logo(g.home_uuid))}<b>${g.home}–${g.away}</b>${raw(logo(g.away_uuid))}
        <span class="ib-res">${res}${raw(g.note ? `<small> ${NOTE[g.note] ?? g.note}</small>` : "")}</span></div>`;
    })
    .join("");
  return html`<div class="ib-left"><div class="ib-clock" data-clock></div>
      <div class="ib-next">${next ? `Nästa match: ${dayTime(next.start_ms)}` : "SHL live!"}</div>
      ${raw(next ? html`<div class="ib-next-game">${next.home}–${next.away}</div>` : "")}</div>
    <div class="ib-right"><div class="tv-label">${tonight.length ? "KVÄLLENS MATCHER" : "SENASTE RESULTAT"}</div>
      ${raw(games || empty("Inga matcher"))}</div>`;
}
