import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api, API, getToken, formatApiError } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import IconRail from "@/components/IconRail";
import MessageBubble from "@/components/MessageBubble";
import ComposerInput from "@/components/ComposerInput";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { Sparkles, PanelLeft, ChevronDown, Cpu, FileText, Braces, Network, Loader2, Download, RefreshCw, FolderKanban } from "lucide-react";

const STARTERS = [
  { icon: FileText, title: "Synthesize an executive summary", prompt: "Write a concise executive summary of the key trends shaping AI agents in 2026." },
  { icon: Braces, title: "Refactor an async Python service", prompt: "Show me how to structure a clean, testable async Python service that calls an external API with retries." },
  { icon: Network, title: "Design a vector search pipeline", prompt: "Design a distributed vector search pipeline for semantic document retrieval. Cover ingestion, embedding, storage and querying." },
];

export default function Workspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [projectId, setProjectId] = useState(searchParams.get("project") || null);
  const [project, setProject] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [loadingConv, setLoadingConv] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [models, setModels] = useState([]);
  const [model, setModel] = useState(null);
  const [streamSources, setStreamSources] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);

  const scrollRef = useRef(null);
  const abortRef = useRef(null);
  const streamTextRef = useRef("");
  const streamSourcesRef = useRef([]);

  const activeConv = conversations.find((c) => c.id === activeId);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    });
  }, []);

  const loadConversations = useCallback(async () => {
    try {
      const { data } = await api.get("/conversations");
      setConversations(data);
    } catch (e) {
      toast.error(formatApiError(e));
    }
  }, []);

  useEffect(() => {
    loadConversations();
    api.get("/models").then(({ data }) => {
      setModels(data.models);
      setModel(data.default);
    }).catch(() => {});
  }, [loadConversations]);

  useEffect(() => { scrollToBottom(); }, [messages, streamText, scrollToBottom]);

  // React to ?conversation= and ?project= deep links (e.g. from a project view).
  useEffect(() => {
    const convParam = searchParams.get("conversation");
    const projParam = searchParams.get("project");
    if (projParam) setProjectId(projParam);
    if (convParam && convParam !== activeId) openConversation(convParam);
    else if (projParam) { setActiveId(null); setMessages([]); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    if (projectId) {
      api.get(`/projects/${projectId}`).then(({ data }) => setProject(data.project)).catch(() => setProject(null));
    } else {
      setProject(null);
    }
  }, [projectId]);

  const openConversation = async (id) => {
    setActiveId(id);
    setSidebarOpen(false);
    setLoadingConv(true);
    setSearchParams((sp) => {
      const n = new URLSearchParams(sp);
      n.set("conversation", id);
      n.delete("project");
      return n;
    }, { replace: true });
    try {
      const { data } = await api.get(`/conversations/${id}`);
      setMessages(data.messages);
      if (data.conversation?.model) setModel(data.conversation.model);
      setProjectId(data.conversation?.projectId || null);
      try {
        const filesRes = await api.get(`/conversations/${id}/files`);
        setAttachments(filesRes.data);
      } catch { setAttachments([]); }
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoadingConv(false);
    }
  };

  const newConversation = () => {
    setActiveId(null);
    setMessages([]);
    setAttachments([]);
    setSidebarOpen(false);
    setSearchParams((sp) => {
      const n = new URLSearchParams();
      const proj = sp.get("project");
      if (proj) n.set("project", proj);
      return n;
    }, { replace: true });
  };

  const deleteConversation = async (id) => {
    try {
      await api.delete(`/conversations/${id}`);
      setConversations((c) => c.filter((x) => x.id !== id));
      if (activeId === id) newConversation();
      toast.success("Conversation deleted");
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const renameConversation = async (id, title) => {
    try {
      const { data } = await api.patch(`/conversations/${id}`, { title });
      setConversations((c) => c.map((x) => (x.id === id ? { ...x, title: data.title } : x)));
      toast.success("Renamed");
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const stopGeneration = () => {
    if (abortRef.current) abortRef.current.abort();
  };

  const exportConversation = () => {
    if (!messages.length) {
      toast.error("Nothing to export yet");
      return;
    }
    const title = activeConv?.title || "RADHA conversation";
    const lines = [`# ${title}`, "", `_Exported from RADHA by A.utomateX_`, ""];
    messages.forEach((m) => {
      lines.push(m.role === "user" ? "## You" : `## RADHA${m.model ? ` (${m.model})` : ""}`);
      lines.push("", m.content, "");
    });
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/[^a-z0-9]+/gi, "-").toLowerCase().slice(0, 50)}.md`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Conversation exported");
  };

  const runStream = async (url, body, convId) => {
    setStreaming(true);
    setStreamText("");
    setStreamSources([]);
    streamTextRef.current = "";
    streamSourcesRef.current = [];
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to reach RADHA");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const evt of events) {
          const lines = evt.split("\n");
          let eventName = "message";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event:")) eventName = line.slice(6).trim();
            else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
          }
          if (eventName === "error") throw new Error(JSON.parse(dataStr || '"Stream error"'));
          if (eventName === "sources") {
            streamSourcesRef.current = JSON.parse(dataStr || "[]");
            setStreamSources(streamSourcesRef.current);
            continue;
          }
          if (eventName === "done") continue;
          if (dataStr) {
            streamTextRef.current += JSON.parse(dataStr);
            setStreamText(streamTextRef.current);
          }
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") toast.error(e.message || "Something went wrong");
    } finally {
      abortRef.current = null;
      setStreaming(false);
      const finalText = streamTextRef.current;
      if (finalText) {
        setMessages((m) => [...m, { id: `ai-${Date.now()}`, role: "assistant", content: finalText, model, sources: streamSourcesRef.current.length ? streamSourcesRef.current : null }]);
      }
      setStreamText("");
      setStreamSources([]);
      // Sync ordering/titles/ids from server.
      try {
        const { data } = await api.get(`/conversations/${convId}`);
        setMessages(data.messages);
      } catch { /* keep local */ }
      loadConversations();
    }
  };

  const ensureConversation = async () => {
    if (activeId) return activeId;
    const { data } = await api.post("/conversations", projectId ? { projectId } : {});
    setActiveId(data.id);
    setConversations((c) => [data, ...c]);
    setSearchParams((sp) => {
      const n = new URLSearchParams(sp);
      n.set("conversation", data.id);
      n.delete("project");
      return n;
    }, { replace: true });
    return data.id;
  };

  const attachFile = async (file) => {
    setUploading(true);
    try {
      const convId = await ensureConversation();
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post(`/conversations/${convId}/files`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setAttachments((a) => [...a, data]);
      if (data.status === "failed") toast.error(`Could not read ${data.filename}`);
      else toast.success(`${data.filename} attached (${data.chunkCount} chunks)`);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setUploading(false);
    }
  };

  const removeAttachment = async (fid) => {
    try { await api.delete(`/files/${fid}`); } catch { /* ignore */ }
    setAttachments((a) => a.filter((x) => x.id !== fid));
  };

  const sendMessage = async (text) => {
    const content = (text ?? input).trim();
    if (!content || streaming) return;

    let convId;
    try {
      convId = await ensureConversation();
    } catch (e) {
      toast.error(formatApiError(e));
      return;
    }

    setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: "user", content, conversationId: convId }]);
    setInput("");
    await runStream(`${API}/conversations/${convId}/stream`, { content, model }, convId);
  };

  const regenerate = async () => {
    if (!activeId || streaming) return;
    setMessages((m) => {
      const copy = [...m];
      if (copy.length && copy[copy.length - 1].role === "assistant") copy.pop();
      return copy;
    });
    await runStream(`${API}/conversations/${activeId}/regenerate`, { model }, activeId);
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <IconRail />
      {/* Desktop sidebar */}
      <div className="hidden lg:block">
        <Sidebar conversations={conversations} activeId={activeId} onSelect={openConversation}
          onNew={newConversation} onDelete={deleteConversation} onRename={renameConversation} onCollapse={() => {}} />
      </div>

      {/* Mobile drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSidebarOpen(false)} />
          <div className="absolute left-0 top-0 h-full">
            <Sidebar conversations={conversations} activeId={activeId} onSelect={openConversation}
              onNew={newConversation} onDelete={deleteConversation} onRename={renameConversation} onCollapse={() => setSidebarOpen(false)} />
          </div>
        </div>
      )}

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header data-testid="chat-workspace-header" className="z-40 flex items-center justify-between border-b border-border bg-background/80 px-4 py-3 backdrop-blur-xl">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={() => setSidebarOpen(true)} className="text-muted-foreground hover:text-foreground lg:hidden">
              <PanelLeft className="h-5 w-5" />
            </button>
            <h1 data-testid="active-conversation-title" className="truncate text-sm font-semibold tracking-tight">
              {activeConv ? activeConv.title : "New conversation"}
            </h1>
            {project && (
              <button onClick={() => navigate(`/projects/${project.id}`)} data-testid="active-project-badge"
                className="flex shrink-0 items-center gap-1.5 rounded-full border border-[#262C3E] bg-[#171B26] px-2.5 py-1 text-[11px] font-medium text-[#A5B4FC] hover:border-primary/50">
                <FolderKanban className="h-3 w-3" /> {project.name}
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {activeId && messages.length > 0 && (
              <Button variant="ghost" size="sm" onClick={exportConversation} data-testid="export-conversation-button" className="gap-1.5 text-muted-foreground hover:text-foreground">
                <Download className="h-3.5 w-3.5" />
                <span className="hidden text-xs sm:inline">Export</span>
              </Button>
            )}
            <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" data-testid="model-selector-dropdown" className="gap-2 border-border bg-card">
                <Cpu className="h-3.5 w-3.5 text-primary" />
                <span className="text-xs font-medium">{models.find((m) => m.id === model)?.label || "Model"}</span>
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              {models.map((m) => (
                <DropdownMenuItem key={m.id} data-testid={`model-option-${m.id}`} onClick={() => setModel(m.id)} className="flex-col items-start gap-0.5">
                  <span className="text-sm font-medium">{m.label}</span>
                  <span className="text-[11px] text-muted-foreground">{m.description}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          </div>
        </header>

        {/* Messages */}
        <div ref={scrollRef} className="radha-scroll flex-1 overflow-y-auto">
          {loadingConv ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : messages.length === 0 && !streaming ? (
            <EmptyState onPick={(p) => sendMessage(p)} />
          ) : (
            <div data-testid="message-list-container" className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
              {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
              {streaming && (
                <MessageBubble message={{ id: "streaming", role: "assistant", content: streamText, model, sources: streamSources }} streaming />
              )}
              {!streaming && messages.length > 0 && messages[messages.length - 1].role === "assistant" && (
                <div className="flex justify-center pt-1">
                  <Button variant="outline" size="sm" onClick={regenerate} data-testid="regenerate-button"
                    className="gap-1.5 border-border bg-card text-muted-foreground hover:text-foreground">
                    <RefreshCw className="h-3.5 w-3.5" /> Regenerate
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Composer */}
        <ComposerInput value={input} onChange={setInput} onSend={() => sendMessage()} onStop={stopGeneration}
          streaming={streaming} disabled={loadingConv}
          onAttach={attachFile} attachments={attachments} onRemoveAttachment={removeAttachment} uploading={uploading} />
      </div>
    </div>
  );
}

function EmptyState({ onPick }) {
  return (
    <div data-testid="empty-state-welcome" className="relative mx-auto flex h-full max-w-3xl flex-col items-center justify-center overflow-hidden px-4">
      <div className="radha-orb -top-10 left-1/4 h-56 w-56 bg-indigo-600/30" />
      <div className="radha-orb bottom-10 right-1/4 h-56 w-56 bg-cyan-500/20" />
      <div className="radha-fade-up relative flex flex-col items-center text-center">
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary shadow-[0_0_50px_rgba(99,102,241,0.6)]">
          <Sparkles className="h-8 w-8 text-white" />
        </div>
        <h2 className="radha-heading-gradient text-3xl font-extrabold tracking-tighter sm:text-4xl">How can RADHA help today?</h2>
        <p className="mt-3 max-w-md text-sm text-muted-foreground">
          A premium AI workspace by A.utomateX. Ask anything, attach a document, or open a project — everything is saved and reloadable.
        </p>
      </div>
      <div className="radha-fade-up relative mt-9 grid w-full gap-3 sm:grid-cols-3" style={{ animationDelay: "0.1s" }}>
        {STARTERS.map((s, i) => (
          <button key={i} data-testid={`prompt-starter-card-${i}`} onClick={() => onPick(s.prompt)}
            className="radha-lift group rounded-xl border border-border bg-card p-4 text-left hover:border-primary/50">
            <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-[#1D2230] text-primary transition-colors group-hover:bg-primary group-hover:text-white">
              <s.icon className="h-4.5 w-4.5" />
            </div>
            <p className="text-sm font-medium leading-snug text-foreground">{s.title}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
