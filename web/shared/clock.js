// Server time from clock_ping / clock_pong (docs/PROTOCOL.md): median offset of the five
// samples with the lowest round trip.
const samples = [];
let offset = 0;
let rtt = null;

export function localNow() {
  return performance.timeOrigin + performance.now();
}

export function now() {
  return localNow() + offset;
}

export function ping() {
  return { t: "clock_ping", t0: localNow() };
}

export function pong(message) {
  const t1 = localNow();
  samples.push({ rtt: t1 - message.t0, offset: message.server_ms - (message.t0 + t1) / 2 });
  if (samples.length > 30) samples.shift();
  const best = [...samples].sort((a, b) => a.rtt - b.rtt).slice(0, 5);
  const offsets = best.map((s) => s.offset).sort((a, b) => a - b);
  offset = offsets[Math.floor(offsets.length / 2)];
  rtt = best[0].rtt;
}

export function stats() {
  return { offset: Math.round(offset), rtt: rtt == null ? null : Math.round(rtt), samples: samples.length };
}
