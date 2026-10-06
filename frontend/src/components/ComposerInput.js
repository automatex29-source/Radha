import { useRef, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ArrowUp, Square, X, Paperclip, FileText, Loader2, Bot, Mic, AudioLines, Film, ShieldCheck, Lightbulb, GraduationCap, Globe, ChevronDown, BookOpenText, MessagesSquare, PlaySquare, Sparkles, Check } from "lucide-react";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { mediaUrl } from "@/lib/api";
import { useRecorder } from "@/hooks/useRecorder";
import { transcribe } from "@/lib/voice";
import { useT } from "@/lib/i18n";


const narrowScreen = () => typeof window !== "undefined" && !!window.matchMedia?.("(max-width: 639px)").matches;
const phoneKeyboard = () => typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches;

export default function ComposerInput({
  value, onChange, onSend, onStop, streaming, disabled,
  onAttach, attachments = [], onRemoveAttachment, uploading,
  images = [], onRemoveImage,
  agentMode, onToggleAgent, agentAvailable, agentHint,
  thinkMode, onToggleThink, studyMode, onToggleStudy, webMode, onToggleWeb, searchFocus = "web", onSearchFocus,
  proSearch, onTogglePro,
  voiceEnabled, voiceHint, onVoiceMode, placeholder,
}) {
  const ref = useRef(null);
  const fileRef = useRef(null);
  const rec = useRecorder();
  const t = useT();
  const [transcribing, setTranscribing] = useState(false);
  const [dragging, setDragging] = useState(false);

  // One after another, so the first file's upload creates the chat before the next one needs it.
  const attachAll = async (files) => {
    for (const f of files) await onAttach(f);
  };

  // Pasting a copied file or a screenshot attaches it, like the paperclip. Text copied from Word or
  // Excel also carries a picture of itself, so whenever there's text, the text is what gets pasted.
  const onPaste = (e) => {
    const files = Array.from(e.clipboardData?.files || []);
    if (!onAttach || !files.length || e.clipboardData.getData("text/plain").trim()) return;
    e.preventDefault();
    attachAll(files);
  };

  const dropProps = onAttach ? {
    onDragOver: (e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); setDragging(true); } },
    onDragLeave: (e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false); },
    onDrop: (e) => {
      const files = Array.from(e.dataTransfer?.files || []);
      setDragging(false);
      if (!files.length) return;
      e.preventDefault();
      attachAll(files);
    },
  } : {};
  const canSend = (value.trim() || images.length > 0 || attachments.some((a) => a.code !== undefined)) && !disabled;

  const toggleMic = async () => {
    if (rec.recording) { rec.stop(); return; }
    try {
      // Stops by itself when you finish speaking, then sends what you said (no need to tap Send).
      const blob = await rec.record({ autoStop: true });
      if (!blob) { toast.message("I didn't hear anything. Tap the mic and speak."); return; }
      setTranscribing(true);
      const text = await transcribe(blob);
      if (!text) { toast.message("Didn't catch that — try again."); return; }
      const full = value ? `${value.trimEnd()} ${text}` : text;
      onChange(full);
      if (!streaming && !disabled) onSend(full);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || "Microphone error");
    } finally {
      setTranscribing(false);
      ref.current?.focus();
    }
  };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  // Esc stops a reply that is being written, like ChatGPT and Claude.
  useEffect(() => {
    if (!streaming || !onStop) return undefined;
    const onEsc = (e) => { if (e.key === "Escape" && !e.defaultPrevented && !document.querySelector("[role=dialog]")) onStop(); };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [streaming, onStop]);

  const onKeyDown = (e) => {
    // On phones the keyboard's return key adds a new line; the send button sends.
    if (e.key === "Enter" && !e.shiftKey && !phoneKeyboard()) {
      e.preventDefault();
      if (!streaming && canSend) onSend();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-3 pb-3 pt-1 sm:px-4 sm:pb-5">
      {images.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2" data-testid="composer-images">
          {groupImages(images).map((img) => img.videoGroup ? (
            <div key={img.videoGroup.id} className="relative flex items-center gap-2 rounded-lg border border-border-strong bg-surface py-1 pl-1 pr-3" data-testid="composer-video">
              <img src={mediaUrl(img.url)} alt="" className="h-14 w-20 rounded-md object-cover" />
              <div className="min-w-0">
                <p className="flex max-w-[180px] items-center gap-1 truncate text-xs text-foreground"><Film className="h-3 w-3 shrink-0 text-primary" /> {img.videoGroup.name}</p>
                <p className="text-[10px] text-muted-foreground">{img.count} frames · {img.videoGroup.duration.toFixed(1)}s</p>
              </div>
              <button onClick={() => images.filter((i) => i.videoGroup?.id === img.videoGroup.id).forEach((i) => onRemoveImage?.(i.id))}
                title="Remove video" className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-border bg-card text-muted-foreground hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <div key={img.id} className="group/img relative">
              <img src={mediaUrl(img.url)} alt={img.name || "Attachment"} className="h-16 w-16 rounded-lg border border-border-strong object-cover" />
              <button onClick={() => onRemoveImage?.(img.id)} data-testid={`remove-image-${img.id}`} title="Remove image"
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-border bg-card text-muted-foreground hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2" data-testid="composer-attachments">
          {attachments.map((a) => (
            <div key={a.id} className="flex items-center gap-1.5 rounded-lg border border-border-strong bg-surface px-2.5 py-1.5 text-xs">
              {a.status === "processing" ? <Loader2 className="h-3 w-3 animate-spin text-amber-600 dark:text-amber-400" /> : <FileText className="h-3 w-3 text-primary" />}
              <span className="max-w-[160px] truncate text-foreground">{a.filename}</span>
              <button onClick={() => onRemoveAttachment?.(a.id)} data-testid={`remove-attachment-${a.id}`} className="text-muted-foreground hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      <div {...dropProps} data-testid="composer-box" className={`${dragging ? "ring-2 ring-indigo-400 " : ""}@container rounded-[26px] border border-white/80 bg-white/85 p-2 shadow-[0_12px_40px_rgba(99,102,241,0.14)] backdrop-blur-xl transition-colors focus-within:border-indigo-200 focus-within:ring-2 focus-within:ring-indigo-200/60 dark:border-border dark:bg-card/90 dark:shadow-[0_8px_40px_rgba(0,0,0,0.4)] dark:focus-within:ring-primary/30 sm:px-3`}>
        <textarea
          ref={ref}
          data-testid="message-composer-textarea"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          disabled={disabled}
          rows={1}
          placeholder={rec.recording ? t("listening") : placeholder || t(agentMode && !narrowScreen() ? "askAnything" : "message")}
          className="radha-scroll max-h-[200px] w-full resize-none bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
        />
        <div className="flex items-center justify-between gap-1 px-1 pt-1">
          <div className="flex min-w-0 items-center gap-1">
            {onAttach && (
              <>
                <input ref={fileRef} type="file" multiple className="hidden" data-testid="composer-file-input"
                  onChange={(e) => { attachAll(Array.from(e.target.files || [])); if (fileRef.current) fileRef.current.value = ""; }} />
                <button onClick={() => fileRef.current?.click()} disabled={uploading || disabled} data-testid="composer-attach-button" title="Attach any file: documents, web pages, code, ZIP, images or video. You can also paste or drag files here."
                  className="flex h-10 w-10 items-center justify-center rounded-lg sm:h-8 sm:w-8 text-muted-foreground transition-colors hover:bg-surface hover:text-foreground disabled:opacity-50">
                  {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
                </button>
              </>
            )}
            {onToggleAgent && (
              <button onClick={onToggleAgent} disabled={!agentAvailable && !agentMode} data-testid="agent-mode-toggle"
                title={agentAvailable ? (agentMode ? "Agent mode on: web search, code execution, image generation" : "Turn on agent mode") : agentHint}
                aria-pressed={!!agentMode}
                className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition-colors disabled:opacity-40 ${
                  agentMode ? "bg-primary/15 text-brand ring-1 ring-primary/50" : "text-muted-foreground hover:bg-surface hover:text-foreground"}`}>
                <Bot className="h-4 w-4" /> Agent
              </button>
            )}
            {onToggleWeb && (
              <SearchChip on={webMode} onToggle={onToggleWeb} label={t("web")} focus={searchFocus} onFocus={onSearchFocus}
                pro={proSearch} onTogglePro={onTogglePro} />
            )}
            {onToggleThink && (
              <ModeChip on={thinkMode} onClick={onToggleThink} icon={Lightbulb} label={t("think")} testId="think-mode-toggle"
                title={thinkMode ? "Think is on: slower, more careful answers" : "Think harder before answering"} />
            )}
            {onToggleStudy && (
              <ModeChip on={studyMode} onClick={onToggleStudy} icon={GraduationCap} label={t("study")} testId="study-mode-toggle"
                title={studyMode ? "Study mode is on: Krish teaches step by step and quizzes you" : "Study mode: learn step by step with quizzes and flashcards"} />
            )}
            <button onClick={toggleMic} disabled={!voiceEnabled || transcribing || disabled} data-testid="composer-mic-button"
              title={voiceEnabled ? (rec.recording ? "Listening… stop talking and it sends by itself" : "Speak your message: it sends when you stop talking") : voiceHint}
              aria-label="Speak your message"
              className={`flex h-10 w-10 items-center justify-center rounded-full transition-colors sm:h-8 sm:w-8 disabled:opacity-40 ${
                rec.recording ? "animate-pulse bg-rose-500 text-white shadow-[0_0_0_4px_rgba(244,63,94,0.25)]"
                  : "bg-indigo-100 text-indigo-600 hover:bg-indigo-200 dark:bg-primary/20 dark:text-brand dark:hover:bg-primary/30"}`}>
              {transcribing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
            </button>
            {onVoiceMode && (
              <button onClick={onVoiceMode} disabled={!voiceEnabled || streaming || disabled} data-testid="voice-mode-button"
                title={voiceEnabled ? "Voice conversation" : voiceHint}
                className="flex h-10 w-10 items-center justify-center rounded-full sm:h-8 sm:w-8 bg-violet-100 text-violet-600 transition-colors hover:bg-violet-200 dark:bg-violet-500/20 dark:text-violet-300 dark:hover:bg-violet-500/30 disabled:opacity-40">
                <AudioLines className="h-4 w-4" />
              </button>
            )}
            {value && !streaming && (
              <button onClick={() => onChange("")} data-testid="clear-composer-button" title="Clear" aria-label="Clear"
                className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-muted-foreground hover:text-foreground @lg:px-2">
                <X className="h-3 w-3" /><span className="@max-lg:hidden">Clear</span>
              </button>
            )}
            <span className="ml-1 hidden whitespace-nowrap text-[11px] text-muted-foreground @2xl:inline">
              {t.parts("toSend", { enter: <span key="k" className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-600 dark:bg-primary/15 dark:text-brand">Enter</span> })}
            </span>
          </div>
          {streaming ? (
            <Button size="icon" onClick={onStop} onMouseDown={(e) => e.preventDefault()} data-testid="stop-generation-button" title="Stop (Esc)" aria-label="Stop the reply"
              className="h-11 w-11 shrink-0 rounded-full bg-foreground text-background shadow-md transition-transform hover:scale-105 hover:bg-foreground/90 active:scale-95">
              <Square className="h-3.5 w-3.5 fill-current" />
            </Button>
          ) : (
            <Button size="icon" onClick={onSend} disabled={!canSend} data-testid="send-message-button" aria-label="Send"
              // Keep the typing focus: on phones losing it brings back the tab bar, which moved this button
              // away mid-tap so the tap landed on the tab bar and the message wasn't sent.
              onMouseDown={(e) => e.preventDefault()}
              className="h-11 w-11 shrink-0 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 shadow-[0_8px_24px_rgba(99,102,241,0.45)] hover:from-indigo-500 hover:to-violet-600">
              <ArrowUp className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      <p className="mt-2 flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground max-sm:hidden"><ShieldCheck className="h-3.5 w-3.5" /> Krish AI can make mistakes. Verify important information.</p>
    </div>
  );
}

function ModeChip({ on, onClick, icon: Icon, label, title, testId }) {
  return (
    <button onClick={onClick} data-testid={testId} title={title} aria-pressed={!!on}
      className={`flex h-10 items-center gap-1.5 rounded-lg px-2 text-xs font-medium transition-colors sm:h-8 sm:px-2.5 ${
        on ? "bg-primary/15 text-brand ring-1 ring-primary/50" : "text-muted-foreground hover:bg-surface hover:text-foreground"}`}>
      <Icon className="h-4 w-4" /> <span className={on ? "" : "@max-lg:hidden"}>{label}</span>
    </button>
  );
}

const FOCUS_OPTIONS = [
  { id: "web", icon: Globe, label: "Web", hint: "Search the whole internet" },
  { id: "academic", icon: BookOpenText, label: "Academic", hint: "Research papers and studies" },
  { id: "social", icon: MessagesSquare, label: "Social", hint: "What people say on Reddit" },
  { id: "video", icon: PlaySquare, label: "Video", hint: "YouTube videos" },
];

// The Search button, like Perplexity's: tap to turn on, the arrow picks where to search and Pro search.
function SearchChip({ on, onToggle, label, focus, onFocus, pro, onTogglePro }) {
  const current = FOCUS_OPTIONS.find((f) => f.id === focus) || FOCUS_OPTIONS[0];
  const Icon = on ? current.icon : Globe;
  const name = on && focus !== "web" ? current.label : label;
  const tone = on ? "bg-primary/15 text-brand ring-1 ring-primary/50" : "text-muted-foreground hover:bg-surface hover:text-foreground";
  return (
    <div className={`flex h-10 items-center rounded-lg transition-colors sm:h-8 ${tone}`}>
      <button onClick={onToggle} data-testid="web-mode-toggle" aria-pressed={!!on}
        title={on ? "Search is on: every answer searches and shows its sources" : "Search the web and show sources for every answer"}
        className="flex h-full items-center gap-1.5 pl-2 pr-1 text-xs font-medium sm:pl-2.5">
        <Icon className="h-4 w-4" /> <span className="@max-lg:hidden">{name}</span>
        {on && pro && <span data-testid="pro-search-badge" className="rounded bg-primary px-1 py-px text-[9px] font-bold uppercase tracking-wide text-primary-foreground">Pro</span>}
      </button>
      {onFocus && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button data-testid="search-options-button" aria-label="Search options" className="flex h-full items-center pl-0.5 pr-1.5">
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-64">
            <DropdownMenuLabel className="text-[11px] uppercase tracking-wider text-muted-foreground">Search in</DropdownMenuLabel>
            {FOCUS_OPTIONS.map((f) => (
              <DropdownMenuItem key={f.id} onSelect={() => onFocus(f.id)} data-testid={`search-focus-${f.id}`} className="gap-2.5">
                <f.icon className="h-4 w-4 text-brand" />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-sm font-medium">{f.label}</span>
                  <span className="text-[11px] text-muted-foreground">{f.hint}</span>
                </span>
                {on && focus === f.id && <Check className="h-4 w-4 text-brand" />}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={(e) => { e.preventDefault(); onTogglePro(); }} data-testid="pro-search-toggle" className="gap-2.5">
              <Sparkles className="h-4 w-4 text-brand" />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-sm font-medium">Pro search</span>
                <span className="text-[11px] text-muted-foreground">Searches several ways and reads the pages. Slower, more thorough.</span>
              </span>
              <span className={`flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors ${pro ? "bg-primary" : "bg-surface-strong"}`}>
                <span className={`h-4 w-4 rounded-full bg-white shadow transition-transform ${pro ? "translate-x-4" : ""}`} />
              </span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}

/** Collapse video frames into one entry per video (with a frame count). */
function groupImages(images) {
  const out = [];
  const seen = new Map();
  for (const img of images) {
    if (!img.videoGroup) { out.push(img); continue; }
    if (seen.has(img.videoGroup.id)) { seen.get(img.videoGroup.id).count += 1; continue; }
    const entry = { ...img, count: 1 };
    seen.set(img.videoGroup.id, entry);
    out.push(entry);
  }
  return out;
}
