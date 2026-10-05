import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, User, FileText as FileIcon, Volume2, Square, Loader2, Globe, CornerDownRight, Plus } from "lucide-react";
import { toast } from "sonner";
import { mediaUrl } from "@/lib/api";
import { speak, stopSpeaking, speechText, unlockSpeech } from "@/lib/voice";
import { ToolSteps, MediaGallery } from "@/components/ToolSteps";
import CodeProject from "@/components/CodeProject";
import { extractFiles, stripFileBlocks } from "@/lib/codeFiles";
import KrishWordmark from "@/components/KrishWordmark";
import BrandMark from "@/components/BrandMark";
import { hideRelatedLine, linkCitations, faviconUrl } from "@/lib/citations";

function SiteIcon({ domain, className = "h-3.5 w-3.5" }) {
  const [failed, setFailed] = useState(false);
  if (failed || !domain) return <Globe className={`${className} text-muted-foreground`} />;
  return <img src={faviconUrl(domain)} alt="" loading="lazy" onError={() => setFailed(true)} className={`${className} rounded-sm`} />;
}

// Like Perplexity: the web pages the answer came from, as cards above it.
function WebSources({ items, id }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 3);
  const more = items.length - shown.length;
  return (
    <div className="mb-3" data-testid={`web-sources-${id}`}>
      <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        <Globe className="h-3.5 w-3.5" /> Sources
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {shown.map((s, i) => (
          <a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer" title={s.snippet || s.title}
            data-testid={`web-source-card-${i + 1}`}
            className="flex min-w-0 flex-col justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2.5 transition-colors hover:border-primary/50 hover:bg-surface">
            <span className="line-clamp-2 text-[12.5px] font-medium leading-snug text-foreground">{s.title}</span>
            <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-muted-foreground">
              <SiteIcon domain={s.domain} />
              <span className="truncate">{s.domain}</span>
              <span className="ml-auto shrink-0 tabular-nums">{i + 1}</span>
            </span>
          </a>
        ))}
        {more > 0 && (
          <button onClick={() => setAll(true)} data-testid={`web-sources-more-${id}`}
            className="flex min-w-0 flex-col justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2.5 text-left transition-colors hover:border-primary/50 hover:bg-surface">
            <span className="flex -space-x-1">
              {items.slice(3, 7).map((s) => <SiteIcon key={s.url} domain={s.domain} className="h-4 w-4 rounded-full bg-card ring-2 ring-card" />)}
            </span>
            <span className="text-[11px] text-muted-foreground">View {more} more</span>
          </button>
        )}
      </div>
    </div>
  );
}

// [1] in the answer: a small pill that opens that source.
function Citation({ href, title, children, ...rest }) {
  if (title !== "cite") return <a href={href} title={title} target="_blank" rel="noopener noreferrer" {...rest}>{children}</a>;
  let domain = "";
  try { domain = new URL(href).hostname.replace(/^www\./, ""); } catch { /* keep the number only */ }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" title={domain} data-testid="citation-link"
      className="krish-cite mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded-full bg-surface-strong px-1.5 align-[0.1em] text-[10.5px] font-semibold leading-none text-muted-foreground no-underline transition-colors hover:bg-primary hover:text-primary-foreground">
      {children}
    </a>
  );
}

function RelatedQuestions({ items, onAsk, id }) {
  return (
    <div className="mt-5" data-testid={`related-questions-${id}`}>
      <p className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        <CornerDownRight className="h-3.5 w-3.5" /> Related
      </p>
      <div className="divide-y divide-border border-y border-border">
        {items.map((q, i) => (
          <button key={q} onClick={() => onAsk(q)} data-testid={`related-question-${i + 1}`} dir="auto"
            className="group/rel flex w-full items-center gap-3 py-2.5 text-left text-[14px] text-foreground transition-colors hover:text-brand">
            <span className="min-w-0 flex-1">{q}</span>
            <Plus className="h-4 w-4 shrink-0 text-muted-foreground group-hover/rel:text-brand" />
          </button>
        ))}
      </div>
    </div>
  );
}

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

export default function MessageBubble({ message, streaming, voiceEnabled, voice, onOpenMedia, codeProject = true, onOpenCode, codeActive, onAsk }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  // With the side panel, the files live there (like Claude's artifacts) and the chat keeps just the words.
  const webSources = useMemo(() => (message.sources || []).filter((s) => s.type === "web" && s.url), [message.sources]);
  const fileSources = useMemo(() => (message.sources || []).filter((s) => s.fileName), [message.sources]);
  const shown = useMemo(() => {
    if (isUser) return message.content || "";
    const text = onOpenCode && codeProject ? stripFileBlocks(message.content, streaming) : message.content || "";
    return linkCitations(streaming ? hideRelatedLine(text) : text, webSources);
  }, [onOpenCode, codeProject, isUser, message.content, streaming, webSources]);

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
        {webSources.length > 0 && <WebSources items={webSources} id={message.id} />}
        <div dir="auto" className="radha-prose min-w-0">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: CodeBlock, a: Citation }}>
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
        {fileSources.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5" data-testid={`message-sources-${message.id}`}>
            <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">Sources</span>
            {fileSources.map((s, i) => (
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
        {!streaming && onAsk && message.related?.length > 0 && <RelatedQuestions items={message.related} onAsk={onAsk} id={message.id} />}
      </div>
    </div>
  );
}
