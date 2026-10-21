// pregame (mockup scene 1): league points, form and the last meeting from tv.league.
import { formRow, tile } from "../../shared/components.js";
import { caps, countdown, dayLabel, decimal, hhmm, html, raw, shortDate } from "../../shared/format.js";
import { barPage, barTeam, every, ordinal, play, shortName, stopTimers, teamHead } from "./common.js";

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
  const side = ctx.side;
  const b = league.teams?.[side];
  const form = b?.form ?? [];
  let card;
  if (side === "home") {
    const m = league.last_meeting;
    card = m
      ? html`<div class="card alt anim"><div class="label">SENASTE MÖTET · ${shortDate(m.date)}</div>
          <div class="latest-text">${m.home} ${m.score} ${m.away}${m.note ? ` (${m.note})` : ""}</div><div class="secondary">${m.arena ?? ""}</div></div>`
      : html`<div class="card alt anim"><div class="label">SENASTE MÖTET</div><div class="latest-text">Inget möte i år</div></div>`;
  } else {
    const start = tv.game?.start_ms;
    card = html`<div class="card alt anim"><div class="label">NEDSLÄPP</div>
      <div class="latest-text">${start ? hhmm(start) : "–"}</div><div class="secondary">${tv.game?.arena ?? ""}</div></div>`;
  }
  ctx.root.innerHTML = html`<div class="portrait-page">
    ${raw(teamHead(tv, side, "anim"))}
    ${raw(b?.rank ? html`<div class="label anim">${caps(ordinal(b.rank))} I TABELLEN</div>` : "")}
    <div class="tiles anim">${raw(tile("MATCHER", b?.gp ?? "–"))}${raw(tile("POÄNG", b?.points ?? "–"))}${raw(tile("MÅLSKILLNAD", signed(b?.diff)))}</div>
    <div class="list anim"><div class="label">FORM, SENASTE 5</div>
      ${raw(form.length ? form.map(formRow).join("") : `<div class="secondary body-text">Inga matcher ännu</div>`)}</div>
    <div class="tiles two anim">${raw(tile("GJORDA MÅL / MATCH", decimal(b?.gf_per_game)))}${raw(tile("INSLÄPPTA / MATCH", decimal(b?.ga_per_game)))}</div>
    <div class="bottom-slot">${raw(card)}</div></div>`;
}
