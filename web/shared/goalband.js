// The cross-screen goal effect: a gold band defined in stage millimetres sweeps from the
// bar's centre outward over both side screens, starting at play_at. Every screen draws
// only its own part, so the band keeps its size and speed across pixel densities.
import { now } from "./clock.js";
import * as stage from "./stage.js";

const BAND_MM = 90;
const SWEEP_MS = 600;
const FADE_MS = 350;

export function goalBand(screenId, host, playAt) {
  const s = stage.screen(screenId);
  const bar = stage.screen("bar");
  const b = stage.bounds();
  const centre = bar.position_mm[0] + bar.physical_mm[0] / 2;
  const widthPx = BAND_MM * s.pxPerMm;
  const bands = [-1, 1].map(() => {
    const el = document.createElement("div");
    el.className = "goal-band";
    el.style.width = `${widthPx}px`;
    host.appendChild(el);
    return el;
  });
  const reach = [centre - b.x0 + BAND_MM, b.x1 - centre + BAND_MM];

  function frame() {
    const t = now() - playAt;
    if (t > SWEEP_MS + FADE_MS) {
      bands.forEach((el) => el.remove());
      return;
    }
    const p = Math.min(1, Math.max(0, t / SWEEP_MS));
    const eased = 1 - (1 - p) ** 3;
    bands.forEach((el, i) => {
      const xMm = centre + (i ? 1 : -1) * eased * reach[i];
      const [xPx] = s.mmToPx(xMm, 0);
      el.style.transform = `translateX(${(xPx - widthPx / 2).toFixed(1)}px)`;
      el.style.opacity = t < 0 ? "0" : t <= SWEEP_MS ? "1" : String(1 - (t - SWEEP_MS) / FADE_MS);
    });
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
