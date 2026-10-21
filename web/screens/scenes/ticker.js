// The bar's bottom strip as a ticker: our own line, then the evening's other games, three
// per page, 8 s a page. The page follows from the synced clock, so all screens agree and
// a reload lands on the same page. A goal elsewhere (its score changing in tv.others at
// its play_at) takes the strip in gold for 8 s.
import { caps, esc, score } from "../../shared/format.js";

const PAGE_MS = 8000;
const FLASH_MS = 8000;
const PER_PAGE = 3;

export function gameStatus(o) {
  if (o.ended) return o.went_to_shootout ? "SLUT STR" : o.overtime ? "SLUT ÖT" : "SLUT";
  if (o.phase === "pregame") {
    return o.start_ms ? new Intl.DateTimeFormat("sv-SE", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Stockholm" }).format(o.start_ms) : "";
  }
  if (o.phase === "intermission") return `PAUS P${o.period}`;
  if (o.period === "shootout") return "STR";
  if (typeof o.period === "number" && o.period > 3) return "ÖT";
  return o.period ? `P${o.period}` : "";
}

export function gameLine(o) {
  const h = o.teams.home.code ?? "";
  const a = o.teams.away.code ?? "";
  const middle = o.phase === "pregame" ? "–" : score(o.score.home, o.score.away);
  return `${h} ${middle} ${a} ${gameStatus(o)}`.trim();
}

/** The same as HTML: the score stands out, the status is quieter. */
function gameHtml(o) {
  const h = esc(o.teams.home.code ?? "");
  const a = esc(o.teams.away.code ?? "");
  const middle = o.phase === "pregame" ? "–" : esc(score(o.score.home, o.score.away));
  const live = !o.ended && o.phase !== "pregame";
  return `<span class="tk-game${live ? " live" : ""}"><b>${h} ${middle} ${a}</b> <span class="tk-status">${esc(gameStatus(o))}</span></span>`;
}

function pages(own, others) {
  const out = own ? [esc(own)] : [];
  for (let i = 0; i < others.length; i += PER_PAGE) {
    out.push(others.slice(i, i + PER_PAGE).map(gameHtml).join('<span class="tk-sep">•</span>'));
  }
  return out;
}

/**
 * Run the ticker in ``el`` (the strip). ``own()`` gives our line; ``blocked()`` is true
 * while an overlay owns the strip. Returns {update(tv)} to call on every patch.
 */
export function ticker(ctx, el, own, blocked = () => false) {
  const state = ctx.ticker ?? (ctx.ticker = { scores: null, flash: null });
  let shown = null;

  function show(text, cls) {
    if (shown === `${cls}|${text}`) return;
    const first = shown === null;
    shown = `${cls}|${text}`;
    const apply = () => {
      el.innerHTML = text;
      el.classList.toggle("gold", cls === "gold");
    };
    if (first) return apply();
    gsap.to(el, { opacity: 0, duration: 0.15, onComplete: () => (apply(), gsap.to(el, { opacity: 1, duration: 0.25 })) });
  }

  function tick() {
    if (blocked()) return;
    const now = ctx.now();
    if (state.flash && state.flash.until > now) return show(esc(state.flash.text), "gold");
    const list = pages(own(), ctx.tv.others ?? []);
    if (!list.length) return;
    show(list[Math.floor(now / PAGE_MS) % list.length], "");
  }

  function update(tv) {
    const scores = Object.fromEntries((tv.others ?? []).map((o) => [o.uuid, o]));
    if (state.scores) {
      for (const [uuid, o] of Object.entries(scores)) {
        const before = state.scores[uuid];
        if (!before || o.phase === "pregame") continue;
        const side = o.score.home > before.home ? "home" : o.score.away > before.away ? "away" : null;
        if (side) {
          state.flash = { text: `MÅL ${caps(o.teams[side].short ?? o.teams[side].code)}!  ${gameLine(o)}`, until: ctx.now() + FLASH_MS };
        }
      }
    }
    state.scores = Object.fromEntries(Object.entries(scores).map(([u, o]) => [u, { ...o.score }]));
    tick();
  }

  update(ctx.tv);
  const id = setInterval(tick, 250);
  ctx.timers = [...(ctx.timers ?? []), id];
  return { update };
}
