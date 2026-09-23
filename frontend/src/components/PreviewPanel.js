import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, mediaUrl, getToken, API, formatApiError } from "@/lib/api";
import { X, Download, Loader2, Code2, Eye, FileSpreadsheet, Presentation, FileText, Globe, File } from "lucide-react";

export function fileKind(item) {
  const ct = item?.contentType || "";
  const name = (item?.name || "").toLowerCase();
  if (ct.includes("spreadsheetml") || name.endsWith(".xlsx") || ct === "text/csv") return "sheet";
  if (ct.includes("presentationml") || name.endsWith(".pptx")) return "slides";
  if (ct.includes("wordprocessingml") || name.endsWith(".docx")) return "doc";
  if (ct === "application/pdf") return "pdf";
  if (ct === "text/html") return "html";
  if (ct.startsWith("image/")) return "image";
  if (ct.startsWith("video/")) return "video";
  return "file";
}

export const KIND_META = {
  sheet: { icon: FileSpreadsheet, label: "Excel", color: "text-emerald-400" },
  slides: { icon: Presentation, label: "PowerPoint", color: "text-orange-400" },
  doc: { icon: FileText, label: "Word", color: "text-sky-400" },
  pdf: { icon: FileText, label: "PDF", color: "text-rose-400" },
  html: { icon: Globe, label: "Web page", color: "text-violet-400" },
  file: { icon: File, label: "File", color: "text-muted-foreground" },
};

const DOC_CSS = `body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1f2937;
max-width:760px;margin:0 auto;padding:40px 44px;line-height:1.65;font-size:15px;background:#fff}
h1{font-size:28px;margin:0 0 16px}h2{font-size:21px;color:#4338ca;margin:28px 0 10px}h3{font-size:17px;margin:22px 0 8px}
table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #e5e7eb;padding:6px 10px;text-align:left}
th{background:#6366f1;color:#fff}blockquote{border-left:3px solid #c7d2fe;margin:12px 0;padding:4px 14px;color:#4b5563;font-style:italic}
a{color:#4f46e5}li{margin:3px 0}`;

function SheetView({ sheets }) {
  const [active, setActive] = useState(0);
  const sheet = sheets[active] || { rows: [] };
  const [head, ...body] = sheet.rows;
  return (
    <div className="flex h-full flex-col">
      {sheets.length > 1 && (
        <div className="flex gap-1 border-b border-border px-3 pt-2">
          {sheets.map((s, i) => (
            <button key={i} onClick={() => setActive(i)}
              className={`rounded-t-md px-3 py-1.5 text-xs font-medium ${i === active ? "bg-[#171B26] text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {s.name}
            </button>
          ))}
        </div>
      )}
      <div className="radha-scroll flex-1 overflow-auto">
        <table className="w-full border-collapse text-xs" data-testid="preview-table">
          {head && (
            <thead className="sticky top-0">
              <tr>
                <th className="w-10 border border-[#222738] bg-[#11141D] px-2 py-1.5 text-muted-foreground">#</th>
                {head.map((c, i) => <th key={i} className="border border-[#222738] bg-[#1E2140] px-3 py-1.5 text-left font-semibold text-[#C7D2FE]">{c}</th>)}
              </tr>
            </thead>
          )}
          <tbody>
            {body.map((row, r) => (
              <tr key={r} className="odd:bg-[#0F121A]">
                <td className="border border-[#222738] px-2 py-1 text-center text-muted-foreground">{r + 2}</td>
                {head?.map((_, c) => (
                  <td key={c} className={`whitespace-nowrap border border-[#222738] px-3 py-1 ${/^-?[\d.,$%]+$/.test(row[c] || "") ? "text-right font-mono" : ""}`}>{row[c]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {sheet.truncated && <p className="p-3 text-xs text-muted-foreground">Showing the first rows only — download for the full sheet.</p>}
      </div>
    </div>
  );
}

function SlidesView({ slides }) {
  return (
    <div className="radha-scroll h-full space-y-5 overflow-y-auto p-5" data-testid="preview-slides">
      {slides.map((s) => (
        <div key={s.index}>
          <div className="relative flex aspect-video flex-col overflow-hidden rounded-lg border border-[#262C3E] bg-[#0B0D14] p-[6%] shadow-lg">
            <p className="text-[clamp(14px,2.4vw,24px)] font-bold leading-tight text-white">{s.title}</p>
            <div className="mt-2 h-1 w-10 rounded bg-primary" />
            {s.table ? (
              <table className="mt-4 w-full text-[11px]">
                <tbody>
                  {s.table.map((row, r) => (
                    <tr key={r}>{row.map((c, i) => <td key={i} className={`border border-[#262C3E] px-2 py-1 ${r === 0 ? "bg-primary font-semibold text-white" : "text-[#D1D5DB]"}`}>{c}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="mt-4 space-y-1.5 overflow-hidden">
                {s.lines.map((l, i) => <p key={i} className="whitespace-pre text-[clamp(10px,1.5vw,15px)] text-[#D1D5DB]">{l}</p>)}
              </div>
            )}
            <span className="absolute bottom-2 right-3 text-[10px] text-muted-foreground">{s.index}</span>
          </div>
          {s.notes && <p className="mt-1.5 px-1 text-[11px] text-muted-foreground"><span className="font-semibold">Notes:</span> {s.notes}</p>}
        </div>
      ))}
    </div>
  );
}

function PdfView({ item }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let url;
    fetch(`${API}${item.url.replace(/^\/api/, "")}`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((b) => { url = URL.createObjectURL(new Blob([b], { type: "application/pdf" })); setSrc(url); })
      .catch(() => setSrc(""));
    return () => url && URL.revokeObjectURL(url);
  }, [item.url]);
  if (src === null) return <Spinner />;
  return <iframe title={item.name} src={src} className="h-full w-full bg-white" data-testid="preview-pdf" />;
}

const Spinner = () => (
  <div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
);

export default function PreviewPanel({ item, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("preview");
  const kind = fileKind(item);
  const meta = KIND_META[kind] || KIND_META.file;

  useEffect(() => {
    setData(null);
    setError("");
    setTab("preview");
    if (["image", "video", "pdf"].includes(kind)) return;
    api.get(`/media/${item.id}/preview`).then(({ data }) => setData(data.preview)).catch((e) => setError(formatApiError(e)));
  }, [item.id, kind]);

  let body;
  if (error) body = <p className="p-6 text-sm text-destructive">{error}</p>;
  else if (kind === "image") body = <div className="flex h-full items-center justify-center p-4"><img src={mediaUrl(item.url)} alt={item.name} className="max-h-full max-w-full rounded-lg" /></div>;
  else if (kind === "video") body = <div className="flex h-full items-center justify-center p-4"><video src={mediaUrl(item.url)} controls className="max-h-full max-w-full rounded-lg" /></div>;
  else if (kind === "pdf") body = <PdfView item={item} />;
  else if (!data) body = <Spinner />;
  else if (data.type === "table") body = <SheetView sheets={data.sheets} />;
  else if (data.type === "slides") body = <SlidesView slides={data.slides} />;
  else if (data.type === "document") {
    body = <iframe title={item.name} sandbox="" className="h-full w-full bg-white" data-testid="preview-document"
      srcDoc={`<!doctype html><meta charset="utf-8"><style>${DOC_CSS}</style>${data.html}`} />;
  } else if (data.type === "html") {
    body = tab === "code"
      ? <pre className="radha-scroll h-full overflow-auto p-4 font-mono text-xs text-[#C7D2FE]">{data.html}</pre>
      // No allow-same-origin: the page runs scripts in an isolated origin with no access to RADHA.
      : <iframe title={item.name} sandbox="allow-scripts allow-forms allow-modals allow-popups" className="h-full w-full bg-white"
          srcDoc={data.html} data-testid="preview-html" />;
  } else if (data.type === "markdown") {
    body = <div className="radha-prose radha-scroll h-full overflow-y-auto p-6"><ReactMarkdown remarkPlugins={[remarkGfm]}>{data.text}</ReactMarkdown></div>;
  } else if (data.type === "code") {
    body = <pre className="radha-scroll h-full overflow-auto whitespace-pre-wrap p-4 font-mono text-xs text-foreground">{data.text}</pre>;
  } else body = <p className="p-6 text-sm text-muted-foreground">No preview for this file type — download it instead.</p>;

  return (
    <aside className="fixed inset-0 z-50 flex flex-col border-l border-border bg-[#0B0D14] lg:static lg:z-auto lg:w-[46%] lg:min-w-[420px] lg:max-w-[820px]"
      data-testid="preview-panel">
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <meta.icon className={`h-4 w-4 shrink-0 ${meta.color}`} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold" data-testid="preview-title">{item.name || "File"}</p>
          <p className="text-[11px] text-muted-foreground">{meta.label}{item.size ? ` · ${(item.size / 1024).toFixed(item.size > 102400 ? 0 : 1)} KB` : ""}</p>
        </div>
        {kind === "html" && (
          <div className="flex rounded-lg border border-border p-0.5">
            {[["preview", Eye], ["code", Code2]].map(([t, Icon]) => (
              <button key={t} onClick={() => setTab(t)} data-testid={`preview-tab-${t}`}
                className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs ${tab === t ? "bg-[#1D2230] text-foreground" : "text-muted-foreground"}`}>
                <Icon className="h-3.5 w-3.5" /> {t === "preview" ? "Preview" : "Code"}
              </button>
            ))}
          </div>
        )}
        <a href={mediaUrl(item.url)} download={item.name || true} data-testid="preview-download"
          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs font-medium hover:border-primary/50">
          <Download className="h-3.5 w-3.5" /> Download
        </a>
        <button onClick={onClose} data-testid="preview-close" title="Close preview"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-[#171B26] hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1">{body}</div>
    </aside>
  );
}
