import { api, API, getToken } from "@/lib/api";

const EXT = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav" };

// Spoken language: "auto" lets the server detect it. `bcp` is the browser voice locale.
// New key: everyone starts on Auto, which follows whatever language they speak.
const LANG_KEY = "krish.voiceLang";
export const VOICE_LANGS = [
  { id: "auto", label: "Auto", name: "Auto (matches the language you speak)", bcp: "en-IN" },
  { id: "hi", label: "हिंदी", name: "Hindi", bcp: "hi-IN" },
  { id: "en", label: "English", name: "English", bcp: "en-IN" },
  { id: "bn", label: "বাংলা", name: "Bengali", bcp: "bn-IN" },
  { id: "mr", label: "मराठी", name: "Marathi", bcp: "mr-IN" },
  { id: "gu", label: "ગુજરાતી", name: "Gujarati", bcp: "gu-IN" },
  { id: "ta", label: "தமிழ்", name: "Tamil", bcp: "ta-IN" },
  { id: "te", label: "తెలుగు", name: "Telugu", bcp: "te-IN" },
  { id: "kn", label: "ಕನ್ನಡ", name: "Kannada", bcp: "kn-IN" },
  { id: "ml", label: "മലയാളം", name: "Malayalam", bcp: "ml-IN" },
  { id: "pa", label: "ਪੰਜਾਬੀ", name: "Punjabi", bcp: "pa-IN" },
  { id: "ur", label: "اردو", name: "Urdu", bcp: "ur-IN" },
  { id: "es", label: "Español", name: "Spanish", bcp: "es-ES" },
  { id: "fr", label: "Français", name: "French", bcp: "fr-FR" },
  { id: "de", label: "Deutsch", name: "German", bcp: "de-DE" },
  { id: "ar", label: "العربية", name: "Arabic", bcp: "ar-SA" },
];

// In auto mode, the script a reply is written in picks the browser voice.
const SCRIPTS = [[/[\u0A00-\u0A7F]/, "pa-IN"], [/[\u0980-\u09FF]/, "bn-IN"], [/[\u0A80-\u0AFF]/, "gu-IN"], [/[\u0B80-\u0BFF]/, "ta-IN"],
  [/[\u0C00-\u0C7F]/, "te-IN"], [/[\u0C80-\u0CFF]/, "kn-IN"], [/[\u0D00-\u0D7F]/, "ml-IN"],
  [/[\u0600-\u06FF]/, "ur-IN"], [/[\u0900-\u097F]/, "hi-IN"]];

function browserLang(text, override) {
  const pref = override || getVoiceLang();
  if (pref !== "auto") return VOICE_LANGS.find((l) => l.id === pref)?.bcp || "en-IN";
  return SCRIPTS.find(([re]) => re.test(text))?.[1] || "en-IN";
}

export function getVoiceLang() {
  try {
    const v = localStorage.getItem(LANG_KEY);
    return VOICE_LANGS.some((l) => l.id === v) ? v : "auto";
  } catch { return "auto"; }
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
  return (await transcribeDetect(blob)).text;
}

/** Speech to text plus the language that was spoken ({ text, language }). */
export async function transcribeDetect(blob) {
  const type = (blob.type || "audio/webm").split(";")[0];
  const fd = new FormData();
  fd.append("file", blob, `speech.${EXT[type] || "webm"}`);
  const lang = getVoiceLang();
  if (lang !== "auto") fd.append("language", lang);
  const { data } = await api.post("/audio/transcribe", fd, { headers: { "Content-Type": "multipart/form-data" } });
  return { text: data.text || "", language: data.language || null };
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
  unlockPlayer();
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

async function speakInBrowser(text, { onStart, lang: forced } = {}) {
  if (!browserSpeechAvailable()) throw new Error("This browser can't read aloud");
  const synth = window.speechSynthesis;
  const lang = browserLang(text, forced);
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

async function fetchSpeech(text, voice, lang) {
  const res = await fetch(`${API}/audio/speech`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ text, voice, lang: lang || getVoiceLang() }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Speech failed");
  }
  return URL.createObjectURL(await res.blob());
}

// One shared <audio> element: once a tap has started it, phones let it keep playing
// clips that start later from async code.
let player = null;
function getPlayer() {
  if (!player && typeof Audio !== "undefined") player = new Audio();
  return player;
}

function silentWav() {
  const bytes = new Uint8Array(46);
  const view = new DataView(bytes.buffer);
  const str = (o, t) => [...t].forEach((c, i) => view.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); view.setUint32(4, 38, true); str(8, "WAVEfmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true); view.setUint32(28, 16000, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); str(36, "data"); view.setUint32(40, 2, true);
  return `data:audio/wav;base64,${btoa(String.fromCharCode(...bytes))}`;
}

function unlockPlayer() {
  const p = getPlayer();
  if (!p || p.dataset?.unlocked) return;
  try {
    p.src = silentWav();
    p.play().catch(() => {});
    if (p.dataset) p.dataset.unlocked = "1";
  } catch { /* optional */ }
}

async function playUrl(url, { onStart } = {}) {
  const audio = getPlayer();
  current = audio;
  try {
    await new Promise((resolve, reject) => {
      audio.onended = resolve;
      audio.onpause = resolve;
      audio.onerror = () => reject(new Error("Could not play audio"));
      audio.src = url;
      audio.play().then(() => onStart?.(), reject);
    });
  } finally {
    if (current === audio) current = null;
    audio.onpause = null;
    audio.onended = null;
    audio.onerror = null;
    URL.revokeObjectURL(url);
  }
}

async function speakOnServer(text, voice, { onStart } = {}) {
  return playUrl(await fetchSpeech(text, voice), { onStart });
}

/**
 * Speaks a reply while it is still being written: feed it the growing text with
 * `push(text)`, then `end(text)`. Whole sentences are voiced as soon as they are
 * complete, and the next sentence's audio is fetched while the current one plays.
 * `done` resolves when everything has been spoken or `stop()` is called.
 */
export function createSpeaker({ voice, onStart, lang } = {}) {
  const queue = [];
  let consumed = 0;
  let ended = false;
  let stopped = false;
  let started = false;
  let useServer = serverSpeech;
  let wake = null;

  const enqueue = (raw) => {
    const text = speechText(raw).replace(/\s+/g, " ").trim();
    if (!text || !/[\p{L}\p{N}]/u.test(text)) return;
    const item = { text };
    if (useServer) item.url = fetchSpeech(text, voice, lang).catch((e) => { item.failed = e; return null; });
    queue.push(item);
    wake?.();
  };

  // Take complete sentences from text[consumed:]; at the end, take everything.
  const take = (text, final) => {
    const rest = text.slice(consumed);
    const re = /[.!?।]+["')\]]*\s+|\n+/g;
    let cut = -1;
    let m;
    while ((m = re.exec(rest))) {
      cut = m.index + m[0].length;
      // Start talking after the first sentence; after that, gather a little more per clip.
      if (!started && queue.length === 0) break;
      if (cut > 160) break;
    }
    if (final) cut = rest.length;
    if (cut <= 0) return;
    // Don't split inside a code block that is still being written.
    const piece = rest.slice(0, cut);
    if (!final && (piece.match(/```/g) || []).length % 2) return;
    consumed += cut;
    enqueue(piece);
    if (!final && consumed < text.length) take(text, false);
  };

  const run = async () => {
    try {
      while (!stopped) {
        const item = queue.shift();
        if (!item) {
          if (ended) break;
          await new Promise((r) => { wake = r; });
          wake = null;
          continue;
        }
        const first = () => { if (!started) { started = true; onStart?.(); } };
        const url = item.url ? await item.url : null;
        if (stopped) { if (url) URL.revokeObjectURL(url); break; }
        if (url) {
          try { await playUrl(url, { onStart: first }); continue; } catch { /* fall back below */ }
        }
        if (item.url) useServer = false; // the free voice service failed; use the browser from now on
        if (browserSpeechAvailable()) await speakInBrowser(item.text, { onStart: first, lang });
        else if (item.failed) throw item.failed;
      }
    } finally {
      queue.forEach((i) => i.url?.then((u) => u && URL.revokeObjectURL(u)));
    }
  };
  const running = run();
  running.catch(() => {}); // callers that don't await `done` shouldn't see an unhandled rejection

  return {
    push(text) { if (!stopped && !ended) take(text || "", false); },
    end(text) {
      if (stopped || ended) return;
      take(text || "", true);
      ended = true;
      wake?.();
    },
    stop() {
      if (stopped) return;
      stopped = true;
      stopSpeaking();
      wake?.();
    },
    get started() { return started; },
    done: running,
  };
}

/**
 * Listens to the microphone while a reply is playing and calls `onSpeech` once the
 * person starts talking over it. Returns a function that stops listening.
 */
export async function watchForSpeech(onSpeech, { holdMs = 300 } = {}) {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch {
    return () => {};
  }
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  const t0 = performance.now();
  const floor = [];
  let threshold = 0.07;
  let loudSince = 0;
  let raf = 0;
  let stopped = false;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    cancelAnimationFrame(raf);
    stream.getTracks().forEach((t) => t.stop());
    ctx.close().catch(() => {});
  };
  const tick = () => {
    if (stopped) return;
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    const now = performance.now();
    if (now - t0 < 600) {
      // Learn how loud the room (and any leftover echo of the reply) is first.
      floor.push(rms);
    } else {
      if (floor.length) {
        floor.sort((a, b) => a - b);
        threshold = Math.max(threshold, floor[Math.floor(floor.length * 0.9)] * 3);
        floor.length = 0;
      }
      if (rms > threshold) {
        loudSince = loudSince || now;
        if (now - loudSince > holdMs) { stop(); onSpeech(); return; }
      } else loudSince = 0;
    }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return stop;
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
