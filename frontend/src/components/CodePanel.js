import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { AppWindow, Check, Code2, Copy, Download, Eye, Loader2, Maximize2, Minimize2, RefreshCw, X } from "lucide-react";
import { buildPreview, extractFiles } from "@/lib/codeFiles";
import { projectBtn, useProjectActions } from "@/components/CodeProject";

/**
 * The chat's side panel for a reply with code files, like Claude's artifacts: a live Preview and the Code,
 * with Download ZIP, full screen and Open in App Builder. The chat stays beside it for follow-up changes.
 * Desktop: a column to the right of the chat. Phone: full screen.
 */
export default function CodePanel({ content, streaming, onClose }) {
  const files = useMemo(() => extractFiles(content, streaming), [content, streaming]);
  const html = useMemo(() => (streaming ? null : buildPreview(files)), [files, streaming]);
  const [tab, setTab] = useState("preview");
  const [path, setPath] = useState(null);
  const [full, setFull] = useState(false);
  const [reload, setReload] = useState(0);
  const [copied, setCopied] = useState(false);
  const { name, download, openInBuilder, creating } = useProjectActions(files, content);

  // While the AI is writing there's nothing to preview yet: show the code as it arrives, then the preview.
  useEffect(() => { setTab(streaming ? "code" : "preview"); }, [streaming]);
  useEffect(() => { if (!html && !streaming) setTab("code"); }, [html, streaming]);

  const file = files.find((f) => f.path === path) || (streaming ? files[files.length - 1] : files[0]);
  if (!files.length) return null;

  const copy = () => {
    navigator.clipboard.writeText(file.content);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1500);
  };

  const tabBtn = (t, Icon, label) => (
    <button onClick={() => setTab(t)} data-testid={`code-panel-tab-${t}`}
      className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ${tab === t ? "bg-surface-strong text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
      <Icon className="h-3.5 w-3.5" /> {label}
    </button>
  );
  const iconBtn = "rounded-md p-1.5 text-muted-foreground hover:bg-surface hover:text-foreground";

  return (
    <aside data-testid="code-panel"
      className={`flex min-h-0 flex-col border-border bg-card ${full
        ? "fixed inset-0 z-50"
        : "max-md:fixed max-md:inset-0 max-md:z-50 md:w-[48%] md:min-w-[380px] md:max-w-[960px] md:shrink-0 md:border-l"}`}>
      <header className="flex items-center gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold" data-testid="code-panel-title">{name}</p>
          <p className="truncate font-mono text-[11px] text-muted-foreground">
            {streaming ? <span className="inline-flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" /> Building…</span>
              : files.map((f) => f.path).join(" · ")}
          </p>
        </div>
        <button onClick={() => setFull((f) => !f)} title={full ? "Exit full screen" : "Full screen"} className={`${iconBtn} max-md:hidden`} data-testid="code-panel-fullscreen">
          {full ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>
        <button onClick={onClose} title="Close" className={iconBtn} data-testid="code-panel-close">
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-3 py-1.5">
        {tabBtn("preview", Eye, "Preview")}
        {tabBtn("code", Code2, "Code")}
        <div className="ml-auto flex items-center gap-1.5">
          {tab === "preview" && html && (
            <button onClick={() => setReload((r) => r + 1)} title="Reload" className={iconBtn} data-testid="code-panel-reload">
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          )}
          <button onClick={download} disabled={streaming} className={projectBtn} data-testid="code-panel-download">
            <Download className="h-3.5 w-3.5" /> ZIP
          </button>
          <button onClick={openInBuilder} disabled={streaming || creating} className={projectBtn} data-testid="code-panel-open-builder">
            {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <AppWindow className="h-3.5 w-3.5" />}
            <span className="max-sm:hidden">Open in App Builder</span><span className="sm:hidden">Builder</span>
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {tab === "preview" ? (
          html ? (
            /* No allow-same-origin: the page can't touch Krish AI's storage or session. */
            <iframe key={reload} title={`${name} preview`} srcDoc={html} data-testid="code-panel-iframe"
              sandbox="allow-scripts allow-forms allow-modals allow-popups"
              className="block h-full w-full border-0 bg-white" />
          ) : (
            <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
              {streaming ? <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> The preview appears when the code is finished.</span>
                : "There's no web page to preview in these files. Open the Code tab."}
            </div>
          )
        ) : (
          <div className="flex h-full min-h-0 flex-col">
            <div className="flex items-center gap-1 overflow-x-auto border-b border-border px-2 py-1">
              {files.map((f) => (
                <button key={f.path} onClick={() => setPath(f.path)} data-testid={`code-panel-file-${f.path}`}
                  className={`shrink-0 rounded px-2 py-1 font-mono text-[11px] ${f.path === file.path ? "bg-surface-strong text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                  {f.path}
                </button>
              ))}
              <button onClick={copy} title="Copy this file" className={`${iconBtn} ml-auto`} data-testid="code-panel-copy">
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>
            <pre className="radha-scroll min-h-0 flex-1 overflow-auto bg-sunken p-3 font-mono text-xs leading-relaxed" data-testid="code-panel-code">
              <code>{file.content}</code>
            </pre>
          </div>
        )}
      </div>
    </aside>
  );
}
