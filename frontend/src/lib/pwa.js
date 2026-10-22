import { api } from "@/lib/api";

// Krish as a phone app: the service worker (public/sw.js) makes the app installable and shows the
// daily Gita verse notification.

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || import.meta.env.DEV) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => { /* the app works without it */ });
  });
}

export const isStandalone = () =>
  window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true;

export const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

// Android and desktop Chrome offer their own install window; keep the event so a button can open it.
let installEvent = null;
const listeners = new Set();
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installEvent = e;
  listeners.forEach((fn) => fn(true));
});
window.addEventListener("appinstalled", () => {
  installEvent = null;
  listeners.forEach((fn) => fn(false));
});

export const canInstall = () => Boolean(installEvent);
export function onInstallChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export async function install() {
  if (!installEvent) return false;
  installEvent.prompt();
  const { outcome } = await installEvent.userChoice;
  installEvent = null;
  listeners.forEach((fn) => fn(false));
  return outcome === "accepted";
}

// ---- daily verse notifications
export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

function keyBytes(base64) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function registration() {
  return navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready);
}

/** True when this device already gets the daily verse. */
export async function verseOn() {
  if (!pushSupported() || Notification.permission !== "granted") return false;
  const reg = await navigator.serviceWorker.getRegistration();
  return Boolean(reg && (await reg.pushManager.getSubscription()));
}

/** Ask for permission and sign this device up. Throws an Error with a friendly message when it can't. */
export async function turnVerseOn() {
  if (!pushSupported()) {
    throw new Error(isIos() && !isStandalone()
      ? "On iPhone, first add Krish to your home screen (Share, then Add to Home Screen), then turn this on there."
      : "This browser can't show notifications.");
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications are blocked. Allow them for Krish AI in your browser settings.");
  const { data } = await api.get("/push/config");
  const reg = await registration();
  const sub = (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(data.publicKey) }));
  const json = sub.toJSON();
  await api.post("/push/subscribe", { endpoint: json.endpoint, keys: json.keys });
}

export async function turnVerseOff() {
  const reg = await navigator.serviceWorker?.getRegistration();
  const sub = reg && (await reg.pushManager.getSubscription());
  if (!sub) return;
  await api.post("/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
  await sub.unsubscribe();
}
