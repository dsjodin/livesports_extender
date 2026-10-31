// WebSocket with reconnect (backoff 0.5 s doubling to 8 s) and clock pings.
import * as clock from "./clock.js";

// ``base``: the service's origin when the page runs elsewhere (the TV app's shell on
// file://, docs/TV_APP.md); default the page's own.
export function connect({ role, id, onMessage, onStatus = () => {}, base = location.origin }) {
  let socket = null;
  let retry = 500;
  let pingTimers = [];

  function stopPings() {
    pingTimers.forEach(clearTimeout);
    pingTimers.forEach(clearInterval);
    pingTimers = [];
  }

  function startPings() {
    stopPings();
    const send = () => socket?.readyState === WebSocket.OPEN && socket.send(JSON.stringify(clock.ping()));
    for (let i = 0; i <= 5; i++) pingTimers.push(setTimeout(send, i * 2000));
    pingTimers.push(setInterval(send, 30000));
  }

  function open() {
    const server = new URL(base);
    const scheme = server.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${scheme}://${server.host}/ws?role=${role}&id=${encodeURIComponent(id)}`);
    socket.onopen = () => {
      retry = 500;
      onStatus("open");
      startPings();
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.t === "clock_pong") clock.pong(message);
      onMessage(message);
    };
    socket.onclose = () => {
      stopPings();
      onStatus("closed");
      setTimeout(open, retry);
      retry = Math.min(retry * 2, 8000);
    };
  }

  open();
  return {
    send(message) {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
    },
  };
}
