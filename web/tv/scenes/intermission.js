// intermission on the TV (L-frame): the column pages through the period's statistics,
// goals, penalties, goalies and special teams, the (live) table and the other games, 12 s
// a slide by the synced clock; the band holds the score and the time to the next period
// (an estimate, as on the wall: the period's end on TV plus the break).
import { compareRow, shotMap } from "../../shared/components.js";
import { caps, countdown, html, percent, periodWord, raw, score, strengthChip } from "../../shared/format.js";
import { ends, savePct } from "../../screens/scenes/intermission.js";
import { gameStatus } from "../../screens/scenes/ticker.js";
import { empty, every, head, lframe, logo, play, row, scoreboard, shortName, slideshow, slides, standingsTable, stopTimers } from "./common.js";

export function enter(ctx, data, at) {
  render(ctx);
  const tl = gsap.timeline({ paused: true });
  tl.from(ctx.root.querySelectorAll(".tv-col, .tv-band"), { opacity: 0, y: 30, duration: 0.5, ease: "power2.out", stagger: 0.1 });
  play(ctx, at, tl);
}

export function update(ctx) {
  render(ctx);
}

export function exit(ctx) {
  stopTimers(ctx);
}

export function after(n) {
  return n === 1 ? "EFTER EN PERIOD" : `EFTER ${caps(periodWord(n))} PERIODER`;
}

function render(ctx) {
  stopTimers(ctx);
  const tv = ctx.tv;
  const n = typeof tv.period === "number" ? tv.period : 1;
  const band = html`${raw(scoreboard(tv))}<div class="im-next"><span class="tv-label">${n >= 3 ? "FÖRLÄNGNING" : `PERIOD ${n + 1}`} OM</span>
    <span class="im-count gold" data-countdown></span><span class="tv-label">${after(n)}</span></div>`;
  ctx.root.innerHTML = lframe(slides(statSlides(tv, after(n))), band, "intermission");
  slideshow(ctx, tv.scene?.since_ms ?? 0);
  const el = ctx.root.querySelector("[data-countdown]");
  every(ctx, 250, () => (el.textContent = countdown(ends(ctx) - ctx.now())));
}

function teams(tv) {
  return html`<div class="cmp-teams"><span>${raw(logo(tv, "home", "tv-logo-sm"))}${caps(shortName(tv, "home"))}</span>
    <span>${caps(shortName(tv, "away"))}${raw(logo(tv, "away", "tv-logo-sm"))}</span></div>`;
}

const last = (p) => caps(p?.last ?? "");

export function goalsList(tv, max = 6) {
  const goals = (tv.goals ?? []).filter((g) => !g.data?.shootout).slice(-max);
  if (!goals.length) return empty("Inga mål ännu");
  return goals
    .map((g) => {
      const chip = strengthChip(g.data?.strength, g.data?.empty_net);
      const sc = g.data?.score ?? {};
      const meta = `P${g.period} ${g.time ?? ""} · ${g.team_code ?? ""}${chip ? ` · ${chip}` : ""}`;
      return row(g.player ? `#${g.player.number ?? ""} ${last(g.player)}` : "MÅL", score(sc.home, sc.away), meta, g.side);
    })
    .join("");
}

function penaltiesList(tv) {
  const pens = (tv.penalties ?? []).slice(-6);
  if (!pens.length) return empty("Inga utvisningar");
  return pens
    .map((pen) => {
      const shot = pen.data?.offence_code === "P-SHOT";
      const name = shot ? "STRAFFSLAG" : pen.player ? `#${pen.player.number ?? ""} ${last(pen.player)}` : "LAGSTRAFF";
      const meta = `P${pen.period} ${pen.time ?? ""} · ${pen.team_code ?? ""}${shot ? "" : ` · ${pen.data?.offence_text ?? ""}`}`;
      return row(name, pen.data?.minutes ? `${pen.data.minutes} MIN` : "", meta, pen.side);
    })
    .join("");
}

/** Shots per period and in all, as bars (also the postgame's statistics). */
export function shotsCompare(tv) {
  const h = tv.stats?.home ?? {};
  const a = tv.stats?.away ?? {};
  const periods = Math.max(h.shots_by_period?.length ?? 0, a.shots_by_period?.length ?? 0);
  const rows = [];
  for (let i = 0; i < periods; i++) rows.push(compareRow(i < 3 ? `P${i + 1}` : "ÖT", h.shots_by_period?.[i] ?? 0, a.shots_by_period?.[i] ?? 0));
  rows.push(compareRow("PÅ MÅL", h.shots_on_goal ?? 0, a.shots_on_goal ?? 0));
  rows.push(compareRow("FÖRSÖK", h.shot_attempts ?? 0, a.shot_attempts ?? 0));
  return rows.join("");
}

export function specialTeams(tv) {
  const h = tv.stats?.home ?? {};
  const a = tv.stats?.away ?? {};
  const hs = savePct(h.goalie);
  const as = savePct(a.goalie);
  return [
    compareRow("POWERPLAY", h.pp?.goals ?? 0, a.pp?.goals ?? 0, `${h.pp?.goals ?? 0}/${h.pp?.chances ?? 0}`, `${a.pp?.goals ?? 0}/${a.pp?.chances ?? 0}`),
    compareRow("UTV.MIN", h.pim ?? 0, a.pim ?? 0),
    compareRow("RÄDDNINGSPROCENT", hs ?? 0, as ?? 0, percent(hs), percent(as)),
  ].join("");
}

function goalies(tv) {
  return ["home", "away"]
    .map((side) => {
      const g = tv.stats?.[side]?.goalie;
      const name = g?.name ? `#${g.number ?? ""} ${caps((g.name ?? "").split(" ").slice(-1)[0])}` : "–";
      return row(name, percent(savePct(g)), `${caps(shortName(tv, side))} · ${g?.saves ?? 0} räddningar`, side);
    })
    .join("");
}

export function tableSlide(tv) {
  const groupings = tv.league?.groupings ?? [];
  if (tv.live_table) return html`${raw(head("SHL", "OM MATCHERNA SLUTADE NU"))}${raw(standingsTable(tv.live_table, groupings, { live: true }))}`;
  if (tv.league?.standings?.length) return html`${raw(head("SHL", "TABELL"))}${raw(standingsTable(tv.league.standings, groupings))}`;
  return null;
}

export function othersSlide(tv) {
  const others = tv.others ?? [];
  if (!others.length) return null;
  const rows = others
    .slice(0, 7)
    .map((o) => row(`${o.teams.home.code ?? ""} – ${o.teams.away.code ?? ""}`, o.phase === "pregame" ? "–" : score(o.score.home, o.score.away), gameStatus(o)))
    .join("");
  return html`${raw(head("KVÄLLENS ANDRA MATCHER", "RESULTAT"))}${raw(rows)}`;
}

function statSlides(tv, label) {
  const maps = ["home", "away"]
    .map((side) => html`<div class="im-map"><div class="tv-label">${caps(shortName(tv, side))} · ${tv.stats?.[side]?.shots_on_goal ?? 0} SKOTT</div>${raw(shotMap(tv.shots?.[side], side))}</div>`)
    .join("");
  return [
    html`${raw(head(label, "SKOTT"))}${raw(teams(tv))}<div class="cmp-list">${raw(shotsCompare(tv))}</div>`,
    html`${raw(head(label, "SKOTTKARTOR"))}<div class="im-maps">${raw(maps)}</div>`,
    html`${raw(head(label, "MÅLEN"))}${raw(goalsList(tv))}`,
    html`${raw(head(label, "UTVISNINGAR"))}${raw(penaltiesList(tv))}`,
    html`${raw(head(label, "MÅLVAKTER OCH SPECIAL TEAMS"))}${raw(goalies(tv))}${raw(teams(tv))}<div class="cmp-list">${raw(specialTeams(tv))}</div>`,
    tableSlide(tv),
    othersSlide(tv),
  ].filter(Boolean);
}
