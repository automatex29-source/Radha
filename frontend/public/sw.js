/* Krish AI service worker: makes the app installable, and shows the daily Gita verse notification.
   Pages and the API always come from the network, so a new version shows up straight away. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

// A fetch handler is what lets browsers offer "Install app". When the network is down, show a short note.
self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(fetch(event.request).catch(() => new Response(
    "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>Krish AI</title>" +
    "<body style='font-family:system-ui;display:grid;place-items:center;min-height:100vh;margin:0;text-align:center;padding:24px'>" +
    "<div><h2>You're offline</h2><p>Krish AI needs the internet. Check your connection and try again.</p>" +
    "<button onclick='location.reload()' style='padding:10px 20px;border-radius:12px;border:0;background:#6366f1;color:#fff;font-weight:600'>Try again</button></div>",
    { headers: { "Content-Type": "text/html; charset=utf-8" } })));
});

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(data.title || "Krish AI", {
    body: data.body || "",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    tag: data.tag || "krish",
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
    for (const w of wins) {
      if ("focus" in w) { w.navigate(url).catch(() => {}); return w.focus(); }
    }
    return self.clients.openWindow(url);
  }));
});
