import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Undo2, Download, Eye, PencilLine, Sparkles, ArrowUp, Check, MessageSquare } from "lucide-react";

const ACTIONS = [
  { id: "shorter", label: "Shorter" }, { id: "longer", label: "Longer" }, { id: "grammar", label: "Fix grammar" },
  { id: "formal", label: "More formal" }, { id: "simple", label: "Simpler" }, { id: "bullets", label: "Bullet points" },
  { id: "hindi", label: "हिंदी में" }, { id: "english", label: "In English" }, { id: "emoji", label: "Add emojis" },
];

export default function DocEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [saved, setSaved] = useState(true);
  const [preview, setPreview] = useState(false);
  const [selection, setSelection] = useState("");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState("");
  const [chat, setChat] = useState([]); // what was asked in the panel and Krish's answers
  const editorRef = useRef(null);
  const saveTimer = useRef(null);

  useEffect(() => {
    api.get(`/docs/${id}`).then(({ data }) => { setDoc(data); setTitle(data.title); setContent(data.content); })
      .catch((e) => { toast.error(formatApiError(e)); navigate("/docs"); });
  }, [id, navigate]);

  const save = useCallback(async (patch) => {
    try {
      const { data } = await api.patch(`/docs/${id}`, patch);
      setDoc(data);
      setSaved(true);
    } catch (e) {
      toast.error(formatApiError(e));
    }
  }, [id]);

  // Typing saves automatically a moment after the last key (title and text changes are saved together).
  const pending = useRef({});
  const edit = (patch) => {
    if ("content" in patch) setContent(patch.content);
    if ("title" in patch) setTitle(patch.title);
    setSaved(false);
    pending.current = { ...pending.current, ...patch };
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      const next = pending.current;
      pending.current = {};
      if (next.title !== undefined && !next.title.trim()) delete next.title;
      if (Object.keys(next).length) save(next); else setSaved(true);
    }, 900);
  };
  useEffect(() => () => clearTimeout(saveTimer.current), []);

  const readSelection = () => {
    const el = editorRef.current;
    if (!el) return;
    setSelection(el.value.slice(el.selectionStart, el.selectionEnd).trim() ? el.value.slice(el.selectionStart, el.selectionEnd) : "");
  };

  const runAi = async (payload, key) => {
    clearTimeout(saveTimer.current);
    setBusy(key);
    try {
      if (!saved) { pending.current = {}; await api.patch(`/docs/${id}`, { content, ...(title.trim() ? { title } : {}) }); }
      const { data } = await api.post(`/docs/${id}/ai`, { ...payload, selection: selection || undefined });
      const asked = payload.instruction || ACTIONS.find((a) => a.id === payload.action)?.label || "";
      setInstruction("");
      if (data.kind === "reply" || data.kind === "handoff") {
        setChat((c) => [...c, { asked, reply: data.reply, handoff: data.handoff }]);
        return;
      }
      setDoc(data); setContent(data.content); setSaved(true); setSelection("");
      const done = selection ? "Changed the selected part." : "Updated the document.";
      setChat((c) => [...c, { asked, reply: `${done} Use Undo to go back.` }]);
      toast.success(selection ? "Changed the selected part" : "Document updated");
    } catch (e) {
      const asked = payload.instruction || ACTIONS.find((a) => a.id === payload.action)?.label || "";
      setChat((c) => [...c, { asked, reply: formatApiError(e), error: true }]);
      toast.error(formatApiError(e));
    } finally {
      setBusy("");
    }
  };

  const openInChat = (text) => {
    try { sessionStorage.setItem("krish.handoff", text); } catch { /* ignore */ }
    navigate("/");
  };

  const undo = async () => {
    setBusy("undo");
    try {
      const { data } = await api.post(`/docs/${id}/undo`);
      setDoc(data); setContent(data.content); setSaved(true);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy("");
    }
  };

  const download = async (format) => {
    setBusy(format);
    try {
      if (!saved) { clearTimeout(saveTimer.current); pending.current = {}; await api.patch(`/docs/${id}`, { content, ...(title.trim() ? { title } : {}) }); setSaved(true); }
      const res = await api.get(`/docs/${id}/export`, { params: { format }, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(title || "document").replace(/[^\w\- ]+/g, "").trim() || "document"}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch {
      toast.error("Download failed. Please try again.");
    } finally {
      setBusy("");
    }
  };

  if (!doc) {
    return <div className="flex h-dvh items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;
  }

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail mobileBar={false} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
        {/* Editor */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2.5 sm:px-5">
            <button onClick={() => navigate("/docs")} aria-label="All documents" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-surface hover:text-foreground">
              <ArrowLeft className="h-4 w-4" />
            </button>
            <input value={title} onChange={(e) => edit({ title: e.target.value })} data-testid="doc-title-input" aria-label="Title"
              className="min-w-0 flex-1 bg-transparent text-base font-semibold focus:outline-none" />
            <span className="hidden shrink-0 items-center gap-1 text-[11px] text-muted-foreground sm:flex">
              {saved ? <><Check className="h-3 w-3" /> Saved</> : "Saving…"}
            </span>
            <Button variant="ghost" size="sm" onClick={() => setPreview((p) => !p)} className="gap-1.5" data-testid="doc-preview-toggle">
              {preview ? <PencilLine className="h-4 w-4" /> : <Eye className="h-4 w-4" />}<span className="max-sm:hidden">{preview ? "Edit" : "Preview"}</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={undo} disabled={!doc.canUndo || !!busy} title="Undo the last Krish change" className="gap-1.5">
              {busy === "undo" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Undo2 className="h-4 w-4" />}<span className="max-sm:hidden">Undo</span>
            </Button>
            <Button variant="outline" size="sm" onClick={() => download("docx")} disabled={!!busy} className="gap-1.5 border-border bg-card" data-testid="doc-download-word">
              {busy === "docx" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} Word
            </Button>
            <Button variant="outline" size="sm" onClick={() => download("pdf")} disabled={!!busy} className="gap-1.5 border-border bg-card max-sm:hidden">
              {busy === "pdf" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} PDF
            </Button>
          </div>
          <div className="radha-scroll min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-3xl px-4 py-5 sm:px-8">
              {preview ? (
                <div className="radha-prose" data-testid="doc-preview"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content || "*Empty document*"}</ReactMarkdown></div>
              ) : (
                <textarea ref={editorRef} value={content} onChange={(e) => edit({ content: e.target.value })}
                  onSelect={readSelection} onKeyUp={readSelection} onMouseUp={readSelection} data-testid="doc-editor"
                  placeholder="Start writing, or ask Krish to write something…"
                  className="min-h-[60vh] w-full resize-none bg-transparent font-[inherit] text-[15px] leading-7 focus:outline-none"
                  style={{ fieldSizing: "content" }} />
              )}
            </div>
          </div>
        </div>

        {/* Krish panel */}
        <aside className="flex shrink-0 flex-col border-t border-border bg-card/70 p-3 backdrop-blur lg:w-[320px] lg:border-l lg:border-t-0 lg:p-4" data-testid="doc-ai-panel">
          <p className="flex items-center gap-1.5 text-sm font-semibold"><Sparkles className="h-4 w-4 text-primary" /> Ask Krish</p>
          <p className="mt-1 text-xs text-muted-foreground" data-testid="doc-ai-target">
            {selection ? `Changes only the ${selection.length}-character part you selected.` : "Ask anything about this document, or tell Krish what to change. Select text first to change just that part."}
          </p>
          <div className="mt-2.5 flex flex-wrap gap-1.5 max-lg:max-h-[68px] max-lg:overflow-y-auto">
            {ACTIONS.map((a) => (
              <button key={a.id} onClick={() => runAi({ action: a.id }, a.id)} disabled={!!busy || !content.trim()}
                className="flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-xs hover:border-primary/50 disabled:opacity-50">
                {busy === a.id && <Loader2 className="h-3 w-3 animate-spin" />}{a.label}
              </button>
            ))}
          </div>
          {chat.length > 0 && (
            <div className="radha-scroll mt-3 min-h-0 space-y-3 overflow-y-auto max-lg:max-h-[30vh] lg:flex-1" data-testid="doc-ai-chat">
              {chat.map((m, i) => (
                <div key={i} className="space-y-1.5">
                  {m.asked && <p className="ml-6 rounded-2xl rounded-br-sm bg-primary/10 px-3 py-2 text-sm">{m.asked}</p>}
                  <div className={`rounded-2xl rounded-bl-sm border border-border bg-background px-3 py-2 text-sm ${m.error ? "text-destructive" : ""}`}>
                    <div className="radha-prose text-sm"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.reply || ""}</ReactMarkdown></div>
                    {m.handoff && (
                      <Button size="sm" onClick={() => openInChat(m.handoff)} className="mt-2 gap-1.5" data-testid="doc-ai-open-chat">
                        <MessageSquare className="h-4 w-4" /> Make it in chat
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <form className="mt-3 flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (instruction.trim()) runAi({ instruction }, "custom"); }}>
            <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={2} data-testid="doc-ai-input"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (instruction.trim() && !busy) runAi({ instruction }, "custom"); } }}
              placeholder={content.trim() ? "e.g. Add a short conclusion, or make a video of it" : "e.g. Write a thank-you note to my team"}
              className="min-h-[44px] flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
            <Button type="submit" size="icon" disabled={!instruction.trim() || !!busy} className="h-11 w-11 shrink-0 rounded-full" aria-label="Send">
              {busy === "custom" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            </Button>
          </form>
        </aside>
      </div>
    </div>
  );
}
