// live (mockup scene 2), with the penalty, timeout and disallowed-goal overlays as
// data.overlay (docs/SCREENS.md, Scenes).
import { shotLegend, shotMap, tile } from "../../shared/components.js";
import { caps, html, penaltyTime, periodName, raw, score } from "../../shared/format.js";
import { barPage, fitText, other, periodLabel, play, shortName, statsLine, stopTimers, team, teamHead, venueLine, who } from "./common.js";
import { ticker } from "./ticker.js";

export function enter(ctx, data, at) {
  // puck drop: the intro, unless it already ran at the scheduled start (docs/SCREENS.md)
  if (ctx.animate && ctx.kind === "portrait" && ctx.previous === "pregame") ctx.video("intro", at);
  ctx.overlay = data.overlay ? data : null;
  render(ctx);
  animateOverlay(ctx, at);
}

export function overlay(ctx, data, at) {
  ctx.overlay = data.overlay ? data : null;
  render(ctx);
  animateOverlay(ctx, at);
}

export function update(ctx) {
  render(ctx);
}

export function exit(ctx) {
  stopTimers(ctx);
}

function render(ctx) {
  const tv = ctx.tv;
  ctx.root.innerHTML = ctx.kind === "bar" ? bar(tv, ctx.overlay) : portrait(tv, ctx.side, ctx.overlay);
  fitText(ctx.root);
  if (ctx.kind === "bar") {
    stopTimers(ctx);
    const overlay = ctx.overlay?.overlay;
    ticker(ctx, ctx.root.querySelector(".strip"), () => ownLine(ctx.tv), () => overlay === "penalty" || overlay === "timeout");
  }
}

function ownLine(tv) {
  return `${statsLine(tv)}${venueLine(tv) ? ` • ${venueLine(tv)}` : ""}`;
}

function animateOverlay(ctx, at) {
  const el = ctx.root.querySelector(".banner-overlay, .strip.alert, .strip.gold");
  if (!el || !ctx.overlay) return;
  const tl = gsap.timeline({ paused: true });
  tl.from(el, { opacity: 0, duration: 0.3, ease: "power2.out" });
  if (el.classList.contains("banner-overlay")) tl.from(el, { scaleY: 0, duration: 0.35, ease: "power3.out" }, 0);
  play(ctx, at, tl);
}

// --- bar ------------------------------------------------------------------------------

export function strengthPill(tv) {
  const st = tv.strength ?? {};
  if (!st.home || !st.away || tv.period === "shootout") return "";
  const normal = tv.overtime ? 3 : 5;
  if (st.home === normal && st.away === normal) return "";
  const count = `${st.home} MOT ${st.away}`;
  if (!st.pp_side) return html`<span class="pill">${count}</span>`;
  const big = Math.abs(st.home - st.away) > 1 || Math.min(st.home, st.away) < normal - 1;
  return html`<span class="pill gold"><span class="dot"></span>PP ${caps(shortName(tv, st.pp_side))}${big ? ` · ${count}` : ""}</span>`;
}

function bar(tv, ov) {
  const p = periodLabel(tv);
  const centre = html`<div class="label">${p.label}</div><div class="period">${p.big}</div>${raw(strengthPill(tv))}`;
  let strip = ownLine(tv);
  let stripClass = "";
  if (ov?.overlay === "penalty") {
    const pen = (tv.penalties ?? []).find((e) => e.key === ov.event_key);
    if (pen) {
      const name = pen.player ? `#${pen.player.number} ${pen.player.last}` : "LAGSTRAFF";
      strip = `UTVISNING ${pen.team_code ?? ""} ${name} · ${pen.data?.offence_text ?? ""} ${caps(penaltyTime(pen.data?.kind, pen.data?.minutes).text)}`;
      stripClass = "alert";
    }
  } else if (ov?.overlay === "timeout") {
    strip = `TIMEOUT ${caps(shortName(tv, ov.side))}`;
    stripClass = "gold";
  }
  const page = barPage(tv, { centre, strip: html`${strip}`, stripClass });
  return ov?.overlay === "goal_disallowed" ? page + `<div class="banner-overlay">MÅLET UNDERKÄNT</div>` : page;
}

// --- portrait -------------------------------------------------------------------------

function portrait(tv, side, ov) {
  // Sized for 3 m (docs/SCREENS.md, Type): the goalie and save % are in the intermission;
  // an empty net still shows, as it changes the game
  const s = tv.stats?.[side] ?? {};
  const pulled = s.goalie?.pulled ? html`<div class="card pulled-card"><div class="label">TOM BUR</div><div class="latest-text">Målvakten utbytt</div></div>` : "";
  return html`<div class="portrait-page">${raw(teamHead(tv, side, "", { compact: true }))}
    <div class="tiles">${raw(tile("SKOTT", s.shots_on_goal ?? 0))}${raw(tile("MÅL", tv.score?.[side] ?? 0))}${raw(tile("UTV.MIN", s.pim ?? 0))}</div>
    ${raw(pulled)}
    <div class="map-block">${raw(shotMap(tv.shots?.[side], side))}${raw(shotLegend(side))}</div>
    <div class="bottom-slot">${raw(bottom(tv, side, ov))}</div></div>
    ${raw(ov?.overlay === "goal_disallowed" ? `<div class="banner-overlay">MÅLET UNDERKÄNT</div>` : "")}`;
}

function bottom(tv, side, ov) {
  const active = tv.penalties_active ?? [];
  const mine = active.filter((p) => p.side === side);
  const theirs = active.filter((p) => p.side === other(side));
  const st = tv.strength ?? {};
  if (st.pp_side === side && theirs.length) {
    const p = theirs[0];
    const count = st.home - st.away === 2 || st.away - st.home === 2 ? ` · ${st[side]} MOT ${st[other(side)]}` : "";
    return html`<div class="pp-banner"><div class="pp-title"><span class="dot"></span>POWERPLAY${count}</div>
      <div class="pp-detail">${p.number ? `#${p.number} ${lastName(p.name)}` : "Lagstraff"} · ${p.offence_text ?? ""} ${penaltyTime(p.kind, p.minutes).text}</div></div>`;
  }
  if (mine.length) {
    const emphKey = ov?.overlay === "penalty" ? ov.event_key : null;
    const [p, ...rest] = [...mine].sort((a, b) => (b.key === emphKey) - (a.key === emphKey));
    const more = rest.map((r) => `#${r.number ?? ""} ${r.name ?? "Lagstraff"} · ${r.offence_text ?? ""} ${penaltyTime(r.kind, r.minutes).text}`).join(", ");
    return html`<div class="pen-card ${p.key === emphKey ? "emph" : ""}"><div class="label">UTVISNING</div>
      <div class="pen-name">${p.number ? `#${p.number} ${p.name ?? ""}` : "Lagstraff"}</div>
      <div class="pen-detail">${p.offence_text ?? ""} · ${penaltyTime(p.kind, p.minutes).text} · ${p.started}</div>
      ${raw(more ? html`<div class="pen-detail">Även: ${more}</div>` : "")}</div>`;
  }
  return latest(tv);
}

const lastName = (name) => (name ?? "").split(" ").slice(-1)[0];

/** The "SENASTE" card: the newest released event, in Swedish. */
function latest(tv) {
  const last = [...(tv.recent ?? [])].reverse().find((r) => r.type !== "shot");
  if (!last) return html`<div class="card alt latest"><div class="label">SENASTE</div><div class="latest-text">Inget ännu</div></div>`;
  const when = last.time ? `${periodName(last.period)} ${last.time}` : periodName(last.period);
  const code = last.side ? team(tv, last.side).code ?? "" : "";
  let title = "SENASTE";
  let text = last.type;
  let detail = when;
  if (last.type === "goal") {
    const g = (tv.goals ?? []).find((e) => e.key === last.key);
    title = `SENASTE · MÅL ${code}`;
    text = who(g?.player) || "Mål";
    detail = `${when} · ${score(g?.data?.score?.home, g?.data?.score?.away)}`;
  } else if (last.type === "penalty") {
    const p = (tv.penalties ?? []).find((e) => e.key === last.key);
    title = `SENASTE · UTVISNING ${code}`;
    text = who(p?.player) || "Lagstraff";
    detail = `${p?.data?.offence_text ?? ""} · ${penaltyTime(p?.data?.kind, p?.data?.minutes).text} · ${when}`;
  } else if (last.type === "period_start") {
    text = `${periodName(last.period)} är igång`;
    detail = "";
  } else if (last.type === "period_end") {
    text = `${periodName(last.period)} är slut`;
    detail = "";
  } else if (last.type === "timeout") {
    text = `Timeout ${shortName(tv, last.side)}`;
  } else if (last.type === "goalie_change") {
    text = `Målvaktsbyte ${code}`;
  } else if (last.type === "goal_disallowed") {
    text = `Mål underkänt ${code}`;
  }
  return html`<div class="card alt latest"><div class="label">${title}</div><div class="latest-text">${text}</div>
    ${raw(detail ? html`<div class="secondary">${detail}</div>` : "")}</div>`;
}
