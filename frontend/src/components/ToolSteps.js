import { useState } from "react";
import { mediaUrl } from "@/lib/api";
import { ChevronRight, FileDown, Eye, Hand, Check, X } from "lucide-react";
import { fileKind, KIND_META } from "@/components/PreviewPanel";
import ThinkingShape from "@/components/ThinkingShape";

function argPreview(step) {
  const a = step.args || {};
  if (step.name === "web_search") return a.query;
  if (step.name === "pro_search") return (a.queries || []).join(" · ") || a.query;
  if (step.name === "fetch_url") return a.url;
  if (step.name === "generate_image") return a.prompt;
  if (step.name === "run_python") return ""; // its first line ("import heapq") says nothing; the code opens on a tap
  if (step.name === "generate_video") return a.prompt;
  if (step.name.startsWith("create_")) return a.filename;
  if (["write_file", "append_file", "edit_file", "read_file", "delete_file"].includes(step.name)) return a.path;
  if (step.name === "run_command") return a.command;
  if (step.name === "commit") return a.message;
  if (step.name === "check_preview") return a.path || "index.html";
  if (["list_files", "plan_app", "check_features"].includes(step.name)) return "";
  if (step.name === "browser") {
    return [a.action, a.url || (a.ref != null ? `#${a.ref}` : ""), a.text ? `“${a.text}”` : "", a.key || "", a.direction || ""]
      .filter(Boolean).join(" ");
  }
  if (step.name === "start_template") return "";
  // Other tools: their first short text argument, never raw JSON.
  const first = Object.values(a).find((v) => typeof v === "string" && v.trim());
  return first ? first.slice(0, 80) : "";
}

// What each step is doing, in plain words (like Claude): "Running code" while it runs, "Ran code" after.
const VERBS = {
  web_search: ["Searching the web", "Searched the web"], pro_search: ["Searching the web", "Searched the web"],
  fetch_url: ["Reading a page", "Read a page"], run_python: ["Running code", "Ran code"],
  generate_image: ["Making a picture", "Made a picture"], edit_image: ["Changing the picture", "Changed the picture"], generate_video: ["Making a video", "Made a video"],
  create_spreadsheet: ["Making a spreadsheet", "Made a spreadsheet"], create_presentation: ["Making slides", "Made slides"],
  create_document: ["Writing a document", "Wrote a document"], create_html: ["Making a page", "Made a page"],
  browser: ["Using the browser", "Used the browser"], write_file: ["Writing", "Wrote"], append_file: ["Writing", "Wrote"],
  edit_file: ["Editing", "Edited"], read_file: ["Reading", "Read"], delete_file: ["Deleting", "Deleted"],
  list_files: ["Looking at the files", "Looked at the files"], search_files: ["Searching the files", "Searched the files"],
  run_command: ["Running a command", "Ran a command"], check_preview: ["Checking the preview", "Checked the preview"],
  commit: ["Saving a version", "Saved a version"], plan_app: ["Planning the app", "Planned the app"],
  check_features: ["Checking the features", "Checked the features"],
};
// The running step's second line on the rail: exactly what Krish is doing right now.
function liveDetail(step) {
  const a = step.args || {};
  if (step.name === "web_search" || step.name === "pro_search") {
    const q = (a.queries || []).join(" · ") || a.query;
    return q ? `“${q}”` : "";
  }
  if (step.name === "run_python" && a.code) {
    const lines = a.code.split("\n").map((l) => l.trim()).filter(Boolean);
    const main = lines.find((l) => !/^(import|from)\s|^#/.test(l)) || lines[0] || "";
    return `${lines.length} ${lines.length === 1 ? "line" : "lines"} of Python · ${main}`;
  }
  return argPreview(step);
}
const MONO = new Set(["run_python", "run_command", "write_file", "append_file", "edit_file", "read_file", "delete_file", "fetch_url"]);

function RailDot({ state }) {
  return (
    <span className={`krish-rail-dot is-${state}`} aria-hidden="true">
      {state === "done" && <Check className="h-2.5 w-2.5" strokeWidth={3.5} />}
      {state === "error" && <X className="h-2.5 w-2.5" strokeWidth={3.5} />}
      {state === "wait" && <Hand className="h-2.5 w-2.5" strokeWidth={2.5} />}
    </span>
  );
}

function Step({ step }) {
  const [open, setOpen] = useState(false);
  const running = step.status === "running";
  const failed = step.status === "error";
  const stopped = step.status === "stopped";
  const [doing, did] = VERBS[step.name] || [step.label || step.name, step.label || step.name];
  const preview = argPreview(step);
  const live = running ? liveDetail(step) : "";
  const details = (step.name === "run_python" && step.args?.code) || step.output || step.summary;
  const note = failed ? "didn't work" : stopped ? "stopped" : step.approval ? "waiting for you" : "";
  const dot = step.approval ? "wait" : running ? "run" : failed ? "error" : stopped ? "stop" : "done";
  const mono = MONO.has(step.name) ? "font-mono text-[11.5px]" : "";
  // A picture being made shows as its own animated frame (PictureMaking), not as a rail row.
  if (running && (step.name === "generate_image" || step.name === "edit_image")) return null;
  return (
    <div className="krish-rail-row" data-testid={`tool-step-${step.name}`} data-status={step.status}>
      <RailDot state={dot} />
      <div className="min-w-0 flex-1">
        <button type="button" onClick={() => setOpen((o) => !o)} disabled={running || !details} aria-expanded={open}
          className="krish-step group/step">
          <span className={`shrink-0 font-medium ${running ? "krish-thinking-words" : "text-foreground/80"}`}>{running ? doing : did}</span>
          {!running && preview && <span className={`min-w-0 truncate text-muted-foreground/75 ${mono}`}>{preview}</span>}
          {note && <span className="shrink-0 text-muted-foreground/75">· {note}</span>}
          {!running && details && <ChevronRight className={`h-3.5 w-3.5 shrink-0 opacity-60 transition-transform group-hover/step:opacity-100 ${open ? "rotate-90" : ""}`} />}
        </button>
        {live && <p className={`krish-rail-live truncate ${mono}`} data-testid="tool-step-live">{live}</p>}
        {open && details && (
          <div className="mb-1 mt-1 space-y-2 rounded-lg border border-border bg-sunken p-2 radha-fade-up">
            {step.summary && <p className="px-1 text-[11.5px] text-muted-foreground">{step.summary}</p>}
            {step.name === "run_python" && step.args?.code && (
              <pre className="radha-scroll max-h-64 overflow-auto rounded-md bg-background p-2 font-mono text-[11px] text-foreground/85">{step.args.code}</pre>
            )}
            {step.output && (
              <pre className="radha-scroll max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-background p-2 font-mono text-[11px] text-muted-foreground">{step.output}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// A square that turns and softens into a circle (saffron centre), then "Krish is thinking…", as the rail's live row: before the first step, and between steps.
function ThinkingRow() {
  return (
    <div className="krish-rail-row" role="status" data-testid="streaming-cursor">
      <ThinkingShape className="krish-rail-shape" />
      <span className="krish-step"><span className="krish-thinking-words font-medium">Krish is thinking…</span></span>
    </div>
  );
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// One line for a finished build ("Planned the app · wrote 4 files · tested it"), like a commit summary.
export function stepsSummary(steps) {
  const done = steps.filter((s) => s.status === "done");
  const count = (...names) => new Set(done.filter((s) => names.includes(s.name)).map((s) => s.args?.path || s.id)).size;
  const parts = [];
  if (done.some((s) => s.name === "plan_app")) parts.push("planned the app");
  const wrote = count("write_file", "append_file");
  const edited = count("edit_file");
  const read = count("read_file", "search_files", "list_files");
  if (wrote) parts.push(`wrote ${plural(wrote, "file")}`);
  if (edited) parts.push(`edited ${plural(edited, "file")}`);
  if (read) parts.push(`read ${plural(read, "file")}`);
  if (done.some((s) => s.name === "run_command")) parts.push("ran tests");
  if (done.some((s) => s.name === "check_preview" || s.name === "check_features")) parts.push("checked it");
  if (done.some((s) => s.name === "commit")) parts.push("saved a version");
  const failed = steps.filter((s) => s.status === "error").length;
  if (failed) parts.push(`${failed} didn't work`);
  const text = parts.join(" · ") || plural(steps.length, "step");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// `compact` (the App Builder) folds a finished reply's steps into one line that opens the full list.
// The steps sit on a rail (a saffron-to-green line): the running step pulses saffron and shows what it is doing
// right now, finished steps get a green tick. `thinking` adds a live "Krish is thinking…" row at the end.
export function ToolSteps({ steps = [], compact = false, thinking = false }) {
  const [open, setOpen] = useState(false);
  if (!steps?.length && !thinking) return null;
  steps = steps || [];
  const finished = steps.every((s) => s.status !== "running");
  if (compact && finished && !thinking && steps.length > 2 && !open) {
    return (
      <button onClick={() => setOpen(true)} data-testid="tool-steps-summary"
        className="mb-3 flex max-w-full items-center gap-1.5 text-left text-xs text-muted-foreground hover:text-foreground">
        <span className="truncate">{stepsSummary(steps)}</span>
        <ChevronRight className="h-3.5 w-3.5 shrink-0" />
      </button>
    );
  }
  return (
    <div className="krish-rail mb-3" data-testid="tool-steps">
      {compact && open && (
        <button onClick={() => setOpen(false)} className="flex items-center gap-1.5 text-left text-xs text-muted-foreground hover:text-foreground">
          {stepsSummary(steps)} <ChevronRight className="h-3.5 w-3.5 rotate-90" />
        </button>
      )}
      {steps.map((s) => <Step key={s.id} step={s} />)}
      {thinking && <ThinkingRow />}
    </div>
  );
}

const INLINE_IMAGE = /^image\/(png|jpe?g|gif|webp)$/;
const PREVIEWABLE = new Set(["sheet", "slides", "doc", "pdf", "html"]);

function FileCard({ item, onOpen }) {
  const kind = fileKind(item);
  const meta = KIND_META[kind] || KIND_META.file;
  const canPreview = PREVIEWABLE.has(kind) || /^(text\/|application\/json)/.test(item.contentType || "");
  return (
    <div className="flex w-full max-w-sm items-center gap-3 rounded-xl border border-border-strong bg-card p-3" data-testid={`file-card-${item.id}`}>
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-strong">
        <meta.icon className={`h-5 w-5 ${meta.color}`} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{item.name || "file"}</p>
        <p className="text-[11px] text-muted-foreground">{meta.label}</p>
      </div>
      {canPreview && onOpen && (
        <button onClick={() => onOpen(item)} data-testid={`open-preview-${item.id}`} title="Preview"
          className="flex h-8 items-center gap-1 rounded-lg border border-border px-2.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground">
          <Eye className="h-3.5 w-3.5" /> Open
        </button>
      )}
      <a href={mediaUrl(item.url)} download={item.name || true} title="Download"
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:border-primary/50 hover:text-foreground">
        <FileDown className="h-3.5 w-3.5" />
      </a>
    </div>
  );
}

function MediaDownload({ item }) {
  return (
    <a href={mediaUrl(item.url)} download={item.name || true} title="Download" data-testid={`media-download-${item.id}`}
      className="absolute right-2 top-2 flex h-8 items-center gap-1 rounded-lg bg-black/60 px-2.5 text-xs font-medium text-white backdrop-blur hover:bg-black/80">
      <FileDown className="h-3.5 w-3.5" /> Download
    </a>
  );
}

export function MediaGallery({ items, onOpen }) {
  if (!items?.length) return null;
  const images = items.filter((m) => INLINE_IMAGE.test(m.contentType || ""));
  const videos = items.filter((m) => (m.contentType || "").startsWith("video/"));
  const files = items.filter((m) => !INLINE_IMAGE.test(m.contentType || "") && !(m.contentType || "").startsWith("video/"));
  return (
    <div className="mt-3 space-y-2" data-testid="message-media">
      {images.length > 0 && (
        <div className={`grid gap-2 ${images.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
          {images.map((m) => (
            <div key={m.id} className="group relative">
              <a href={mediaUrl(m.url)} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl border border-border bg-sunken">
                <img src={mediaUrl(m.url)} alt={m.name || "Generated image"} loading="lazy" className="max-h-[480px] w-full object-contain" data-testid={`media-image-${m.id}`} />
              </a>
              <MediaDownload item={m} />
            </div>
          ))}
        </div>
      )}
      {videos.map((m) => (
        <div key={m.id} className="group relative">
          <video src={mediaUrl(m.url)} controls playsInline data-testid={`media-video-${m.id}`}
            className="max-h-[480px] w-full rounded-xl border border-border bg-black" />
          <MediaDownload item={m} />
        </div>
      ))}
      {files.length > 0 && (
        <div className="flex flex-col gap-2">
          {files.map((m) => <FileCard key={m.id} item={m} onOpen={onOpen} />)}
        </div>
      )}
    </div>
  );
}
