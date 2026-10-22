// A friend's invite link is the app address with ?ref=CODE. The code is kept on this device until the
// person signs up (by email or Google), then sent with the sign-up so both people get free Pro days.
const KEY = "krish.ref";

export function captureRef() {
  try {
    const code = new URLSearchParams(window.location.search).get("ref");
    if (code && /^[A-Za-z0-9]{4,20}$/.test(code)) localStorage.setItem(KEY, code.toUpperCase());
  } catch { /* optional */ }
}

export function getRef() {
  try { return localStorage.getItem(KEY) || null; } catch { return null; }
}

export function clearRef() {
  try { localStorage.removeItem(KEY); } catch { /* optional */ }
}

export const inviteLink = (code) => `${window.location.origin}/?ref=${code}`;
