// goal on the TV: over the full picture, a gold MÅL! band sweeps across the lower part,
// then the lower third: the scorer with portrait, EQ/PP/SH and the time, assists, the
// score after the goal. The scoring team's animation (tvgoal, WebP) plays at play_at.
// A MÅL! press shows the team only ("Väntar på SHL") and is filled in when the feed's goal
// is linked to it (relink), without playing the sequence again.
import { caps, html, raw, score, strengthChip } from "../../shared/format.js";
import { logo, longName, ordinal, periodTime, play } from "./common.js";

const GOLD = "#F5C542";
const GOLD_FLASH = "#FFE08A";

export function enter(ctx, data, at) {
  ctx.data = data;
  const side = goalFor(ctx)?.side ?? data.side ?? "home";
  if (ctx.animate) ctx.anim("tvgoal", side, at);
  render(ctx, at);
}

export function update() {
  // a fixed moment; later patches show when it goes back to live
}

export function relink(ctx, data) {
  ctx.data = data;
  ctx.animate = false;
  render(ctx, ctx.now());
}

export function onEventUpdate(ctx, event) {
  if (event.key !== ctx.data?.event_key) return;
  ctx.animate = false;
  render(ctx, ctx.now());
}

function goalFor(ctx) {
  const key = ctx.data.event_key;
  const d = ctx.data;
  const manual = d.manual ? { key: d.event_key, side: d.side, player: null, data: { manual: true, score: d.score } } : undefined;
  return (ctx.tv.goals ?? []).find((g) => g.key === key) ?? ctx.goalEvent(key) ?? manual;
}

function render(ctx, at) {
  const tv = ctx.tv;
  const goal = goalFor(ctx);
  const side = goal?.side ?? ctx.data.side ?? "home";
  const p = goal?.player;
  const d = goal?.data ?? {};
  const sc = d.score ?? tv.score ?? { home: 0, away: 0 };
  const chips = [
    strengthChip(d.strength, d.empty_net),
    d.penalty_shot ? "STRAFFSLAG" : null,
    goal?.time ? periodTime(goal) : null,
    d.scorer_game_goals === 3 ? "HATTRICK" : d.scorer_game_goals > 1 ? `${caps(ordinal(d.scorer_game_goals))} MÅLET IKVÄLL` : null,
    goal?.test ? "TEST" : null,
  ].filter(Boolean);
  const assists = (d.assists ?? []).slice(0, 2).map((a) => `#${a.number} ${a.first ?? ""} ${a.last ?? ""}`.trim());
  const portrait = p?.id ? `<img class="gl-portrait" src="/assets/players/${encodeURIComponent(p.id)}.png" alt="" onerror="this.remove()">` : "";
  const name = p ? html`<div class="gl-first">${p.number != null ? `#${p.number} ` : ""}${p.first ?? ""}</div><div class="gl-last">${caps(p.last ?? "")}</div>`
    : html`<div class="gl-first">${d.manual ? "Väntar på SHL" : ""}</div><div class="gl-last">${caps(longName(tv, side))}</div>`;
  ctx.root.innerHTML = html`<div class="gl-sweep"></div>
    <div class="tv-goal" style="--c: var(--${side}); --on: var(--on-${side})">${raw(portrait)}
      <div class="gl-head"><span class="gl-mal">MÅL!</span><span class="gl-team">${caps(longName(tv, side))}</span></div>
      <div class="gl-body ${p?.id ? "with-portrait" : ""}">
        <div class="gl-who">${raw(name)}
          <div class="gl-chips">${raw(chips.map((c) => html`<span class="chip ${c === "PP" ? "gold" : ""}">${c}</span>`).join(""))}</div>
          <div class="gl-assist">${d.manual ? "" : assists.length ? `Assist: ${assists.join(", ")}` : "Utan assist"}</div></div>
        <div class="gl-score">${raw(logo(tv, "home", "gl-logo"))}<span>${score(sc.home, sc.away)}</span>${raw(logo(tv, "away", "gl-logo"))}</div>
      </div></div>`;
  const q = (s) => ctx.root.querySelector(s);
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(q(".gl-sweep"), { xPercent: -110 }, { xPercent: 110, duration: 0.9, ease: "power2.inOut" }, 0);
  tl.from(q(".tv-goal"), { y: 80, opacity: 0, duration: 0.45, ease: "power3.out" }, 0.35);
  tl.fromTo(q(".gl-head"), { backgroundColor: GOLD }, { backgroundColor: GOLD_FLASH, duration: 0.45, repeat: 9, yoyo: true, ease: "none" }, 0.35);
  if (q(".gl-portrait")) tl.from(q(".gl-portrait"), { opacity: 0, x: -40, duration: 0.5, ease: "power2.out" }, 0.8);
  tl.from([q(".gl-first"), q(".gl-last")], { x: 60, opacity: 0, duration: 0.4, ease: "power3.out", stagger: 0.1 }, 0.8);
  tl.from(ctx.root.querySelectorAll(".chip"), { scale: 0.6, opacity: 0, duration: 0.3, ease: "back.out(2)", stagger: 0.07 }, 1.2);
  tl.from([q(".gl-assist"), q(".gl-score")], { y: 20, opacity: 0, duration: 0.35, stagger: 0.08 }, 1.5);
  play(ctx, at, tl);
}
