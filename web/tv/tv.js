// Entry point of the TV overlay, loaded by the TV app's shell: as /tv/ in its iframe, or
// imported straight into the shell (fallback). Shows the graphics (overlay.js), or the
// test page (probe.js) while the service says so (`tv_probe`, set in /sim); either one
// reloads when that setting changes (docs/TV_APP.md).
import * as host from "./host.js";

let probe = false;
try {
  const r = await fetch(`${host.base}/api/state`, { cache: "no-store" });
  probe = (await r.json()).status?.tv_probe === true;
} catch {
  // no answer yet: the graphics, which wait for the service themselves
}
await import(probe ? "./probe.js" : "./overlay.js");
