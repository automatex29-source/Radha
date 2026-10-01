import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api, API, getToken, formatApiError } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import IconRail from "@/components/IconRail";
import MessageBubble from "@/components/MessageBubble";
import ComposerInput from "@/components/ComposerInput";
import VoiceMode from "@/components/VoiceMode";
import { setServerSpeech, browserSpeechAvailable, unlockSpeech } from "@/lib/voice";
import PreviewPanel from "@/components/PreviewPanel";
import ShareDialog from "@/components/ShareDialog";
import { sampleVideoFrames } from "@/lib/videoFrames";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { PanelLeft, ChevronDown, Cpu, FileText, Braces, Network, Loader2, Download, RefreshCw, SquarePen, ArrowRight, FolderKanban, Link2, Coffee, BookOpen, Zap, Heart, MessageCircle, Lightbulb } from "lucide-react";
import Mascot from "@/components/Mascot";
import { useAuth } from "@/context/AuthContext";

const STARTERS = [
  { icon: FileText, tone: "indigo", hint: "Turn ideas into clear, concise summaries.", title: "Synthesize an executive summary", prompt: "Write a concise executive summary of the key trends shaping AI agents in 2026." },
  { icon: Braces, tone: "sky", hint: "Clean, optimize and modernize your code.", title: "Refactor an async Python service", prompt: "Show me how to structure a clean, testable async Python service that calls an external API with retries." },
  { icon: Network, tone: "emerald", hint: "Build fast, scalable search solutions.", title: "Design a vector search pipeline", prompt: "Design a distributed vector search pipeline for semantic document retrieval. Cover ingestion, embedding, storage and querying." },
];

// The Counsellor tab: a cheerful friend who shares Krishna's wisdom from the Gita when it helps (see backend/counsellor.py).
const COUNSEL_STARTERS = [
  { icon: Coffee, tone: "amber", hint: "No agenda, just vibes.", title: "Just wanna chat ☕", prompt: "Hey! Just wanna chat for a bit. How's it going?" },
  { icon: BookOpen, tone: "sky", hint: "Exams, deadlines, all of it.", title: "Study stress is real 📚", prompt: "Bro exams are coming and I'm lowkey stressed. Help me chill and make a plan?" },
  { icon: Zap, tone: "violet", hint: "A little push for today.", title: "Motivate me, I'm lazy 😴", prompt: "I'm feeling super lazy today and can't start anything. Motivate me!" },
  { icon: Heart, tone: "pink", hint: "Crush, friends, family drama.", title: "Relationship tea 💌", prompt: "Need some advice about a relationship thing. Can I tell you about it?" },
  { icon: MessageCircle, tone: "emerald", hint: "हिंदी में बात करते हैं।", title: "यार, मन नहीं लग रहा", prompt: "यार, आज मन नहीं लग रहा। थोड़ी बात करो ना।" },
  { icon: Lightbulb, tone: "indigo", hint: "Think it through together.", title: "Help me decide 🤔", prompt: "I have a big decision to make and I keep going back and forth. Help me think it through?" },
];

// A fresh, positive greeting on every visit, matched to the time of day. {name} is the user's first name.
const GREETINGS = {
  morning: [
    ["Good morning, {name}! ☀️", "Let's make today", "a good one"],
    ["Rise and shine, {name} 🌅", "Fresh day,", "fresh start"],
    ["Morning, {name}! ☕", "What's on your", "mind today?"],
  ],
  afternoon: [
    ["Hey {name}, good afternoon! 🌤️", "How's your day", "going so far?"],
    ["Hi {name}! 😊", "Take a breath,", "you're doing great"],
    ["Namaste, {name} 🙏", "Kaisa chal raha hai", "aaj ka din?"],
  ],
  evening: [
    ["Good evening, {name} 🌇", "How was", "your day?"],
    ["Hey {name}! 🌸", "Let's unwind", "and talk"],
    ["Evening, {name} ✨", "Tell me the best part", "of your day"],
  ],
  night: [
    ["Hey night owl, {name} 🌙", "Can't sleep?", "Let's talk"],
    ["Hi {name} ✨", "Before you rest,", "what's on your mind?"],
    ["Late night thoughts, {name}? 🌌", "I'm all", "ears"],
  ],
};
const TAGLINES = ["Let's talk!", "I'm here for you", "Smile please! 😄", "Good vibes only", "Aaj kya scene hai?"];

function pickGreeting(name) {
  const h = new Date().getHours();
  const part = h >= 5 && h < 12 ? "morning" : h >= 12 && h < 17 ? "afternoon" : h >= 17 && h < 22 ? "evening" : "night";
  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  const [hello, lead, highlight] = pick(GREETINGS[part]);
  return { hello: name ? hello.replace("{name}", name) : hello.replace(/,? \{name\}/, ""), lead, highlight, tagline: pick(TAGLINES) };
}

export default function Workspace({ mode = null }) {
  const counselling = mode === "counsellor";
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
  const [pendingImages, setPendingImages] = useState([]);
  const [streamSteps, setStreamSteps] = useState([]);
  const [caps, setCaps] = useState(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [previewItem, setPreviewItem] = useState(null);
  const [shareOpen, setShareOpen] = useState(false);

  const scrollRef = useRef(null);
  const abortRef = useRef(null);
  const streamTextRef = useRef("");
  const streamSourcesRef = useRef([]);
  const streamStepsRef = useRef([]);

  // Chat always uses Krish AI's tools (web search, code, files) whenever the model supports them; no mode switch.
  const agentAvailable = !counselling && !!(caps && model && caps.agent?.[model]);
  const voiceEnabled = !!caps?.voice;
  const speechEnabled = !!caps?.serverSpeech || browserSpeechAvailable();

  const activeConv = conversations.find((c) => c.id === activeId);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      // The welcome screen starts at its top; a conversation follows its newest message.
      if (el) el.scrollTop = el.querySelector("[data-testid=message-list-container]") ? el.scrollHeight : 0;
    });
  }, []);

  const loadConversations = useCallback(async () => {
    try {
      const { data } = await api.get("/conversations", mode ? { params: { mode } } : undefined);
      setConversations(data);
    } catch (e) {
      toast.error(formatApiError(e));
    }
  }, [mode]);

  useEffect(() => {
    loadConversations();
    api.get("/models").then(({ data }) => {
      setModels(data.models);
      setModel(data.default);
    }).catch(() => {});
    api.get("/capabilities").then(({ data }) => { setServerSpeech(data.serverSpeech); setCaps(data); }).catch(() => {});
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
    setPreviewItem(null);
    setActiveId(null);
    setMessages([]);
    setAttachments([]);
    setPendingImages([]);
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
    const title = activeConv?.title || "Krish AI conversation";
    const lines = [`# ${title}`, "", `_Exported from Krish AI by EmpireX_`, ""];
    messages.forEach((m) => {
      lines.push(m.role === "user" ? "## You" : `## Krish AI${m.model ? ` (${m.model})` : ""}`);
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
    setStreamSteps([]);
    streamTextRef.current = "";
    streamSourcesRef.current = [];
    streamStepsRef.current = [];
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
        throw new Error(err.detail || "Failed to reach Krish AI");
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
          if (eventName === "tool" || eventName === "tool_result") {
            const step = JSON.parse(dataStr);
            const others = streamStepsRef.current.filter((s) => s.id !== step.id);
            streamStepsRef.current = eventName === "tool" ? [...others, step]
              : streamStepsRef.current.map((s) => (s.id === step.id ? step : s));
            setStreamSteps(streamStepsRef.current);
            // Like Claude's artifacts: open newly created documents in the side panel.
            const doc = eventName === "tool_result" && (step.media || []).find((m) => m.kind === "document");
            if (doc) setPreviewItem(doc);
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
      if (finalText || streamStepsRef.current.length) {
        setMessages((m) => [...m, { id: `ai-${Date.now()}`, role: "assistant", content: finalText, model,
          sources: streamSourcesRef.current.length ? streamSourcesRef.current : null,
          steps: streamStepsRef.current, media: streamStepsRef.current.flatMap((s) => s.media || []) }]);
      }
      setStreamText("");
      setStreamSources([]);
      setStreamSteps([]);
      // Sync ordering/titles/ids from server.
      try {
        const { data } = await api.get(`/conversations/${convId}`);
        setMessages(data.messages);
      } catch { /* keep local */ }
      loadConversations();
    }
    return streamTextRef.current;
  };

  const ensureConversation = async () => {
    if (activeId) return activeId;
    const { data } = await api.post("/conversations", counselling ? { mode } : projectId ? { projectId } : {});
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

  const attachImage = async (file) => {
    setUploading(true);
    try {
      const convId = await ensureConversation();
      const fd = new FormData();
      fd.append("file", file);
      fd.append("conversationId", convId);
      const { data } = await api.post("/media", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPendingImages((imgs) => [...imgs, data]);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setUploading(false);
    }
  };

  const attachVideo = async (file) => {
    setUploading(true);
    try {
      const convId = await ensureConversation();
      const { duration, frames } = await sampleVideoFrames(file, 8);
      if (!frames.length) throw new Error("Couldn't read any frames from that video");
      const group = { id: `vid-${Date.now()}`, name: file.name, duration };
      const uploaded = [];
      for (const f of frames) {
        const fd = new FormData();
        fd.append("file", new File([f.blob], `${file.name}@${f.time.toFixed(1)}s.jpg`, { type: "image/jpeg" }));
        fd.append("conversationId", convId);
        const { data } = await api.post("/media", fd, { headers: { "Content-Type": "multipart/form-data" } });
        uploaded.push({ ...data, videoGroup: group, time: f.time });
      }
      setPendingImages((imgs) => [...imgs, ...uploaded]);
      toast.success(`${file.name}: ${uploaded.length} frames ready`);
    } catch (e) {
      toast.error(e?.response ? formatApiError(e) : e.message);
    } finally {
      setUploading(false);
    }
  };

  const attachFile = async (file) => {
    if (file.type?.startsWith("image/")) return attachImage(file);
    if (file.type?.startsWith("video/")) return attachVideo(file);
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
    const images = text === undefined ? pendingImages : [];
    const groups = [...new Map(images.filter((i) => i.videoGroup).map((i) => [i.videoGroup.id, i.videoGroup])).values()];
    const typed = (text ?? input).trim() || (groups.length ? "What happens in this video?" : images.length ? "What's in this image?" : "");
    // Tell the model which images are video frames (and when they were taken).
    const videoNotes = groups.map((g) => {
      const times = images.filter((i) => i.videoGroup?.id === g.id).map((i) => `${i.time.toFixed(1)}s`);
      return `[Video attached: “${g.name}” (${g.duration.toFixed(1)}s). Its ${times.length} frames below were sampled at ${times.join(", ")}.]`;
    });
    const content = [...videoNotes, typed].join("\n\n").trim();
    if (!content || streaming) return "";

    let convId;
    try {
      convId = await ensureConversation();
    } catch (e) {
      toast.error(formatApiError(e));
      return "";
    }

    const imageIds = images.map((i) => i.id);
    setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: "user", content, images: imageIds, conversationId: convId }]);
    if (text === undefined) { setInput(""); setPendingImages([]); }
    return runStream(`${API}/conversations/${convId}/stream`, { content, model, images: imageIds, agent: agentAvailable }, convId);
  };

  // Voice mode keeps its first callback for the whole session; route through a ref
  // so each utterance uses the current conversation, model and agent setting.
  const sendRef = useRef(sendMessage);
  sendRef.current = sendMessage;

  const regenerate = async () => {
    if (!activeId || streaming) return;
    setMessages((m) => {
      const copy = [...m];
      if (copy.length && copy[copy.length - 1].role === "assistant") copy.pop();
      return copy;
    });
    await runStream(`${API}/conversations/${activeId}/regenerate`, { model, agent: agentAvailable }, activeId);
  };

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      {/* Desktop sidebar */}
      <div className="hidden lg:block">
        <Sidebar conversations={conversations} activeId={activeId} onSelect={openConversation}
          onNew={newConversation} onDelete={deleteConversation} onRename={renameConversation}
          newLabel={counselling ? "New session" : undefined} onCollapse={() => {}} />
      </div>

      {/* Mobile drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" data-testid="mobile-drawer">
          <div className="krish-fade-in absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]" onClick={() => setSidebarOpen(false)} />
          <div className="krish-drawer-in krish-canvas absolute left-0 top-0 h-full max-w-[85vw] shadow-2xl">
            <Sidebar conversations={conversations} activeId={activeId} onSelect={openConversation}
              onNew={newConversation} onDelete={deleteConversation} onRename={renameConversation}
          newLabel={counselling ? "New session" : undefined} onCollapse={() => setSidebarOpen(false)} />
          </div>
        </div>
      )}

      {/* Main */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header data-testid="chat-workspace-header" className="z-40 flex items-center justify-between gap-2 px-2 py-2 sm:px-6 sm:py-4">
          <div className="flex min-w-0 items-center gap-1 sm:gap-3">
            <button onClick={() => setSidebarOpen(true)} data-testid="open-sidebar-button" aria-label="Show chats"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground active:bg-surface lg:hidden">
              <PanelLeft className="h-5 w-5" />
            </button>
            <h1 data-testid="active-conversation-title" className="krish-tab-title truncate text-sm font-semibold tracking-tight">
              {activeConv ? activeConv.title : counselling ? "Counsellor" : "New conversation"}
            </h1>
            {project && (
              <button onClick={() => navigate(`/projects/${project.id}`)} data-testid="active-project-badge"
                className="flex shrink-0 items-center gap-1.5 rounded-full border border-border-strong bg-surface px-2.5 py-1 text-[11px] font-medium text-brand hover:border-primary/50">
                <FolderKanban className="h-3 w-3" /> {project.name}
              </button>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
            {activeConv && messages.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => setShareOpen(true)} data-testid="share-conversation-button"
                className={`gap-1.5 hover:text-foreground ${activeConv.shareId ? "text-brand" : "text-muted-foreground"}`}>
                <Link2 className="h-3.5 w-3.5" />
                <span className="hidden text-xs sm:inline">{activeConv.shareId ? "Shared" : "Share"}</span>
              </Button>
            )}
            {activeId && messages.length > 0 && (
              <Button variant="ghost" size="sm" onClick={exportConversation} data-testid="export-conversation-button" className="gap-1.5 text-muted-foreground hover:text-foreground max-sm:hidden">
                <Download className="h-3.5 w-3.5" />
                <span className="hidden text-xs sm:inline">Export</span>
              </Button>
            )}
            {!counselling && <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" data-testid="model-selector-dropdown" className="h-9 gap-2 rounded-full border-white/80 bg-white/80 px-3.5 shadow-sm backdrop-blur dark:border-border dark:bg-card sm:h-10">
                <Cpu className="h-3.5 w-3.5 text-primary" />
                <span className="max-w-[92px] truncate text-xs font-medium sm:max-w-none">{models.find((m) => m.id === model)?.label || "Model"}</span>
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
          </DropdownMenu>}
            <button onClick={newConversation} data-testid="mobile-new-chat-button" aria-label={counselling ? "New session" : "New chat"}
              className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground active:bg-surface lg:hidden">
              <SquarePen className="h-5 w-5" />
            </button>
          </div>
        </header>

        {/* Messages */}
        <div ref={scrollRef} className={`radha-scroll flex-1 overflow-y-auto ${messages.length === 0 && !streaming && !loadingConv ? "krish-no-scrollbar" : ""}`}>
          {loadingConv ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : messages.length === 0 && !streaming ? (
            counselling ? <CounselEmptyState onPick={(p) => sendMessage(p)} /> : <EmptyState onPick={(p) => sendMessage(p)} />
          ) : (
            <div data-testid="message-list-container" className="mx-auto w-full max-w-3xl space-y-6 px-4 py-5 sm:py-8">
              {messages.map((m) => <MessageBubble key={m.id} message={m} voiceEnabled={speechEnabled} onOpenMedia={setPreviewItem} />)}
              {streaming && (
                <MessageBubble message={{ id: "streaming", role: "assistant", content: streamText, model, sources: streamSources,
                  steps: streamSteps, media: streamSteps.flatMap((s) => s.media || []) }} streaming onOpenMedia={setPreviewItem} />
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
        {counselling && (
          <p data-testid="counsellor-care-note" className="mx-auto w-full max-w-3xl px-5 text-center text-[11px] leading-snug text-muted-foreground">
            Need urgent help? Tele-MANAS 14416, free 24x7 💛
          </p>
        )}
        <ComposerInput value={input} onChange={setInput} onSend={() => sendMessage()} onStop={stopGeneration}
          streaming={streaming} disabled={loadingConv}
          onAttach={counselling ? undefined : attachFile} attachments={attachments} onRemoveAttachment={removeAttachment} uploading={uploading}
          images={pendingImages} onRemoveImage={(id) => setPendingImages((imgs) => imgs.filter((i) => i.id !== id))}
          agentMode={agentAvailable} agentAvailable={agentAvailable}
          agentHint="Agent mode needs a provider API key for this model on the backend"
          voiceEnabled={voiceEnabled} voiceHint="Voice needs GROQ_API_KEY (free) on the backend"
          onVoiceMode={() => { unlockSpeech(); setVoiceOpen(true); }}
          placeholder={counselling ? "Type anything… how's your day going? 😊" : undefined} />
      </div>
      <ShareDialog open={shareOpen} onOpenChange={setShareOpen} conversation={activeConv}
        onChange={(shareId) => setConversations((cs) => cs.map((c) => (c.id === activeId ? { ...c, shareId } : c)))} />
      {previewItem && <PreviewPanel item={previewItem} onClose={() => setPreviewItem(null)} />}
      {voiceOpen && <VoiceMode onClose={() => setVoiceOpen(false)} onUtterance={(t) => sendRef.current(t)} />}
    </div>
  );
}

// Soft colour for each starter card. Full class names so Tailwind keeps them.
const TONES = {
  indigo: { card: "from-indigo-50/90 dark:from-indigo-500/10", icon: "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300", wave: "text-indigo-200/70 dark:text-indigo-500/15", arrow: "text-indigo-500" },
  sky: { card: "from-sky-50/90 dark:from-sky-500/10", icon: "bg-sky-100 text-sky-600 dark:bg-sky-500/20 dark:text-sky-300", wave: "text-sky-200/70 dark:text-sky-500/15", arrow: "text-sky-500" },
  emerald: { card: "from-emerald-50/90 dark:from-emerald-500/10", icon: "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300", wave: "text-emerald-200/70 dark:text-emerald-500/15", arrow: "text-emerald-500" },
  pink: { card: "from-pink-50/90 dark:from-pink-500/10", icon: "bg-pink-100 text-pink-600 dark:bg-pink-500/20 dark:text-pink-300", wave: "text-pink-200/70 dark:text-pink-500/15", arrow: "text-pink-500" },
  amber: { card: "from-amber-50/90 dark:from-amber-500/10", icon: "bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-300", wave: "text-amber-200/70 dark:text-amber-500/15", arrow: "text-amber-500" },
  violet: { card: "from-violet-50/90 dark:from-violet-500/10", icon: "bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-300", wave: "text-violet-200/70 dark:text-violet-500/15", arrow: "text-violet-500" },
};

function StarterCard({ s, i, onPick, testid, hideOnPhone }) {
  const t = TONES[s.tone] || TONES.indigo;
  return (
    <button data-testid={testid} onClick={() => onPick(s.prompt)}
      className={`${hideOnPhone ? "max-sm:hidden " : ""}krish-card group relative flex items-center gap-3 overflow-hidden rounded-2xl border border-white/70 bg-gradient-to-br ${t.card} to-white/70 p-3 text-left shadow-[0_8px_30px_rgba(99,102,241,0.08)] backdrop-blur-sm transition-all hover:-translate-y-0.5 hover:shadow-[0_14px_40px_rgba(99,102,241,0.16)] active:scale-[0.99] dark:border-white/5 dark:to-card/60 sm:block sm:px-5 sm:py-4`}
      style={{ animationDelay: `${0.05 * i}s` }}>
      <svg viewBox="0 0 200 80" preserveAspectRatio="none" aria-hidden="true" className={`pointer-events-none absolute -bottom-1 right-0 h-16 w-3/4 ${t.wave}`}>
        <path d="M0 80 C 60 70, 110 20, 200 10 L200 80 Z" fill="currentColor" />
      </svg>
      <div className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl sm:mb-2.5 sm:h-10 sm:w-10 ${t.icon}`}>
        <s.icon className="h-[18px] w-[18px]" />
      </div>
      <div className="relative min-w-0 flex-1 sm:pr-6">
        <p className="text-sm font-semibold leading-snug text-foreground sm:text-[15px]">{s.title}</p>
        {s.hint && <p className="mt-1 text-xs leading-snug text-muted-foreground max-sm:hidden">{s.hint}</p>}
      </div>
      <ArrowRight className={`relative h-4 w-4 shrink-0 transition-transform group-hover:translate-x-0.5 sm:absolute sm:right-5 sm:top-6 ${t.arrow}`} />
    </button>
  );
}

function EmptyState({ onPick }) {
  return (
    <div data-testid="empty-state-welcome" className="relative mx-auto flex min-h-full max-w-5xl flex-col justify-center px-4 py-6 sm:px-8 sm:py-8">
      <div className="radha-fade-up relative flex items-center gap-4 max-md:flex-col-reverse md:gap-10">
        <div className="relative min-w-0 flex-1 max-md:text-center">
          <Sparkle className="absolute -left-7 top-10 h-6 w-6 text-violet-500 max-md:hidden" />
          <h2 className="text-[1.6rem] font-extrabold leading-[1.1] tracking-tight text-foreground sm:text-4xl lg:text-[2.75rem]">
            How can<br className="max-md:hidden" /> <span className="krish-gradient-text">Krish AI</span> help today?
          </h2>
          <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground max-sm:hidden">
            A premium AI workspace by EmpireX. Ask anything, attach a document, or open a project. Everything is saved and reloadable.
          </p>
        </div>
        <div className="relative shrink-0">
          <p className="krish-hand absolute -left-28 top-4 -rotate-12 text-2xl text-indigo-500 max-lg:hidden dark:text-indigo-300">
            Ideas<br /><span className="ml-5">to Impact</span>
            <svg viewBox="0 0 120 12" className="ml-4 mt-0.5 h-3 w-28" aria-hidden="true"><path d="M2 9 C 40 2, 80 2, 118 6" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" /></svg>
          </p>
          <Mascot className="krish-float h-28 w-auto sm:h-40 md:h-44 lg:h-48" />
        </div>
      </div>
      <div className="relative mt-5 grid w-full gap-2.5 sm:mt-6 sm:grid-cols-3 sm:gap-4">
        {STARTERS.map((s, i) => (
          <StarterCard key={i} s={s} i={i} onPick={onPick} testid={`prompt-starter-card-${i}`} />
        ))}
      </div>
    </div>
  );
}

const Sparkle = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
    <path d="M12 0 L14.5 9.5 L24 12 L14.5 14.5 L12 24 L9.5 14.5 L0 12 L9.5 9.5 Z" />
  </svg>
);

function CounselEmptyState({ onPick }) {
  const { user } = useAuth();
  const first = (user?.name || "").trim().split(/\s+/)[0];
  const g = useMemo(() => pickGreeting(first), [first]);
  return (
    <div data-testid="counsellor-welcome" className="relative mx-auto flex min-h-full max-w-5xl flex-col justify-center px-4 py-6 sm:px-8 sm:py-8">
      <div className="radha-fade-up relative flex items-center gap-4 max-md:flex-col-reverse md:gap-10">
        <div className="relative min-w-0 flex-1 max-md:text-center">
          <Sparkle className="absolute -left-7 top-6 h-6 w-6 text-amber-400 max-md:hidden" />
          <h2 className="text-[1.6rem] font-extrabold leading-[1.1] tracking-tight text-foreground sm:text-4xl lg:text-[2.75rem]">
            <span data-testid="counsellor-greeting" className="block text-lg font-bold text-muted-foreground sm:text-xl">{g.hello}</span>
            {g.lead} <span className="krish-gradient-text">{g.highlight}</span>
          </h2>
          <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground">
            Talk about anything: your day, exams, crush, family, big dreams. No judgement, just good vibes,
            real advice and a little Krishna wisdom when you need it ✨ Hindi, English or Hinglish, all chill.
          </p>
        </div>
        <div className="relative shrink-0">
          <p className="krish-hand absolute -left-24 top-4 -rotate-12 text-2xl text-pink-500 max-lg:hidden dark:text-pink-300">
            {g.tagline}
            <svg viewBox="0 0 120 12" className="ml-2 mt-0.5 h-3 w-24" aria-hidden="true"><path d="M2 9 C 40 2, 80 2, 118 6" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" /></svg>
          </p>
          <Mascot className="krish-float h-28 w-auto sm:h-40 md:h-44 lg:h-48" />
        </div>
      </div>
      <div className="relative mt-5 grid w-full gap-2.5 sm:mt-6 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
        {COUNSEL_STARTERS.map((s, i) => (
          <StarterCard key={i} s={s} i={i} onPick={onPick} testid={`counsellor-starter-${i}`} hideOnPhone={i >= 4} />
        ))}
      </div>
    </div>
  );
}
