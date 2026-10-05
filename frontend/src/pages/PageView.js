import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { API } from "@/lib/api";
import ThemeToggle from "@/components/ThemeToggle";
import BrandMark from "@/components/BrandMark";
import { LiveCards } from "@/components/LiveCards";
import { linkCitations, faviconUrl } from "@/lib/citations";
import { Link2, Loader2 } from "lucide-react";

function Cite({ href, title, children }) {
  if (title !== "cite") return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer"
      className="krish-cite mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded-full bg-surface-strong px-1.5 align-[0.1em] text-[10.5px] font-semibold leading-none no-underline">
      {children}
    </a>
  );
}

/** A Page: one Krish answer published as a clean article anyone can read (like Perplexity Pages). */
export default function PageView() {
  const { pageId } = useParams();
  const [page, setPage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios.get(`${API}/pages/${encodeURIComponent(pageId)}`)
      .then((r) => { setPage(r.data); document.title = `${r.data.title} · Krish AI`; })
      .catch((e) => setError(e?.response?.data?.detail || "Couldn't open this page."));
  }, [pageId]);

  const sources = useMemo(() => (page?.sources || []).filter((s) => s.type === "web" || s.type === "video"), [page]);
  const images = useMemo(() => (page?.sources || []).filter((s) => s.type === "image"), [page]);
  const live = useMemo(() => (page?.sources || []).filter((s) => s.type === "weather" || s.type === "stock"), [page]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(window.location.href); toast.success("Link copied"); } catch { toast.error("Copy the link from the address bar"); }
  };

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/80 px-4 py-3 backdrop-blur-xl">
        <a href="/" className="flex items-center gap-2.5">
          <BrandMark className="h-8 w-8" />
          <span className="text-sm font-extrabold tracking-tight">Krish AI</span>
        </a>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {page && <button onClick={copy} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold"><Link2 className="h-3.5 w-3.5" /> Copy link</button>}
          <a href="/" className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white">Try Krish AI</a>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl px-4 py-10" data-testid="page-view">
        {!page && !error && <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>}
        {error && <p className="py-20 text-center text-sm text-muted-foreground" data-testid="page-error">{error}</p>}
        {page && (
          <article>
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-brand">Krish AI Page</p>
            <h1 className="mt-2 text-3xl font-extrabold leading-tight tracking-tight [text-wrap:balance] sm:text-4xl" data-testid="page-title">{page.title}</h1>
            <p className="mt-2 text-xs text-muted-foreground">
              {new Date(page.createdAt).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })}
              {sources.length > 0 && ` · ${sources.length} sources`}
            </p>

            {images.length > 0 && (
              <div className="mt-6 grid grid-cols-3 gap-1.5">
                {images.slice(0, 3).map((im) => (
                  <a key={im.thumbnail} href={im.url} target="_blank" rel="noopener noreferrer" className="block overflow-hidden rounded-xl bg-surface">
                    <img src={im.thumbnail} alt={im.title || ""} className="aspect-[4/3] h-full w-full object-cover" />
                  </a>
                ))}
              </div>
            )}

            <div className="mt-6"><LiveCards items={live} /></div>
            <div className="radha-prose mt-2 text-[1.02rem]" dir="auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: Cite }}>{linkCitations(page.content, sources)}</ReactMarkdown>
            </div>

            {sources.length > 0 && (
              <section className="mt-10 border-t border-border pt-6">
                <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-muted-foreground">Sources</h2>
                <ol className="mt-3 space-y-2.5">
                  {sources.map((s, i) => (
                    <li key={s.url} className="flex gap-3 text-sm">
                      <span className="w-5 shrink-0 text-right tabular-nums text-muted-foreground">{i + 1}.</span>
                      <a href={s.url} target="_blank" rel="noopener noreferrer" className="min-w-0 hover:text-brand">
                        <span className="block font-medium leading-snug">{s.title}</span>
                        <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                          <img src={faviconUrl(s.domain)} alt="" className="h-3.5 w-3.5 rounded-sm" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                          {s.domain}
                        </span>
                      </a>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            <div className="mt-12 rounded-2xl border border-border bg-card p-5 text-center">
              <p className="text-sm font-semibold">Have a question of your own?</p>
              <p className="mt-1 text-xs text-muted-foreground">Krish AI searches the web and answers with sources. Free to use.</p>
              <a href="/" className="mt-3 inline-block rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">Ask Krish AI</a>
            </div>
          </article>
        )}
      </main>
    </div>
  );
}
