// idle on the TV (L-frame), between games: the column pages through the standings, my
// team's next game, my team's form and scoring leaders, and the latest results, 12 s a
// slide (as the wall's screens between games, asked for by the user 2026-10-31); the band
// holds the clock, my team's next game and tonight's games (or the latest results).
import { caps, dayLabel, dayTime, decimal, hhmm, html, raw, shortDate } from "../../shared/format.js";
import { empty, every, head, lframe, logoUrl, ordinal, play, row, slideshow, slides, standingsTable, stopTimers } from "./common.js";

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
  const list = [html`${raw(head("SHL", "TABELL"))}${raw(table)}`];
  const next = nextGameSlide(league, ctx.now());
  if (next) list.push(next);
  const mine = myTeamSlide(league);
  if (mine) list.push(mine);
  // the band shows the latest results when nobody plays tonight; else they get a slide
  if ((league.tonight ?? []).length && (league.recent ?? []).length) list.push(recentSlide(league));
  ctx.root.innerHTML = lframe(slides(list), band(league), "idle");
  slideshow(ctx, ctx.tv?.scene?.since_ms ?? 0);
  const clock = ctx.root.querySelector("[data-clock]");
  every(ctx, 1000, () => (clock.textContent = hhmm(ctx.now())));
}

const signed = (n) => (n == null ? "–" : n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0");
const rowOf = (league, uuid) => (league.standings ?? []).find((r) => r.uuid === uuid);
const teamName = (league, uuid, code) => rowOf(league, uuid)?.short ?? code ?? "";
const bigLogo = (uuid) => (uuid ? `<img class="nx-logo" src="${logoUrl(uuid)}" alt="" onerror="this.remove()">` : "");

/** My team's next game: when, where, and both teams' place in the table. */
function nextGameSlide(league, now) {
  const g = league.my_team?.next_game;
  if (!g) return null;
  const side = (uuid, code) => {
    const r = rowOf(league, uuid);
    return html`<div class="nx-team">${raw(bigLogo(uuid))}<div class="nx-name">${caps(teamName(league, uuid, code))}</div>
      <div class="tvr-meta">${r ? `${caps(ordinal(r.rank))} · ${r.points} p · ${r.gp} matcher` : ""}</div></div>`;
  };
  return html`${raw(head(dayLabel(g.start_ms, now), "NÄSTA MATCH"))}
    <div class="nx-when"><span class="nx-time">${hhmm(g.start_ms)}</span><span class="tvr-meta">${dayTime(g.start_ms)}${g.arena ? ` · ${g.arena}` : ""}</span></div>
    <div class="nx-teams">${raw(side(g.home_uuid, g.home))}<div class="nx-vs">–</div>${raw(side(g.away_uuid, g.away))}</div>`;
}

/** My team: place, points and form, then its points leaders (the leader with a portrait). */
function myTeamSlide(league) {
  const mine = league.my_team ?? {};
  const t = mine.team;
  if (!t?.rank) return null;
  const name = caps(teamName(league, mine.uuid, ""));
  const form = (t.form ?? []).map((f) => `<span class="form-chip ${f.result === "V" ? "won" : "lost"}">${f.result}</span>`).join("");
  const leaders = mine.leaders?.points ?? [];
  const [first, ...rest] = leaders;
  const portrait = first?.portrait ? html`<img class="ld-img small" src="${first.portrait}" alt="" onerror="this.remove()">` : "";
  const leader = first
    ? html`<div class="tv-label">POÄNGLIGA</div><div class="ld-card small" style="--c: var(--gold)">${raw(portrait)}<div class="ld-text">
        <div class="ld-first">${first.number != null ? `#${first.number} ` : ""}${first.first ?? ""}</div>
        <div class="ld-last" data-fit>${caps(first.last ?? "")}</div>
        <div class="ld-value">${first.tp ?? 0}<span> POÄNG</span></div></div></div>
      ${raw(rest.slice(0, 2).map((r) => row(`${r.number != null ? `#${r.number} ` : ""}${caps(r.last ?? "")}`, r.tp ?? 0, `${r.g ?? 0} MÅL · ${r.a ?? 0} ASSIST`)).join(""))}`
    : "";
  return html`${raw(head("MITT LAG", name))}
    <div class="my-line"><span class="st-big">${caps(ordinal(t.rank))}</span><span class="tvr-meta">${t.points} poäng · ${t.gp} matcher ·
      mål ${signed(t.diff)} · ${decimal(t.gf_per_game)}–${decimal(t.ga_per_game)} per match</span></div>
    <div class="st-form">${raw(form || "–")}</div>${raw(leader)}`;
}

function recentSlide(league) {
  const rows = (league.recent ?? [])
    .slice(0, 7)
    .map((g) => row(`${g.home}–${g.away}`, g.score ?? "", `${shortDate(new Date(g.start_ms).toISOString().slice(0, 10))}${g.note ? ` · ${NOTE[g.note] ?? g.note}` : ""}`))
    .join("");
  return html`${raw(head("SHL", "SENASTE RESULTAT"))}${raw(rows)}`;
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
