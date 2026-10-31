// live on the TV: the full picture, and only what the broadcast does not show itself
// (it has its own score bug). A penalty is a lower third for a few seconds when it
// happens (the director's overlay), then a small power-play pill stays bottom right until
// the power play is over; a timeout and a disallowed goal are short banners. Lower thirds
// keep clear of the broadcaster's ticker (bottom 8 %) and its bug (top left).
import { caps, html, raw } from "../../shared/format.js";
import { gameClock, longName, other, periodTime, play, shortName } from "./common.js";

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
  let card = "";
  if (ov?.overlay === "penalty") card = penaltyCard(ctx.tv, ov.event_key);
  else if (ov?.overlay === "timeout") lower = banner(`TIMEOUT ${caps(shortName(ctx.tv, ov.side))}`, "gold");
  else if (ov?.overlay === "goal_disallowed") lower = banner("MÅLET UNDERKÄNT", "alert");
  ctx.root.innerHTML = `${card}<div class="tv-lower-slot">${lower}</div><div class="tv-pill-slot"></div>`;
  pill(ctx);
}

function animate(ctx, at) {
  const q = (sel) => ctx.root.querySelector(sel);
  const tl = gsap.timeline({ paused: true });
  const card = q(".tv-goal");
  if (card) {
    // as the goal's lower third (goal.js), without the sweep
    tl.from(card, { y: 80, opacity: 0, duration: 0.45, ease: "power3.out" });
    if (q(".gl-portrait")) tl.from(q(".gl-portrait"), { opacity: 0, x: -40, duration: 0.5, ease: "power2.out" }, 0.3);
    tl.from([q(".gl-first"), q(".gl-last")], { x: 60, opacity: 0, duration: 0.4, ease: "power3.out", stagger: 0.1 }, 0.3);
    tl.from(ctx.root.querySelectorAll(".chip"), { scale: 0.6, opacity: 0, duration: 0.3, ease: "back.out(2)", stagger: 0.07 }, 0.6);
    tl.from([q(".gl-assist"), q(".gl-score")].filter(Boolean), { y: 20, opacity: 0, duration: 0.35, stagger: 0.08 }, 0.8);
    return play(ctx, at, tl);
  }
  const el = q(".tv-lower-slot > *");
  if (!el) return;
  tl.from(el, { x: -80, opacity: 0, duration: 0.4, ease: "power3.out" });
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

/** The penalty's lower third, built as the goal's (goal.js, asked for by the user
 * 2026-10-31): a band in the penalty colour with the team, the player with portrait, the
 * offence, minutes and when it ends as chips, the power play it gives, the minutes big. */
function penaltyCard(tv, key) {
  const pen = (tv.penalties ?? []).find((e) => e.key === key);
  if (!pen) return "";
  const side = pen.side;
  const p = pen.player;
  const d = pen.data ?? {};
  const active = (tv.penalties_active ?? []).find((x) => x.key === key);
  const chips = [
    d.offence_text,
    pen.time ? periodTime(pen) : null,
    active?.expires_game_seconds != null ? `TILL ${gameClock(active.expires_game_seconds)}` : null,
  ].filter(Boolean);
  const st = tv.strength ?? {};
  const pp = st.pp_side === other(side) ? `POWERPLAY ${caps(shortName(tv, other(side)))}${count(st) ? ` · ${count(st)}` : ""}` : "";
  const portrait = p?.id ? `<img class="gl-portrait" src="/assets/players/${encodeURIComponent(p.id)}.png" alt="" onerror="this.remove()">` : "";
  const name = p
    ? html`<div class="gl-first">${p.number != null ? `#${p.number} ` : ""}${p.first ?? ""}</div><div class="gl-last">${caps(p.last ?? "")}</div>`
    : html`<div class="gl-first">Lagstraff</div><div class="gl-last">${caps(longName(tv, side))}</div>`;
  return html`<div class="tv-goal pen" style="--c: var(--${side})">${raw(portrait)}
    <div class="gl-head"><span class="gl-mal">UTVISNING</span><span class="gl-team">${caps(longName(tv, side))}</span></div>
    <div class="gl-body">
      <div class="gl-who">${raw(name)}
        <div class="gl-chips">${raw(chips.map((c) => html`<span class="chip">${c}</span>`).join(""))}</div>
        ${raw(pp ? html`<div class="gl-assist pc-pp"><span class="dot"></span>${pp}</div>` : "")}</div>
      ${raw(d.minutes ? html`<div class="gl-score">${d.minutes}<span class="gl-unit">MIN</span></div>` : "")}
    </div></div>`;
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
