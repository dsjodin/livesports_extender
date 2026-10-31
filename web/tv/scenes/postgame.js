// postgame on the TV (L-frame): the final score in the band; the column pages through
// the final statistics, the goals (and the shootout) and the table.
import { caps, html, raw } from "../../shared/format.js";
import { goalsList, shotsCompare, specialTeams, tableSlide } from "./intermission.js";
import { head, lframe, play, row, scoreboard, slideshow, slides, stopTimers, who } from "./common.js";

export function enter(ctx, data, at) {
  render(ctx);
  const tl = gsap.timeline({ paused: true });
  tl.from(ctx.root.querySelectorAll(".tv-col, .tv-band"), { opacity: 0, y: 30, duration: 0.5, ease: "power2.out", stagger: 0.1 });
  play(ctx, at, tl);
}

export function update(ctx) {
  render(ctx);
}

export function exit(ctx) {
  stopTimers(ctx);
}

function render(ctx) {
  stopTimers(ctx);
  const tv = ctx.tv;
  const suffix = tv.went_to_shootout ? "EFTER STRAFFAR" : tv.overtime ? "EFTER FÖRLÄNGNING" : "";
  const band = html`${raw(scoreboard(tv))}<div class="im-next"><span class="pg-final">SLUT</span>
    <span class="tv-label">${suffix || "SLUTRESULTAT"}</span><span class="tv-label quiet">${tv.game?.arena ?? ""}</span></div>`;
  const list = [
    html`${raw(head("SLUT", "SLUTSTATISTIK"))}<div class="cmp-list">${raw(shotsCompare(tv))}${raw(specialTeams(tv))}</div>`,
    html`${raw(head("MATCHEN", "MÅLEN"))}${raw(goalsList(tv, 7))}`,
  ];
  const attempts = tv.shootout ?? [];
  if (attempts.length) {
    const rows = attempts.map((a) => row(`${a.data?.index ?? ""}. ${caps(who(a.player))}`, a.data?.scored ? "MÅL" : "–", a.team_code ?? "", a.side)).join("");
    list.push(html`${raw(head("MATCHEN", "STRAFFLÄGGNING"))}${raw(rows)}`);
  }
  const table = tableSlide(tv);
  if (table) list.push(table);
  ctx.root.innerHTML = lframe(slides(list), band, "postgame");
  slideshow(ctx, tv.scene?.since_ms ?? 0);
}
