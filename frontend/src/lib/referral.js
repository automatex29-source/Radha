// A friend's invite link is /i/CODE (older links: the app address with ?ref=CODE). The code is kept on this device until the
// person signs up (by email or Google), then sent with the sign-up so both people get free Pro days.
const KEY = "krish.ref";

export function captureRef() {
  try {
    const path = window.location.pathname.match(/^\/i\/([A-Za-z0-9]{4,20})\/?$/);
    const code = path ? path[1] : new URLSearchParams(window.location.search).get("ref");
    if (code && /^[A-Za-z0-9]{4,20}$/.test(code)) localStorage.setItem(KEY, code.toUpperCase());
  } catch { /* optional */ }
}

export function getRef() {
  try { return localStorage.getItem(KEY) || null; } catch { return null; }
}

export function clearRef() {
  try { localStorage.removeItem(KEY); } catch { /* optional */ }
}

export const inviteLink = (code) => `${window.location.origin}/i/${code}`;

/** The message people send with their invite link: personal, short, and says what Krish does. */
export function inviteMessage(link, days) {
  return [
    "I've been using Krish AI and thought you'd like it. It answers anything, helps with study and writing, and makes slides, pictures and even apps.",
    "",
    `Join with my link and we both get ${days} days of Pro, free:`,
    link,
  ].join("\n");
}
