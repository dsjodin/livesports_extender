// Minimal service worker so the app can be installed. Always the network: the app is
// only useful with the service on the LAN, and stale state would mislead.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
