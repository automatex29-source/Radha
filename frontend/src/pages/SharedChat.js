import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API, absoluteUrl } from "@/lib/api";
import { MediaGallery } from "@/components/ToolSteps";
import ThemeToggle from "@/components/ThemeToggle";
import { Loader2, User } from "lucide-react";
import BrandMark from "@/components/BrandMark";

/** Public, read-only view of a chat someone shared. Works without signing in. */
export default function SharedChat() {
  const { shareId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios.get(`${API}/share/${encodeURIComponent(shareId)}`)
      .then((r) => { setData(r.data); document.title = `${r.data.title} · Krish AI`; })
      .catch((e) => setError(e?.response?.data?.detail || "Couldn't open this chat."));
  }, [shareId]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/80 px-4 py-3 backdrop-blur-xl">
        <a href="/" className="flex items-center gap-2.5">
          <BrandMark className="h-8 w-8" />
          <span className="text-sm font-extrabold tracking-tight">Krish AI</span>
        </a>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <a href="/" className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white">Try Krish AI</a>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl px-4 py-8">
        {!data && !error && <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>}
        {error && <p className="py-20 text-center text-sm text-muted-foreground" data-testid="shared-chat-error">{error}</p>}
        {data && (
          <>
            <h1 className="text-xl font-bold tracking-tight" data-testid="shared-chat-title">{data.title}</h1>
            <p className="mb-8 mt-1 text-xs text-muted-foreground">Shared chat · read only</p>
            <div className="space-y-6" data-testid="shared-chat-messages">
              {data.messages.map((m) => (m.role === "user" ? (
                <div key={m.id} className="flex justify-end gap-3">
                  <div className="max-w-[85%] rounded-2xl rounded-tr-sm border border-border bg-card px-4 py-3 text-[0.95rem] leading-relaxed">
                    {m.images.length > 0 && (
                      <div className="mb-2 flex flex-wrap gap-2">
                        {m.images.map((src) => <img key={src} src={absoluteUrl(src)} alt="Attached" className="h-28 max-w-[220px] rounded-lg border border-border object-cover" />)}
                      </div>
                    )}
                    <p className="whitespace-pre-wrap break-words">{m.content}</p>
                  </div>
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border-strong bg-surface-strong">
                    <User className="h-4 w-4 text-brand" />
                  </div>
                </div>
              ) : (
                <div key={m.id} className="flex gap-3">
                  <BrandMark className="mt-0.5 h-8 w-8 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="mb-1 text-sm font-semibold tracking-tight">Krish AI</p>
                    <div className="radha-prose min-w-0">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </div>
                    <MediaGallery items={m.media} />
                  </div>
                </div>
              )))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
