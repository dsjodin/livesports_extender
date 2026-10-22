// pregame (mockup scene 1): standings, form, scoring leaders and head-to-head from tv.league.
import { tile } from "../../shared/components.js";
import { caps, countdown, dayLabel, decimal, hhmm, html, raw } from "../../shared/format.js";
import { barPage, barTeam, every, ordinal, plainLogo, play, shortName, slideshow, stopTimers, teamHead } from "./common.js";

const COUNTDOWN_FROM_MS = 60 * 60_000;

export function enter(ctx, data, at) {
  render(ctx);
  const tl = gsap.timeline({ paused: true });
  tl.from(ctx.root.querySelectorAll(".anim"), { y: 30, opacity: 0, duration: 0.45, ease: "power2.out", stagger: 0.07 });
  play(ctx, at, tl);
  intro(ctx);
}

export function update(ctx) {
  render(ctx);
  intro(ctx);
}

export function exit(ctx) {
  stopTimers(ctx);
  ctx.introCancel?.();
}

/** The team's intro video at puck drop on TV time (docs/SCREENS.md, Team videos). */
function intro(ctx) {
  const drop = dropOnTv(ctx);
  if (ctx.kind !== "portrait" || drop == null || drop === ctx.introAt || drop <= ctx.now()) return;
  ctx.introCancel?.();
  ctx.introAt = drop;
  ctx.introCancel = ctx.video("intro", drop, true) || null;
}

/** Puck drop as seen on TV: the scheduled start plus the TV's delay. */
function dropOnTv(ctx) {
  const start = ctx.tv.game?.start_ms;
  return start == null ? null : start + (ctx.config.offset_ms ?? 0);
}

const signed = (n) => (n == null ? "–" : n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0");

function render(ctx) {
  stopTimers(ctx);
  const tv = ctx.tv;
  const league = tv.league ?? {};
  if (ctx.kind === "bar") {
    const blocks = league.teams ?? {};
    const home = barTeam(tv, "home", blocks.home?.points ?? "–", { sub: "POÄNG" });
    const away = barTeam(tv, "away", blocks.away?.points ?? "–", { sub: "POÄNG" });
    const start = tv.game?.start_ms;
    const centre = html`<div class="label" data-when>${start ? dayLabel(start, ctx.now()) : ""}</div><div class="big-word" data-time>${start ? hhmm(start) : "–"}</div>
      <div class="small">${tv.game?.arena ?? ""}</div>`;
    const others = (league.tonight ?? []).filter((g) => g.uuid !== tv.game?.uuid);
    const strip = others.length
      ? `ÄVEN IKVÄLL: ${others.map((g) => `${g.home}–${g.away} ${hhmm(g.start_ms)}`).join(" · ")}`
      : ["home", "away"]
          .filter((s) => blocks[s]?.rank)
          .map((s) => `${caps(shortName(tv, s))} ${caps(ordinal(blocks[s].rank))} I TABELLEN`)
          .join(" • ");
    ctx.root.innerHTML = barPage(tv, { home, away, centre, strip: html`${strip}` });
    const when = ctx.root.querySelector("[data-when]");
    const time = ctx.root.querySelector("[data-time]");
    every(ctx, 250, () => {
      const drop = dropOnTv(ctx);
      if (drop == null) return;
      const left = drop - ctx.now();
      if (left < COUNTDOWN_FROM_MS) {
        when.textContent = left > 0 ? "NEDSLÄPP OM" : "NEDSLÄPP";
        time.textContent = left > 0 ? countdown(left) : "STRAX";
        time.classList.add("gold");
      }
    });
    return;
  }
  // portraits, sized for 3 m (docs/SCREENS.md, Type): a slideshow, 12 s a slide
  const side = ctx.side;
  const b = league.teams?.[side];
  const slides = [standingSlide(b)];
  if (b?.leaders?.points?.length) slides.push(leaderSlide(b.leaders.points, "POÄNGLIGA", "tp", "POÄNG"));
  if (b?.leaders?.goals?.length) slides.push(leaderSlide(b.leaders.goals, "MÅLLIGA", "g", "MÅL"));
  if (league.head_to_head?.games?.length) slides.push(h2hSlide(tv, league.head_to_head));
  const start = tv.game?.start_ms;
  ctx.root.innerHTML = html`<div class="portrait-page pre-page">
    ${raw(teamHead(tv, side, "anim", { compact: true }))}
    <div class="slides anim">${raw(slides.map((x, i) => `<section class="slide" data-i="${i}">${x}</section>`).join(""))}</div>
    <div class="pre-foot anim"><div class="dots">${raw(slides.length > 1 ? slides.map((_, i) => `<span data-dot="${i}"></span>`).join("") : "")}</div>
      <div class="card alt drop-card"><div><div class="label">NEDSLÄPP</div><div class="secondary">${tv.game?.arena ?? ""}</div></div>
      <div class="drop-time">${start ? hhmm(start) : "–"}</div></div></div></div>`;
  slideshow(ctx, tv.scene?.since_ms ?? 0);
}

function standingSlide(b) {
  const rank = b?.rank ? caps(ordinal(b.rank)) : "–";
  const form = b?.form ?? [];
  return html`<div class="tiles">${raw(tile("PLATS", rank))}${raw(tile("POÄNG", b?.points ?? "–"))}${raw(tile("MÅL +/−", signed(b?.diff)))}</div>
    <div class="form3"><div class="label">FORM, SENASTE 5</div>
      ${raw(form.length ? form.map(formLine).join("") : `<div class="empty3">Inga matcher ännu</div>`)}</div>
    <div class="card per-game"><div class="label">MÅL PER MATCH</div>
      <div class="pg-values"><div><div class="pg-value">${decimal(b?.gf_per_game)}</div><div class="secondary">GJORDA</div></div>
      <div><div class="pg-value">${decimal(b?.ga_per_game)}</div><div class="secondary">INSLÄPPTA</div></div></div></div>`;
}

/** The team's top three by points or goals: the leader large with a portrait. */
function leaderSlide(rows, title, field, unit) {
  const [first, ...rest] = rows;
  const detail = (r) => (field === "tp" ? `${r.g ?? 0} MÅL · ${r.a ?? 0} ASSIST` : `${r.gp ?? "–"} MATCHER`);
  const portrait = first.portrait ? html`<img class="leader-img" src="${first.portrait}" alt="" onerror="this.remove()">` : "";
  return html`<div class="slide-head"><div class="label">INOM LAGET</div><div class="slide-title">${title}</div></div>
    <div class="leader-card">${raw(portrait)}
      <div class="leader-text"><div class="leader-first">${first.number != null ? `#${first.number} ` : ""}${first.first ?? ""}</div>
        <div class="leader-last" data-fit>${caps(first.last ?? "")}</div>
        <div class="leader-value">${first[field] ?? 0}<span>${unit}</span></div>
        <div class="r3-meta">${detail(first)}</div></div></div>
    <div class="list3">${raw(rest.map((r) => html`<div class="row3"><div class="r3-main"><span class="r3-name">${r.number != null ? `#${r.number} ` : ""}${caps(r.last ?? "")}</span><span class="r3-score">${r[field] ?? 0}</span></div>
      <div class="r3-meta">${detail(r)}</div></div>`).join(""))}</div>`;
}

const MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
const dateText = (iso) => {
  const [y, m, d] = (iso ?? "").split("-").map(Number);
  return y ? `${d} ${MONTHS[m - 1]} ${y}` : "";
};

/** The last five meetings, over seasons and playoffs, and the wins of each side. */
function h2hSlide(tv, h2h) {
  const home = tv.teams?.home?.uuid;
  const rows = h2h.games
    .map((g) => {
      const winner = g.winner_uuid === home ? "home" : "away";
      const meta = [dateText(g.date), g.note ? (NOTE[g.note] ?? g.note) : null].filter(Boolean).join(" · ");
      return html`<div class="row3" style="--c: var(--${winner})"><div class="r3-main"><span class="r3-name">${g.home} ${g.score} ${g.away}</span>
        ${raw(g.playoff ? `<span class="tag-gold">SLUTSPEL</span>` : "")}</div><div class="r3-meta">${meta}</div></div>`;
    })
    .join("");
  return html`<div class="slide-head"><div class="label">SENASTE ${h2h.games.length}</div><div class="slide-title">INBÖRDES MÖTEN</div></div>
    <div class="h2h-sum"><div class="h2h-side">${raw(plainLogo(tv, "home", "sm"))}<span>${h2h.wins?.home ?? 0}</span></div>
      <div class="label">VINSTER</div><div class="h2h-side away"><span>${h2h.wins?.away ?? 0}</span>${raw(plainLogo(tv, "away", "sm"))}</div></div>
    <div class="list3">${raw(rows)}</div>`;
}

const NOTE = { övertid: "ÖT", straffar: "STR" };

/** One form row at 3 m: V/F, home or away, the opponent's logo and code, the score. */
function formLine(row) {
  const won = row.result === "V";
  const logo = row.opponent_uuid ? html`<img class="logo3" src="/assets/teams/${row.opponent_uuid}.svg" alt="" onerror="this.remove()">` : "";
  return html`<div class="fl3"><span class="form-chip ${won ? "won" : "lost"}">${row.result}</span>
    <span class="fl3-ha">${row.home_away === "H" ? "HEMMA" : "BORTA"}</span>${raw(logo)}<span class="fl3-opp">${row.opponent ?? ""}</span>
    <span class="fl3-score">${row.score}${raw(row.note ? html` <small>${NOTE[row.note] ?? row.note}</small>` : "")}</span></div>`;
}
