// Stage coordinates (docs/SCREENS.md): millimetres, origin at the top-left of the left
// screen's active area. Converts to and from this screen's CSS pixels.
let wall = null;

/** ``base``: the service's origin when the page runs elsewhere (the TV app's shell). */
export async function load(base = "") {
  if (!wall) wall = await (await fetch(`${base}/api/wall`)).json();
  return wall;
}

/** One screen of the wall, or the TV (``tv``, not on the wall: no position). */
export function screen(id) {
  const s = id === "tv" ? { position_mm: [0, 0], ...wall.tv } : wall.screens.find((x) => x.id === id);
  const [wPx, hPx] = s.resolution;
  const [wMm, hMm] = s.physical_mm;
  const [xMm, yMm] = s.position_mm;
  return {
    ...s,
    mmToPx: (x, y) => [((x - xMm) / wMm) * wPx, ((y - yMm) / hMm) * hPx],
    pxToMm: (x, y) => [xMm + (x / wPx) * wMm, yMm + (y / hPx) * hMm],
    pxPerMm: wPx / wMm,
  };
}

export function bounds() {
  const xs = wall.screens.flatMap((s) => [s.position_mm[0], s.position_mm[0] + s.physical_mm[0]]);
  const ys = wall.screens.flatMap((s) => [s.position_mm[1], s.position_mm[1] + s.physical_mm[1]]);
  return { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
}

export function all() {
  return wall.screens;
}

// Cap height of Barlow / Barlow Condensed per em (measured in the page: 0.72).
const CAP_PER_EM = 0.72;

/**
 * Text sizes on this screen from the viewing distance in wall.json (docs/SCREENS.md, Type;
 * the TV has its own distance, docs/TV_APP.md):
 * sets --fs-floor (the smallest text allowed: labels, times) and --fs-text (names, rows)
 * on the root as CSS pixels, so the same cap height in mm on every screen.
 */
export function applyType(id, root = document.documentElement) {
  const s = screen(id);
  const v = { distance_m: 3, floor_mm_per_m: 3.67, text_mm_per_m: 6, ...wall.viewing, ...s.viewing };
  const pxPerMmY = s.resolution[1] / s.physical_mm[1];
  const font = (mmPerM) => `${Math.round((mmPerM * v.distance_m * pxPerMmY) / CAP_PER_EM)}px`;
  root.style.setProperty("--fs-floor", font(v.floor_mm_per_m));
  root.style.setProperty("--fs-text", font(v.text_mm_per_m));
}
