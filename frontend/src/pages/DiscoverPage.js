import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { askAbout, SourceLine } from "@/components/TopStories";
import { useT } from "@/lib/i18n";
import { Compass, Loader2, Sparkles, RefreshCw } from "lucide-react";

export const TOPICS = [
  { id: "top", label: "Top" }, { id: "india", label: "India" }, { id: "world", label: "World" },
  { id: "business", label: "Business" }, { id: "tech", label: "Tech" }, { id: "sports", label: "Sports" },
  { id: "science", label: "Science" }, { id: "entertainment", label: "Entertainment" }, { id: "health", label: "Health" },
];

function StoryCard({ story, big, onAsk }) {
  return (
    <article className={`group flex flex-col justify-between gap-3 rounded-2xl border border-border bg-card p-4 transition-colors hover:border-primary/40 ${
      big ? "bg-gradient-to-br from-primary/10 via-card to-card sm:col-span-2 sm:p-6" : ""}`} data-testid="discover-story">
      <div className="space-y-2">
        <SourceLine story={story} />
        <a href={story.url} target="_blank" rel="noopener noreferrer"
          className={`block font-semibold leading-snug text-foreground [text-wrap:balance] hover:text-brand ${big ? "text-xl sm:text-2xl" : "text-[15px]"}`}>
          {story.title}
        </a>
      </div>
      <button onClick={() => onAsk(story)} data-testid="discover-ask-button"
        className="flex w-fit items-center gap-1.5 rounded-full border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-brand transition-colors hover:bg-primary hover:text-primary-foreground">
        <Sparkles className="h-3.5 w-3.5" /> Ask Krish about this
      </button>
    </article>
  );
}

/** Today's news by topic, like Perplexity's Discover. Each story can be opened or asked about. */
export default function DiscoverPage() {
  const t = useT();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const topic = TOPICS.some((x) => x.id === params.get("topic")) ? params.get("topic") : "top";
  const [stories, setStories] = useState(null);
  const [error, setError] = useState("");

  const load = () => {
    setStories(null);
    setError("");
    api.get("/discover", { params: { topic } })
      .then(({ data }) => setStories(data.stories))
      .catch((e) => setError(formatApiError(e)));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [topic]);

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-10" data-testid="discover-page">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Compass className="h-6 w-6" /></div>
            <div>
              <h1 className="radha-heading-gradient text-3xl font-extrabold tracking-tighter">{t("discover")}</h1>
              <p className="text-sm text-muted-foreground">Today's top stories. Tap one to read it, or ask Krish to explain.</p>
            </div>
          </div>

          <div className="radha-scroll -mx-4 mt-6 flex gap-2 overflow-x-auto px-4 pb-1" data-testid="discover-topics">
            {TOPICS.map((x) => (
              <button key={x.id} onClick={() => setParams(x.id === "top" ? {} : { topic: x.id }, { replace: true })}
                data-testid={`discover-topic-${x.id}`} aria-pressed={topic === x.id}
                className={`shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors ${
                  topic === x.id ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground"}`}>
                {x.label}
              </button>
            ))}
          </div>

          {!stories && !error && <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>}
          {error && (
            <div className="py-16 text-center">
              <p className="text-sm text-muted-foreground">{error}</p>
              <button onClick={load} className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-brand"><RefreshCw className="h-4 w-4" /> Try again</button>
            </div>
          )}
          {stories && stories.length === 0 && <p className="py-16 text-center text-sm text-muted-foreground">No stories right now. Try another topic.</p>}
          {stories?.length > 0 && (
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {stories.map((s, i) => <StoryCard key={s.url} story={s} big={i === 0} onAsk={(st) => askAbout(navigate, st)} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
