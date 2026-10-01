import { api, API, getToken } from "@/lib/api";

const EXT = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav" };

// Spoken language: "auto" lets the server detect Hindi or English.
const LANG_KEY = "radha.voiceLang";
export const VOICE_LANGS = [
  { id: "auto", label: "Auto" },
  { id: "hi", label: "हिंदी" },
  { id: "en", label: "English" },
];

export function getVoiceLang() {
  try { return localStorage.getItem(LANG_KEY) || "auto"; } catch { return "auto"; }
}

export function setVoiceLang(lang) {
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* optional */ }
}

// The server speaks with natural voices (free Microsoft neural voices, or OpenAI with a key);
// if that fails, the browser reads replies aloud.
let serverSpeech = false;
export function setServerSpeech(on) { serverSpeech = !!on; }

export function browserSpeechAvailable() {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
}

export async function transcribe(blob) {
  const type = (blob.type || "audio/webm").split(";")[0];
  const fd = new FormData();
  fd.append("file", blob, `speech.${EXT[type] || "webm"}`);
  const lang = getVoiceLang();
  if (lang !== "auto") fd.append("language", lang);
  const { data } = await api.post("/audio/transcribe", fd, { headers: { "Content-Type": "multipart/form-data" } });
  return data.text || "";
}

let current = null;

let browserRun = null; // { cancelled, resolve } for the in-progress browser utterance

export function stopSpeaking() {
  if (current) {
    current.pause();
    current = null;
  }
  if (browserRun) {
    browserRun.cancelled = true;
    const done = browserRun.resolve;
    browserRun = null;
    window.speechSynthesis.cancel();
    done();
  }
}

/**
 * Browsers (iOS Safari especially) only allow speech that starts from a tap.
 * Call this inside a click handler before speaking later from async code.
 */
export function unlockSpeech() {
  if (!browserSpeechAvailable()) return;
  try {
    const u = new SpeechSynthesisUtterance(" ");
    u.volume = 0;
    window.speechSynthesis.speak(u);
  } catch { /* optional */ }
}

function loadVoices() {
  const synth = window.speechSynthesis;
  const now = synth.getVoices();
  if (now.length) return Promise.resolve(now);
  return new Promise((resolve) => {
    const t = setTimeout(() => resolve(synth.getVoices()), 1500);
    synth.addEventListener("voiceschanged", () => { clearTimeout(t); resolve(synth.getVoices()); }, { once: true });
  });
}

function pickVoice(voices, lang) {
  const base = lang.slice(0, 2);
  const matches = voices.filter((v) => v.lang?.replace("_", "-").toLowerCase().startsWith(base));
  const exact = matches.filter((v) => v.lang.replace("_", "-").toLowerCase() === lang.toLowerCase());
  const pool = exact.length ? exact : matches;
  // Prefer natural-sounding voices where the browser offers them.
  return pool.find((v) => /google|natural|neural|premium|enhanced/i.test(v.name)) || pool[0] || null;
}

// Chrome stops long utterances after ~15s, so speak sentence-sized chunks.
function chunks(text, max = 200) {
  const parts = text.match(/[^.!?।\n]+[.!?।]*|\n+/g) || [text];
  const out = [];
  let cur = "";
  for (const p of parts) {
    const piece = p.trim();
    if (!piece) continue;
    if ((cur + " " + piece).length > max && cur) { out.push(cur); cur = piece; }
    else cur = cur ? `${cur} ${piece}` : piece;
    while (cur.length > max) {
      const cut = cur.lastIndexOf(" ", max) > 40 ? cur.lastIndexOf(" ", max) : max;
      out.push(cur.slice(0, cut));
      cur = cur.slice(cut).trim();
    }
  }
  if (cur) out.push(cur);
  return out;
}

async function speakInBrowser(text, { onStart } = {}) {
  if (!browserSpeechAvailable()) throw new Error("This browser can't read aloud");
  const synth = window.speechSynthesis;
  const pref = getVoiceLang();
  const lang = pref === "hi" || (pref === "auto" && /[\u0900-\u097F]/.test(text)) ? "hi-IN" : "en-IN";
  const voice = pickVoice(await loadVoices(), lang);
  const run = { cancelled: false, resolve: () => {} };
  browserRun = run;
  let started = false;
  try {
    for (const part of chunks(text)) {
      if (run.cancelled) break;
      await new Promise((resolve, reject) => {
        run.resolve = resolve;
        const u = new SpeechSynthesisUtterance(part);
        u.lang = voice?.lang || lang;
        if (voice) u.voice = voice;
        u.onstart = () => { if (!started) { started = true; onStart?.(); } };
        u.onend = resolve;
        u.onerror = (e) => (e.error === "interrupted" || e.error === "canceled" ? resolve() : reject(new Error("Could not read aloud")));
        synth.speak(u);
      });
    }
  } finally {
    if (browserRun === run) browserRun = null;
  }
}

/** Speak text aloud; resolves when playback ends or is stopped. */
export async function speak(text, voice, { onStart } = {}) {
  stopSpeaking();
  if (!serverSpeech) return speakInBrowser(text, { onStart });
  try {
    return await speakOnServer(text, voice, { onStart });
  } catch (e) {
    if (!browserSpeechAvailable()) throw e;
    return speakInBrowser(text, { onStart });
  }
}

async function speakOnServer(text, voice, { onStart } = {}) {
  const res = await fetch(`${API}/audio/speech`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ text, voice, lang: getVoiceLang() }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Speech failed");
  }
  const url = URL.createObjectURL(await res.blob());
  const audio = new Audio(url);
  current = audio;
  try {
    await new Promise((resolve, reject) => {
      audio.onended = resolve;
      audio.onpause = resolve;
      audio.onerror = () => reject(new Error("Could not play audio"));
      audio.play().then(() => onStart?.(), reject);
    });
  } finally {
    if (current === audio) current = null;
    URL.revokeObjectURL(url);
  }
}

/** Markdown -> something pleasant to read aloud (drop code, links' URLs, symbols). */
export function speechText(markdown) {
  return (markdown || "")
    .replace(/```[\s\S]*?```/g, " (code omitted) ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/[*_~>|]/g, "")
    .replace(/\n{2,}/g, "\n")
    .trim();
}
