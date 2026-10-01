import { useRef, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ArrowUp, Square, X, Paperclip, FileText, Loader2, Bot, Mic, AudioLines, Film, ShieldCheck, Lightbulb, GraduationCap } from "lucide-react";
import { toast } from "sonner";
import { mediaUrl } from "@/lib/api";
import { useRecorder } from "@/hooks/useRecorder";
import { transcribe } from "@/lib/voice";

const DOC_TYPES = ".pdf,.docx,.pptx,.xlsx,.xlsm,.csv,.txt,.md,.markdown,.json,.log";
const IMAGE_TYPES = ".png,.jpg,.jpeg,.webp,.gif";
const VIDEO_TYPES = ".mp4,.webm,.mov,.m4v";

const narrowScreen = () => typeof window !== "undefined" && !!window.matchMedia?.("(max-width: 639px)").matches;
const phoneKeyboard = () => typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches;

export default function ComposerInput({
  value, onChange, onSend, onStop, streaming, disabled,
  onAttach, attachments = [], onRemoveAttachment, uploading,
  images = [], onRemoveImage,
  agentMode, onToggleAgent, agentAvailable, agentHint,
  thinkMode, onToggleThink, studyMode, onToggleStudy,
  voiceEnabled, voiceHint, onVoiceMode, placeholder,
}) {
  const ref = useRef(null);
  const fileRef = useRef(null);
  const rec = useRecorder();
  const [transcribing, setTranscribing] = useState(false);
  const canSend = (value.trim() || images.length > 0) && !disabled;

  const toggleMic = async () => {
    if (rec.recording) { rec.stop(); return; }
    try {
      const blob = await rec.record();
      if (!blob) return;
      setTranscribing(true);
      const text = await transcribe(blob);
      if (text) onChange(value ? `${value.trimEnd()} ${text}` : text);
      else toast.message("Didn't catch that — try again.");
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
      <div className="rounded-[26px] border border-white/80 bg-white/85 p-2 shadow-[0_12px_40px_rgba(99,102,241,0.14)] backdrop-blur-xl transition-colors focus-within:border-indigo-200 focus-within:ring-2 focus-within:ring-indigo-200/60 dark:border-border dark:bg-card/90 dark:shadow-[0_8px_40px_rgba(0,0,0,0.4)] dark:focus-within:ring-primary/30 sm:px-3">
        <textarea
          ref={ref}
          data-testid="message-composer-textarea"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          rows={1}
          placeholder={rec.recording ? "Listening… tap the mic to finish" : placeholder || (agentMode && !narrowScreen() ? "Ask Krish AI anything: it can search the web, run code and make files…" : "Message Krish AI…")}
          className="radha-scroll max-h-[200px] w-full resize-none bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
        />
        <div className="flex items-center justify-between px-1 pt-1">
          <div className="flex items-center gap-1">
            {onAttach && (
              <>
                <input ref={fileRef} type="file" className="hidden" data-testid="composer-file-input"
                  accept={`${DOC_TYPES},${IMAGE_TYPES},${VIDEO_TYPES}`}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) onAttach(f); if (fileRef.current) fileRef.current.value = ""; }} />
                <button onClick={() => fileRef.current?.click()} disabled={uploading || disabled} data-testid="composer-attach-button" title="Attach a document, image or video"
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
            {onToggleThink && (
              <ModeChip on={thinkMode} onClick={onToggleThink} icon={Lightbulb} label="Think" testId="think-mode-toggle"
                title={thinkMode ? "Think is on: slower, more careful answers" : "Think harder before answering"} />
            )}
            {onToggleStudy && (
              <ModeChip on={studyMode} onClick={onToggleStudy} icon={GraduationCap} label="Study" testId="study-mode-toggle"
                title={studyMode ? "Study mode is on: Krish teaches step by step and quizzes you" : "Study mode: learn step by step with quizzes and flashcards"} />
            )}
            <button onClick={toggleMic} disabled={!voiceEnabled || transcribing || disabled} data-testid="composer-mic-button"
              title={voiceEnabled ? (rec.recording ? "Stop and transcribe" : "Dictate") : voiceHint}
              className={`flex h-10 w-10 items-center justify-center rounded-lg transition-colors sm:h-8 sm:w-8 disabled:opacity-40 ${
                rec.recording ? "bg-destructive/20 text-destructive" : "text-muted-foreground hover:bg-surface hover:text-foreground"}`}>
              {transcribing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
            </button>
            {onVoiceMode && (
              <button onClick={onVoiceMode} disabled={!voiceEnabled || streaming || disabled} data-testid="voice-mode-button"
                title={voiceEnabled ? "Voice conversation" : voiceHint}
                className="flex h-10 w-10 items-center justify-center rounded-lg sm:h-8 sm:w-8 text-muted-foreground transition-colors hover:bg-surface hover:text-foreground disabled:opacity-40">
                <AudioLines className="h-4 w-4" />
              </button>
            )}
            {value && !streaming && (
              <button onClick={() => onChange("")} data-testid="clear-composer-button"
                className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground">
                <X className="h-3 w-3" /> Clear
              </button>
            )}
            <span className="ml-1 hidden text-[11px] text-muted-foreground md:inline">
              <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-600 dark:bg-primary/15 dark:text-brand">Enter</span> to send
            </span>
          </div>
          {streaming ? (
            <Button size="icon" variant="secondary" onClick={onStop} data-testid="stop-generation-button" className="h-11 w-11 rounded-full">
              <Square className="h-4 w-4" />
            </Button>
          ) : (
            <Button size="icon" onClick={onSend} disabled={!canSend} data-testid="send-message-button"
              className="h-11 w-11 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 shadow-[0_8px_24px_rgba(99,102,241,0.45)] hover:from-indigo-500 hover:to-violet-600">
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
      <Icon className="h-4 w-4" /> <span className={on ? "" : "max-sm:hidden"}>{label}</span>
    </button>
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
