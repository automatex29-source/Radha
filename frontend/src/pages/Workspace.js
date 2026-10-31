import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api, API, getToken, formatApiError } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import IconRail from "@/components/IconRail";
import MessageBubble from "@/components/MessageBubble";
import ComposerInput from "@/components/ComposerInput";
import VoiceMode from "@/components/VoiceMode";
import { setServerSpeech, browserSpeechAvailable, unlockSpeech, getVoiceLang } from "@/lib/voice";
import PreviewPanel from "@/components/PreviewPanel";
import CodePanel from "@/components/CodePanel";
import { extractFiles } from "@/lib/codeFiles";
import ShareDialog from "@/components/ShareDialog";
import BreatheDialog from "@/components/BreatheDialog";
import { sampleVideoFrames } from "@/lib/videoFrames";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Mail, Plane, Dumbbell, ChefHat, GraduationCap, Briefcase, Calculator, Languages, PenLine, TrendingUp, Bug, Database, Globe, ListChecks, Sparkles, PanelLeft, FileText, Braces, Network, Loader2, Download, RefreshCw, SquarePen, ArrowUpRight, ArrowRight, FolderKanban, Link2, Coffee, BookOpen, Zap, Heart, MessageCircle, Lightbulb, Wind, History, Lock, Phone, Sun, CloudSun, Moon, CloudRain, Flame } from "lucide-react";
import Mascot from "@/components/Mascot";
import BrandMark from "@/components/BrandMark";
import { useAuth } from "@/context/AuthContext";
import UpgradeButton from "@/components/UpgradeButton";
import ModelMenu from "@/components/ModelMenu";
import { menuModel, modelLabel } from "@/lib/models";
import { showPlanLimit } from "@/lib/planLimits";
import { useT } from "@/lib/i18n";
import { KRISH_ROBO } from "@/lib/counselAgents";
import AgentPortrait from "@/components/AgentPortrait";

// A big pool of everyday tasks; the home page shows 3 different ones on every visit.
const STARTERS = [
  { icon: FileText, hint: "Turn ideas into clear, concise summaries.", title: "Synthesize an executive summary", prompt: "Write a concise executive summary of the key trends shaping AI agents in 2026." },
  { icon: Braces, hint: "Clean, optimize and modernize your code.", title: "Refactor an async Python service", prompt: "Show me how to structure a clean, testable async Python service that calls an external API with retries." },
  { icon: Network, hint: "Build fast, scalable search solutions.", title: "Design a vector search pipeline", prompt: "Design a distributed vector search pipeline for semantic document retrieval. Cover ingestion, embedding, storage and querying." },
  { icon: Mail, hint: "Polite, clear and ready to send.", title: "Write a professional email", prompt: "Write a short, professional email asking my manager for a day off next Friday." },
  { icon: Plane, hint: "Day-by-day plan with budget tips.", title: "Plan a 3-day trip", prompt: "Plan a 3-day budget trip to Goa with a day-by-day itinerary, food spots and rough costs." },
  { icon: Dumbbell, hint: "Simple routine, no gym needed.", title: "Make a home workout plan", prompt: "Make a 4-week beginner home workout plan, 30 minutes a day, no equipment." },
  { icon: ChefHat, hint: "Quick, healthy and tasty.", title: "Suggest a dinner recipe", prompt: "Suggest a quick, healthy vegetarian dinner recipe I can make in 20 minutes with simple ingredients." },
  { icon: GraduationCap, hint: "Learn anything, step by step.", title: "Explain a topic simply", prompt: "Explain how the internet works, simply, like I'm 15 years old." },
  { icon: Briefcase, hint: "Practice the questions that matter.", title: "Prepare for an interview", prompt: "Help me prepare for a software developer job interview: common questions and strong sample answers." },
  { icon: TrendingUp, hint: "Ideas, audience and first steps.", title: "Brainstorm a business idea", prompt: "Give me 5 small online business ideas I can start with low money, with first steps for each." },
  { icon: Languages, hint: "Natural, not word-for-word.", title: "Translate and polish text", prompt: "Translate this into natural Hindi and English: 'Thank you for your support, we will reach out soon.'" },
  { icon: PenLine, hint: "Catchy lines for any platform.", title: "Write a social media post", prompt: "Write a catchy LinkedIn post announcing the launch of my new startup, with 3 hashtags." },
  { icon: Bug, hint: "Find and fix the problem fast.", title: "Debug my code", prompt: "My JavaScript fetch call returns 'undefined'. Explain the common causes and how to fix them with async/await." },
  { icon: Database, hint: "Clear tables and queries.", title: "Write an SQL query", prompt: "Write an SQL query to find the top 5 customers by total spend last month, and explain it." },
  { icon: ListChecks, hint: "Get your day under control.", title: "Make a to-do plan", prompt: "Help me turn my busy week into a simple, prioritised to-do plan. Ask me what I have on." },
  { icon: Calculator, hint: "Budget, savings and EMIs.", title: "Plan my monthly budget", prompt: "Help me make a monthly budget for a ₹40,000 salary, with savings and an emergency fund." },
  { icon: Globe, hint: "Latest facts from the web.", title: "Research a topic", prompt: "Research the latest news on electric cars in India and summarise the key points with sources." },
  { icon: Sparkles, hint: "Fresh names that stand out.", title: "Name my brand", prompt: "Suggest 10 short, catchy brand names for a modern tea cafe, with a one-line reason for each." },
];
const TONE_ORDER = ["indigo", "sky", "emerald", "violet", "amber", "pink"];

// Three different starters (with different colours) each time the home page opens.
function pickStarters() {
  const pool = [...STARTERS];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  const t = Math.floor(Math.random() * TONE_ORDER.length);
  return pool.slice(0, 3).map((s, i) => ({ ...s, tone: TONE_ORDER[(t + i * 2) % TONE_ORDER.length] }));
}

// The Counsellor tab: Krish Robo, a cheerful friend for whatever is on your mind (see backend/counsellor.py).
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
// The mood check-in on the Counsellor welcome. Picks are kept in this browser only (Counsellor chats are never
// saved to memory), so the next visit can ask whether things got better; Pro and Max also see their mood week.
const MOODS = [
  { id: "great", icon: Sun, label: "Great", feel: "great", tint: "bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300" },
  { id: "okay", icon: CloudSun, label: "Okay", feel: "okay", tint: "bg-sky-100 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300" },
  { id: "tired", icon: Moon, label: "Tired", feel: "tired", tint: "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300" },
  { id: "low", icon: CloudRain, label: "Low", feel: "low", tint: "bg-slate-200 text-slate-600 dark:bg-slate-500/20 dark:text-slate-300" },
  { id: "stressed", icon: Zap, label: "Stressed", feel: "stressed", tint: "bg-orange-100 text-orange-600 dark:bg-orange-500/15 dark:text-orange-300" },
  { id: "angry", icon: Flame, label: "Angry", feel: "angry", tint: "bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300" },
];
const MOOD_KEY = "krish-counsel-mood";

// Every check-in, oldest first (an older single pick is read as a list of one).
function moodHistory() {
  try {
    const saved = JSON.parse(localStorage.getItem(MOOD_KEY) || "[]");
    return (Array.isArray(saved) ? saved : [saved]).filter((x) => MOODS.some((m) => m.id === x?.id) && x.at);
  } catch { return []; }
}

function readMood() {
  const saved = moodHistory().pop();
  const days = Math.floor((Date.now() - new Date(saved?.at).getTime()) / 86400000);
  return saved && days >= 0 && days <= 14 ? { mood: MOODS.find((m) => m.id === saved.id), days } : null;
}

function saveMood(id) {
  try {
    localStorage.setItem(MOOD_KEY, JSON.stringify([...moodHistory(), { id, at: new Date().toISOString() }].slice(-30)));
  } catch { /* optional */ }
}

// The last 7 days, each with that day's latest check-in (or none).
function moodWeek() {
  const byDay = {};
  moodHistory().forEach((x) => { byDay[new Date(x.at).toDateString()] = x.id; });
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(Date.now() - (6 - i) * 86400000);
    return { day: i === 6 ? "Today" : d.toLocaleDateString("en", { weekday: "short" }), mood: MOODS.find((m) => m.id === byDay[d.toDateString()]) };
  });
}

const TAGLINES = ["Let's talk!", "I'm here for you", "Smile please! 😄", "Good vibes only", "Aaj kya scene hai?"];

function pickGreeting(name) {
  const h = new Date().getHours();
  const part = h >= 5 && h < 12 ? "morning" : h >= 12 && h < 17 ? "afternoon" : h >= 17 && h < 22 ? "evening" : "night";
  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  const [hello, lead, highlight] = pick(GREETINGS[part]);
  return { hello: name ? hello.replace("{name}", name) : hello.replace(/,? \{name\}/, ""), lead, highlight, tagline: pick(TAGLINES) };
}

const CODE_FILE_RE = /\.(html?|css|m?js|jsx)$/i;

export default function Workspace({ mode = null }) {
  const counselling = mode === "counsellor";
  const { user } = useAuth();
  const proPlan = user?.plan === "pro" || user?.plan === "max";
  const t = useT();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [projectId, setProjectId] = useState(searchParams.get("project") || null);
  const [project, setProject] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [breatheOpen, setBreatheOpen] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  // The code side panel: null (closed), "live" (the newest reply with code, following the stream) or a message id.
  const [codePanel, setCodePanel] = useState(null);
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
  // Think (careful answers) and Study (tutor) stay on for this browser until turned off.
  const [think, setThink] = useState(() => readFlag("krish.think"));
  const [study, setStudy] = useState(() => readFlag("krish.study"));
  const toggleThink = () => setThink((v) => { saveFlag("krish.think", !v); return !v; });
  const toggleStudy = () => setStudy((v) => { saveFlag("krish.study", !v); return !v; });
  // The welcome screen can turn Study mode on (WelcomeQuestions).
  useEffect(() => {
    const on = (e) => { if (e.detail === "krish.study") setStudy(true); };
    window.addEventListener("krish-flag", on);
    return () => window.removeEventListener("krish-flag", on);
  }, []);
  // Web search is off unless turned on; when on, every question searches the web and cites its sources.
  const [webMode, setWebMode] = useState(() => readFlag("krish.web"));
  const toggleWeb = () => setWebMode((v) => { saveFlag("krish.web", !v); return !v; });
  // Where Search looks (Web, Academic, Social, Video) and Pro search (several searches, reads the pages).
  const [focus, setFocusState] = useState(() => { try { return localStorage.getItem("krish.focus") || "web"; } catch { return "web"; } });
  const [pro, setPro] = useState(() => readFlag("krish.pro"));
  const setFocus = (f) => {
    setFocusState(f);
    try { localStorage.setItem("krish.focus", f); } catch { /* optional */ }
    if (!webMode) { setWebMode(true); saveFlag("krish.web", true); }
  };
  const togglePro = () => setPro((v) => {
    saveFlag("krish.pro", !v);
    if (!v && !webMode) { setWebMode(true); saveFlag("krish.web", true); }
    return !v;
  });
  // Krish suggested the web for this answer: turn web search on and answer again with it.
  const searchWebNow = () => {
    if (!webMode) { setWebMode(true); saveFlag("krish.web", true); }
    regenerate({ withWeb: true });
  };
  const searchOpts = () => (webMode && !counselling ? { web: true, focus, pro } : { web: false });

  const scrollRef = useRef(null);
  const abortRef = useRef(null);
  // Bumped whenever the screen switches chats, so a reply or load still running for the
  // chat that was left can't write its messages into the one now open.
  const chatSeq = useRef(0);
  const leaveChat = () => {
    chatSeq.current += 1;
    if (abortRef.current) abortRef.current.abort();
  };
  const streamTextRef = useRef("");
  const streamSourcesRef = useRef([]);
  const streamRelatedRef = useRef([]);
  const streamWebHintRef = useRef(false);
  const streamStepsRef = useRef([]);

  // Chat always uses Krish AI's tools (web search, code, files) whenever the model supports them; no mode switch.
  const agentAvailable = !counselling && !!(caps && model && caps.agent?.[model]);
  const voiceEnabled = !!caps?.voice;
  const speechEnabled = !!caps?.serverSpeech || browserSpeechAvailable();

  const activeConv = conversations.find((c) => c.id === activeId);
  const chatAgent = counselling ? KRISH_ROBO : null;  // every Counsellor talk is with Krish Robo

  // Like Claude: the chat moves only when you open a chat (to its newest message) or send one
  // (your question near the top, the answer writing out below it). While Krish writes and when
  // it finishes, the view stays where it is, so you can read from the start of the answer.
  const scrollNext = useRef("bottom");
  const placeView = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (!el) return;
      const list = el.querySelector("[data-testid=message-list-container]");
      // The welcome screen starts at its top.
      if (!list) { el.scrollTop = 0; return; }
      const target = scrollNext.current;
      scrollNext.current = null;
      if (target === "bottom") el.scrollTop = el.scrollHeight;
      else if (typeof target === "number") {
        const q = list.children[target];
        if (q) el.scrollTop += q.getBoundingClientRect().top - el.getBoundingClientRect().top - 16;
      }
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

  useEffect(() => { placeView(); }, [messages, loadingConv, placeView]);

  // A reply that builds something opens the side panel on its own: on a computer as soon as the first
  // file is written, on a phone (where the panel is full screen) or for a ready reply (your own code) once it is finished.
  const streamHasCode = useMemo(() => streaming && extractFiles(streamText, true).length > 0, [streaming, streamText]);
  const phone = () => window.matchMedia?.("(max-width: 767px)").matches;
  const autoOpened = useRef(false);
  useEffect(() => { if (streaming) autoOpened.current = false; }, [streaming]);
  useEffect(() => {
    if (streamHasCode && !autoOpened.current && !phone()) { autoOpened.current = true; setCodePanel("live"); }
  }, [streamHasCode]);
  const latestCode = useMemo(
    () => [...messages].reverse().find((m) => m.role === "assistant" && extractFiles(m.content).length),
    [messages]);
  useEffect(() => {
    if (!streaming && autoOpened.current === false && latestCode && latestCode.id.startsWith("ai-")) {
      autoOpened.current = true;
      setCodePanel("live");
    }
  }, [streaming, latestCode]);
  useEffect(() => { setCodePanel(null); }, [activeId]);
  const panelLive = codePanel === "live";
  const panelMessage = panelLive ? (streaming && streamHasCode ? null : latestCode) : messages.find((m) => m.id === codePanel);
  const panelContent = panelLive && streaming && streamHasCode ? streamText : panelMessage?.content;

  // React to ?conversation= and ?project= deep links (e.g. from a project view).
  useEffect(() => {
    const convParam = searchParams.get("conversation");
    const projParam = searchParams.get("project");
    if (projParam) setProjectId(projParam);
    if (convParam && convParam !== activeId) openConversation(convParam);
    else if (projParam) { leaveChat(); setActiveId(null); setMessages([]); }
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
    leaveChat();
    const seq = chatSeq.current;
    scrollNext.current = "bottom";
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
      if (seq !== chatSeq.current) return;
      setMessages(data.messages);
      if (data.conversation?.model) setModel(menuModel(data.conversation.model));
      setProjectId(data.conversation?.projectId || null);
      let files = [];
      try { files = (await api.get(`/conversations/${id}/files`)).data; } catch { /* none */ }
      if (seq === chatSeq.current) setAttachments(files);
    } catch (e) {
      if (seq === chatSeq.current) toast.error(formatApiError(e));
    } finally {
      if (seq === chatSeq.current) setLoadingConv(false);
    }
  };

  const newConversation = () => {
    leaveChat();
    setAgentId(null);
    setPreviewItem(null);
    setLoadingConv(false);
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
      lines.push(m.role === "user" ? "## You" : `## Krish AI${m.model ? ` (${modelLabel(m.model)})` : ""}`);
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

  const runStream = async (url, body, convId, onText) => {
    setStreaming(true);
    setStreamText("");
    setStreamSources([]);
    setStreamSteps([]);
    streamTextRef.current = "";
    streamSourcesRef.current = [];
    streamRelatedRef.current = [];
    streamWebHintRef.current = false;
    streamStepsRef.current = [];
    const controller = new AbortController();
    abortRef.current = controller;
    const seq = chatSeq.current;

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 402) showPlanLimit(err.detail);
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
          if (eventName === "plan_limit") {
            showPlanLimit(JSON.parse(dataStr || '""'));
            continue;
          }
          if (eventName === "web_hint") {
            streamWebHintRef.current = true;
            continue;
          }
          if (eventName === "related") {
            streamRelatedRef.current = JSON.parse(dataStr || "[]");
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
            onText?.(streamTextRef.current);
          }
        }
      }
    } catch (e) {
      // When the reply already explains the failure (the server writes a note with Regenerate), no technical toast.
      if (e.name !== "AbortError" && !streamTextRef.current.trim()) toast.error(e.message || "Something went wrong");
    } finally {
      const stopped = controller.signal.aborted;
      if (abortRef.current === controller) abortRef.current = null;
      setStreaming(false);
      const finalText = streamTextRef.current;
      // The user moved to another chat: the server keeps what was written in the old one,
      // and none of it belongs on the screen now.
      const left = seq !== chatSeq.current;
      // A stopped reply keeps what was written so far (the server saves the same part).
      const steps = stopped ? streamStepsRef.current.map((s) => (s.status === "running" ? { ...s, status: "stopped", summary: "Stopped" } : s))
        : streamStepsRef.current;
      if (!left && (finalText || steps.length)) {
        setMessages((m) => [...m, { id: `ai-${Date.now()}`, role: "assistant", content: finalText, model, stopped,
          sources: streamSourcesRef.current.length ? streamSourcesRef.current : null, related: streamRelatedRef.current,
          webHint: streamWebHintRef.current,
          steps, media: steps.flatMap((s) => s.media || []) }]);
      }
      setStreamText("");
      setStreamSources([]);
      setStreamSteps([]);
      // Sync ordering/titles/ids from server. After Stop the server needs a moment to save the
      // part already written, so wait for it rather than replacing the reply with nothing.
      if (!left) try {
        for (let tries = 0; ; tries++) {
          const { data } = await api.get(`/conversations/${convId}`);
          if (seq !== chatSeq.current) break;
          const saved = data.messages[data.messages.length - 1]?.role === "assistant";
          if (saved || !(stopped && (finalText || steps.length))) { setMessages(data.messages); break; }
          if (tries >= 5) break; // keep the local copy
          await new Promise((r) => setTimeout(r, 400));
        }
      } catch { /* keep local */ }
      loadConversations();
    }
    return streamTextRef.current;
  };

  const ensureConversation = async () => {
    if (activeId) return activeId;
    const { data } = await api.post("/conversations",
      counselling ? { mode, agent: KRISH_ROBO.id } : projectId ? { projectId } : {});
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
    // Photos the AI can look at directly; every other file (HEIC, SVG, HTML, code, ZIP...) is read on the server.
    if (/^image\/(png|jpe?g|webp|gif)$/.test(file.type || "")) return attachImage(file);
    if (/^video\/(mp4|webm|quicktime|x-m4v)$/.test(file.type || "")) return attachVideo(file);
    // Web code files (HTML, CSS, JS) go with the message as they are, so Krish shows them exactly as given.
    if (CODE_FILE_RE.test(file.name || "") && file.size < 400000) {
      const code = await file.text();
      setAttachments((a) => [...a.filter((x) => x.filename !== file.name), { id: `code-${Date.now()}-${file.name}`, filename: file.name, status: "ready", code }]);
      toast.success(`${file.name} attached`);
      return;
    }
    setUploading(true);
    try {
      const convId = await ensureConversation();
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post(`/conversations/${convId}/files`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setAttachments((a) => [...a, data]);
      if (data.status === "failed") toast.error(`Could not read ${data.filename}`);
      else if (!data.chunkCount) toast.message(`${data.filename} attached. It has no text to read, but you can still ask about it.`);
      else toast.success(`${data.filename} attached`);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setUploading(false);
    }
  };

  const removeAttachment = async (fid) => {
    if (!String(fid).startsWith("code-")) {
      try { await api.delete(`/files/${fid}`); } catch { /* ignore */ }
    }
    setAttachments((a) => a.filter((x) => x.id !== fid));
  };

  // `composer`: sent from the message box (typed, or dictated text), so attached pictures go too.
  const sendMessage = async (text, { voice = false, voiceLang, onText, frame, composer = text === undefined } = {}) => {
    const images = composer ? pendingImages : [];
    const groups = [...new Map(images.filter((i) => i.videoGroup).map((i) => [i.videoGroup.id, i.videoGroup])).values()];
    const typed = (text ?? input).trim() || (groups.length ? "What happens in this video?" : images.length ? "What's in this image?" : "");
    // Tell the model which images are video frames (and when they were taken).
    const videoNotes = groups.map((g) => {
      const times = images.filter((i) => i.videoGroup?.id === g.id).map((i) => `${i.time.toFixed(1)}s`);
      return `[Video attached: “${g.name}” (${g.duration.toFixed(1)}s). Its ${times.length} frames below were sampled at ${times.join(", ")}.]`;
    });
    const codeFiles = composer ? attachments.filter((a) => a.code !== undefined) : [];
    const codeBlocks = codeFiles.map((f) => {
      const fence = f.code.includes("```") ? "````" : "```";
      return `${fence}${f.filename.split(".").pop().toLowerCase()} ${f.filename}\n${f.code.replace(/\s+$/, "")}\n${fence}`;
    });
    // Voice chat with the camera or screen on sends one picture of what it shows right now.
    const liveNote = frame ? [`[Live ${frame.source} view: the picture below is what my ${frame.source} shows right now.]`] : [];
    const content = [...videoNotes, ...liveNote, typed, ...codeBlocks].join("\n\n").trim();
    if (!content || streaming) return "";

    let convId;
    try {
      convId = await ensureConversation();
    } catch (e) {
      toast.error(formatApiError(e));
      return "";
    }
    if (frame) {
      try {
        const fd = new FormData();
        fd.append("file", new File([frame.blob], `${frame.source}-${Date.now()}.jpg`, { type: "image/jpeg" }));
        fd.append("conversationId", convId);
        const { data } = await api.post("/media", fd, { headers: { "Content-Type": "multipart/form-data" } });
        images.push(data);
      } catch { /* answer without the picture */ }
    }

    const imageIds = images.map((i) => i.id);
    scrollNext.current = messages.length;
    setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: "user", content, images: imageIds, conversationId: convId }]);
    if (composer) { setInput(""); setPendingImages([]); if (codeFiles.length) setAttachments((a) => a.filter((x) => x.code === undefined)); }
    return runStream(`${API}/conversations/${convId}/stream`, { content, model, images: imageIds, agent: agentAvailable, think: think && !counselling, study: study && !counselling, ...searchOpts(), voice, voiceLang }, convId, onText);
  };

  // A request handed over from another page (e.g. "make a video of this" in Docs) starts a new chat once ready.
  const handoffDone = useRef(false);
  useEffect(() => {
    if (handoffDone.current || counselling || !model || !caps) return;
    let text = "";
    try { text = sessionStorage.getItem("krish.handoff") || ""; sessionStorage.removeItem("krish.handoff"); } catch { /* ignore */ }
    handoffDone.current = true;
    if (text) sendMessage(text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, caps]);

  // Voice mode keeps its first callback for the whole session; route through a ref
  // so each utterance uses the current conversation, model and agent setting.
  const sendRef = useRef(sendMessage);
  sendRef.current = sendMessage;

  const regenerate = async ({ withWeb = false } = {}) => {
    if (!activeId || streaming) return;
    setMessages((m) => {
      const copy = [...m];
      if (copy.length && copy[copy.length - 1].role === "assistant") copy.pop();
      return copy;
    });
    const search = withWeb ? { web: true, focus, pro } : searchOpts();
    await runStream(`${API}/conversations/${activeId}/regenerate`, { model, agent: agentAvailable, think: think && !counselling, study: study && !counselling, ...search }, activeId);
  };

  // Edit an earlier question (like ChatGPT): the answers after it go, and Krish answers the new wording.
  const editMessage = async (id, content) => {
    const text = (content || "").trim();
    if (!activeId || streaming || !text) return;
    setMessages((m) => {
      const i = m.findIndex((x) => x.id === id);
      return i < 0 ? m : [...m.slice(0, i), { ...m[i], content: text }];
    });
    await runStream(`${API}/conversations/${activeId}/messages/${id}/edit`, { content: text, model, agent: agentAvailable, think: think && !counselling, study: study && !counselling, ...searchOpts() }, activeId);
  };

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      {/* Desktop sidebar */}
      <div className="hidden lg:block">
        <Sidebar conversations={conversations} activeId={activeId} onSelect={openConversation}
          onNew={newConversation} onDelete={deleteConversation} onRename={renameConversation}
          newLabel={counselling ? t("newSession") : undefined} onCollapse={() => {}} searchContent={!counselling} />
      </div>

      {/* Mobile drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" data-testid="mobile-drawer">
          <div className="krish-fade-in absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]" onClick={() => setSidebarOpen(false)} />
          <div className="krish-drawer-in krish-canvas absolute left-0 top-0 h-full max-w-[85vw] shadow-2xl">
            <Sidebar conversations={conversations} activeId={activeId} onSelect={openConversation}
              onNew={newConversation} onDelete={deleteConversation} onRename={renameConversation}
          newLabel={counselling ? t("newSession") : undefined} onCollapse={() => setSidebarOpen(false)} searchContent={!counselling} />
          </div>
        </div>
      )}

      {/* Main */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header data-testid="chat-workspace-header" className="@container z-40 flex items-center justify-between gap-2 px-2 py-2 sm:px-6 sm:py-4">
          <div className="flex min-w-0 items-center gap-1 sm:gap-3">
            <button onClick={() => setSidebarOpen(true)} data-testid="open-sidebar-button" aria-label="Show chats"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground active:bg-surface lg:hidden">
              <PanelLeft className="h-5 w-5" />
            </button>
            <h1 data-testid="active-conversation-title" className={`krish-tab-title truncate text-sm font-semibold tracking-tight max-sm:hidden ${!activeConv && !counselling ? "invisible" : ""}`}>
              {activeConv ? activeConv.title : t(counselling ? "counsellor" : "newConversation")}
            </h1>
            {project && (
              <button onClick={() => navigate(`/projects/${project.id}`)} data-testid="active-project-badge"
                className="flex shrink-0 items-center gap-1.5 rounded-full border border-border-strong bg-surface px-2.5 py-1 text-[11px] font-medium text-brand hover:border-primary/50">
                <FolderKanban className="h-3 w-3" /> {project.name}
              </button>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
            {!counselling && <UpgradeButton />}
            {activeConv && messages.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => setShareOpen(true)} data-testid="share-conversation-button"
                className={`gap-1.5 hover:text-foreground ${activeConv.shareId ? "text-brand" : "text-muted-foreground"}`}>
                <Link2 className="h-3.5 w-3.5" />
                <span className="hidden text-xs @2xl:inline">{t(activeConv.shareId ? "shared" : "share")}</span>
              </Button>
            )}
            {activeId && messages.length > 0 && (
              <Button variant="ghost" size="sm" onClick={exportConversation} data-testid="export-conversation-button" className="gap-1.5 text-muted-foreground hover:text-foreground @max-xl:hidden">
                <Download className="h-3.5 w-3.5" />
                <span className="hidden text-xs @2xl:inline">{t("export")}</span>
              </Button>
            )}
            {!counselling && <ModelMenu models={models} model={model} setModel={setModel} caps={caps} label={t("model")} />}
            <button onClick={newConversation} data-testid="mobile-new-chat-button" aria-label={t(counselling ? "newSession" : "newChat")}
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
            counselling ? <CounselEmptyState onPick={(p) => sendMessage(p)} onBreathe={() => setBreatheOpen(true)}
              last={conversations[0]} onResume={openConversation}
              onCall={() => { unlockSpeech(); setVoiceOpen(true); }} /> : <EmptyState onPick={(p) => sendMessage(p)} />
          ) : (
            <div data-testid="message-list-container" className="mx-auto w-full max-w-3xl space-y-6 px-4 py-5 sm:py-8">
              {messages.map((m, i) => <MessageBubble key={m.id} message={m} voiceEnabled={speechEnabled} onOpenMedia={setPreviewItem}
                onEdit={!streaming && m.role === "user" && !String(m.id).startsWith("tmp-") ? (text) => editMessage(m.id, text) : undefined}
                onAsk={i === messages.length - 1 && !streaming ? (q) => sendMessage(q) : undefined}
                onOpenCode={() => setCodePanel(m.id === latestCode?.id ? "live" : m.id)}
                codeActive={!!codePanel && panelMessage?.id === m.id} quickReplies={counselling}
                agent={chatAgent} voice={chatAgent?.voice} />)}
              {streaming && (
                <MessageBubble message={{ id: "streaming", role: "assistant", content: streamText, model, sources: streamSources,
                  steps: streamSteps, media: streamSteps.flatMap((s) => s.media || []) }} streaming onOpenMedia={setPreviewItem}
                  onOpenCode={() => setCodePanel("live")} codeActive={panelLive} agent={chatAgent} />
              )}
              {!streaming && messages.length > 0 && messages[messages.length - 1].role === "assistant" && (
                <div className="flex flex-wrap items-center justify-center gap-2 pt-1"
                  // Keep the typing focus so the phone tab bar doesn't reappear and move these buttons mid-tap.
                  onMouseDown={(e) => e.preventDefault()}>
                  {messages[messages.length - 1].webHint && !webMode && (
                    <Button size="sm" onClick={searchWebNow} data-testid="web-hint-button"
                      title="This answer may change over time. Turn on web search for the latest."
                      className="gap-1.5 rounded-full bg-primary text-primary-foreground shadow-sm hover:bg-primary/90">
                      <Globe className="h-3.5 w-3.5" /> Get the latest from the web
                    </Button>
                  )}
                  <Button variant="outline" size="sm" onClick={() => regenerate()} data-testid="regenerate-button"
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
          <p data-testid="counsellor-care-note" className="mx-auto flex w-full max-w-3xl flex-wrap items-center justify-center gap-x-3 gap-y-0.5 px-5 text-center text-[11px] leading-snug text-muted-foreground">
            {messages.length > 0 && (
              <button onClick={() => setBreatheOpen(true)} data-testid="breathe-button-chat"
                className="inline-flex items-center gap-1 font-semibold text-violet-600 hover:underline dark:text-violet-300">
                <Wind className="h-3 w-3" /> Breathe with me
              </button>
            )}
            {/* The helpline for where they said they live (welcome questions); India's when unknown. */}
            {!user?.about?.country || user.about.country === "India"
              ? <span>Need urgent help? Tele-MANAS 14416, free 24x7 💛</span>
              : <span>Need urgent help? Call your local emergency number, or <a href="https://findahelpline.com" target="_blank" rel="noreferrer" className="underline">findahelpline.com</a> 💛</span>}
          </p>
        )}
        <ComposerInput value={input} onChange={setInput} onSend={(dictated) => sendMessage(typeof dictated === "string" ? dictated : undefined, { composer: true })} onStop={stopGeneration}
          streaming={streaming} disabled={loadingConv}
          onAttach={counselling ? undefined : attachFile} attachments={attachments} onRemoveAttachment={removeAttachment} uploading={uploading}
          images={pendingImages} onRemoveImage={(id) => setPendingImages((imgs) => imgs.filter((i) => i.id !== id))}
          agentMode={agentAvailable} agentAvailable={agentAvailable}
          agentHint="Agent mode needs a provider API key for this model on the backend"
          thinkMode={think} onToggleThink={counselling ? undefined : toggleThink}
          studyMode={study} onToggleStudy={counselling ? undefined : toggleStudy}
          webMode={webMode} onToggleWeb={counselling ? undefined : toggleWeb}
          searchFocus={focus} onSearchFocus={setFocus} proSearch={pro} onTogglePro={togglePro}
          voiceEnabled={voiceEnabled} voiceHint="Voice needs GROQ_API_KEY (free) on the backend"
          onVoiceMode={() => { unlockSpeech(); setVoiceOpen(true); }}
          placeholder={chatAgent ? `Talk to ${chatAgent.name}…` : counselling ? "Type anything… how's your day going? 😊" : undefined} />
      </div>
      {counselling && <BreatheDialog open={breatheOpen} onOpenChange={setBreatheOpen} onDone={(text) => sendMessage(text)}
        pro={proPlan} />}
      {codePanel && panelContent && (
        <CodePanel content={panelContent} streaming={panelLive && streaming && streamHasCode} onClose={() => setCodePanel(null)} />
      )}
      <ShareDialog open={shareOpen} onOpenChange={setShareOpen} conversation={activeConv}
        onChange={(shareId) => setConversations((cs) => cs.map((c) => (c.id === activeId ? { ...c, shareId } : c)))} />
      {previewItem && <PreviewPanel item={previewItem} onClose={() => setPreviewItem(null)} />}
      {voiceOpen && <VoiceMode onClose={() => setVoiceOpen(false)} onCancelReply={stopGeneration}
        agent={chatAgent} voice={chatAgent?.voice}
        onUtterance={(t, opts) => sendRef.current(t, { voiceLang: getVoiceLang(), ...opts, voice: true })} />}
    </div>
  );
}

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

function greetingFor(name) {
  const h = new Date().getHours();
  const part = h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  return name ? `${part}, ${name}` : part;
}

// Home screen topics: each tab shows four ready-made requests.
const TOPICS = [
  { id: "popular", label: "Popular", icon: Sparkles },
  { id: "write", label: "Write", icon: PenLine, items: [
    { icon: Mail, title: "Draft a professional email", hint: "Polite, clear and to the point.", prompt: "Write a polite, professional email asking my manager for a day off next Friday." },
    { icon: PenLine, title: "Write a social media post", hint: "Catchy lines for any platform.", prompt: "Write a catchy LinkedIn post announcing the launch of my new startup, with 3 hashtags." },
    { icon: Languages, title: "Translate and polish text", hint: "Natural, not word-for-word.", prompt: "Translate this into natural Hindi and English: 'Thank you for your support, we will reach out soon.'" },
    { icon: FileText, title: "Summarise a long text", hint: "The key points in seconds.", prompt: "I'll paste a long article. Summarise it into 5 clear bullet points." },
  ] },
  { id: "code", label: "Code", icon: Braces, items: [
    { icon: Bug, title: "Debug my code", hint: "Find and fix the problem fast.", prompt: "My JavaScript fetch call returns 'undefined'. Explain the common causes and how to fix them with async/await." },
    { icon: Database, title: "Write an SQL query", hint: "Clear tables and queries.", prompt: "Write an SQL query to find the top 5 customers by total spend last month, and explain it." },
    { icon: Braces, title: "Build a landing page", hint: "A ready-to-use web page.", prompt: "Build a modern, responsive landing page for a coffee shop with a menu and contact section." },
    { icon: Network, title: "Explain a system design", hint: "Big ideas, made simple.", prompt: "Explain how a URL shortener like bit.ly works, with a simple system design diagram." },
  ] },
  { id: "learn", label: "Learn", icon: GraduationCap, items: [
    { icon: GraduationCap, title: "Explain a topic simply", hint: "Learn anything, step by step.", prompt: "Explain how the stock market works in simple words, like I'm 15." },
    { icon: Globe, title: "Research a topic", hint: "Latest facts from the web.", prompt: "Research the latest news on electric cars in India and summarise the key points with sources." },
    { icon: BookOpen, title: "Quiz me", hint: "Practice with quick questions.", prompt: "Quiz me with 5 questions on Indian history, one at a time, and tell me if I'm right." },
    { icon: Briefcase, title: "Prepare for an interview", hint: "Practice the questions that matter.", prompt: "Help me prepare for a marketing job interview. Ask me common questions one by one and give feedback." },
  ] },
  { id: "plan", label: "Plan", icon: ListChecks, items: [
    { icon: ListChecks, title: "Make a to-do plan", hint: "Get your day under control.", prompt: "Help me turn my busy week into a simple, prioritised to-do plan. Ask me what I have on." },
    { icon: Calculator, title: "Plan my monthly budget", hint: "Budget, savings and EMIs.", prompt: "Help me make a monthly budget for a ₹40,000 salary, with savings and an emergency fund." },
    { icon: Plane, title: "Plan a trip", hint: "Day-by-day, on budget.", prompt: "Plan a 3-day budget trip to Jaipur with places to visit, food and costs." },
    { icon: Dumbbell, title: "Make a workout plan", hint: "Simple routine, no gym needed.", prompt: "Make me a 4-week home workout plan for beginners, 30 minutes a day, no equipment." },
  ] },
  { id: "create", label: "Create", icon: Lightbulb, items: [
    { icon: Sparkles, title: "Name my brand", hint: "Fresh names that stand out.", prompt: "Suggest 10 short, catchy brand names for a modern tea cafe, with a one-line reason for each." },
    { icon: TrendingUp, title: "Brainstorm a business idea", hint: "Ideas, audience and first steps.", prompt: "Brainstorm 5 small business ideas I can start in India with under ₹50,000, with first steps." },
    { icon: Lightbulb, title: "Create a picture", hint: "Describe it, Krish draws it.", prompt: "Create a picture of a cozy reading corner by a rainy window, warm light, realistic style." },
    { icon: ChefHat, title: "Suggest a dinner recipe", hint: "Quick, healthy and tasty.", prompt: "Suggest a quick, healthy vegetarian dinner recipe I can make in 20 minutes." },
  ] },
];
TOPICS[0].items = [TOPICS[2].items[1], TOPICS[3].items[0], TOPICS[1].items[0], TOPICS[5].items[0]];

function TopicCard({ s, i, onPick }) {
  const t = TONES[TONE_ORDER[i % TONE_ORDER.length]];
  return (
    <button data-testid={`prompt-starter-card-${i}`} onClick={() => onPick(s.prompt)}
      className={`krish-topic-card group relative flex items-center gap-3 overflow-hidden rounded-xl border border-white/70 bg-gradient-to-br ${t.card} to-white/70 px-3.5 py-2.5 text-left shadow-[0_8px_30px_rgba(99,102,241,0.08)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_40px_rgba(99,102,241,0.18)] active:translate-y-0 active:scale-[0.99] dark:border-white/5 dark:to-card/60`}
      style={{ animationDelay: `${0.04 * i}s` }}>
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-transform group-hover:scale-110 ${t.icon}`}>
        <s.icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{s.title}</p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground max-sm:hidden">{s.hint}</p>
      </div>
      <ArrowUpRight className={`h-4 w-4 shrink-0 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 ${t.arrow}`} />
    </button>
  );
}

// Lines the hero types out one after another, like a short looping video.
const HERO_LINES = ["write your emails", "debug your code", "plan your week", "research any topic", "make slides and pictures", "explain anything simply"];

function TypingLine() {
  const [i, setI] = useState(0);
  const [n, setN] = useState(0);
  const [del, setDel] = useState(false);
  useEffect(() => {
    const word = HERO_LINES[i];
    const done = !del && n === word.length;
    const empty = del && n === 0;
    const id = setTimeout(() => {
      if (done) setDel(true);
      else if (empty) { setDel(false); setI((i + 1) % HERO_LINES.length); }
      else setN(n + (del ? -1 : 1));
    }, done ? 1400 : empty ? 250 : del ? 35 : 65);
    return () => clearTimeout(id);
  }, [i, n, del]);
  return (
    <p className="mt-1.5 text-sm text-muted-foreground sm:text-base" aria-live="off">
      Krish can <span className="font-semibold text-foreground">{HERO_LINES[i].slice(0, n)}</span>
      <span className="krish-caret ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[3px] bg-[#FF8A1E]" />
    </p>
  );
}

function EmptyState({ onPick }) {
  const t = useT();
  const { user } = useAuth();
  const first = user?.about?.callMe || (user?.name || "").trim().split(/\s+/)[0];
  const [topic, setTopic] = useState("popular");
  const items = TOPICS.find((x) => x.id === topic)?.items || [];
  return (
    <div data-testid="empty-state-welcome" className="relative mx-auto flex min-h-full max-w-3xl flex-col justify-center px-3 py-4 sm:px-4">
      <div className="krish-hero radha-fade-up relative overflow-hidden rounded-3xl border border-border bg-card/60 px-5 py-4 sm:px-8 sm:py-5 [@media(max-height:760px)]:sm:py-3">
        <div className="krish-aurora" aria-hidden="true"><span /><span /><span /></div>
        <div className="krish-hero-grid" aria-hidden="true" />
        <div className="relative flex items-center gap-3 sm:gap-4 md:gap-8">
          <div className="min-w-0 flex-1">
            {t.lang === "en" && <p className="text-sm font-medium text-muted-foreground">{greetingFor(first)}</p>}
            <h2 className="mt-0.5 text-xl font-semibold tracking-tight text-foreground sm:text-[1.75rem] sm:leading-[1.2]">
              {t.lang === "en" ? <>How can <span className="krish-gradient-text">Krish AI</span> help today?</> : t.parts("helpToday", { krish: <span key="k" className="krish-gradient-text">Krish AI</span> })}
            </h2>
            {t.lang === "en" && <TypingLine />}
          </div>
          <div className="relative shrink-0">
            <div className="krish-orbit" aria-hidden="true"><i /><i /><i /></div>
            <Mascot className="krish-float relative h-16 w-auto sm:h-24 md:h-28 [@media(max-height:760px)]:md:h-20" />
          </div>
        </div>
      </div>

      <div role="tablist" aria-label="Ideas" className="krish-no-scrollbar mt-4 flex gap-1.5 overflow-x-auto pb-1 sm:justify-center">
        {TOPICS.map((x) => {
          const on = x.id === topic;
          return (
            <button key={x.id} role="tab" aria-selected={on} data-testid={`topic-${x.id}`} onClick={() => setTopic(x.id)}
              className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-all duration-200 ${
                on ? "border-primary bg-primary text-primary-foreground shadow-sm" : "border-border bg-card text-muted-foreground hover:border-foreground/20 hover:text-foreground"}`}>
              <x.icon className="h-3.5 w-3.5" /> {x.label}
            </button>
          );
        })}
      </div>

      <div key={topic} className="mt-2.5 grid w-full gap-2 sm:grid-cols-2 max-sm:[&>*:nth-child(4)]:hidden">
        {items.map((s, i) => <TopicCard key={s.title} s={s} i={i} onPick={onPick} />)}
      </div>
          </div>
  );
}

const Sparkle = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
    <path d="M12 0 L14.5 9.5 L24 12 L14.5 14.5 L12 24 L9.5 14.5 L0 12 L9.5 9.5 Z" />
  </svg>
);

function MoodWeek({ pro }) {
  const navigate = useNavigate();
  const week = useMemo(moodWeek, []);
  if (!pro) {
    return (
      <button onClick={() => navigate("/plans")} data-testid="mood-week-locked"
        className="mt-2.5 flex w-full items-center justify-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground sm:justify-start">
        <Lock className="h-3 w-3" /> See your mood week with <span className="font-semibold text-violet-600 dark:text-violet-300">Pro</span>
      </button>
    );
  }
  return (
    <div data-testid="mood-week" className="mt-3 border-t border-border pt-2.5">
      <p className="text-xs font-semibold text-muted-foreground max-sm:text-center">Your mood week</p>
      <div className="mt-1.5 grid grid-cols-7 gap-1 text-center">
        {week.map((d, i) => (
          <div key={i} className="flex flex-col items-center gap-0.5">
            <span title={d.mood?.label} className={`flex h-8 w-8 items-center justify-center rounded-full ${d.mood ? d.mood.tint : "bg-muted/60"}`}>
              {d.mood ? <d.mood.icon className="h-4 w-4" /> : <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />}
            </span>
            <span className="text-[10.5px] text-muted-foreground">{d.day}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MoodCheckIn({ onPick, pro }) {
  const [last] = useState(readMood);
  const when = last && (last.days === 0 ? "earlier today" : last.days === 1 ? "yesterday" : `${last.days} days ago`);
  const pick = (m) => {
    saveMood(m.id);
    const before = last && last.mood.id !== m.id ? ` Last time I was feeling ${last.mood.feel}.` : "";
    onPick(`I'm feeling ${m.feel} right now.${before}`);
  };
  return (
    <div data-testid="mood-check-in" className="radha-fade-up relative mt-5 rounded-2xl border border-border bg-card/70 px-4 py-3 shadow-sm backdrop-blur-sm sm:mt-6 sm:px-5">
      <p className="text-sm font-semibold text-foreground max-sm:text-center">
        {last ? <>You felt {last.mood.feel} {when}. How are you now?</> : "How are you feeling right now?"}
      </p>
      <div className="mt-2.5 flex flex-wrap justify-center gap-2 sm:justify-start">
        {MOODS.map((m) => (
          <button key={m.id} onClick={() => pick(m)} data-testid={`mood-${m.id}`}
            className={`group flex items-center gap-2 rounded-full border py-1.5 pl-1.5 pr-3 transition-all hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-sm active:scale-95 ${
              last?.mood.id === m.id ? "border-violet-300 bg-violet-50/60 dark:border-violet-400/40 dark:bg-violet-500/10" : "border-border bg-background/60"}`}>
            <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${m.tint}`}><m.icon className="h-3.5 w-3.5" /></span>
            <span className="text-[13px] font-medium text-foreground">{m.label}</span>
          </button>
        ))}
      </div>
      <MoodWeek pro={pro} />
    </div>
  );
}

// Krish Robo, the Counsellor: type below to chat, or call and talk out loud (see lib/counselAgents.js).
function RoboCallCard({ onCall }) {
  return (
    <section data-testid="counsellor-robo" className="mt-6 flex items-center gap-3.5 rounded-3xl border border-border bg-card p-3.5 shadow-sm sm:gap-4 sm:p-4">
      <span className="relative shrink-0">
        <AgentPortrait id={KRISH_ROBO.id} className="h-14 w-14 sm:h-16 sm:w-16" />
        <span className="absolute bottom-0.5 right-0.5 h-3.5 w-3.5 rounded-full border-2 border-card bg-emerald-500" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-bold text-foreground">{KRISH_ROBO.name}</p>
        <p className="text-xs leading-snug text-muted-foreground">Online now. Type below, or call and just talk.</p>
      </div>
      <button onClick={onCall} data-testid="counsellor-robo-call" title={`Call ${KRISH_ROBO.name}`}
        className="flex h-11 shrink-0 items-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-pink-500 px-4 text-sm font-semibold text-white shadow-md transition hover:opacity-90 sm:px-5">
        <Phone className="h-4 w-4" /> Call
      </button>
    </section>
  );
}

function CounselEmptyState({ onPick, onBreathe, last, onResume, onCall }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const pro = user?.plan === "pro" || user?.plan === "max";
  const first = user?.about?.callMe || (user?.name || "").trim().split(/\s+/)[0];
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
            honest advice from Krish Robo, your AI buddy ✨ Any language you like, all chill.
          </p>
          {pro ? (
            <p data-testid="counsellor-pro-badge" className="mt-2.5 inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-violet-500/15 to-pink-500/15 px-3 py-1 text-xs font-semibold text-violet-700 dark:text-violet-200">
              <Sparkles className="h-3.5 w-3.5" /> Counsellor Pro: I remember our last talk
            </p>
          ) : (
            <button onClick={() => navigate("/plans")} data-testid="counsellor-pro-upsell"
              className="mt-2.5 inline-flex items-center gap-1.5 rounded-full border border-violet-200 px-3 py-1 text-xs font-medium text-muted-foreground transition hover:text-foreground dark:border-violet-400/25">
              <Sparkles className="h-3.5 w-3.5 text-violet-500" /> With Pro, I remember our last talk and go deeper
              <ArrowRight className="h-3 w-3" />
            </button>
          )}
        </div>
        <div className="relative shrink-0">
          <p className="krish-hand absolute -left-24 top-4 -rotate-12 text-2xl text-pink-500 max-lg:hidden dark:text-pink-300">
            {g.tagline}
            <svg viewBox="0 0 120 12" className="ml-2 mt-0.5 h-3 w-24" aria-hidden="true"><path d="M2 9 C 40 2, 80 2, 118 6" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" /></svg>
          </p>
          <Mascot className="krish-float h-28 w-auto sm:h-40 md:h-44 lg:h-48" />
        </div>
      </div>
      <RoboCallCard onCall={onCall} />
      <MoodCheckIn onPick={onPick} pro={pro} />
      <div className="mt-3 flex flex-wrap justify-center gap-2 sm:justify-start">
        <button onClick={onBreathe} data-testid="breathe-button"
          className="inline-flex items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-3.5 py-1.5 text-[13px] font-medium text-violet-700 transition hover:-translate-y-0.5 hover:shadow-sm dark:border-violet-400/25 dark:bg-violet-500/10 dark:text-violet-200">
          <Wind className="h-3.5 w-3.5" /> Breathe with me
        </button>
        {last && (
          <button onClick={() => onResume(last.id)} data-testid="counsellor-resume"
            className="inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-1.5 text-[13px] font-medium text-foreground transition hover:-translate-y-0.5 hover:shadow-sm">
            <History className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="shrink-0 text-muted-foreground">Pick up where we left off:</span>
            <span className="truncate">{last.title}</span>
          </button>
        )}
      </div>
      <div className="relative mt-4 grid w-full gap-2.5 sm:mt-5 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
        {COUNSEL_STARTERS.map((s, i) => (
          <StarterCard key={i} s={s} i={i} onPick={onPick} testid={`counsellor-starter-${i}`} hideOnPhone={i >= 2} />
        ))}
      </div>
    </div>
  );
}

function readFlag(key) {
  try { return localStorage.getItem(key) === "1"; } catch { return false; }
}

function saveFlag(key, on) {
  try { localStorage.setItem(key, on ? "1" : "0"); } catch { /* optional */ }
}
