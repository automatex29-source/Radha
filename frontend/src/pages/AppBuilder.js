import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api, API, absoluteUrl, formatApiError, getToken } from "@/lib/api";
import ThemeToggle from "@/components/ThemeToggle";
import { streamSSE } from "@/lib/sse";
import MessageBubble from "@/components/MessageBubble";
import GitHubPushButton from "@/components/GitHubPushButton";
import DataTab from "@/components/DataTab";
import DevicePreview from "@/components/DevicePreview";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  ArrowLeft, Loader2, Send, Square, RefreshCw, ExternalLink, Code2, Eye, SquareTerminal, History, Rocket,
  Download, Save, FilePlus, Trash2, RotateCcw, Globe, Copy, Play, Circle, AppWindow, MessageSquare, Database,
  Paperclip, X, Wand2, ImagePlus, MousePointerClick, Monitor, Tablet, Smartphone, Sparkles, Undo2, GitCompare,
} from "lucide-react";

const FILE_TOOLS = new Set(["write_file", "append_file", "edit_file", "delete_file", "commit", "start_template"]);
const SCREENSHOT_ASK = "Build this design as a working app. Match its layout, colours, fonts, spacing and content as closely as you can, and make every button work.";

const PANES = [["preview", Eye, "Preview"], ["code", Code2, "Code"], ["terminal", SquareTerminal, "Terminal"], ["history", History, "History"], ["data", Database, "Data"]];

export default function AppBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [app, setApp] = useState(null);
  const [files, setFiles] = useState([]);
  const [changes, setChanges] = useState({});
  const [commits, setCommits] = useState([]);
  // Phones show one pane at a time, starting with the chat.
  const [tab, setTab] = useState(() => (window.matchMedia?.("(max-width: 767px)").matches ? "chat" : "preview"));
  const [previewKey, setPreviewKey] = useState(0);
  // Auto-fix: after a build the user asked for, errors in the preview are sent back to Krish once, without a tap.
  const [autoArmed, setAutoArmed] = useState(false);
  const [historyFocus, setHistoryFocus] = useState(null);
  // A new app arrives with the user's request from the Apps page: the builder starts on it at once.
  const [fixAsk, setFixAsk] = useState(() => (location.state?.prompt ? { content: location.state.prompt, at: Date.now() } : null));
  useEffect(() => {
    if (location.state?.prompt) navigate(location.pathname, { replace: true, state: null });
  }, [location, navigate]);
  const [previewUrl, setPreviewUrl] = useState(null);

  useEffect(() => {
    api.get(`/apps/${id}/preview-token`).then(({ data }) => setPreviewUrl(absoluteUrl(data.url))).catch((e) => toast.error(formatApiError(e)));
  }, [id]);

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
    return <div className="flex h-dvh items-center justify-center bg-background"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;
  }
  const pending = Object.keys(changes).length;

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden bg-background" data-testid="app-builder">
      <header className="flex items-center gap-2 border-b border-border px-2 py-2 sm:gap-3 sm:px-4 sm:py-2.5">
        <button onClick={() => navigate("/apps")} title="All apps" className="rounded-md p-2 text-muted-foreground hover:bg-surface hover:text-foreground sm:p-1.5">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <AppWindow className="h-4 w-4 shrink-0 text-primary max-sm:hidden" />
        <h1 className="truncate text-sm font-semibold" data-testid="app-title">{app.name}</h1>
        {pending > 0 && (
          <span className="shrink-0 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] max-sm:hidden text-amber-600 dark:text-amber-400" data-testid="unsaved-changes">
            {pending} unsaved change{pending === 1 ? "" : "s"}
          </span>
        )}
        <div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2">
          <ThemeToggle className="h-8 w-8 rounded-md max-sm:hidden" />
          <Button variant="outline" size="sm" onClick={saveVersion} disabled={!pending} data-testid="save-version-button" className="gap-1.5 border-border bg-card">
            <Save className="h-3.5 w-3.5" /><span className="max-sm:hidden">Save version</span>{pending > 0 && <span className="sm:hidden">{pending}</span>}
          </Button>
          <a href={`${API}/apps/${id}/export?auth=${encodeURIComponent(getToken() || "")}`} data-testid="download-app"
            className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-xs font-medium hover:border-primary/50"
            title="Download the code with its full git history">
            <Download className="h-3.5 w-3.5" /><span className="max-sm:hidden">Download</span>
          </a>
          <GitHubPushButton app={app} onPushed={refresh} />
          <PublishButton app={app} onChange={(a) => { setApp(a); refresh(); }} />
        </div>
      </header>

      {/* Phones: one row of tabs, chat included */}
      <nav className="flex items-center border-b border-border md:hidden" data-testid="builder-phone-tabs">
        {[["chat", MessageSquare, "Chat"], ...PANES].map(([t, Icon, label]) => (
          <button key={t} onClick={() => setTab(t)} data-testid={`builder-phone-tab-${t}`}
            className={`flex flex-1 flex-col items-center gap-0.5 border-b-2 py-2 text-[11px] font-medium ${tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground"}`}>
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </nav>
      <div className="flex min-h-0 flex-1">
        <BuilderChat app={app} appId={id} onFilesChanged={onFilesChanged} hiddenOnPhone={tab !== "chat"} ask={fixAsk}
          previewUrl={previewUrl} previewKey={previewKey} onShowPreview={() => setTab("preview")}
          onTurnDone={(auto) => setAutoArmed(!auto)} onBuildStart={() => setAutoArmed(false)}
          onShowChanges={(commitId) => { setHistoryFocus({ id: commitId, at: Date.now() }); setTab("history"); }} />
        <section className={`flex min-w-0 flex-1 flex-col border-l border-border max-md:border-l-0 ${tab === "chat" ? "max-md:hidden" : ""}`}>
          <nav className="flex items-center gap-1 border-b border-border px-3 py-1.5 max-md:hidden">
            {PANES.map(([t, Icon, label]) => (
              <button key={t} onClick={() => setTab(t)} data-testid={`builder-tab-${t}`}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium ${tab === t || (t === "preview" && tab === "chat") ? "bg-surface-strong text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                <Icon className="h-3.5 w-3.5" /> {label}
              </button>
            ))}
          </nav>
          <div className="min-h-0 flex-1">
            {(tab === "preview" || tab === "chat") && <PreviewTab url={previewUrl} reloadKey={previewKey} onReload={() => setPreviewKey((k) => k + 1)}
              appId={id} onChanged={onFilesChanged} autoFix={autoArmed}
              onAutoFix={(content) => { setAutoArmed(false); setFixAsk({ content, at: Date.now(), auto: true }); }}
              onFix={(content) => { setFixAsk({ content, at: Date.now() }); if (window.matchMedia?.("(max-width: 767px)").matches) setTab("chat"); }} />}
            {tab === "code" && <CodeTab appId={id} files={files} changes={changes} onSaved={onFilesChanged} />}
            {tab === "terminal" && <TerminalTab appId={id} />}
            {tab === "data" && <DataTab appId={id} />}
            {tab === "history" && <HistoryTab appId={id} commits={commits} pending={pending} onRestored={onFilesChanged} focus={historyFocus} />}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ chat */
function BuilderChat({ app, appId, onFilesChanged, hiddenOnPhone, ask, previewUrl, previewKey, onShowPreview, onTurnDone, onBuildStart, onShowChanges }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState("");
  const [steps, setSteps] = useState([]);
  const [model, setModel] = useState(null);
  const [needsKey, setNeedsKey] = useState(false);
  const [attached, setAttached] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [draft, setDraft] = useState(null); // the file being typed right now: {key, path, text}
  const [images, setImages] = useState([]); // screenshots to build from
  const [boosting, setBoosting] = useState(false);
  const [ideas, setIdeas] = useState([]);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  const fileRef = useRef(null);
  const imageRef = useRef(null);
  const askedRef = useRef(null);

  // A screenshot or design to copy: sent with the next message, and Krish builds that design.
  const attachImage = async (e) => {
    const picked = Array.from(e.target.files || []).filter((f) => f.type.startsWith("image/"));
    e.target.value = "";
    if (!picked.length) return;
    setUploading(true);
    for (const file of picked) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("conversationId", app.conversationId);
      try {
        const { data } = await api.post("/media", fd, { headers: { "Content-Type": "multipart/form-data" } });
        setImages((list) => [...list, { id: data.id, url: URL.createObjectURL(file), name: file.name }]);
      } catch (err) {
        toast.error(formatApiError(err));
      }
    }
    setUploading(false);
  };

  // "Improve prompt": a short idea becomes a detailed brief the user can still edit before sending.
  const boost = async () => {
    if (!input.trim() || boosting) return;
    setBoosting(true);
    try {
      const { data } = await api.post("/apps/boost", { text: input });
      setInput(data.text);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBoosting(false);
    }
  };

  // A sample file (a log, an export) or a logo goes into the app too (samples/, assets/), so Krish reads all of it.
  const attach = async (e) => {
    const picked = Array.from(e.target.files || []);
    e.target.value = "";
    if (!picked.length) return;
    setUploading(true);
    for (const file of picked) {
      const fd = new FormData();
      fd.append("file", file);
      try {
        const { data } = await api.post(`/conversations/${app.conversationId}/files`, fd, { headers: { "Content-Type": "multipart/form-data" } });
        setAttached((a) => [...a, data]);
      } catch (err) {
        toast.error(formatApiError(err?.response?.data?.detail) || `Couldn't attach ${file.name}`);
      }
    }
    setUploading(false);
    onFilesChanged();
  };

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

  // `typed` is a message from outside the text box (the preview's "Fix errors" button).
  // Undo one AI step: the app goes back to the version saved just before it (itself kept as a version).
  const undo = async (m) => {
    if (!window.confirm("Undo this change? The app goes back to how it was before it (you can redo it from History).")) return;
    try {
      await api.post(`/apps/${appId}/commits/${m.versions.before}/restore`);
      toast.success("Change undone");
      onFilesChanged();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const send = async (typed, auto = false) => {
    const sending = typeof typed === "string" ? [] : images;
    const content = (typeof typed === "string" ? typed : input).trim() || (sending.length ? SCREENSHOT_ASK : "");
    if (!content || streaming) return;
    if (typeof typed !== "string") { setInput(""); setImages([]); }
    setAttached([]);
    setIdeas([]);
    setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: "user", content, images: sending.map((i) => i.id) }]);
    setStreaming(true);
    onBuildStart?.();
    setText("");
    setSteps([]);
    setDraft(null);
    let acc = "";
    let current = [];
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamSSE(`${API}/conversations/${app.conversationId}/stream`, { content, model, agent: true, images: sending.map((i) => i.id) }, {
        signal: controller.signal,
        onText: (d) => { acc += d; setText(acc); },
        onEvent: (name, step) => {
          if (name === "code_draft") {
            setDraft((d) => (d && d.key === step.key && !step.reset
              ? { ...d, text: d.text + step.text }
              : { key: step.key, path: step.path, text: step.text }));
            return;
          }
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
      // After Stop the server is still saving the part already written; give it a moment.
      if (controller.signal.aborted) await new Promise((r) => setTimeout(r, 800));
      await load().catch(() => {});
      setText("");
      setSteps([]);
      setDraft(null);
      onFilesChanged();
      onTurnDone?.(auto);
    }
  };

  // The latest reply that changed the app gets live laptop and phone previews under it.
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const lastBuild = lastAssistant?.steps?.some((s) => FILE_TOOLS.has(s.name) && s.status === "done") ? lastAssistant.id : null;

  // Next steps to offer under the latest build (what the app doesn't have yet).
  useEffect(() => {
    if (streaming || !lastBuild) { setIdeas([]); return; }
    api.get(`/apps/${appId}/ideas`).then(({ data }) => setIdeas(data.ideas || [])).catch(() => setIdeas([]));
  }, [appId, lastBuild, streaming]);

  // An ask from outside the box (Fix errors, click-to-edit, a new app's request), once the model is known.
  useEffect(() => {
    if (!ask || !model || askedRef.current === ask.at) return;
    askedRef.current = ask.at;
    send(ask.content, !!ask.auto);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ask, model]);

  return (
    <aside className={`flex w-[400px] shrink-0 flex-col max-md:w-full ${hiddenOnPhone ? "max-md:hidden" : ""}`} data-testid="builder-chat">
      <div ref={scrollRef} className="radha-scroll flex-1 space-y-5 overflow-y-auto px-4 py-5">
        {messages.length === 0 && !streaming && (
          <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
            <p className="font-semibold text-foreground">What should we build?</p>
            <p className="mt-1">Describe the app. Krish AI writes the code, checks the preview for errors, runs tests and saves versions as it goes.</p>
            {app.description && !ask && (
              <button onClick={() => setInput(`Build this app: ${app.description}`)} className="mt-3 block text-left text-xs text-brand hover:underline">
                Start with: “{app.description}”
              </button>
            )}
            <button onClick={() => imageRef.current?.click()} data-testid="builder-from-screenshot"
              className="mt-3 flex items-center gap-1.5 text-left text-xs text-brand hover:underline">
              <ImagePlus className="h-3.5 w-3.5" /> Or start from a screenshot of a design you like
            </button>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id}>
            <MessageBubble message={m} codeProject={false} compactSteps />
            {!streaming && m.role === "assistant" && m.versions?.after && (
              <div className="mt-1.5 flex gap-1 md:ml-11" data-testid="builder-step-actions">
                <button onClick={() => onShowChanges?.(m.versions.after)} data-testid="builder-see-changes"
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:bg-surface hover:text-foreground">
                  <GitCompare className="h-3 w-3" /> See changes
                </button>
                <button onClick={() => undo(m)} data-testid="builder-undo"
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:bg-surface hover:text-foreground">
                  <Undo2 className="h-3 w-3" /> Undo
                </button>
              </div>
            )}
            {!streaming && m.id === lastBuild && previewUrl && (
              <DevicePreview url={previewUrl} reloadKey={previewKey} onOpen={onShowPreview} className="mt-2 md:ml-11" />
            )}
            {!streaming && m.id === lastBuild && ideas.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5 md:ml-11" data-testid="builder-ideas">
                {ideas.map((i) => (
                  <button key={i.label} onClick={() => send(i.prompt)} title={i.prompt} data-testid={`builder-idea-${i.label}`}
                    className="flex items-center gap-1 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground">
                    <Sparkles className="h-3 w-3 text-primary" /> {i.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {streaming && <MessageBubble message={{ id: "streaming", role: "assistant", content: text, steps, media: steps.flatMap((s) => s.media || []) }} streaming codeProject={false} compactSteps />}
        {streaming && draft && <LiveCode draft={draft} />}
      </div>
      <div className="border-t border-border p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        {needsKey && <p className="mb-2 text-[11px] text-amber-600 dark:text-amber-400">The builder needs an AI provider key on the backend (see .env.example).</p>}
        <div className="rounded-xl border border-border bg-card p-2 focus-within:border-primary/60">
          <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={3} data-testid="builder-input"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !window.matchMedia?.("(pointer: coarse)").matches) { e.preventDefault(); send(); } }}
            placeholder="Add a dark mode toggle and save todos in the browser…"
            className="radha-scroll w-full resize-none bg-transparent px-2 py-1 text-sm focus:outline-none" />
          {images.length > 0 && (
            <div className="flex flex-wrap gap-2 px-1 pb-1.5" data-testid="builder-images">
              {images.map((img) => (
                <span key={img.id} className="relative">
                  <img src={img.url} alt={img.name} className="h-14 w-20 rounded-md border border-border object-cover" />
                  <button onClick={() => setImages((l) => l.filter((x) => x.id !== img.id))} aria-label="Remove picture"
                    className="absolute -right-1.5 -top-1.5 rounded-full bg-foreground p-0.5 text-background"><X className="h-3 w-3" /></button>
                </span>
              ))}
              <span className="self-center text-[11px] text-muted-foreground">Krish builds this design</span>
            </div>
          )}
          {attached.length > 0 && (
            <div className="flex flex-wrap gap-1.5 px-1 pb-1.5" data-testid="builder-attachments">
              {attached.map((f) => (
                <span key={f.id} className="inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-muted px-2 py-0.5 text-[11px]">
                  <Paperclip className="h-3 w-3 shrink-0" /><span className="truncate">{f.filename}</span>
                  <button onClick={() => setAttached((a) => a.filter((x) => x.id !== f.id))} aria-label="Hide" className="text-muted-foreground hover:text-foreground"><X className="h-3 w-3" /></button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-0.5">
            <input ref={fileRef} type="file" multiple hidden onChange={attach} data-testid="builder-file-input" />
            <input ref={imageRef} type="file" accept="image/*" hidden onChange={attachImage} data-testid="builder-image-input" />
            <Button size="icon" variant="ghost" onClick={() => fileRef.current?.click()} disabled={uploading}
              title="Attach a sample file or your logo" aria-label="Attach a sample file or your logo" data-testid="builder-attach" className="h-10 w-10 sm:h-8 sm:w-8">
              {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Paperclip className="h-3.5 w-3.5" />}
            </Button>
            <Button size="icon" variant="ghost" onClick={() => imageRef.current?.click()} disabled={uploading}
              title="Build from a screenshot" aria-label="Build from a screenshot" data-testid="builder-screenshot" className="h-10 w-10 sm:h-8 sm:w-8">
              <ImagePlus className="h-3.5 w-3.5" />
            </Button>
            <Button size="icon" variant="ghost" onClick={boost} disabled={!input.trim() || boosting || streaming}
              title="Improve my prompt" aria-label="Improve my prompt" data-testid="builder-boost" className="h-10 w-10 sm:h-8 sm:w-8">
              {boosting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
            </Button>
            <span className="flex-1" />
            {streaming ? (
              <Button size="icon" onClick={() => abortRef.current?.abort()} title="Stop" aria-label="Stop the reply" data-testid="builder-stop"
                className="h-10 w-10 rounded-full bg-foreground text-background hover:bg-foreground/90 sm:h-8 sm:w-8"><Square className="h-3 w-3 fill-current" /></Button>
            ) : (
              <Button size="icon" onClick={send} onMouseDown={(e) => e.preventDefault()} disabled={!input.trim() && !images.length} data-testid="builder-send" className="h-10 w-10 sm:h-8 sm:w-8"><Send className="h-3.5 w-3.5" /></Button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

/* ------------------------------------------------------------ live code */
// The file Krish is typing right now, shown as it streams in, so a build never looks stuck.
function LiveCode({ draft }) {
  const ref = useRef(null);
  const lines = draft.text.split("\n");
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [draft.text]);
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-sunken md:ml-11" data-testid="live-code">
      <div className="flex items-center gap-2 border-b border-border px-3 py-1.5 text-[11px] text-muted-foreground">
        <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-primary" /></span>
        Writing <span className="font-mono text-foreground">{draft.path}</span>
        <span className="ml-auto font-mono">{lines.length} lines</span>
      </div>
      <pre ref={ref} className="radha-scroll max-h-56 overflow-auto px-3 py-2 font-mono text-[11px] leading-relaxed text-foreground/90">
        {lines.slice(-200).join("\n")}<span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-primary align-middle" />
      </pre>
    </div>
  );
}

/* --------------------------------------------------------------- preview */
const DEVICES = [["full", Monitor, "Laptop", null], ["tablet", Tablet, "Tablet", 820], ["phone", Smartphone, "Phone", 390]];

// rgb(12, 34, 56) -> #0c2238, for the colour pickers ("" for transparent).
function toHex(rgb) {
  const m = String(rgb || "").match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/);
  if (!m || (m[4] !== undefined && Number(m[4]) === 0)) return "";
  return "#" + [m[1], m[2], m[3]].map((n) => Number(n).toString(16).padStart(2, "0")).join("");
}

function PreviewTab({ url, reloadKey, onReload, onFix, appId, onChanged, autoFix, onAutoFix }) {
  const [logs, setLogs] = useState([]);
  const [device, setDevice] = useState("full");
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState(null);
  const [change, setChange] = useState("");
  const [mode, setMode] = useState("ai"); // "ai": describe the change; "now": edit text and colours directly
  const [edit, setEdit] = useState({ text: "", color: "", bg: "" });
  const [saving, setSaving] = useState(false);
  const frameRef = useRef(null);

  useEffect(() => { setLogs([]); setPicking(false); }, [reloadKey]);

  useEffect(() => {
    const onMessage = (e) => {
      if (e.source !== frameRef.current?.contentWindow || e.data?.source !== "radha-preview") return;
      if (e.data.kind === "pick") {
        setPicking(false);
        const p = { selector: String(e.data.selector || "").slice(0, 300), html: String(e.data.html || "").slice(0, 800), text: String(e.data.text || "").slice(0, 160),
          raw: String(e.data.raw || "").slice(0, 500), tag: String(e.data.tag || ""), leaf: !!e.data.leaf, color: toHex(e.data.color), bg: toHex(e.data.bg) };
        setPicked(p);
        setEdit({ text: p.leaf ? p.raw : "", color: p.color, bg: p.bg });
        setChange("");
        return;
      }
      if (e.data.kind === "pick-cancel") { setPicking(false); return; }
      setLogs((l) => [...l.slice(-199), { level: e.data.level, message: String(e.data.message).slice(0, 2000) }]);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  // Click to edit: the page outlines what's under the pointer, and a click picks it instead of pressing it.
  const togglePick = () => {
    const next = !picking;
    setPicking(next);
    setPicked(null);
    frameRef.current?.contentWindow?.postMessage({ source: "radha-builder", pick: next }, "*");
  };
  const sendChange = (e) => {
    e.preventDefault();
    if (!picked || !change.trim()) return;
    onFix(`Change only this part of the app: ${change.trim()}\n\nThe part (CSS path: ${picked.selector}):\n${picked.html}\n\nFind it in the files and change just that with edit_file. Leave everything else exactly as it is.`);
    setPicked(null);
  };
  // Edit now: words are changed where they are written in the code, colours go into the page's own style block.
  // No AI, so it is instant; text written in more than one place goes to Krish instead.
  const saveNow = async (e) => {
    e.preventDefault();
    if (!picked || saving) return;
    const textChanged = picked.leaf && edit.text.trim() && edit.text.trim() !== picked.raw;
    const styles = {};
    if (edit.color && edit.color !== picked.color) styles.color = edit.color;
    if (edit.bg && edit.bg !== picked.bg) styles.background = edit.bg;
    if (!textChanged && !Object.keys(styles).length) { setPicked(null); return; }
    setSaving(true);
    try {
      if (textChanged) {
        try {
          await api.post(`/apps/${appId}/quick-edit`, { kind: "text", old: picked.raw, new: edit.text });
        } catch (err) {
          if (err?.response?.status !== 409) throw err;
          onFix(`Change the text "${picked.raw}" to "${edit.text.trim()}" (CSS path: ${picked.selector}). Change only that.`);
        }
      }
      if (Object.keys(styles).length) await api.post(`/apps/${appId}/quick-edit`, { kind: "style", selector: picked.selector, styles });
      setPicked(null);
      onChanged?.();
      toast.success("Saved");
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSaving(false);
    }
  };
  const width = DEVICES.find((d) => d[0] === device)[3];

  const errors = logs.filter((l) => l.level === "error").length;

  // Auto-fix: once the page has settled after a build, any errors go straight back to Krish (once per build).
  const autoFixRef = useRef(onAutoFix);
  autoFixRef.current = onAutoFix;
  useEffect(() => {
    if (!autoFix || !errors || !autoFixRef.current) return;
    const t = setTimeout(() => {
      const found = [...new Set(logs.filter((l) => l.level === "error").map((l) => l.message.slice(0, 500)))].slice(0, 5);
      autoFixRef.current(`Auto-fix: the preview shows ${found.length === 1 ? "this error" : "these errors"} after your last change. Find the cause in the code and fix it:\n${found.join("\n")}`);
    }, 2500);
    return () => clearTimeout(t);
  }, [autoFix, errors, logs]);
  const fixErrors = (e) => {
    e.preventDefault();
    const found = [...new Set(logs.filter((l) => l.level === "error").map((l) => l.message.slice(0, 500)))].slice(0, 5);
    onFix(`The preview shows ${found.length === 1 ? "this error" : "these errors"}. Find the cause in the code and fix it:\n${found.join("\n")}`);
  };
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3 py-1.5 text-xs text-muted-foreground">
        <button onClick={onReload} title="Reload" data-testid="preview-reload" className="rounded p-1 hover:bg-surface hover:text-foreground"><RefreshCw className="h-3.5 w-3.5" /></button>
        <div className="flex items-center rounded-md border border-border p-0.5" role="group" aria-label="Screen size" data-testid="preview-devices">
          {DEVICES.map(([d, Icon, label]) => (
            <button key={d} onClick={() => setDevice(d)} title={label} aria-label={label} aria-pressed={device === d} data-testid={`preview-device-${d}`}
              className={`rounded p-1 ${device === d ? "bg-surface-strong text-foreground" : "hover:text-foreground"}`}><Icon className="h-3.5 w-3.5" /></button>
          ))}
        </div>
        {onFix && (
          <button onClick={togglePick} data-testid="preview-pick" title="Click something in the preview to change it"
            className={`flex items-center gap-1 rounded-md px-2 py-1 font-medium ${picking ? "bg-primary text-primary-foreground" : "hover:bg-surface hover:text-foreground"}`}>
            <MousePointerClick className="h-3.5 w-3.5" /> <span className="max-sm:hidden">{picking ? "Click a part…" : "Edit a part"}</span>
          </button>
        )}
        <span className="truncate font-mono max-lg:hidden">Live preview</span>
        {url && <a href={url} target="_blank" rel="noreferrer" className="ml-auto flex items-center gap-1 hover:text-foreground"><ExternalLink className="h-3.5 w-3.5" /> Open</a>}
      </div>
      {picked && (
        <div className="border-b border-border bg-primary/5 px-3 py-2" data-testid="preview-picked">
          <div className="flex items-center gap-2">
            <span className="max-w-[45%] shrink-0 truncate rounded bg-primary/15 px-1.5 py-0.5 font-mono text-[11px] text-primary" title={picked.selector}>
              {picked.tag}{picked.text ? ` “${picked.text.slice(0, 30)}”` : ""}
            </span>
            <div className="flex rounded-md border border-border p-0.5 text-[11px]" role="group">
              {[["ai", "Ask Krish"], ["now", "Edit now"]].map(([m, label]) => (
                <button key={m} type="button" onClick={() => setMode(m)} data-testid={`preview-mode-${m}`}
                  className={`rounded px-2 py-0.5 ${mode === m ? "bg-surface-strong text-foreground" : "hover:text-foreground"}`}>{label}</button>
              ))}
            </div>
            <button type="button" onClick={() => setPicked(null)} aria-label="Cancel" className="ml-auto text-muted-foreground hover:text-foreground"><X className="h-3.5 w-3.5" /></button>
          </div>
          {mode === "ai" ? (
            <form onSubmit={sendChange} className="mt-2 flex items-center gap-2">
              <input autoFocus value={change} onChange={(e) => setChange(e.target.value)} data-testid="preview-picked-input"
                placeholder="What should change? e.g. make it red and bigger"
                className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs focus:outline-none" />
              <Button size="sm" type="submit" disabled={!change.trim()} className="h-7 px-2.5 text-xs">Change</Button>
            </form>
          ) : (
            <form onSubmit={saveNow} className="mt-2 flex flex-wrap items-center gap-2" data-testid="preview-edit-now">
              {picked.leaf && picked.raw && (
                <input autoFocus value={edit.text} onChange={(e) => setEdit((x) => ({ ...x, text: e.target.value }))} data-testid="preview-edit-text"
                  className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs focus:outline-none" />
              )}
              <label className="flex items-center gap-1 text-[11px] text-muted-foreground">Text
                <input type="color" value={edit.color || "#000000"} onChange={(e) => setEdit((x) => ({ ...x, color: e.target.value }))} data-testid="preview-edit-color"
                  className="h-6 w-7 cursor-pointer rounded border border-border bg-transparent" />
              </label>
              <label className="flex items-center gap-1 text-[11px] text-muted-foreground">Fill
                <input type="color" value={edit.bg || "#ffffff"} onChange={(e) => setEdit((x) => ({ ...x, bg: e.target.value }))} data-testid="preview-edit-bg"
                  className="h-6 w-7 cursor-pointer rounded border border-border bg-transparent" />
              </label>
              <Button size="sm" type="submit" disabled={saving} className="h-7 px-2.5 text-xs" data-testid="preview-edit-save">
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
              </Button>
            </form>
          )}
        </div>
      )}
      <div className={`min-h-0 flex-1 ${width ? "flex justify-center overflow-auto bg-sunken p-3" : "bg-white"}`}>
        {url && (
          <iframe key={reloadKey} ref={frameRef} src={url} title="App preview" data-testid="app-preview-frame"
            onLoad={() => { if (picking) frameRef.current?.contentWindow?.postMessage({ source: "radha-builder", pick: true }, "*"); }}
            sandbox="allow-scripts allow-forms allow-modals allow-popups allow-downloads"
            style={width ? { width, maxWidth: "100%" } : undefined}
            className={width ? "h-full shrink-0 rounded-xl border border-border bg-white shadow-lg" : "h-full w-full"} />
        )}
      </div>
      <details className="max-h-48 overflow-auto border-t border-border bg-sunken" open={errors > 0} data-testid="preview-console">
        <summary className="cursor-pointer px-3 py-1.5 text-xs text-muted-foreground">
          Console {logs.length ? `(${logs.length})` : ""} {errors > 0 && <span className="ml-1 text-destructive">{errors} error{errors === 1 ? "" : "s"}</span>}
          {errors > 0 && onFix && (
            <button onClick={fixErrors} data-testid="preview-fix-errors"
              className="ml-3 rounded-md bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground hover:opacity-90">
              Fix errors with AI
            </button>
          )}
        </summary>
        <div className="space-y-0.5 px-3 pb-2 font-mono text-[11px]">
          {logs.map((l, i) => (
            <p key={i} className={l.level === "error" ? "text-destructive" : l.level === "warn" ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"}>{l.message}</p>
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
            className={`flex w-full items-center gap-1.5 truncate px-3 py-1 text-left font-mono text-xs ${f.path === path ? "bg-surface-strong text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
            {changes[f.path] ? <Circle className="h-2 w-2 shrink-0 fill-amber-400 text-amber-600 dark:text-amber-400" /> : <span className="w-2" />}
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
            className="radha-scroll flex-1 resize-none bg-background p-4 font-mono text-[12.5px] leading-relaxed text-foreground/90 focus:outline-none" />
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
    <div className="flex h-full flex-col bg-background font-mono text-xs" data-testid="terminal">
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
            <p className="text-brand">$ {e.command}</p>
            {e.stdout && <pre className="whitespace-pre-wrap text-foreground/90">{e.stdout}</pre>}
            {e.stderr && <pre className="whitespace-pre-wrap text-rose-700 dark:text-rose-300">{e.stderr}</pre>}
            <p className={e.exitCode === 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"} data-testid="terminal-exit">
              {e.timedOut ? "timed out" : `exit ${e.exitCode}`}{e.seconds != null ? ` · ${e.seconds}s` : ""}
            </p>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); run(); }} className="flex items-center gap-2 border-t border-border px-3 py-2">
        <span className="text-brand">$</span>
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
          <p className="border-b border-border bg-card px-3 py-1.5 font-mono text-xs">
            <span className={d.status === "added" ? "text-emerald-600 dark:text-emerald-400" : d.status === "deleted" ? "text-rose-600 dark:text-rose-400" : "text-amber-600 dark:text-amber-400"}>{d.status}</span> {d.path}
          </p>
          <pre className="overflow-x-auto bg-background p-3 font-mono text-[11px] leading-relaxed">
            {d.diff.split("\n").filter((l) => !l.startsWith("---") && !l.startsWith("+++")).map((l, i) => (
              <div key={i} className={l.startsWith("+") ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : l.startsWith("-") ? "bg-rose-500/10 text-rose-700 dark:text-rose-300" : l.startsWith("@@") ? "text-brand" : "text-muted-foreground"}>{l || " "}</div>
            ))}
          </pre>
        </div>
      ))}
    </div>
  );
}

function HistoryTab({ appId, commits, pending, onRestored, focus }) {
  const [selected, setSelected] = useState(focus?.id || (pending ? "working" : commits[0]?.id));
  useEffect(() => { if (focus?.id) setSelected(focus.id); }, [focus]);
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
          <button onClick={() => setSelected("working")} className={`block w-full border-b border-border px-3 py-2.5 text-left ${selected === "working" ? "bg-surface-strong" : "hover:bg-card"}`}>
            <p className="text-xs font-semibold text-amber-600 dark:text-amber-400">Unsaved changes</p>
            <p className="text-[11px] text-muted-foreground">{pending} file{pending === 1 ? "" : "s"}</p>
          </button>
        )}
        {commits.map((c, i) => (
          <div key={c.id} className={`group border-b border-border px-3 py-2.5 ${selected === c.id ? "bg-surface-strong" : "hover:bg-card"}`} data-testid={`commit-${c.id}`}>
            <button onClick={() => setSelected(c.id)} className="block w-full text-left">
              <p className="line-clamp-2 text-xs font-medium text-foreground">{c.message}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                <span className="font-mono">{c.id.slice(0, 7)}</span> · {c.author} · {new Date(c.createdAt).toLocaleString()}
              </p>
            </button>
            {i > 0 && (
              <button onClick={() => restore(c)} className="mt-1 flex items-center gap-1 text-[11px] text-brand opacity-0 hover:underline group-hover:opacity-100">
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
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [canPublish, setCanPublish] = useState(true);
  const [domain, setDomain] = useState(app.domain || "");
  const [savingDomain, setSavingDomain] = useState(false);
  const url = app.published ? absoluteUrl(app.published.url) : null;

  // A custom domain: the owner points a CNAME at this server, and the site answers there too.
  const saveDomain = async (e) => {
    e.preventDefault();
    setSavingDomain(true);
    try {
      const { data } = await api.put(`/apps/${app.id}/domain`, { domain });
      onChange(data.app);
      setDomain(data.app.domain || "");
      toast.success(data.app.domain ? "Domain saved. Now add the DNS record below." : "Domain removed");
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSavingDomain(false);
    }
  };

  useEffect(() => {
    if (open) api.get("/usage").then(({ data }) => setCanPublish(data.canPublish !== false)).catch(() => {});
  }, [open]);

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
        <div className="absolute right-0 top-10 z-30 w-80 max-w-[calc(100vw-1rem)] rounded-xl border border-border bg-card p-4 shadow-2xl" data-testid="publish-panel">
          {app.published ? (
            <>
              <p className="flex items-center gap-1.5 text-sm font-semibold text-emerald-600 dark:text-emerald-400"><Globe className="h-4 w-4" /> Live on the web</p>
              <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-border bg-background px-2 py-1.5">
                <a href={url} target="_blank" rel="noreferrer" className="truncate font-mono text-[11px] text-brand" data-testid="published-url">{url}</a>
                <button onClick={() => { navigator.clipboard.writeText(url); toast.success("Link copied"); }} className="ml-auto text-muted-foreground hover:text-foreground"><Copy className="h-3.5 w-3.5" /></button>
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">Visitors see the version published {new Date(app.published.publishedAt).toLocaleString()}. Publish again to ship your latest changes.</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={publish} disabled={busy} data-testid="publish-button" className="flex-1">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Update site"}</Button>
                <Button size="sm" variant="outline" onClick={unpublish} className="border-border">Unpublish</Button>
              </div>
              <form onSubmit={saveDomain} className="mt-4 border-t border-border pt-3" data-testid="custom-domain">
                <p className="text-xs font-semibold">Your own domain</p>
                <div className="mt-1.5 flex gap-1.5">
                  <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="shop.yourname.com" data-testid="custom-domain-input"
                    className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 font-mono text-[11px] focus:outline-none focus:border-primary/60" />
                  <Button size="sm" type="submit" variant="outline" disabled={savingDomain || domain.trim() === (app.domain || "")} className="h-7 border-border px-2.5 text-xs">
                    {savingDomain ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
                  </Button>
                </div>
                {app.domain && (
                  <p className="mt-2 text-[11px] text-muted-foreground" data-testid="custom-domain-steps">
                    At your domain provider, add a <b>CNAME</b> record for <span className="font-mono">{app.domain}</span> pointing to{" "}
                    <span className="font-mono">{window.location.host}</span>. Then add the same domain in your hosting dashboard so it gets HTTPS.
                  </p>
                )}
              </form>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold">Publish to the web</p>
              {canPublish ? (
                <>
                  <p className="mt-1 text-[11px] text-muted-foreground">Saves your current files as a version and serves it at a public link anyone can open.</p>
                  <Button size="sm" onClick={publish} disabled={busy} data-testid="publish-button" className="mt-3 w-full">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Publish"}</Button>
                </>
              ) : (
                <>
                  <p className="mt-1 text-[11px] text-muted-foreground" data-testid="publish-needs-plan">Publishing apps is part of the Pro and Max plans. You can still build, preview and download your app for free.</p>
                  <Button size="sm" onClick={() => navigate("/plans")} className="mt-3 w-full">See plans</Button>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
