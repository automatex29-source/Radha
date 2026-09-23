import { useState } from "react";
import { mediaUrl } from "@/lib/api";
import { Globe, Search, Code2, ImagePlus, Wrench, Loader2, CheckCircle2, XCircle, ChevronRight, FileDown } from "lucide-react";

const ICONS = { web_search: Search, fetch_url: Globe, run_python: Code2, generate_image: ImagePlus };

function argPreview(step) {
  const a = step.args || {};
  if (step.name === "web_search") return a.query;
  if (step.name === "fetch_url") return a.url;
  if (step.name === "generate_image") return a.prompt;
  if (step.name === "run_python") return (a.code || "").split("\n").find((l) => l.trim()) || "";
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

export function MediaGallery({ items }) {
  if (!items?.length) return null;
  const images = items.filter((m) => INLINE_IMAGE.test(m.contentType || ""));
  const files = items.filter((m) => !INLINE_IMAGE.test(m.contentType || ""));
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
      {files.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {files.map((m) => (
            <a key={m.id} href={mediaUrl(m.url)} download={m.name || true}
              className="flex items-center gap-1.5 rounded-lg border border-[#262C3E] bg-[#171B26] px-2.5 py-1.5 text-xs text-foreground hover:border-primary/50">
              <FileDown className="h-3.5 w-3.5 text-primary" /> {m.name || "file"}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
