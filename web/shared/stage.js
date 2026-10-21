// Stage coordinates (docs/SCREENS.md): millimetres, origin at the top-left of the left
// screen's active area. Converts to and from this screen's CSS pixels.
let wall = null;

export async function load() {
  if (!wall) wall = await (await fetch("/api/wall")).json();
  return wall;
}

export function screen(id) {
  const s = wall.screens.find((x) => x.id === id);
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
