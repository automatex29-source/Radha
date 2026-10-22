import { api } from "@/lib/api";

// Crashes on someone's device are sent to the server, so the owner hears about them (see backend/monitor.py).
// The same problem is sent once per page load, and at most 10 a page load, so a loop can't flood the server.
const seen = new Set();

export function reportError(error, extra = "") {
  try {
    const message = String(error?.message || error || "Unknown error").slice(0, 500);
    if (seen.has(message) || seen.size >= 10) return;
    seen.add(message);
    const stack = `${String(error?.stack || "").slice(0, 6000)}${extra ? `\n${extra}` : ""}`;
    api.post("/client-errors", { message, stack, path: window.location.pathname }).catch(() => {});
  } catch { /* reporting must never cause a crash itself */ }
}

// Old tabs after a deploy, browser extensions and blocked third-party scripts aren't Krish's problems.
const NOISE = /ResizeObserver loop|Script error\.?$|dynamically imported module|Loading chunk|ChunkLoadError|PerformanceServerTiming|extension:\/\//i;

export function installCrashReporting() {
  window.addEventListener("error", (e) => {
    const msg = e?.error?.message || e?.message || "";
    if (!NOISE.test(msg) && !NOISE.test(e?.filename || "")) reportError(e.error || msg, e.filename || "");
  });
  window.addEventListener("unhandledrejection", (e) => {
    const reason = e?.reason;
    // API errors (a wrong password, a plan limit) are already shown to the person; they aren't crashes.
    if (reason?.isAxiosError || reason?.response) return;
    const msg = reason?.message || String(reason || "");
    if (msg && !NOISE.test(msg)) reportError(reason);
  });
}
