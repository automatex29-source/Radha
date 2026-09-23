import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Sparkles, Copy, Check, User, FileText as FileIcon } from "lucide-react";
import { toast } from "sonner";

function CodeBlock({ inline, className, children }) {
  const [copied, setCopied] = useState(false);
  if (inline) return <code className={className}>{children}</code>;
  const text = String(children).replace(/\n$/, "");
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="group/code relative">
      <button onClick={copy} data-testid="copy-code-button"
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-border bg-[#11141D] px-2 py-1 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover/code:opacity-100">
        {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
        {copied ? "Copied" : "Copy"}
      </button>
      <pre><code className={className}>{children}</code></pre>
    </div>
  );
}

export default function MessageBubble({ message, streaming }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const copyMsg = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1500);
  };

  if (isUser) {
    return (
      <div className="flex justify-end gap-3 radha-fade-up" data-testid={`user-message-item-${message.id}`}>
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm border border-[#222738] bg-[#141721] px-4 py-3 text-[0.95rem] leading-relaxed text-foreground sm:px-5">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#2E364A] bg-[#1D2230]">
          <User className="h-4 w-4 text-[#A5B4FC]" />
        </div>
      </div>
    );
  }

  return (
    <div className="group flex gap-3 radha-fade-up" data-testid={`ai-message-item-${message.id}`}>
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary shadow-[0_0_20px_rgba(99,102,241,0.35)]">
        <Sparkles className="h-4 w-4 text-white" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-sm font-semibold tracking-tight">RADHA</span>
          {message.model && (
            <span className="rounded-full border border-[#262C3E] bg-[#171B26] px-2 py-0.5 font-mono text-[10px] tracking-wide text-[#A5B4FC]">
              {message.model}
            </span>
          )}
        </div>
        <div className="radha-prose min-w-0">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
            {message.content || ""}
          </ReactMarkdown>
          {streaming && <span className="radha-cursor" data-testid="streaming-cursor" />}
        </div>
        {message.sources?.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5" data-testid={`message-sources-${message.id}`}>
            <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">Sources</span>
            {message.sources.map((s, i) => (
              <span key={i} className="flex items-center gap-1 rounded-full border border-[#262C3E] bg-[#171B26] px-2 py-0.5 font-mono text-[10px] text-[#A5B4FC]">
                <FileIcon className="h-2.5 w-2.5" /> {s.fileName}
              </span>
            ))}
          </div>
        )}
        {!streaming && message.content && (
          <button onClick={copyMsg} data-testid={`copy-message-button-${message.id}`}
            className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100">
            {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
    </div>
  );
}
