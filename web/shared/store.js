// The TV state on the client. Every change is applied at its play_at, never on receipt
// (CLAUDE.md rule 1). Patches go before events and scene changes due at the same moment.
import { at, cancelAll } from "./scheduler.js";

export class Store {
  constructor() {
    this.tv = null;
    this.config = {};
    this.handlers = {};
    this.upcoming = new Map(); // key -> play_at, for the debug overlay
  }

  on(name, fn) {
    (this.handlers[name] ??= []).push(fn);
  }

  emit(name, ...args) {
    (this.handlers[name] ?? []).forEach((fn) => fn(...args));
  }

  handle(m) {
    switch (m.t) {
      case "hello":
      case "config":
        this.config = m.config;
        this.emit("config", m.config);
        break;
      case "state":
        cancelAll();
        this.upcoming.clear();
        this.tv = m.state;
        this.emit("state", this.tv);
        break;
      case "state_patch":
        this.later(m, 0, () => {
          Object.assign(this.tv, m.patch);
          this.tv.rev = m.rev;
          this.emit("patch", m.patch);
        });
        break;
      case "event":
      case "event_update":
        this.emit("preload", m.event);
        this.later(m, 1, (late) => this.emit(m.t === "event" ? "event" : "event_update", m.event, m.play_at_ms, late));
        break;
      case "scene":
        this.later(m, 2, (late) => {
          this.tv.scene = m.scene;
          this.emit("scene", m.scene, m.play_at_ms, late);
        });
        break;
      default:
        this.emit(m.t, m);
    }
  }

  later(m, priority, fn) {
    const key = m.event?.key ?? m.scene?.name ?? m.t;
    this.upcoming.set(`${m.t}:${key}:${m.play_at_ms}`, { key: `${m.t} ${key}`, playAt: m.play_at_ms });
    at(
      m.play_at_ms,
      (late) => {
        this.upcoming.delete(`${m.t}:${key}:${m.play_at_ms}`);
        if (this.tv) fn(late);
      },
      priority,
    );
  }
}
