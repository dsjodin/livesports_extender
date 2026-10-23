// Pieces shared by the scene modules.
import { badge } from "../../shared/components.js";
import { caps, DASH, html, periodName, raw, score, thousands } from "../../shared/format.js";

export const other = (side) => (side === "home" ? "away" : "home");
export const team = (tv, side) => tv?.teams?.[side] ?? {};
export const shortName = (tv, side) => team(tv, side).short ?? team(tv, side).code ?? (side === "home" ? "Hemma" : "Borta");
export const longName = (tv, side) => team(tv, side).long ?? shortName(tv, side);

/** Start a paused GSAP timeline as if it began at play_at (jumping ahead if we are late).
 * Without animation (a fresh state on connect) it goes straight to its end. */
export function play(ctx, at, tl) {
  if (!ctx.animate) return tl.progress(1);
  tl.time(Math.max(0, ctx.now() - at) / 1000, false); // callbacks we jumped over still run
  return tl.play();
}

/** Re-run fn every ms while the scene is shown (countdowns, the idle clock). */
export function every(ctx, ms, fn) {
  fn();
  const id = setInterval(fn, ms);
  ctx.timers = [...(ctx.timers ?? []), id];
}

export function stopTimers(ctx) {
  (ctx.timers ?? []).forEach(clearInterval);
  ctx.timers = [];
}

/** Portrait header: team-colour rule, badge, "HEMMA"/"BORTA", long name. */
export function teamHead(tv, side, extraClass = "", { compact = false } = {}) {
  const rule = html`<div class="rule" style="--c: var(--${side}); --ol: var(--${side}-outline)"></div>`;
  if (compact) {
    // 3 m (live): the logo large and toned down behind the short name, no badge circle,
    // no HEMMA/BORTA label (the screen's place says it); asked for by the user 2026-10-21
    const logo = team(tv, side).logo;
    const img = logo ? html`<img class="head-logo" src="${logo}" alt="" onerror="this.remove()">` : "";
    return html`${raw(rule)}<div class="team-head compact ${extraClass}">${raw(img)}
      <div class="team-name" data-fit>${caps(shortName(tv, side))}</div></div>`;
  }
  return html`${raw(rule)}<div class="team-head ${extraClass}">${raw(badge(team(tv, side), side, "lg"))}
    <div><div class="label">${side === "home" ? "HEMMA" : "BORTA"}</div><div class="team-name">${longName(tv, side)}</div></div></div>`;
}

/** The team's logo on its own (the bar, 3 m); the code badge when there is none. */
export function plainLogo(tv, side, size = "md") {
  const t = team(tv, side);
  return t.logo ? html`<img class="plain-logo plain-${size}" src="${t.logo}" alt="">` : badge(t, side, size);
}

/** Shrink text marked data-fit until it fits its box on one line (long team names). */
export function fitText(root, min = 0.6) {
  for (const el of root.querySelectorAll("[data-fit]")) {
    el.style.fontSize = "";
    const base = parseFloat(getComputedStyle(el).fontSize);
    let size = base;
    el.style.whiteSpace = "nowrap";
    while (el.scrollWidth > el.clientWidth && size > base * min) {
      size -= 4;
      el.style.fontSize = `${size}px`;
    }
  }
}

/** One half of the bar's main row. `value` goes in the score box, `sub` under it. */
export function barTeam(tv, side, value, { sub = "", flash = false, id = "" } = {}) {
  return html`<div class="bar-team ${side}" style="--c: var(--${side})"><div class="edge"></div>
    ${raw(plainLogo(tv, side))}<div class="bar-name" data-fit>${caps(shortName(tv, side))}</div>
    <div class="score-box ${flash ? "flash" : ""}" ${raw(id ? `id="${id}"` : "")}><div class="digits ${String(value).length > 1 ? "narrow" : ""}">${value}</div>${raw(sub ? `<div class="sub label">${sub}</div>` : "")}</div></div>`;
}

export function barPage(tv, { home, away, centre, strip, stripClass = "" }) {
  return html`<div class="bar-page"><div class="bar-main">${raw(home ?? barTeam(tv, "home", tv.score?.home ?? 0))}
    <div class="bar-centre">${raw(centre)}</div>${raw(away ?? barTeam(tv, "away", tv.score?.away ?? 0))}</div>
    <div class="strip ${stripClass}">${raw(strip ?? "")}</div></div>`;
}

/** "SKOTT 36–26 • UTV.MIN 2–6" */
export function statsLine(tv) {
  const s = tv.stats ?? {};
  return `SKOTT ${score(s.home?.shots_on_goal, s.away?.shots_on_goal)} • UTV.MIN ${score(s.home?.pim, s.away?.pim)}`;
}

export function venueLine(tv) {
  const g = tv.game ?? {};
  const parts = [g.arena, g.attendance ? `${thousands(g.attendance)} ÅSKÅDARE` : null].filter(Boolean);
  return parts.join(" · ");
}

export function periodLabel(tv) {
  const p = tv.period;
  if (p === "shootout") return { label: "", big: "STRAFFAR" };
  if (p === 4 || (typeof p === "number" && p > 4)) return { label: "FÖRLÄNGNING", big: "ÖT" };
  return { label: "PERIOD", big: p ?? DASH };
}

export function periodTime(event) {
  return `${caps(periodName(event.period))} ${event.time ?? ""}`.trim();
}

/** "3:e" style ordinals for the copy ("2:a målet"). */
export const ordinal = (n) => `${n}:${n % 10 === 1 || n % 10 === 2 ? "a" : "e"}`;

/** Text of a player: "#25 Arttu Ruotsalainen". */
export const who = (p) => (p ? `#${p.number ?? ""} ${p.first ?? ""} ${p.last ?? ""}`.replace(/\s+/g, " ").trim() : "");

const SLIDE_MS = 12_000;

/**
 * Show the .slide elements in ctx.root one at a time, 12 s each, cross-fading. The slide
 * follows from the synced clock and ``startMs`` (the scene start), so every screen and any
 * reload agree; [data-dot] elements mark the one shown (intermission, pregame).
 */
export function slideshow(ctx, startMs) {
  const slides = [...ctx.root.querySelectorAll(".slide")];
  const dots = [...ctx.root.querySelectorAll("[data-dot]")];
  if (!slides.length) return;
  let current = null;
  const pick = () => Math.floor(Math.max(0, ctx.now() - startMs) / SLIDE_MS) % slides.length;
  const show = (i, animate) => {
    slides.forEach((el, j) => {
      gsap.killTweensOf(el);
      if (j === i) {
        if (animate) gsap.fromTo(el, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" });
        else gsap.set(el, { opacity: 1, y: 0 });
      } else if (j === current && animate) {
        gsap.to(el, { opacity: 0, duration: 0.35, ease: "power1.out" });
      } else {
        gsap.set(el, { opacity: 0 });
      }
    });
    dots.forEach((d, j) => d.classList.toggle("on", j === i));
    current = i;
  };
  show(pick(), false);
  every(ctx, 250, () => {
    const i = pick();
    if (i !== current) show(i, true);
  });
}

// --- the standings table (idle, intermission), sized for 3 m --------------------------

const ZONE_LABEL = { playoff: "SLUTSPEL", playin: "PLAY IN", qualdown: "KVAL" };

/**
 * SHL's table with its zones (league.groupings: playoff 1–6, play in 7–10, kval 13–14):
 * a coloured edge per zone, a heavier line where a zone ends, and a legend. ``live`` rows
 * (the live table) show a movement arrow and tonight's score; else goal difference.
 */
export function standingsTable(rows, groupings = [], { mine = null, live = false } = {}) {
  const ends = new Set(groupings.map((g) => g.last));
  const logo = (url) => (url ? `<img class="logo3" src="${url}" alt="" onerror="this.remove()">` : `<span class="logo3"></span>`);
  const signed = (n) => (n == null ? "" : n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0");
  const body = rows
    .map((r) => {
      const move = !live ? "" : r.move > 0 ? `<span class="mv up">▲</span>` : r.move < 0 ? `<span class="mv down">▼</span>` : "";
      const middle = live ? (r.live ? `${r.live.for}–${r.live.against}` : "") : signed(r.diff);
      const cls = ["t3-row", r.zone ? `zone-${r.zone}` : "", ends.has(r.rank) ? "zone-end" : "", live && r.live ? "playing" : "", r.uuid === mine ? "mine" : ""];
      return html`<div class="${cls.filter(Boolean).join(" ")}"><span class="num">${r.rank}</span><span class="mv">${raw(move)}</span>${raw(logo(r.logo))}
        <span class="t3-team">${r.short ?? r.code}</span><span class="num ${live ? "t3-live" : ""}">${middle}</span><span class="num t3-pts">${r.points}</span></div>`;
    })
    .join("");
  const legend = groupings
    .filter((g) => ZONE_LABEL[g.zone])
    .map((g) => html`<span class="zl zone-${g.zone}"><i></i>${ZONE_LABEL[g.zone]}</span>`)
    .join("");
  return html`<div class="table3"><div class="t3-row t3-head label"><span class="num">#</span><span></span><span></span><span>LAG</span>
      <span class="num">${live ? "IKVÄLL" : "+/−"}</span><span class="num">P</span></div>${raw(body)}</div>
    ${raw(legend ? `<div class="zone-legend">${legend}</div>` : "")}`;
}
