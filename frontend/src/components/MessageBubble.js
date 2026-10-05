import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, User, FileText as FileIcon, Volume2, Square, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { mediaUrl } from "@/lib/api";
import { speak, stopSpeaking, speechText, unlockSpeech } from "@/lib/voice";
import { ToolSteps, MediaGallery } from "@/components/ToolSteps";
import CodeProject from "@/components/CodeProject";
import { extractFiles, stripFileBlocks } from "@/lib/codeFiles";
import KrishWordmark from "@/components/KrishWordmark";
import BrandMark from "@/components/BrandMark";

// Only fenced code gets the box and copy button; `inline code` stays in the sentence.
function CodeBlock({ node, children }) {
  const [copied, setCopied] = useState(false);
  const text = (node?.children?.[0]?.children || []).map((c) => c.value || "").join("").replace(/\n$/, "");
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="group/code relative">
      <button onClick={copy} data-testid="copy-code-button"
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-border bg-card px-2 py-1 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover/code:opacity-100">
        {copied ? <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" /> : <Copy className="h-3 w-3" />}
        {copied ? "Copied" : "Copy"}
      </button>
      <pre className="max-h-[28rem] overflow-auto">{children}</pre>
    </div>
  );
}

function SpeakButton({ text, voice, id }) {
  const [state, setState] = useState("idle");
  const toggle = async () => {
    if (state !== "idle") { stopSpeaking(); setState("idle"); return; }
    setState("loading");
    unlockSpeech();
    try {
      await speak(speechText(text), voice, { onStart: () => setState("playing") });
    } catch (e) {
      toast.error(e.message || "Could not read aloud");
    } finally {
      setState("idle");
    }
  };
  return (
    <button onClick={toggle} data-testid={`speak-message-button-${id}`}
      className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
      {state === "loading" ? <Loader2 className="h-3 w-3 animate-spin" /> : state === "playing" ? <Square className="h-3 w-3" /> : <Volume2 className="h-3 w-3" />}
      {state === "playing" ? "Stop" : "Listen"}
    </button>
  );
}

export default function MessageBubble({ message, streaming, voiceEnabled, voice, onOpenMedia, codeProject = true, onOpenCode, codeActive }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  // With the side panel, the files live there (like Claude's artifacts) and the chat keeps just the words.
  const shown = useMemo(() => (onOpenCode && codeProject && !isUser ? stripFileBlocks(message.content, streaming) : message.content || ""),
    [onOpenCode, codeProject, isUser, message.content, streaming]);

  // Code the user pasted or attached shows as file chips (Krish shows the page itself in the side panel).
  const userFiles = useMemo(() => {
    if (!isUser) return [];
    const files = extractFiles(message.content);
    if (files.length) return files;
    const text = (message.content || "").trim();
    return text.startsWith("<") && text.length > 80 && /<\/[A-Za-z][\w-]*>\s*$/.test(text) ? [{ path: "index.html", content: text, whole: true }] : [];
  }, [isUser, message.content]);
  const userText = userFiles.length ? (userFiles[0].whole ? "" : stripFileBlocks(message.content)) : message.content;

  const copyMsg = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1500);
  };

  if (isUser) {
    return (
      <div className="flex justify-end gap-3 radha-fade-up" data-testid={`user-message-item-${message.id}`}>
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm border border-border bg-card px-4 py-3 text-[0.95rem] leading-relaxed text-foreground sm:px-5">
          {message.images?.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2" data-testid={`user-message-images-${message.id}`}>
              {message.images.map((mid) => (
                <img key={mid} src={mediaUrl(`/api/media/${mid}`)} alt="Attached"
                  className="h-28 max-w-[220px] rounded-lg border border-border object-cover" />
              ))}
            </div>
          )}
          {userText && <p dir="auto" className="whitespace-pre-wrap break-words">{userText}</p>}
          {userFiles.length > 0 && (
            <div className={`flex flex-wrap gap-2 ${userText ? "mt-2" : ""}`} data-testid={`user-message-files-${message.id}`}>
              {userFiles.map((f) => (
                <span key={f.path} className="flex items-center gap-1.5 rounded-lg border border-border-strong bg-surface px-2.5 py-1.5 font-mono text-xs">
                  <FileIcon className="h-3 w-3 text-primary" /> {f.path}
                  <span className="text-muted-foreground">· {f.content.split("\n").length} lines</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border-strong bg-surface-strong">
          <User className="h-4 w-4 text-brand" />
        </div>
      </div>
    );
  }

  return (
    <div className="group flex gap-3 radha-fade-up" data-testid={`ai-message-item-${message.id}`}>
      <BrandMark className="mt-0.5 h-8 w-8 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <KrishWordmark className="text-[15px]" />
          {message.model && (
            <span className="rounded-full border border-border-strong bg-surface px-2 py-0.5 font-mono text-[10px] tracking-wide text-brand">
              {message.model}
            </span>
          )}
        </div>
        <ToolSteps steps={message.steps} />
        <div dir="auto" className="radha-prose min-w-0">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: CodeBlock }}>
            {shown}
          </ReactMarkdown>
          {streaming && <span className="radha-cursor" data-testid="streaming-cursor" />}
        </div>
        {message.stopped && !streaming && (
          <p className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground" data-testid="reply-stopped-note">
            <Square className="h-2.5 w-2.5 fill-current" /> You stopped this reply
          </p>
        )}
        {codeProject && <CodeProject content={message.content || ""} streaming={streaming} onOpen={onOpenCode} active={codeActive} />}
        <MediaGallery items={message.media} onOpen={onOpenMedia} />
        {message.sources?.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5" data-testid={`message-sources-${message.id}`}>
            <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">Sources</span>
            {message.sources.map((s, i) => (
              <span key={i} className="flex items-center gap-1 rounded-full border border-border-strong bg-surface px-2 py-0.5 font-mono text-[10px] text-brand">
                <FileIcon className="h-2.5 w-2.5" /> {s.fileName}
              </span>
            ))}
          </div>
        )}
        {!streaming && message.content && (
          <div className="mt-2 flex items-center gap-3 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
            <button onClick={copyMsg} data-testid={`copy-message-button-${message.id}`}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
              {copied ? <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied" : "Copy"}
            </button>
            {voiceEnabled && <SpeakButton text={message.content} voice={voice} id={message.id} />}
          </div>
        )}
      </div>
    </div>
  );
}
