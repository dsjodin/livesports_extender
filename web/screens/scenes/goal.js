// goal (mockup scene 3). Timing relative to play_at follows docs/SCREENS.md, Goal sequence.
import { badge, goalRow } from "../../shared/components.js";
import { caps, html, raw, score, strengthChip } from "../../shared/format.js";
import { goalBand } from "../../shared/goalband.js";
import { barPage, barTeam, longName, ordinal, periodTime, play, shortName, team, teamHead, who } from "./common.js";

const FLASH_S = 6;
const GOLD = "#F5C542";
const GOLD_FLASH = "#FFE08A";

export function enter(ctx, data, at) {
  ctx.data = data;
  if (ctx.animate) goalBand(ctx.screen, ctx.fx, at);
  render(ctx, at);
}

export function update() {
  // The goal scene is a fixed moment; later patches show up when it goes back to live.
}

export function onEventUpdate(ctx, event) {
  // A corrected scorer or assist: redraw the text without replaying the sequence.
  if (event.key !== ctx.data?.event_key) return;
  ctx.animate = false;
  render(ctx, ctx.now());
}

function render(ctx, at) {
  const tv = ctx.tv;
  const goal = (tv.goals ?? []).find((g) => g.key === ctx.data.event_key);
  const side = goal?.side ?? ctx.data.side ?? "home";
  if (ctx.kind === "bar") bar(ctx, tv, goal, side, at);
  else if (ctx.side === side) scorer(ctx, tv, goal, side, at);
  else conceded(ctx, tv, goal, side, at);
}

function scoreAfter(tv, goal) {
  return goal?.data?.score ?? tv.score ?? { home: 0, away: 0 };
}

// --- bar ------------------------------------------------------------------------------

function bar(ctx, tv, goal, side, at) {
  const sc = scoreAfter(tv, goal);
  const before = { ...sc, [side]: Math.max(0, (sc[side] ?? 0) - 1) };
  const teams = {};
  for (const s of ["home", "away"]) {
    teams[s] = barTeam(tv, s, before[s], { flash: s === side, id: s === side ? "goal-box" : "" });
  }
  const strength = goal?.data?.strength;
  const tag = goal?.data?.empty_net ? "TOM BUR" : strength?.startsWith("PP") ? "PP" : strength?.startsWith("SH") ? "BOXPLAY" : null;
  const when = goal ? `P${goal.period} ${goal.time}` : "";
  const centre = html`<div class="big-word gold" id="goal-word">MÅL</div><div class="mid">${[tag, when].filter(Boolean).join(" · ")}</div>`;
  const assists = (goal?.data?.assists ?? []).map((a) => `#${a.number} ${caps(a.last)}`).join(", ");
  const strip = [caps(who(goal?.player)), assists ? `ASSIST ${assists}` : "UTAN ASSIST"].filter(Boolean).join(" • ");
  ctx.root.innerHTML = barPage(tv, { home: teams.home, away: teams.away, centre, strip: html`${strip}`, stripClass: "gold" });

  const box = ctx.root.querySelector("#goal-box");
  const digits = box.querySelector(".digits");
  const tl = gsap.timeline({ paused: true });
  tl.from("#goal-word", { scale: 0.3, opacity: 0, duration: 0.45, ease: "back.out(2)" }, 0);
  tl.from(ctx.root.querySelector(".strip"), { opacity: 0, duration: 0.3 }, 0);
  tl.to(digits, { scaleY: 0, duration: 0.12, ease: "power1.in" }, 0.18);
  tl.call(() => (digits.textContent = sc[side]), null, 0.3);
  tl.to(digits, { scaleY: 1, duration: 0.18, ease: "power2.out" }, 0.3);
  tl.fromTo(box, { backgroundColor: GOLD }, { backgroundColor: GOLD_FLASH, duration: 0.45, repeat: 13, yoyo: true, ease: "none" }, 0);
  play(ctx, at, tl);
}

// --- scoring side ---------------------------------------------------------------------

function scorer(ctx, tv, goal, side, at) {
  const p = goal?.player ?? {};
  const d = goal?.data ?? {};
  const chips = [
    p.number ? `#${p.number}` : null,
    strengthChip(d.strength, d.empty_net),
    d.penalty_shot ? "STRAFFSLAG" : null,
    goal ? periodTime(goal) : null,
    d.scorer_game_goals === 3 ? "HATTRICK" : d.scorer_game_goals > 1 ? `${caps(ordinal(d.scorer_game_goals))} MÅLET IKVÄLL` : null,
  ].filter(Boolean);
  const assists = (d.assists ?? []).slice(0, 2);
  const sc = scoreAfter(tv, goal);
  const onIce = (d.on_ice ?? []).slice(0, 6);
  const portrait = p.id ? `<img class="portrait-img" src="/assets/players/${encodeURIComponent(p.id)}.png" alt="" onerror="this.remove()">` : "";
  ctx.root.innerHTML = html`<div class="portrait-page goal-page" style="--c: var(--${side})">
    <div class="goal-head"><div class="mal">MÅL!</div><div class="goal-team">${caps(longName(tv, side))}</div></div>
    <div class="goal-body">
      ${raw(p.number ? html`<div class="outline-number">${p.number}</div>` : "")}${raw(portrait)}
      <div class="scorer"><div class="label">MÅLSKYTT</div><div class="first">${p.first ?? ""}</div><div class="last">${caps(p.last ?? "")}</div></div>
      <div class="chips">${raw(chips.map((c) => html`<span class="chip ${c === "POWERPLAY" ? "gold" : ""}">${c}</span>`).join(""))}</div>
      <div class="card assist-card"><div class="label">ASSIST</div>
        ${raw(assists.length ? assists.map((a) => html`<div class="assist-name">#${a.number} ${a.first} ${a.last}</div>`).join("") : `<div class="assist-name secondary">Utan assist</div>`)}</div>
      <div class="score-row">${raw(badge(team(tv, "home"), "home", "md"))}<div class="big">${score(sc.home, sc.away)}</div>${raw(badge(team(tv, "away"), "away", "md"))}</div>
      ${raw(onIce.length ? html`<div class="onice-block"><div class="label">PÅ ISEN</div><div class="onice">${raw(onIce.map((o) => html`<div><b>#${o.number}</b>${o.last}</div>`).join(""))}</div></div>` : "")}
    </div></div>`;

  const q = (s) => ctx.root.querySelector(s);
  const qa = (s) => ctx.root.querySelectorAll(s);
  const tl = gsap.timeline({ paused: true });
  const head = q(".goal-head");
  tl.from(head, { yPercent: -100, duration: 0.35, ease: "power3.out" }, 0);
  tl.fromTo(head, { backgroundColor: GOLD }, { backgroundColor: GOLD_FLASH, duration: 0.45, repeat: Math.round(FLASH_S / 0.45) - 1, yoyo: true, ease: "none" }, 0);
  tl.from([q(".outline-number"), q(".portrait-img")].filter(Boolean), { opacity: 0, duration: 0.5, ease: "power1.out" }, 0.6);
  tl.from([q(".scorer .label"), q(".scorer .first"), q(".scorer .last")], { x: 80, opacity: 0, duration: 0.45, ease: "power3.out", stagger: 0.12 }, 0.6);
  tl.from(qa(".chip"), { scale: 0.6, opacity: 0, duration: 0.3, ease: "back.out(2)", stagger: 0.08 }, 1.2);
  tl.from([q(".assist-card"), q(".score-row"), q(".onice-block")].filter(Boolean), { y: 40, opacity: 0, duration: 0.4, ease: "power2.out", stagger: 0.06 }, 1.8);
  play(ctx, at, tl);
}

// --- the other side -------------------------------------------------------------------

function conceded(ctx, tv, goal, side, at) {
  const me = ctx.side;
  const sc = scoreAfter(tv, goal);
  const lead = sc.home === sc.away ? null : sc.home > sc.away ? "home" : "away";
  const line = lead ? `${caps(shortName(tv, lead))} LEDER` : "KVITTERING";
  const st = tv.stats ?? {};
  const goals = (tv.goals ?? []).slice(-7);
  ctx.root.innerHTML = html`<div class="portrait-page">
    <div class="dim-wrap">${raw(teamHead(tv, me))}</div>
    <div><div class="label">MÅL ${team(tv, side).code ?? ""}</div><div class="big-line">${line} ${score(sc.home, sc.away)}</div></div>
    <div class="label">SKOTT ${score(st.home?.shots_on_goal, st.away?.shots_on_goal)}</div>
    <div class="list"><div class="label">MÅLEN</div>${raw(goals.map((g) => goalRow(g, false).replace('class="goal-row', `data-key="${g.key}" class="goal-row`)).join(""))}</div>
  </div>`;
  const tl = gsap.timeline({ paused: true });
  tl.to(ctx.root.querySelector(".dim-wrap"), { opacity: 0.6, duration: 0.4, ease: "power1.out" }, 0);
  tl.from(ctx.root.querySelectorAll(".big-line, .list"), { y: 30, opacity: 0, duration: 0.4, stagger: 0.1 }, 0.3);
  const row = goal ? ctx.root.querySelector(`[data-key="${goal.key}"]`) : null;
  if (row) tl.call(() => row.classList.add("highlight"), null, 1.5);
  play(ctx, at, tl);
}
