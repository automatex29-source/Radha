import { useEffect, useMemo, useRef, useState } from "react";
import { X, Loader2, FileText, FileSpreadsheet, Presentation, FileArchive, FileCode2, Globe, File, FileAudio,
  Play, Pause, AlertCircle, Mic, Trash2, ArrowUp, Film } from "lucide-react";
import { mediaUrl } from "@/lib/api";

// Attachment cards for the message box and the sent message, like ChatGPT and Claude: pictures as thumbnails,
// every other file as a card with a coloured type tile, its name, its type and its size.

const KINDS = {
  pdf: { label: "PDF", icon: FileText, tile: "from-rose-500 to-pink-500" },
  doc: { label: "Word", icon: FileText, tile: "from-sky-500 to-blue-600" },
  sheet: { label: "Spreadsheet", icon: FileSpreadsheet, tile: "from-emerald-500 to-green-600" },
  slides: { label: "Slides", icon: Presentation, tile: "from-orange-500 to-amber-500" },
  zip: { label: "ZIP", icon: FileArchive, tile: "from-amber-500 to-yellow-500" },
  code: { label: "Code", icon: FileCode2, tile: "from-teal-500 to-cyan-600" },
  html: { label: "Web page", icon: Globe, tile: "from-violet-500 to-purple-600" },
  text: { label: "Text", icon: FileText, tile: "from-slate-500 to-slate-600" },
  video: { label: "Video", icon: Film, tile: "from-indigo-500 to-blue-600" },
  audio: { label: "Audio", icon: FileAudio, tile: "from-pink-500 to-fuchsia-600" },
  file: { label: "File", icon: File, tile: "from-slate-400 to-slate-500" },
};

export function attachmentKind(name = "", contentType = "") {
  const n = name.toLowerCase();
  const ext = n.includes(".") ? n.split(".").pop() : "";
  const ct = (contentType || "").toLowerCase();
  if (ct === "application/pdf" || ext === "pdf") return "pdf";
  if (/wordprocessingml|msword|opendocument\.text|rtf/.test(ct) || ["doc", "docx", "odt", "rtf", "pages"].includes(ext)) return "doc";
  if (/spreadsheetml|ms-excel|csv/.test(ct) || ["xls", "xlsx", "csv", "tsv", "ods", "numbers"].includes(ext)) return "sheet";
  if (/presentationml|powerpoint/.test(ct) || ["ppt", "pptx", "odp", "key"].includes(ext)) return "slides";
  if (/zip|compressed|x-tar|gzip/.test(ct) || ["zip", "rar", "7z", "tar", "gz"].includes(ext)) return "zip";
  if (ct === "text/html" || ["html", "htm"].includes(ext)) return "html";
  if (ct.startsWith("video/") || ["mp4", "mov", "m4v"].includes(ext)) return "video";
  if (ct.startsWith("audio/") || ["mp3", "wav", "m4a", "ogg", "webm", "aac", "flac"].includes(ext)) return "audio";
  if (/^(py|m?js|cjs|jsx|tsx?|css|scss|json|sql|sh|java|kt|c|h|cpp|hpp|cs|go|rs|rb|php|swift|dart|ya?ml|toml|xml|vue|ipynb)$/.test(ext)) return "code";
  if (ct.startsWith("text/") || ["txt", "md", "markdown", "log", "srt", "vtt"].includes(ext)) return "text";
  return "file";
}

export function formatSize(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

function RemoveButton({ onClick, label, testId }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId} title={label} aria-label={label}
      className="absolute -right-1.5 -top-1.5 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white shadow-md ring-2 ring-white transition-all hover:scale-110 hover:bg-rose-600 dark:bg-slate-100 dark:text-slate-900 dark:ring-card dark:hover:bg-rose-500 dark:hover:text-white sm:h-5 sm:w-5 sm:opacity-0 sm:group-hover/att:opacity-100 sm:focus-visible:opacity-100">
      <X className="h-3 w-3" strokeWidth={2.75} />
    </button>
  );
}

/** A file card: coloured tile, name, type and size. `status` "uploading" or "processing" shows a spinner. */
export function FileCard({ name, contentType, size, status, extra, onRemove, onOpen, testId, inMessage = false }) {
  const kind = attachmentKind(name, contentType);
  const meta = KINDS[kind];
  const Icon = meta.icon;
  const busy = status === "uploading" || status === "processing";
  const failed = status === "failed";
  const ext = (name || "").includes(".") ? name.split(".").pop().toUpperCase() : "";
  const type = kind === "file" || kind === "code" || kind === "text" ? (ext || meta.label) : meta.label;
  const detail = failed ? "Couldn't read it" : status === "uploading" ? "Uploading…" : status === "processing" ? "Reading…"
    : [type, formatSize(size), extra].filter(Boolean).join(" · ");
  const Tag = onOpen ? "button" : "div";
  return (
    <div className="group/att relative shrink-0" data-testid={testId}>
      <Tag type={onOpen ? "button" : undefined} onClick={onOpen}
        className={`flex h-14 w-[220px] items-center gap-2.5 rounded-2xl border p-2 pr-3 text-left transition-colors sm:w-[236px] ${
          inMessage ? "border-indigo-200/70 bg-white/80 dark:border-white/10 dark:bg-white/[0.06]"
            : "border-border-strong bg-white dark:bg-surface"} ${onOpen ? "hover:border-indigo-300 dark:hover:border-primary/50" : ""}`}>
        <span className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${meta.tile} text-white shadow-sm`}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : failed ? <AlertCircle className="h-4 w-4" /> : <Icon className="h-[18px] w-[18px]" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium leading-tight text-foreground" title={name}>{name}</span>
          <span className={`mt-0.5 block truncate text-[11px] leading-tight ${failed ? "text-destructive" : "text-muted-foreground"}`}>{detail}</span>
        </span>
      </Tag>
      {onRemove && <RemoveButton onClick={onRemove} label={`Remove ${name}`} testId={testId ? `${testId}-remove` : undefined} />}
    </div>
  );
}

/** A picture thumbnail. While it uploads it shows the local picture, dimmed, with a spinner. */
export function ImageThumb({ src, name, uploading, onRemove, onOpen, testId, removeTestId, badge }) {
  return (
    <div className="group/att relative shrink-0" data-testid={testId}>
      <button type="button" onClick={onOpen} disabled={!onOpen} title={name}
        className="block h-14 w-14 overflow-hidden rounded-2xl border border-border-strong bg-surface disabled:cursor-default">
        {src && <img src={src} alt={name || "Picture"} className={`h-full w-full object-cover transition-opacity ${uploading ? "opacity-50" : ""}`} />}
      </button>
      {uploading && (
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-white"><Loader2 className="h-4 w-4 animate-spin" /></span>
        </span>
      )}
      {badge && <span className="pointer-events-none absolute bottom-1 left-1 rounded-md bg-black/60 px-1 text-[9px] font-semibold text-white">{badge}</span>}
      {onRemove && <RemoveButton onClick={onRemove} label="Remove picture" testId={removeTestId} />}
    </div>
  );
}

/** The drop overlay shown over the whole page while files are dragged in. */
export function DropOverlay({ show }) {
  if (!show) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-[60] flex items-center justify-center bg-indigo-500/10 backdrop-blur-[3px] dark:bg-black/50" data-testid="drop-overlay">
      <div className="mx-4 flex flex-col items-center rounded-3xl border-2 border-dashed border-indigo-400 bg-white/95 px-10 py-8 text-center shadow-2xl dark:border-primary/70 dark:bg-card/95">
        <div className="mb-3 flex -space-x-3">
          {["from-rose-500 to-pink-500", "from-sky-500 to-blue-600", "from-emerald-500 to-green-600"].map((g, i) => (
            <span key={g} className={`flex h-12 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${g} text-white shadow-lg ring-2 ring-white dark:ring-card`}
              style={{ transform: `rotate(${(i - 1) * 12}deg) translateY(${i === 1 ? -4 : 0}px)` }}>
              <FileText className="h-5 w-5" />
            </span>
          ))}
        </div>
        <p className="text-base font-semibold text-foreground">Drop files here</p>
        <p className="mt-1 text-sm text-muted-foreground">Pictures, PDFs, Word, Excel, slides, code and more</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- voice notes

const fmt = (s) => {
  const t = Math.max(0, Math.round(s || 0));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

/** Bar heights for a voice note: from the recording itself when it can be read, else a steady pattern. */
function useWaveform(src, bars) {
  const seeded = useMemo(() => {
    let h = 0;
    for (const c of src || "") h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return Array.from({ length: bars }, (_, i) => {
      h = (h * 1103515245 + 12345) >>> 0;
      return 0.3 + ((h >>> 16) % 1000) / 1000 * 0.6 * (0.6 + 0.4 * Math.sin(i / 2.3));
    });
  }, [src, bars]);
  const [peaks, setPeaks] = useState(null);
  useEffect(() => {
    let off = false;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!src || !Ctx) return undefined;
    fetch(src).then((r) => r.arrayBuffer()).then((buf) => {
      const ctx = new Ctx();
      return ctx.decodeAudioData(buf).finally(() => ctx.close?.());
    }).then((audio) => {
      const ch = audio.getChannelData(0);
      const step = Math.floor(ch.length / bars) || 1;
      const out = [];
      for (let b = 0; b < bars; b++) {
        let sum = 0;
        for (let i = b * step; i < Math.min(ch.length, (b + 1) * step); i += 16) sum += ch[i] * ch[i];
        out.push(Math.sqrt(sum / (step / 16)));
      }
      const max = Math.max(...out, 0.0001);
      if (!off) setPeaks(out.map((v) => 0.15 + 0.85 * Math.pow(v / max, 0.7)));
    }).catch(() => {});
    return () => { off = true; };
  }, [src, bars]);
  return peaks || seeded;
}

/** A voice note on a sent message: play button, waveform that fills as it plays, and its length. */
export function VoiceNotePlayer({ id, seconds, testId }) {
  const src = mediaUrl(`/api/media/${id}`);
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [length, setLength] = useState(seconds || 0);
  const peaks = useWaveform(src, 36);
  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) a.play().catch(() => {}); else a.pause();
  };
  const seek = (e) => {
    const a = audioRef.current;
    const rect = e.currentTarget.getBoundingClientRect();
    const dur = isFinite(a?.duration) ? a.duration : length;
    if (!a || !dur) return;
    a.currentTime = Math.min(dur, Math.max(0, ((e.clientX - rect.left) / rect.width) * dur));
  };
  return (
    <div className="flex w-[250px] max-w-full items-center gap-3 sm:w-[280px]" data-testid={testId}>
      <audio ref={audioRef} src={src} preload="metadata"
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => { setPlaying(false); setProgress(0); }}
        onLoadedMetadata={(e) => { if (isFinite(e.currentTarget.duration)) setLength(e.currentTarget.duration); }}
        onTimeUpdate={(e) => { const a = e.currentTarget; const d = isFinite(a.duration) ? a.duration : length; setProgress(d ? a.currentTime / d : 0); }} />
      <button type="button" onClick={toggle} aria-label={playing ? "Pause voice note" : "Play voice note"} data-testid={testId ? `${testId}-play` : undefined}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_6px_16px_-4px_rgba(99,102,241,0.6)] transition-transform hover:scale-105 active:scale-95">
        {playing ? <Pause className="h-4 w-4 fill-current" /> : <Play className="ml-0.5 h-4 w-4 fill-current" />}
      </button>
      <div className="min-w-0 flex-1">
        <div role="slider" aria-label="Voice note position" aria-valuenow={Math.round(progress * 100)} tabIndex={-1}
          onClick={seek} className="flex h-8 cursor-pointer items-center gap-[2px]">
          {peaks.map((p, i) => (
            <span key={i} className={`w-[3px] flex-1 rounded-full transition-colors ${i / peaks.length < progress ? "bg-indigo-500 dark:bg-indigo-300" : "bg-indigo-300/60 dark:bg-white/25"}`}
              style={{ height: `${Math.round(p * 100)}%` }} />
          ))}
        </div>
        <p className="mt-0.5 flex items-center gap-1 text-[11px] tabular-nums text-muted-foreground">
          <Mic className="h-3 w-3" /> {fmt(playing || progress ? progress * length : length)}
        </p>
      </div>
    </div>
  );
}

/** The bar that replaces the message box while a voice note is recorded: timer, live level, delete and send. */
export function VoiceNoteRecorder({ level = 0, startedAt, sending, onCancel, onSend }) {
  const [now, setNow] = useState(Date.now());
  const [history, setHistory] = useState(() => Array(40).fill(0.08));
  const levelRef = useRef(level);
  levelRef.current = level;
  useEffect(() => {
    if (sending) return undefined;
    const t = setInterval(() => {
      setNow(Date.now());
      setHistory((h) => [...h.slice(1), Math.max(0.08, Math.min(1, levelRef.current * 1.6))]);
    }, 90);
    return () => clearInterval(t);
  }, [sending]);
  const secs = (now - (startedAt || now)) / 1000;
  return (
    <div className="flex items-center gap-2 px-1 py-1" data-testid="voice-note-recorder">
      <button type="button" onClick={onCancel} disabled={sending} data-testid="voice-note-cancel" aria-label="Delete voice note" title="Delete"
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-rose-50 hover:text-rose-600 disabled:opacity-40 dark:hover:bg-rose-500/15 dark:hover:text-rose-300">
        <Trash2 className="h-4 w-4" />
      </button>
      <span className="flex shrink-0 items-center gap-1.5 text-sm font-medium tabular-nums text-foreground">
        {sending ? <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-500" />
          : <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-rose-500 shadow-[0_0_0_4px_rgba(244,63,94,0.18)]" />}
        <span data-testid="voice-note-timer">{fmt(secs)}</span>
      </span>
      <div className="flex h-9 min-w-0 flex-1 items-center justify-end gap-[2px] overflow-hidden px-1">
        {sending ? <span className="w-full text-center text-xs text-muted-foreground">Sending your voice note…</span>
          : history.map((v, i) => (
            <span key={i} className="w-[3px] shrink-0 rounded-full bg-gradient-to-t from-indigo-500 to-violet-400 transition-[height] duration-100"
              style={{ height: `${Math.round(v * 100)}%`, opacity: 0.35 + 0.65 * (i / history.length) }} />
          ))}
      </div>
      <button type="button" onClick={onSend} disabled={sending} data-testid="voice-note-send" aria-label="Send voice note"
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_8px_24px_rgba(99,102,241,0.45)] transition-transform hover:scale-105 active:scale-95 disabled:opacity-60">
        {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
      </button>
    </div>
  );
}
