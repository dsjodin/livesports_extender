// live on the TV: the full picture, and only what the broadcast does not show itself
// (it has its own score bug). A penalty is a lower third for a few seconds when it
// happens (the director's overlay), then a small power-play pill stays bottom right until
// the power play is over; a timeout and a disallowed goal are short banners. Lower thirds
// keep clear of the broadcaster's ticker (bottom 8 %) and its bug (top left).
import { caps, html, raw } from "../../shared/format.js";
import { gameClock, logo, other, play, shortName, who } from "./common.js";

export function enter(ctx, data, at) {
  ctx.overlay = data.overlay ? data : null;
  render(ctx);
  animate(ctx, at);
}

export function overlay(ctx, data, at) {
  ctx.overlay = data.overlay ? data : null;
  render(ctx);
  animate(ctx, at);
}

export function update(ctx, tv, patch) {
  // the pill follows the strength; a running lower third stays as it is
  if (patch.strength || patch.penalties_active) pill(ctx);
}

function render(ctx) {
  const ov = ctx.overlay;
  let lower = "";
  if (ov?.overlay === "penalty") lower = penaltyCard(ctx.tv, ov.event_key);
  else if (ov?.overlay === "timeout") lower = banner(`TIMEOUT ${caps(shortName(ctx.tv, ov.side))}`, "gold");
  else if (ov?.overlay === "goal_disallowed") lower = banner("MÅLET UNDERKÄNT", "alert");
  ctx.root.innerHTML = `<div class="tv-lower-slot">${lower}</div><div class="tv-pill-slot"></div>`;
  pill(ctx);
}

function animate(ctx, at) {
  const el = ctx.root.querySelector(".tv-lower-slot > *");
  if (!el) return;
  const tl = gsap.timeline({ paused: true });
  tl.from(el, { x: -80, opacity: 0, duration: 0.4, ease: "power3.out" });
  tl.from(el.querySelectorAll(".pc-line"), { opacity: 0, x: -30, duration: 0.3, stagger: 0.08 }, 0.2);
  play(ctx, at, tl);
}

function banner(text, kind) {
  return html`<div class="tv-banner ${kind}">${text}</div>`;
}

/** "5 MOT 4" from the penalties alone: a pulled goalie (a guess from the feed) does not
 * change a power play's count (the user 2026-10-31: "6 mot 4", "powerplay 5 mot 5"). */
function count(st) {
  const home = st.pen_home ?? st.home;
  const away = st.pen_away ?? st.away;
  return home && away && home !== away ? `${home} MOT ${away}` : "";
}

/** The shorthanded side's penalties still running, soonest out first. */
function running(tv, side) {
  return (tv.penalties_active ?? []).filter((p) => p.side === side).sort((a, b) => (a.expires_game_seconds ?? 1e9) - (b.expires_game_seconds ?? 1e9));
}

function penaltyCard(tv, key) {
  const pen = (tv.penalties ?? []).find((e) => e.key === key);
  if (!pen) return "";
  const side = pen.side;
  const name = pen.player ? who(pen.player) : "Lagstraff";
  const minutes = pen.data?.minutes ? `${pen.data.minutes} min` : "";
  const active = (tv.penalties_active ?? []).find((p) => p.key === key);
  const until = active?.expires_game_seconds != null ? `till ${gameClock(active.expires_game_seconds)}` : "";
  const st = tv.strength ?? {};
  const pp = st.pp_side === other(side) ? html`<div class="pc-line pc-pp"><span class="dot"></span>POWERPLAY ${caps(shortName(tv, other(side)))}${count(st) ? ` · ${count(st)}` : ""}</div>` : "";
  return html`<div class="tv-penalty" style="--c: var(--${side})">${raw(logo(tv, side, "pc-logo"))}
    <div class="pc-body"><div class="pc-line tv-label">UTVISNING · ${caps(shortName(tv, side))}</div>
      <div class="pc-line pc-name">${name}</div>
      <div class="pc-line pc-detail">${[pen.data?.offence_text, minutes, until].filter(Boolean).join(" · ")}</div>${raw(pp)}</div></div>`;
}

/** "POWERPLAY ÖREBRO · 5 MOT 4 · TILL P2 14:23" while a power play runs. */
function pill(ctx) {
  const slot = ctx.root.querySelector(".tv-pill-slot");
  if (!slot) return;
  const tv = ctx.tv;
  const st = tv.strength ?? {};
  const pp = st.pp_side;
  // while the penalty's lower third is up it says the same; the pill comes after it
  if (!pp || tv.period === "shootout" || ctx.overlay?.overlay === "penalty") {
    delete slot.dataset.text;
    slot.innerHTML = "";
    return;
  }
  const first = running(tv, other(pp))[0];
  const until = first?.expires_game_seconds != null ? ` · TILL ${gameClock(first.expires_game_seconds)}` : "";
  const text = `POWERPLAY ${caps(shortName(tv, pp))}${count(st) ? ` · ${count(st)}` : ""}${until}`;
  if (slot.dataset.text === text) return;
  const fresh = !slot.dataset.text;
  slot.dataset.text = text;
  slot.innerHTML = html`<div class="tv-pp-pill" style="--c: var(--${pp})"><span class="dot"></span>${text}</div>`;
  if (fresh) gsap.from(slot.firstChild, { opacity: 0, y: 20, duration: 0.35, ease: "power2.out" });
}
