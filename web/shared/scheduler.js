// Run callbacks at a server-time play_at. A timer wakes us about 15 ms early, then a
// MessageChannel spin hits the moment within a millisecond or two (rAF alone is too coarse).
// Callbacks due at the same time run by priority, then in order of scheduling.
import { now } from "./clock.js";

const queue = [];
let seq = 0;
let timer = null;
const channel = new MessageChannel();
channel.port1.onmessage = check;

function check() {
  timer = null;
  const t = now();
  queue.sort((a, b) => a.playAt - b.playAt || a.priority - b.priority || a.seq - b.seq);
  while (queue.length && queue[0].playAt <= t) {
    const item = queue.shift();
    try {
      item.fn(t - item.playAt);
    } catch (err) {
      console.error(err);
    }
  }
  if (!queue.length) return;
  const wait = queue[0].playAt - now();
  if (wait <= 15) channel.port2.postMessage(0);
  else timer = setTimeout(check, wait - 15);
}

export function at(playAt, fn, priority = 1) {
  const item = { playAt, fn, priority, seq: seq++ };
  queue.push(item);
  if (timer) clearTimeout(timer);
  timer = null;
  channel.port2.postMessage(0);
  return () => {
    const i = queue.indexOf(item);
    if (i >= 0) queue.splice(i, 1);
  };
}

export function cancelAll() {
  queue.length = 0;
}

export function pending() {
  return queue.map((q) => ({ playAt: q.playAt, label: q.label }));
}
