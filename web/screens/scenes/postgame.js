// postgame: final score, final statistics left, goals (and the shootout) right.
import { badge, goalRow } from "../../shared/components.js";
import { html, raw } from "../../shared/format.js";
import { barPage, play, statsLine, team, venueLine, who } from "./common.js";
import { comparison } from "./intermission.js";

export function enter(ctx, data, at) {
  render(ctx);
  const tl = gsap.timeline({ paused: true });
  tl.from(ctx.root.querySelectorAll(".anim"), { y: 30, opacity: 0, duration: 0.45, ease: "power2.out", stagger: 0.07 });
  play(ctx, at, tl);
}

export function update(ctx) {
  render(ctx);
}

function suffix(tv) {
  return tv.went_to_shootout ? "STR" : tv.overtime ? "ÖT" : "";
}

function render(ctx) {
  const tv = ctx.tv;
  if (ctx.kind === "bar") {
    const sfx = suffix(tv);
    const centre = html`<div class="label">SLUTRESULTAT</div><div class="big-word">SLUT</div>${raw(sfx ? html`<span class="pill">${sfx}</span>` : "")}`;
    const strip = [statsLine(tv), venueLine(tv)].filter(Boolean).join(" • ");
    ctx.root.innerHTML = barPage(tv, { centre, strip: html`${strip}` });
    return;
  }
  ctx.root.innerHTML = ctx.side === "home" ? finalStats(tv) : goals(tv);
}

function finalStats(tv) {
  return html`<div class="portrait-page"><div class="rule" style="--c: var(--home)"></div>
    <div class="anim"><div class="label">SLUT${suffix(tv) ? ` · ${suffix(tv)}` : ""}</div><div class="section-title">SLUTSTATISTIK</div></div>
    <div class="duo anim"><div class="team">${raw(badge(team(tv, "home"), "home", "sm"))}${team(tv, "home").short ?? ""}</div>
      <div class="team">${team(tv, "away").short ?? ""}${raw(badge(team(tv, "away"), "away", "sm"))}</div></div>
    <div class="list cmp-list">${raw(comparison(tv, { perPeriod: true }))}</div></div>`;
}

function goals(tv) {
  const list = (tv.goals ?? []).filter((g) => !g.data?.shootout).slice(-8);
  const attempts = tv.shootout ?? [];
  const so = attempts.length
    ? html`<div class="list anim"><div class="label">STRAFFLÄGGNING</div>${raw(
        attempts
          .map((a) => html`<div class="pen-row" style="--c: var(--${a.side})"><div class="pen-time">${a.data?.index ?? ""}</div>
            <div class="pen-team">${a.team_code ?? ""}</div><div class="pen-who">${who(a.player)}</div><div class="pen-min">${a.data?.scored ? "MÅL" : "–"}</div></div>`)
          .join(""),
      )}</div>`
    : "";
  return html`<div class="portrait-page"><div class="rule" style="--c: var(--away)"></div>
    <div class="list anim"><div class="label">MÅLEN</div>
      ${raw(list.length ? list.map((g) => goalRow(g)).join("") : `<div class="secondary body-text">Inga mål</div>`)}</div>
    ${raw(so)}</div>`;
}
