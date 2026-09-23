import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, API, absoluteUrl, formatApiError, getToken } from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import MessageBubble from "@/components/MessageBubble";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  ArrowLeft, Loader2, Send, Square, RefreshCw, ExternalLink, Code2, Eye, SquareTerminal, History, Rocket,
  Download, Save, FilePlus, Trash2, RotateCcw, Globe, Copy, Play, Circle, AppWindow,
} from "lucide-react";

const FILE_TOOLS = new Set(["write_file", "edit_file", "delete_file", "commit"]);

export default function AppBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [app, setApp] = useState(null);
  const [files, setFiles] = useState([]);
  const [changes, setChanges] = useState({});
  const [commits, setCommits] = useState([]);
  const [tab, setTab] = useState("preview");
  const [previewKey, setPreviewKey] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [{ data }, { data: history }] = await Promise.all([api.get(`/apps/${id}`), api.get(`/apps/${id}/commits`)]);
      setApp(data.app);
      setFiles(data.files);
      setChanges(data.changes);
      setCommits(history);
    } catch (e) {
      toast.error(formatApiError(e));
      if (e?.response?.status === 404) navigate("/apps");
    }
  }, [id, navigate]);

  useEffect(() => { refresh(); }, [refresh]);

  const onFilesChanged = useCallback(() => { refresh(); setPreviewKey((k) => k + 1); }, [refresh]);

  const saveVersion = async () => {
    const message = window.prompt("Describe this version", "Update");
    if (!message) return;
    try {
      await api.post(`/apps/${id}/commits`, { message });
      toast.success("Version saved");
      refresh();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  if (!app) {
    return <div className="flex h-screen items-center justify-center bg-background"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;
  }
  const pending = Object.keys(changes).length;

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background" data-testid="app-builder">
      <header className="flex items-center gap-3 border-b border-border px-4 py-2.5">
        <button onClick={() => navigate("/apps")} title="All apps" className="rounded-md p-1.5 text-muted-foreground hover:bg-[#171B26] hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <AppWindow className="h-4 w-4 text-primary" />
        <h1 className="truncate text-sm font-semibold" data-testid="app-title">{app.name}</h1>
        {pending > 0 && (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-400" data-testid="unsaved-changes">
            {pending} unsaved change{pending === 1 ? "" : "s"}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={saveVersion} disabled={!pending} data-testid="save-version-button" className="gap-1.5 border-border bg-card">
            <Save className="h-3.5 w-3.5" /> Save version
          </Button>
          <a href={`${API}/apps/${id}/export?auth=${encodeURIComponent(getToken() || "")}`} data-testid="download-app"
            className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-xs font-medium hover:border-primary/50"
            title="Download the code with its full git history">
            <Download className="h-3.5 w-3.5" /> Download
          </a>
          <PublishButton app={app} onChange={(a) => { setApp(a); refresh(); }} />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <BuilderChat app={app} onFilesChanged={onFilesChanged} />
        <section className="flex min-w-0 flex-1 flex-col border-l border-border">
          <nav className="flex items-center gap-1 border-b border-border px-3 py-1.5">
            {[["preview", Eye, "Preview"], ["code", Code2, "Code"], ["terminal", SquareTerminal, "Terminal"], ["history", History, "History"]].map(([t, Icon, label]) => (
              <button key={t} onClick={() => setTab(t)} data-testid={`builder-tab-${t}`}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium ${tab === t ? "bg-[#1D2230] text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                <Icon className="h-3.5 w-3.5" /> {label}
              </button>
            ))}
          </nav>
          <div className="min-h-0 flex-1">
            {tab === "preview" && <PreviewTab appId={id} reloadKey={previewKey} onReload={() => setPreviewKey((k) => k + 1)} />}
            {tab === "code" && <CodeTab appId={id} files={files} changes={changes} onSaved={onFilesChanged} />}
            {tab === "terminal" && <TerminalTab appId={id} />}
            {tab === "history" && <HistoryTab appId={id} commits={commits} pending={pending} onRestored={onFilesChanged} />}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ chat */
function BuilderChat({ app, onFilesChanged }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState("");
  const [steps, setSteps] = useState([]);
  const [model, setModel] = useState(null);
  const [needsKey, setNeedsKey] = useState(false);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);

  const load = useCallback(async () => {
    const { data } = await api.get(`/conversations/${app.conversationId}`);
    setMessages(data.messages);
  }, [app.conversationId]);

  useEffect(() => {
    load().catch(() => {});
    Promise.all([api.get("/models"), api.get("/capabilities")]).then(([m, c]) => {
      const usable = m.data.models.map((x) => x.id).filter((mid) => c.data.agent?.[mid]);
      setModel(usable.includes(m.data.default) ? m.data.default : usable[0] || m.data.default);
      setNeedsKey(usable.length === 0);
    }).catch(() => {});
  }, [load]);

  useEffect(() => {
    requestAnimationFrame(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; });
  }, [messages, text, steps]);

  const send = async () => {
    const content = input.trim();
    if (!content || streaming) return;
    setInput("");
    setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: "user", content }]);
    setStreaming(true);
    setText("");
    setSteps([]);
    let acc = "";
    let current = [];
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamSSE(`${API}/conversations/${app.conversationId}/stream`, { content, model, agent: true }, {
        signal: controller.signal,
        onText: (d) => { acc += d; setText(acc); },
        onEvent: (name, step) => {
          if (name !== "tool" && name !== "tool_result") return;
          current = name === "tool" ? [...current.filter((s) => s.id !== step.id), step] : current.map((s) => (s.id === step.id ? step : s));
          setSteps(current);
          if (name === "tool_result" && FILE_TOOLS.has(step.name)) onFilesChanged();
        },
      });
    } catch (e) {
      if (e.name !== "AbortError") toast.error(e.message);
    } finally {
      setStreaming(false);
      abortRef.current = null;
      await load().catch(() => {});
      setText("");
      setSteps([]);
      onFilesChanged();
    }
  };

  return (
    <aside className="flex w-[400px] shrink-0 flex-col" data-testid="builder-chat">
      <div ref={scrollRef} className="radha-scroll flex-1 space-y-5 overflow-y-auto px-4 py-5">
        {messages.length === 0 && !streaming && (
          <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
            <p className="font-semibold text-foreground">What should we build?</p>
            <p className="mt-1">Describe the app. RADHA writes the code, checks the preview for errors, runs tests and saves versions as it goes.</p>
            {app.description && (
              <button onClick={() => setInput(`Build this app: ${app.description}`)} className="mt-3 text-left text-xs text-[#A5B4FC] hover:underline">
                Start with: “{app.description}”
              </button>
            )}
          </div>
        )}
        {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
        {streaming && <MessageBubble message={{ id: "streaming", role: "assistant", content: text, steps, media: steps.flatMap((s) => s.media || []) }} streaming />}
      </div>
      <div className="border-t border-border p-3">
        {needsKey && <p className="mb-2 text-[11px] text-amber-400">The builder needs an AI provider key on the backend (see .env.example).</p>}
        <div className="rounded-xl border border-[#222738] bg-[#11141D] p-2 focus-within:border-primary/60">
          <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={3} data-testid="builder-input"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Add a dark mode toggle and save todos in the browser…"
            className="radha-scroll w-full resize-none bg-transparent px-2 py-1 text-sm focus:outline-none" />
          <div className="flex justify-end">
            {streaming ? (
              <Button size="icon" variant="secondary" onClick={() => abortRef.current?.abort()} className="h-8 w-8"><Square className="h-3.5 w-3.5" /></Button>
            ) : (
              <Button size="icon" onClick={send} disabled={!input.trim()} data-testid="builder-send" className="h-8 w-8"><Send className="h-3.5 w-3.5" /></Button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

/* --------------------------------------------------------------- preview */
function PreviewTab({ appId, reloadKey, onReload }) {
  const [url, setUrl] = useState(null);
  const [logs, setLogs] = useState([]);
  const frameRef = useRef(null);

  useEffect(() => {
    api.get(`/apps/${appId}/preview-token`).then(({ data }) => setUrl(absoluteUrl(data.url))).catch((e) => toast.error(formatApiError(e)));
  }, [appId]);

  useEffect(() => { setLogs([]); }, [reloadKey]);

  useEffect(() => {
    const onMessage = (e) => {
      if (e.source !== frameRef.current?.contentWindow || e.data?.source !== "radha-preview") return;
      setLogs((l) => [...l.slice(-199), { level: e.data.level, message: String(e.data.message).slice(0, 2000) }]);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  const errors = logs.filter((l) => l.level === "error").length;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3 py-1.5 text-xs text-muted-foreground">
        <button onClick={onReload} title="Reload" data-testid="preview-reload" className="rounded p-1 hover:bg-[#171B26] hover:text-foreground"><RefreshCw className="h-3.5 w-3.5" /></button>
        <span className="truncate font-mono">Live preview (latest files, including unsaved changes)</span>
        {url && <a href={url} target="_blank" rel="noreferrer" className="ml-auto flex items-center gap-1 hover:text-foreground"><ExternalLink className="h-3.5 w-3.5" /> Open</a>}
      </div>
      <div className="min-h-0 flex-1 bg-white">
        {url && (
          <iframe key={reloadKey} ref={frameRef} src={url} title="App preview" data-testid="app-preview-frame"
            sandbox="allow-scripts allow-forms allow-modals allow-popups allow-downloads" className="h-full w-full" />
        )}
      </div>
      <details className="max-h-48 overflow-auto border-t border-border bg-[#0B0D14]" open={errors > 0} data-testid="preview-console">
        <summary className="cursor-pointer px-3 py-1.5 text-xs text-muted-foreground">
          Console {logs.length ? `(${logs.length})` : ""} {errors > 0 && <span className="ml-1 text-destructive">{errors} error{errors === 1 ? "" : "s"}</span>}
        </summary>
        <div className="space-y-0.5 px-3 pb-2 font-mono text-[11px]">
          {logs.map((l, i) => (
            <p key={i} className={l.level === "error" ? "text-destructive" : l.level === "warn" ? "text-amber-400" : "text-muted-foreground"}>{l.message}</p>
          ))}
        </div>
      </details>
    </div>
  );
}

/* ------------------------------------------------------------------ code */
function CodeTab({ appId, files, changes, onSaved }) {
  const [path, setPath] = useState(null);
  const [content, setContent] = useState("");
  const [original, setOriginal] = useState("");
  const [loading, setLoading] = useState(false);

  const open = useCallback(async (p) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/apps/${appId}/files/${p}`);
      setPath(p);
      setContent(data.content);
      setOriginal(data.content);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [appId]);

  useEffect(() => {
    if (!path && files.length) open(files.find((f) => f.path === "index.html")?.path || files[0].path);
  }, [files, path, open]);

  // Pick up edits made by the builder while this file is open (unless the user has local edits).
  useEffect(() => {
    if (path && content === original) open(path);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files]);

  const save = async () => {
    try {
      await api.put(`/apps/${appId}/files/${path}`, { content });
      setOriginal(content);
      toast.success(`Saved ${path}`);
      onSaved();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const newFile = async () => {
    const p = window.prompt("New file path", "src/utils.js");
    if (!p) return;
    try {
      await api.put(`/apps/${appId}/files/${p}`, { content: "" });
      onSaved();
      open(p);
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const removeFile = async () => {
    if (!path || !window.confirm(`Delete ${path}?`)) return;
    try {
      await api.delete(`/apps/${appId}/files/${path}`);
      setPath(null);
      onSaved();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const onKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); save(); }
    if (e.key === "Tab") {
      e.preventDefault();
      const el = e.target;
      const { selectionStart: s, selectionEnd: end } = el;
      setContent(content.slice(0, s) + "  " + content.slice(end));
      requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = s + 2; });
    }
  };

  const dirty = content !== original;
  return (
    <div className="flex h-full">
      <div className="radha-scroll w-56 shrink-0 overflow-y-auto border-r border-border py-2" data-testid="file-tree">
        <div className="flex items-center justify-between px-3 pb-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">Files</span>
          <button onClick={newFile} title="New file" data-testid="new-file" className="text-muted-foreground hover:text-foreground"><FilePlus className="h-3.5 w-3.5" /></button>
        </div>
        {files.map((f) => (
          <button key={f.path} onClick={() => open(f.path)} data-testid={`file-${f.path}`}
            className={`flex w-full items-center gap-1.5 truncate px-3 py-1 text-left font-mono text-xs ${f.path === path ? "bg-[#1D2230] text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
            {changes[f.path] ? <Circle className="h-2 w-2 shrink-0 fill-amber-400 text-amber-400" /> : <span className="w-2" />}
            <span className="truncate">{f.path}</span>
          </button>
        ))}
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-3 py-1.5 text-xs">
          <span className="truncate font-mono text-muted-foreground">{path || "No file"}{dirty ? " •" : ""}</span>
          <div className="ml-auto flex items-center gap-1.5">
            {path && <button onClick={removeFile} title="Delete file" className="rounded p-1 text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>}
            <Button size="sm" onClick={save} disabled={!dirty} data-testid="save-file" className="h-7 gap-1 text-xs"><Save className="h-3 w-3" /> Save</Button>
          </div>
        </div>
        {loading ? <div className="flex flex-1 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div> : (
          <textarea value={content} onChange={(e) => setContent(e.target.value)} onKeyDown={onKeyDown} spellCheck={false}
            data-testid="code-editor" disabled={!path}
            className="radha-scroll flex-1 resize-none bg-[#07080B] p-4 font-mono text-[12.5px] leading-relaxed text-[#E5E7EB] focus:outline-none" />
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- terminal */
function TerminalTab({ appId }) {
  const [command, setCommand] = useState("");
  const [entries, setEntries] = useState([]);
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView(); }, [entries]);

  const run = async (cmd) => {
    const c = (cmd ?? command).trim();
    if (!c || busy) return;
    setBusy(true);
    setCommand("");
    try {
      const { data } = await api.post(`/apps/${appId}/run`, { command: c });
      setEntries((e) => [...e, { command: c, ...data }]);
    } catch (e) {
      setEntries((x) => [...x, { command: c, stderr: formatApiError(e), exitCode: -1 }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-[#07080B] font-mono text-xs" data-testid="terminal">
      <div className="flex flex-wrap gap-1.5 border-b border-border px-3 py-2">
        {["ls -R", "node --test", "python3 -m unittest discover -v", "node --version"].map((c) => (
          <button key={c} onClick={() => run(c)} className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground">
            <Play className="h-3 w-3" /> {c}
          </button>
        ))}
      </div>
      <div className="radha-scroll flex-1 space-y-3 overflow-y-auto p-3">
        {entries.length === 0 && <p className="text-muted-foreground">Commands run in a sandbox copy of the app's files (no network). Changes they make aren't saved.</p>}
        {entries.map((e, i) => (
          <div key={i}>
            <p className="text-[#A5B4FC]">$ {e.command}</p>
            {e.stdout && <pre className="whitespace-pre-wrap text-[#E5E7EB]">{e.stdout}</pre>}
            {e.stderr && <pre className="whitespace-pre-wrap text-rose-300">{e.stderr}</pre>}
            <p className={e.exitCode === 0 ? "text-emerald-400" : "text-rose-400"} data-testid="terminal-exit">
              {e.timedOut ? "timed out" : `exit ${e.exitCode}`}{e.seconds != null ? ` · ${e.seconds}s` : ""}
            </p>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); run(); }} className="flex items-center gap-2 border-t border-border px-3 py-2">
        <span className="text-[#A5B4FC]">$</span>
        <input value={command} onChange={(e) => setCommand(e.target.value)} data-testid="terminal-input" placeholder="node --test"
          className="flex-1 bg-transparent text-foreground focus:outline-none" />
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />}
      </form>
    </div>
  );
}

/* --------------------------------------------------------------- history */
function DiffView({ diffs }) {
  if (!diffs) return <div className="flex h-full items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>;
  if (!diffs.length) return <p className="p-4 text-xs text-muted-foreground">No file changes.</p>;
  return (
    <div className="radha-scroll h-full space-y-4 overflow-y-auto p-4" data-testid="diff-view">
      {diffs.map((d) => (
        <div key={d.path} className="overflow-hidden rounded-lg border border-border">
          <p className="border-b border-border bg-[#11141D] px-3 py-1.5 font-mono text-xs">
            <span className={d.status === "added" ? "text-emerald-400" : d.status === "deleted" ? "text-rose-400" : "text-amber-400"}>{d.status}</span> {d.path}
          </p>
          <pre className="overflow-x-auto bg-[#07080B] p-3 font-mono text-[11px] leading-relaxed">
            {d.diff.split("\n").filter((l) => !l.startsWith("---") && !l.startsWith("+++")).map((l, i) => (
              <div key={i} className={l.startsWith("+") ? "bg-emerald-500/10 text-emerald-300" : l.startsWith("-") ? "bg-rose-500/10 text-rose-300" : l.startsWith("@@") ? "text-[#A5B4FC]" : "text-muted-foreground"}>{l || " "}</div>
            ))}
          </pre>
        </div>
      ))}
    </div>
  );
}

function HistoryTab({ appId, commits, pending, onRestored }) {
  const [selected, setSelected] = useState(pending ? "working" : commits[0]?.id);
  const [diffs, setDiffs] = useState(null);

  useEffect(() => {
    if (!selected) return;
    setDiffs(null);
    api.get(`/apps/${appId}/commits/${selected}/diff`).then(({ data }) => setDiffs(data)).catch((e) => toast.error(formatApiError(e)));
  }, [appId, selected]);

  const restore = async (c) => {
    if (!window.confirm(`Restore “${c.message}”? Your current files are replaced (and saved as a new version, so you can go back).`)) return;
    try {
      await api.post(`/apps/${appId}/commits/${c.id}/restore`);
      toast.success("Version restored");
      onRestored();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  return (
    <div className="flex h-full">
      <div className="radha-scroll w-72 shrink-0 overflow-y-auto border-r border-border" data-testid="commit-list">
        {pending > 0 && (
          <button onClick={() => setSelected("working")} className={`block w-full border-b border-border px-3 py-2.5 text-left ${selected === "working" ? "bg-[#1D2230]" : "hover:bg-[#11141D]"}`}>
            <p className="text-xs font-semibold text-amber-400">Unsaved changes</p>
            <p className="text-[11px] text-muted-foreground">{pending} file{pending === 1 ? "" : "s"}</p>
          </button>
        )}
        {commits.map((c, i) => (
          <div key={c.id} className={`group border-b border-border px-3 py-2.5 ${selected === c.id ? "bg-[#1D2230]" : "hover:bg-[#11141D]"}`} data-testid={`commit-${c.id}`}>
            <button onClick={() => setSelected(c.id)} className="block w-full text-left">
              <p className="line-clamp-2 text-xs font-medium text-foreground">{c.message}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                <span className="font-mono">{c.id.slice(0, 7)}</span> · {c.author} · {new Date(c.createdAt).toLocaleString()}
              </p>
            </button>
            {i > 0 && (
              <button onClick={() => restore(c)} className="mt-1 flex items-center gap-1 text-[11px] text-[#A5B4FC] opacity-0 hover:underline group-hover:opacity-100">
                <RotateCcw className="h-3 w-3" /> Restore this version
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="min-w-0 flex-1"><DiffView diffs={diffs} /></div>
    </div>
  );
}

/* --------------------------------------------------------------- publish */
function PublishButton({ app, onChange }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const url = app.published ? absoluteUrl(app.published.url) : null;

  const publish = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/apps/${app.id}/publish`);
      onChange(data);
      toast.success(app.published ? "Site updated" : "Your app is live");
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const unpublish = async () => {
    try {
      const { data } = await api.delete(`/apps/${app.id}/publish`);
      onChange(data);
      toast.success("Site taken offline");
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  return (
    <div className="relative">
      <Button size="sm" onClick={() => setOpen((o) => !o)} data-testid="publish-menu" className="gap-1.5">
        <Rocket className="h-3.5 w-3.5" /> {app.published ? "Live" : "Publish"}
      </Button>
      {open && (
        <div className="absolute right-0 top-10 z-30 w-80 rounded-xl border border-border bg-card p-4 shadow-2xl" data-testid="publish-panel">
          {app.published ? (
            <>
              <p className="flex items-center gap-1.5 text-sm font-semibold text-emerald-400"><Globe className="h-4 w-4" /> Live on the web</p>
              <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-border bg-background px-2 py-1.5">
                <a href={url} target="_blank" rel="noreferrer" className="truncate font-mono text-[11px] text-[#A5B4FC]" data-testid="published-url">{url}</a>
                <button onClick={() => { navigator.clipboard.writeText(url); toast.success("Link copied"); }} className="ml-auto text-muted-foreground hover:text-foreground"><Copy className="h-3.5 w-3.5" /></button>
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">Visitors see the version published {new Date(app.published.publishedAt).toLocaleString()}. Publish again to ship your latest changes.</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={publish} disabled={busy} data-testid="publish-button" className="flex-1">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Update site"}</Button>
                <Button size="sm" variant="outline" onClick={unpublish} className="border-border">Unpublish</Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold">Publish to the web</p>
              <p className="mt-1 text-[11px] text-muted-foreground">Saves your current files as a version and serves it at a public link anyone can open.</p>
              <Button size="sm" onClick={publish} disabled={busy} data-testid="publish-button" className="mt-3 w-full">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Publish"}</Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
