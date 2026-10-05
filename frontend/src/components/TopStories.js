import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { faviconUrl } from "@/lib/citations";
import { ArrowRight, Newspaper } from "lucide-react";

export function timeAgo(iso) {
  if (!iso) return "";
  const mins = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? `${hrs} hr ago` : `${Math.round(hrs / 24)} d ago`;
}

export const askText = (story) =>
  `Tell me about this news: "${story.title}"${story.source ? ` (${story.source})` : ""}. What happened and why does it matter?`;

// Starts a new chat about a story: Krish searches it and explains.
export function askAbout(navigate, story) {
  try { sessionStorage.setItem("krish.handoff", askText(story)); } catch { /* the chat just opens empty */ }
  navigate("/");
}

export function SourceLine({ story }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-muted-foreground">
      {story.domain && <img src={faviconUrl(story.domain)} alt="" loading="lazy" className="h-3.5 w-3.5 rounded-sm"
        onError={(e) => { e.currentTarget.style.display = "none"; }} />}
      <span className="truncate font-medium">{story.source}</span>
      {story.published && <span className="shrink-0">· {timeAgo(story.published)}</span>}
    </span>
  );
}

/** "Today's top stories" on the chat home: three headlines, each one tap from an explained answer. */
export default function TopStories({ onAsk }) {
  const navigate = useNavigate();
  const [stories, setStories] = useState([]);
  useEffect(() => {
    api.get("/discover", { params: { limit: 3 } }).then(({ data }) => setStories(data.stories || [])).catch(() => {});
  }, []);
  if (!stories.length) return null;
  return (
    <section className="relative mt-5 sm:mt-6" data-testid="top-stories">
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          <Newspaper className="h-3.5 w-3.5" /> Today's top stories
        </p>
        <button onClick={() => navigate("/discover")} data-testid="top-stories-see-all"
          className="flex items-center gap-1 text-xs font-semibold text-brand hover:underline">
          Discover more <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="grid gap-2 sm:grid-cols-3 sm:gap-3">
        {stories.map((s) => (
          <button key={s.url} onClick={() => onAsk(askText(s))} title="Ask Krish about this"
            className="flex min-w-0 flex-col gap-1.5 rounded-xl border border-border bg-card/80 px-3.5 py-3 text-left transition-colors hover:border-primary/40 hover:bg-card">
            <SourceLine story={s} />
            <span className="line-clamp-2 text-[13.5px] font-medium leading-snug text-foreground">{s.title}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
