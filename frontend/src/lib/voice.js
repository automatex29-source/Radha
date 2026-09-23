import { api, API, getToken } from "@/lib/api";

const EXT = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav" };

export async function transcribe(blob) {
  const type = (blob.type || "audio/webm").split(";")[0];
  const fd = new FormData();
  fd.append("file", blob, `speech.${EXT[type] || "webm"}`);
  const { data } = await api.post("/audio/transcribe", fd, { headers: { "Content-Type": "multipart/form-data" } });
  return data.text || "";
}

let current = null;

export function stopSpeaking() {
  if (current) {
    current.pause();
    current = null;
  }
}

/** Speak text aloud; resolves when playback ends or is stopped. */
export async function speak(text, voice, { onStart } = {}) {
  stopSpeaking();
  const res = await fetch(`${API}/audio/speech`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ text, voice }),
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
