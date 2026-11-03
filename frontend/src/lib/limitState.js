import { useEffect, useState } from "react";

/** The usage limit the user is waiting out right now, shared by the chat's banner and limit cards.
 *
 *  kind "ai": the free AI's own limit (from the reply's ai_limit event).
 *  kind "plan": the user's plan meter (Basic, Pro or Max) is used up (a 402 from the server).
 *  { kind, resetsAt (seconds), since (seconds, when the wait began), daily, week, plan }
 *  Kept in localStorage so the banner is still there after a reload, until the limit resets. */
const KEY = "krish-limit";
const EVENT = "krish:limit-state";
let banners = 0; // chat banners on screen: when one shows the limit, the popup isn't needed

function read() {
  try {
    const info = JSON.parse(localStorage.getItem(KEY) || "null");
    if (!info) return null;
    const until = info.resetsAt || (info.since || 0) + 90;
    return until * 1000 > Date.now() ? info : null;
  } catch {
    return null;
  }
}

export function setLimit(info) {
  const value = { since: Date.now() / 1000, ...info };
  try { localStorage.setItem(KEY, JSON.stringify(value)); } catch { /* still shown until reload */ }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: value }));
}

export function clearLimit() {
  try { localStorage.removeItem(KEY); } catch { /* nothing kept */ }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: null }));
}

export const bannerShown = () => banners > 0;
export function trackBanner() {
  banners += 1;
  return () => { banners -= 1; };
}

/** The active limit (or null), with `now` ticking every second while one is active. */
export function useLimit() {
  const [info, setInfo] = useState(read);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const on = (e) => setInfo(e.detail === null ? null : read());
    window.addEventListener(EVENT, on);
    window.addEventListener("storage", on);
    return () => { window.removeEventListener(EVENT, on); window.removeEventListener("storage", on); };
  }, []);
  useEffect(() => {
    if (!info) return undefined;
    const t = setInterval(() => {
      setNow(Date.now());
      if (!read()) setInfo(null);
    }, 1000);
    return () => clearInterval(t);
  }, [info]);
  return { info, now };
}

/** "7:09" or "3:12:05" */
export function clock(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

export const timeOf = (sec) => new Date(sec * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
