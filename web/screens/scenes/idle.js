// idle: clock and my team's next game on the bar, standings left, tonight's games or the
// latest results right. Nothing moves except the clock.
import { dayTime, hhmm, html, raw, shortDate } from "../../shared/format.js";
import { every, play, stopTimers } from "./common.js";

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

const logo = (url) => (url ? `<img class="logo-xs" src="${url}" alt="" onerror="this.remove()">` : `<span class="logo-xs"></span>`);
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
  const mine = league.my_team?.uuid ?? null;
  const body = rows
    .map(
      (r) => html`<div class="table-row anim ${r.uuid === mine ? "mine" : ""}"><span class="num">${r.rank}</span>${raw(logo(r.logo))}
        <span class="team-cell">${r.short ?? r.code}</span><span class="num">${r.gp}</span><span class="num">${signed(r.diff)}</span><span class="num strong">${r.points}</span></div>`,
    )
    .join("");
  return html`<div class="portrait-page"><div class="anim"><div class="label">SHL</div><div class="section-title">TABELL</div></div>
    <div class="list"><div class="table-row head label"><span class="num">#</span><span></span><span>LAG</span><span class="num">M</span><span class="num">+/−</span><span class="num">P</span></div>
    ${raw(body || `<div class="secondary body-text">Tabellen hämtas…</div>`)}</div></div>`;
}

function games(league) {
  const tonight = league.tonight ?? [];
  const list = tonight.length ? tonight : (league.recent ?? []).slice(0, 8);
  const title = tonight.length ? "KVÄLLENS MATCHER" : "SENASTE RESULTAT";
  const rows = list
    .map((g) => {
      const when = tonight.length ? hhmm(g.start_ms) : shortDate(new Date(g.start_ms).toISOString().slice(0, 10));
      const res = tonight.length ? "" : `${g.score ?? ""}`;
      return html`<div class="game-row anim"><span class="when">${when}</span>
        <span class="teams">${raw(logo(teamLogo(g.home_uuid)))} ${g.home}–${g.away} ${raw(logo(teamLogo(g.away_uuid)))}</span>
        <span class="res">${res}${raw(g.note ? `<span class="muted note"> ${g.note === "straffar" ? "STR" : g.note === "övertid" ? "ÖT" : g.note}</span>` : "")}</span></div>`;
    })
    .join("");
  return html`<div class="portrait-page"><div class="anim"><div class="label">SHL</div><div class="section-title">${title}</div></div>
    <div class="list">${raw(rows || `<div class="secondary body-text">Inga matcher</div>`)}</div>
  </div>`;
}
