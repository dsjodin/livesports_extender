// Shared building blocks for the scenes (docs/SCREENS.md, Components). They return HTML.
import { caps, decimal, esc, html, percent, raw, score, strengthChip } from "./format.js";

export function teamVars(root, teams) {
  for (const side of ["home", "away"]) {
    const t = teams?.[side] ?? {};
    const color = t.color || "#8A93A6";
    root.style.setProperty(`--${side}`, color);
    root.style.setProperty(`--on-${side}`, t.on || "#0B0F17");
    root.style.setProperty(`--${side}-outline`, t.outline ? "rgba(255,255,255,0.55)" : "transparent");
  }
}

export function badge(team, side, size = "md") {
  const code = team?.code ?? "";
  const logo = team?.logo
    ? html`<img src="${team.logo}" alt="" onerror="this.remove()">`
    : "";
  return html`<div class="badge badge-${size}" style="--c: var(--${side}); --on: var(--on-${side}); --ol: var(--${side}-outline)"><span>${code}</span>${raw(logo)}</div>`;
}

export function tile(label, value, extra = "") {
  return html`<div class="tile ${extra}"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

export function goalieCard(goalie) {
  if (!goalie) return "";
  const saves = goalie.saves ?? 0;
  const against = goalie.shots_against ?? 0;
  const pct = against ? saves / against : null;
  const name = goalie.on_ice ? `#${goalie.number ?? ""} ${goalie.name ?? ""}` : "";
  return html`<div class="card goalie ${goalie.pulled ? "pulled" : ""}">
    <div><div class="label">${goalie.pulled ? "TOM BUR" : "MÅLVAKT"}</div>
    <div class="goalie-name">${goalie.pulled ? "Målvakten utbytt" : name}</div></div>
    <div class="goalie-stats"><div class="goalie-pct">${percent(pct)}</div>
    <div class="secondary">${saves} räddningar</div></div></div>`;
}

export function goalRow(goal, highlight = false) {
  const p = goal.player ?? {};
  const assists = (goal.data?.assists ?? []).map((a) => `#${a.number} ${a.last}`).join(", ");
  const chip = strengthChip(goal.data?.strength, goal.data?.empty_net);
  const sc = goal.data?.score ?? {};
  return html`<div class="goal-row ${highlight ? "highlight" : ""}" style="--c: var(--${goal.side})">
    <div class="goal-meta">P${goal.period} ${goal.time} · ${goal.team_code}${chip ? ` · ${chip}` : ""}</div>
    <div class="goal-scorer">#${p.number ?? ""} ${p.first ?? ""} ${p.last ?? ""}</div>
    <div class="goal-assist">${assists ? `Assist: ${assists}` : "Inget assist"}</div>
    <div class="goal-score">${score(sc.home, sc.away)}</div></div>`;
}

export function penaltyRow(pen) {
  const p = pen.player ?? {};
  const who = pen.player ? `#${p.number} ${p.first ?? ""} ${p.last ?? ""}` : "Lagstraff";
  return html`<div class="pen-row" style="--c: var(--${pen.side})">
    <div class="pen-time">P${pen.period} ${pen.time}</div><div class="pen-team">${pen.team_code}</div>
    <div class="pen-who">${who}<span class="secondary"> · ${pen.data?.offence_text ?? ""}</span></div>
    <div class="pen-min">${pen.data?.minutes ?? ""} min</div></div>`;
}

export function compareRow(label, home, away, homeText = home, awayText = away) {
  const total = (Number(home) || 0) + (Number(away) || 0);
  const share = total ? (Number(home) || 0) / total : 0.5;
  return html`<div class="cmp">
    <div class="cmp-values"><span class="cmp-home">${homeText}</span><span class="label">${label}</span><span class="cmp-away">${awayText}</span></div>
    <div class="cmp-bar"><div style="width:${(share * 100).toFixed(1)}%; background: var(--home)"></div><div style="flex:1; background: var(--away)"></div></div></div>`;
}

export function formRow(row) {
  const won = row.result === "V";
  return html`<div class="form-row"><span class="form-chip ${won ? "won" : "lost"}">${row.result}</span>
    <span class="secondary">${row.date ? row.date.slice(5).split("-").reverse().map(Number).join("/") : ""}</span>
    <span>${row.home_away} ${row.opponent ?? ""}</span><span class="muted">${row.note ?? ""}</span>
    <span class="form-score">${row.score}</span></div>`;
}

// --- shot map (docs/SCREENS.md, Shot map), in decimetres -------------------------------
const W = 300;
const MARK = 1.4; // shot symbols, scaled up for 3 m (about 10 mm on the wall)
const GOAL_LINE = 40;
const BLUE = GOAL_LINE + 180;
const H = BLUE + 14;

function star(cx, cy, r) {
  const pts = [];
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    const rr = i % 2 ? r * 0.45 : r;
    pts.push(`${(cx + rr * Math.cos(a)).toFixed(1)},${(cy + rr * Math.sin(a)).toFixed(1)}`);
  }
  return `<polygon class="shot-goal" points="${pts.join(" ")}"/>`;
}

export function shotMap(shots, side) {
  const c = `var(--${side})`;
  const marks = (shots ?? [])
    .filter((s) => s.x_dm >= 0 && s.x_dm <= BLUE - GOAL_LINE)
    .map((s) => {
      const x = W / 2 + s.y_dm;
      const y = GOAL_LINE + s.x_dm;
      const k = MARK;
      if (s.goal) return star(x, y, 7.2 * k);
      if (s.result === "blocked") return `<rect class="shot" x="${x - 3.4 * k}" y="${y - 3.4 * k}" width="${6.8 * k}" height="${6.8 * k}" style="fill:${c}"/>`;
      if (s.result === "wide") return `<path class="shot-wide" d="M${x - 3.6 * k} ${y - 3.6 * k}L${x + 3.6 * k} ${y + 3.6 * k}M${x + 3.6 * k} ${y - 3.6 * k}L${x - 3.6 * k} ${y + 3.6 * k}" style="stroke:${c}"/>`;
      return `<circle class="shot" cx="${x}" cy="${y}" r="${3.9 * k}" style="fill:${c}"/>`;
    })
    .join("");
  const r = 85;
  return `<svg class="shotmap" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
    <path class="rink" d="M0 ${H} V${r} Q0 0 ${r} 0 H${W - r} Q${W} 0 ${W} ${r} V${H}"/>
    <line class="rink-red" x1="${11}" y1="${GOAL_LINE}" x2="${W - 11}" y2="${GOAL_LINE}"/>
    <path class="crease" d="M${W / 2 - 18} ${GOAL_LINE} A18 18 0 0 0 ${W / 2 + 18} ${GOAL_LINE} Z"/>
    <rect class="net" x="${W / 2 - 9.15}" y="${GOAL_LINE - 11}" width="18.3" height="11"/>
    ${[-70, 70].map((dx) => `<circle class="faceoff" cx="${W / 2 + dx}" cy="${GOAL_LINE + 60}" r="45"/><circle class="faceoff-dot" cx="${W / 2 + dx}" cy="${GOAL_LINE + 60}" r="2.4"/>`).join("")}
    <line class="rink-blue" x1="0" y1="${BLUE}" x2="${W}" y2="${BLUE}"/>
    ${marks}</svg>`;
}

export function shotLegend(side) {
  return `<div class="legend">
    <span><svg viewBox="-5 -5 10 10"><circle r="4" style="fill:var(--${side})"/></svg>På mål</span>
    <span><svg viewBox="-5 -5 10 10"><path d="M-3.5 -3.5L3.5 3.5M3.5 -3.5L-3.5 3.5" style="stroke:var(--${side});stroke-width:1.5"/></svg>Utanför</span>
    <span><svg viewBox="-5 -5 10 10"><rect x="-3.5" y="-3.5" width="7" height="7" style="fill:var(--${side})"/></svg>Täckt</span>
    <span><svg viewBox="-8 -8 16 16">${star(0, 0, 7)}</svg>Mål</span></div>`;
}

export { caps, decimal, esc };
