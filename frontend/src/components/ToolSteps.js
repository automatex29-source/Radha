import { useState } from "react";
import { mediaUrl } from "@/lib/api";
import { Globe, Search, Code2, ImagePlus, Wrench, Loader2, CheckCircle2, XCircle, ChevronRight, FileDown,
  FileSpreadsheet, Presentation, FileText, Clapperboard, MousePointerClick, Eye } from "lucide-react";
import { fileKind, KIND_META } from "@/components/PreviewPanel";

const ICONS = {
  web_search: Search, fetch_url: Globe, run_python: Code2, generate_image: ImagePlus, generate_video: Clapperboard,
  create_spreadsheet: FileSpreadsheet, create_presentation: Presentation, create_document: FileText, create_html: Globe,
  browser: MousePointerClick,
};

function argPreview(step) {
  const a = step.args || {};
  if (step.name === "web_search") return a.query;
  if (step.name === "fetch_url") return a.url;
  if (step.name === "generate_image") return a.prompt;
  if (step.name === "run_python") return (a.code || "").split("\n").find((l) => l.trim()) || "";
  if (step.name === "generate_video") return a.prompt;
  if (step.name.startsWith("create_")) return a.filename;
  if (step.name === "browser") {
    return [a.action, a.url || (a.ref != null ? `#${a.ref}` : ""), a.text ? `“${a.text}”` : "", a.key || "", a.direction || ""]
      .filter(Boolean).join(" ");
  }
  return JSON.stringify(a);
}

function Step({ step }) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[step.name] || Wrench;
  const running = step.status === "running";
  const failed = step.status === "error";
  return (
    <div className="rounded-lg border border-[#222738] bg-[#0F121A]" data-testid={`tool-step-${step.name}`}>
      <button onClick={() => setOpen((o) => !o)} disabled={running}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
        <span className="shrink-0 font-semibold text-foreground">{step.label || step.name}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">{argPreview(step)}</span>
        {running ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-amber-400" />
          : failed ? <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
          : <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" />}
        {!running && <ChevronRight className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`} />}
      </button>
      {!running && step.summary && !open && (
        <p className="truncate px-3 pb-2 pl-8 text-[11px] text-muted-foreground">{step.summary}</p>
      )}
      {open && (
        <div className="space-y-2 border-t border-[#222738] px-3 py-2">
          {step.name === "run_python" && step.args?.code && (
            <pre className="radha-scroll max-h-64 overflow-auto rounded-md bg-[#07080B] p-2 font-mono text-[11px] text-[#C7D2FE]">{step.args.code}</pre>
          )}
          {step.output && (
            <pre className="radha-scroll max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-[#07080B] p-2 font-mono text-[11px] text-muted-foreground">{step.output}</pre>
          )}
        </div>
      )}
    </div>
  );
}

export function ToolSteps({ steps }) {
  if (!steps?.length) return null;
  return (
    <div className="mb-3 space-y-1.5" data-testid="tool-steps">
      {steps.map((s) => <Step key={s.id} step={s} />)}
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
    <div className="flex w-full max-w-sm items-center gap-3 rounded-xl border border-[#262C3E] bg-[#11141D] p-3" data-testid={`file-card-${item.id}`}>
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#1D2230]">
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
            <a key={m.id} href={mediaUrl(m.url)} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl border border-[#222738] bg-[#0F121A]">
              <img src={mediaUrl(m.url)} alt={m.name || "Generated image"} loading="lazy" className="max-h-[480px] w-full object-contain" data-testid={`media-image-${m.id}`} />
            </a>
          ))}
        </div>
      )}
      {videos.map((m) => (
        <video key={m.id} src={mediaUrl(m.url)} controls playsInline data-testid={`media-video-${m.id}`}
          className="max-h-[480px] w-full rounded-xl border border-[#222738] bg-black" />
      ))}
      {files.length > 0 && (
        <div className="flex flex-col gap-2">
          {files.map((m) => <FileCard key={m.id} item={m} onOpen={onOpen} />)}
        </div>
      )}
    </div>
  );
}
