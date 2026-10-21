// Swedish formatting for the screens. Scores and ranges use the en dash (–).
export const DASH = "–";
const TZ = "Europe/Stockholm";

export const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/** Tagged template that escapes interpolations; nest with raw(). */
export function html(strings, ...values) {
  return strings.reduce((out, s, i) => {
    const v = values[i - 1];
    const text = Array.isArray(v) ? v.map((x) => (x?.__raw ? x.html : esc(x))).join("") : v?.__raw ? v.html : esc(v);
    return out + text + s;
  });
}
export const raw = (h) => ({ __raw: true, html: h });

export const caps = (s) => String(s ?? "").toLocaleUpperCase("sv-SE");
export const score = (a, b) => `${a ?? 0}${DASH}${b ?? 0}`;
export const thousands = (n) => (n == null ? "" : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "));
export const decimal = (x, digits = 1) => (x == null || Number.isNaN(x) ? DASH : x.toFixed(digits).replace(".", ","));
export const percent = (ratio) => (ratio == null || Number.isNaN(ratio) ? DASH : `${decimal(ratio * 100)} %`);

export function periodName(p) {
  if (p === "shootout") return "Straffar";
  if (p === 4) return "Förlängning";
  if (p > 4) return `Förlängning ${p - 3}`;
  return { 1: "1:a perioden", 2: "2:a perioden", 3: "3:e perioden" }[p] ?? `Period ${p}`;
}
export const periodWord = (n) => ({ 1: "en", 2: "två", 3: "tre" })[n] ?? String(n);

export function strengthChip(status, emptyNet) {
  if (emptyNet) return "TOM BUR";
  if (!status) return null;
  if (status === "EQ") return "FULLT LAG";
  if (status.startsWith("PP")) return "POWERPLAY";
  if (status.startsWith("SH")) return "BOXPLAY";
  if (status === "EN") return "TOM BUR";
  return status; // unknown values are shown raw (CLAUDE.md rule 7)
}

export function hhmm(ms) {
  return new Intl.DateTimeFormat("sv-SE", { hour: "2-digit", minute: "2-digit", timeZone: TZ }).format(ms);
}

export function dayTime(ms) {
  const day = new Intl.DateTimeFormat("sv-SE", { weekday: "long", day: "numeric", month: "short", timeZone: TZ }).format(ms);
  return `${day} ${hhmm(ms)}`;
}

const dayKey = (ms) => new Intl.DateTimeFormat("sv-SE", { dateStyle: "short", timeZone: TZ }).format(ms);

/** "IKVÄLL" for today, "IMORGON", else the weekday ("LÖRDAG"). */
export function dayLabel(ms, nowMs) {
  if (dayKey(ms) === dayKey(nowMs)) return "IKVÄLL";
  if (dayKey(ms) === dayKey(nowMs + 86_400_000)) return "IMORGON";
  return caps(new Intl.DateTimeFormat("sv-SE", { weekday: "long", timeZone: TZ }).format(ms));
}

export function shortDate(iso) {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${Number(d)}/${Number(m)}`;
}

export function countdown(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${String(m).padStart(2, "0")}:${ss}`;
}

function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [n >> 16, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}
const contrast = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

/** Text colour on a team colour: dark or light, whichever contrasts more. */
export function onColor(hex) {
  if (!/^#[0-9a-f]{6}$/i.test(hex || "")) return "#0B0F17";
  return contrast(hex, "#0B0F17") >= contrast(hex, "#F2F4F8") ? "#0B0F17" : "#F2F4F8";
}

/** Very light or very dark team colours need an outline on the dark wall. */
export function needsOutline(hex) {
  if (!/^#[0-9a-f]{6}$/i.test(hex || "")) return false;
  const l = luminance(hex);
  return l > 0.7 || contrast(hex, "#070A10") < 1.6;
}
