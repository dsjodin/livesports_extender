// Where the TV picture goes per scene (docs/TV_APP.md, Scenes on the TV). The page is
// 1920×1080 CSS pixels; the shell turns a rectangle into the TV window's position.

export const W = 1920;
export const H = 1080;
export const MARGIN = 40;

/** The TV picture in the L-frame: 60 % at the top left, inside a 40 px margin. */
export const LFRAME = [MARGIN, MARGIN, 1152, 648];

/** The L-frame's own areas around the picture: the column right of it, the band below. */
export const COLUMN = [LFRAME[0] + LFRAME[2] + MARGIN, MARGIN, W - (LFRAME[0] + LFRAME[2] + 2 * MARGIN), H - 2 * MARGIN];
export const BAND = [MARGIN, LFRAME[1] + LFRAME[3] + MARGIN, LFRAME[2], H - (LFRAME[1] + LFRAME[3] + 2 * MARGIN)];

const LFRAME_SCENES = new Set(["idle", "pregame", "intermission", "postgame"]);
const FULL_SCENES = new Set(["live", "goal"]);
const warned = new Set();

/** The TV picture's rectangle for a scene: the L-frame outside play, null (full screen)
 * in play or when the viewer asked for the full picture. */
export function windowFor(scene, full = false) {
  if (!LFRAME_SCENES.has(scene) && !FULL_SCENES.has(scene) && !warned.has(scene)) {
    warned.add(scene);
    console.warn("tv: unknown scene, full picture", scene);
  }
  return !full && LFRAME_SCENES.has(scene) ? LFRAME : null;
}
