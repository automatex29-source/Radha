import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ChevronDown, Download, Eye, EyeOff, FileArchive, FileCode2, FileText, Globe, Loader2, Maximize2, Minimize2, AppWindow, Printer, RefreshCw } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, formatApiError } from "@/lib/api";
import { buildPreview, extractFiles, makeZip, projectName, withImages, withKit } from "@/lib/codeFiles";

/** Download ZIP and Open in App Builder for a set of code files. */
export function useProjectActions(replyFiles, content) {
  const [creating, setCreating] = useState(false);
  const files = withKit(replyFiles);
  const navigate = useNavigate();
  const name = projectName(files, content);
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "my-app";

  const download = () => saveBlob(new Blob([makeZip(withImages(files), slug)], { type: "application/zip" }), `${slug}.zip`);

  const openInBuilder = async () => {
    setCreating(true);
    try {
      const { data } = await api.post("/apps", {
        name, files: Object.fromEntries(files.map((f) => [f.path, f.content])),
      });
      navigate(`/apps/${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
      setCreating(false);
    }
  };
  return { name, slug, download, openInBuilder, creating };
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const MIME = { html: "text/html", htm: "text/html", css: "text/css", js: "text/javascript", mjs: "text/javascript",
  json: "application/json", svg: "image/svg+xml", csv: "text/csv", md: "text/markdown", xml: "application/xml" };
const mimeFor = (path) => `${MIME[path.split(".").pop().toLowerCase()] || "text/plain"};charset=utf-8`;
const baseName = (path) => path.split("/").pop();

/** Download in the format the user wants: every file on its own (in its own format), the page as one HTML file
 * or a PDF, all the code as one text or Markdown file, or everything as a ZIP. */
export function DownloadMenu({ files: replyFiles, content, label = "Download", className = projectBtn }) {
  const { slug, download } = useProjectActions(replyFiles, content);
  const page = useMemo(() => buildPreview(replyFiles), [replyFiles]);
  const allCode = (markdown) => replyFiles.map((f) => (markdown
    ? `## ${f.path}\n\n\`\`\`${f.lang || ""}\n${f.content}\n\`\`\`\n`
    : `===== ${f.path} =====\n${f.content}\n`)).join("\n");
  // Printed from a sandboxed frame (no allow-same-origin), so the page's scripts can't reach Krish AI's session.
  const printPdf = () => {
    const frame = document.createElement("iframe");
    frame.setAttribute("sandbox", "allow-scripts allow-modals");
    frame.setAttribute("aria-hidden", "true");
    frame.style.cssText = "position:fixed;left:-10000px;top:0;width:1024px;height:800px;border:0";
    frame.srcdoc = page.replace(/<\/body>(?![\s\S]*<\/body>)/i, "") +
      "<script>addEventListener('load',function(){setTimeout(function(){print()},400)})<\/script></body>";
    document.body.appendChild(frame);
    setTimeout(() => frame.remove(), 120000);
    toast.info("In the print window, choose “Save as PDF”.");
  };
  const item = "cursor-pointer gap-2 text-xs";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className={className} data-testid="code-download-menu" title="Download">
          <Download className="h-3.5 w-3.5" />{label && <span className="max-sm:hidden">{label}</span>}<ChevronDown className="h-3 w-3" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[70vh] w-64 overflow-y-auto">
        <DropdownMenuItem className={item} onSelect={download} data-testid="download-zip">
          <FileArchive className="h-3.5 w-3.5" /> Everything (.zip)
        </DropdownMenuItem>
        {page && (
          <>
            <DropdownMenuItem className={item} data-testid="download-page-html"
              onSelect={() => saveBlob(new Blob([page], { type: "text/html;charset=utf-8" }), `${slug}.html`)}>
              <Globe className="h-3.5 w-3.5" /> Web page in one file (.html)
            </DropdownMenuItem>
            <DropdownMenuItem className={item} onSelect={printPdf} data-testid="download-page-pdf">
              <Printer className="h-3.5 w-3.5" /> Web page as PDF (.pdf)
            </DropdownMenuItem>
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[11px] font-medium text-muted-foreground">Each file</DropdownMenuLabel>
        {replyFiles.map((f) => (
          <DropdownMenuItem key={f.path} className={`${item} font-mono`} data-testid={`download-file-${f.path}`}
            onSelect={() => saveBlob(new Blob([f.content], { type: mimeFor(f.path) }), baseName(f.path))}>
            <FileCode2 className="h-3.5 w-3.5" /> <span className="truncate">{f.path}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem className={item} data-testid="download-all-txt"
          onSelect={() => saveBlob(new Blob([allCode(false)], { type: "text/plain;charset=utf-8" }), `${slug}.txt`)}>
          <FileText className="h-3.5 w-3.5" /> All code as text (.txt)
        </DropdownMenuItem>
        <DropdownMenuItem className={item} data-testid="download-all-md"
          onSelect={() => saveBlob(new Blob([allCode(true)], { type: "text/markdown;charset=utf-8" }), `${slug}.md`)}>
          <FileText className="h-3.5 w-3.5" /> All code as Markdown (.md)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const projectBtn = "flex h-7 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 text-xs font-medium hover:border-primary/50 disabled:opacity-50";

/** In the chat, a reply with code files shows as a card that opens the side panel (like Claude's artifacts). */
function CodeCard({ files, content, streaming, onOpen, active }) {
  const { name } = useProjectActions(files, content);
  return (
    <div className={`mt-3 flex items-center gap-3 rounded-xl border bg-card p-3 transition ${active ? "border-primary/60 ring-2 ring-primary/15" : "border-border-strong hover:border-primary/50"}`}
      data-testid="code-project">
      <button onClick={onOpen} className="flex min-w-0 flex-1 items-center gap-3 text-left" data-testid="code-project-open-panel">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {streaming ? <Loader2 className="h-5 w-5 animate-spin" /> : <FileCode2 className="h-5 w-5" />}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold">{name}</span>
          <span className="block truncate text-xs text-muted-foreground">
            {streaming ? `Building ${files.length} file${files.length === 1 ? "" : "s"}…` : `${files.length} file${files.length === 1 ? "" : "s"} · Click to ${active ? "view" : "open"} preview`}
          </span>
        </span>
      </button>
      {!streaming && <DownloadMenu files={files} content={content} />}
    </div>
  );
}

/** Under an AI reply that contains code files: a card for the side panel, or (with no panel) an inline preview. */
export default function CodeProject({ content, streaming, onOpen, active }) {
  const files = useMemo(() => extractFiles(content, streaming), [content, streaming]);
  if (!files.length) return null;
  if (onOpen) return <CodeCard files={files} content={content} streaming={streaming} onOpen={onOpen} active={active} />;
  return <InlineProject files={files} content={content} streaming={streaming} />;
}

/** Elsewhere (shared chats): the preview right under the reply. */
function InlineProject({ files, content, streaming }) {
  const html = useMemo(() => (streaming ? null : buildPreview(files)), [files, streaming]);
  const [open, setOpen] = useState(true);
  const [big, setBig] = useState(false);
  const [reload, setReload] = useState(0);
  const { name, openInBuilder, creating } = useProjectActions(files, content);

  const btn = projectBtn;

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-border-strong bg-sunken" data-testid="code-project">
      <div className="flex flex-wrap items-center gap-2 border-b border-border-strong px-3 py-2">
        <FileCode2 className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold">{name}</span>
        <span className="truncate font-mono text-[11px] text-muted-foreground">
          {files.map((f) => f.path).join(" · ")}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          {streaming ? (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Building {files.length} file{files.length === 1 ? "" : "s"}…
            </span>
          ) : (
            <>
              {html && (
                <button onClick={() => setOpen((o) => !o)} className={btn} data-testid="code-project-preview">
                  {open ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />} {open ? "Hide preview" : "Preview"}
                </button>
              )}
              <DownloadMenu files={files} content={content} />
              <button onClick={openInBuilder} disabled={creating} className={btn} data-testid="code-project-open-builder">
                {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <AppWindow className="h-3.5 w-3.5" />} Open in App Builder
              </button>
            </>
          )}
        </div>
      </div>
      {html && open && (
        <div className="relative bg-white">
          <div className="absolute right-2 top-2 z-10 flex gap-1">
            <button onClick={() => setReload((r) => r + 1)} title="Reload" className="rounded-md bg-black/60 p-1.5 text-white hover:bg-black/80">
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
            <button onClick={() => setBig((b) => !b)} title={big ? "Smaller" : "Bigger"} className="rounded-md bg-black/60 p-1.5 text-white hover:bg-black/80">
              {big ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>
          </div>
          {/* No allow-same-origin: the page can't touch Krish AI's storage or session. */}
          <iframe key={reload} title={`${name} preview`} srcDoc={html} data-testid="code-project-iframe"
            sandbox="allow-scripts allow-forms allow-modals allow-popups"
            className={`block w-full border-0 ${big ? "h-[80vh]" : "h-[420px]"}`} />
        </div>
      )}
    </div>
  );
}
