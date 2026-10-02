import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Download, Eye, EyeOff, FileCode2, Loader2, Maximize2, Minimize2, AppWindow, RefreshCw } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { buildPreview, extractFiles, makeZip, projectName, withKit } from "@/lib/codeFiles";

/** Download ZIP and Open in App Builder for a set of code files. */
export function useProjectActions(replyFiles, content) {
  const [creating, setCreating] = useState(false);
  const files = withKit(replyFiles);
  const navigate = useNavigate();
  const name = projectName(files, content);
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "my-app";

  const download = () => {
    const blob = new Blob([makeZip(files, slug)], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };

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
  return { name, download, openInBuilder, creating };
}

export const projectBtn = "flex h-7 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 text-xs font-medium hover:border-primary/50 disabled:opacity-50";

/** In the chat, a reply with code files shows as a card that opens the side panel (like Claude's artifacts). */
function CodeCard({ files, content, streaming, onOpen, active }) {
  const { name, download } = useProjectActions(files, content);
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
      {!streaming && (
        <button onClick={download} className={projectBtn} title="Download ZIP" data-testid="code-project-download">
          <Download className="h-3.5 w-3.5" /><span className="max-sm:hidden">ZIP</span>
        </button>
      )}
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
  const { name, download, openInBuilder, creating } = useProjectActions(files, content);

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
              <button onClick={download} className={btn} data-testid="code-project-download">
                <Download className="h-3.5 w-3.5" /> Download ZIP
              </button>
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
