import { useState } from "react";
import { Globe, ChevronRight, Search, Sparkles, ListOrdered, Image as ImageIcon, PlayCircle } from "lucide-react";
import { faviconUrl, siteName } from "@/lib/citations";

export function SiteIcon({ domain, className = "h-3.5 w-3.5" }) {
  const [failed, setFailed] = useState(false);
  if (failed || !domain) return <Globe className={`${className} text-muted-foreground`} />;
  return <img src={faviconUrl(domain)} alt="" loading="lazy" onError={() => setFailed(true)} className={`${className} rounded-sm`} />;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// While the search runs (like Claude): "Searching the web" with the same shine as "Krish is thinking…", what
// is being looked up, and faint placeholder cards where the sources will appear.
export function SearchingStatus({ query }) {
  return (
    <div className="mb-4" role="status" data-testid="web-searching">
      <div className="krish-search-status">
        <Globe className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="krish-thinking-words shrink-0">Searching the web</span>
        {query && <span className="min-w-0 truncate font-normal text-muted-foreground/75">“{query}”</span>}
      </div>
      <div className="krish-read-line pointer-events-none mt-2" aria-hidden>
        <span className="flex shrink-0 -space-x-1.5">
          {[0, 1, 2, 3, 4].map((i) => <span key={i} className="krish-read-icon krish-skeleton-dot" style={{ animationDelay: `${i * 120}ms` }} />)}
        </span>
        <span className="krish-skeleton-bar" />
      </div>
    </div>
  );
}

// Every page the search read, numbered like the answer's citation chips: site, title and a short summary.
// Used in the chat's Sources tab and at the end of a shared page.
export function SourceList({ items, queries = [], id = "" }) {
  return (
    <div data-testid={`web-sources-list-${id}`}>
      {queries.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {queries.map((q) => (
            <span key={q} className="inline-flex max-w-full items-center gap-1.5 truncate rounded-full bg-surface px-2.5 py-1 text-[12px] text-muted-foreground">
              <Search className="h-3 w-3 shrink-0" /><span className="truncate">{q}</span>
            </span>
          ))}
        </div>
      )}
      <ol className="space-y-2">
        {items.map((s, i) => (
          <li key={s.url}>
            <a href={s.url} target="_blank" rel="noopener noreferrer" data-testid={`web-source-card-${i + 1}`} className="krish-source-item">
              <span className="krish-source-badge">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] text-muted-foreground">
                  <SiteIcon domain={s.domain} className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{s.domain}</span>
                </span>
                <span className="mt-1 block text-[13.5px] font-semibold leading-snug text-foreground">{s.title}</span>
                {s.snippet && <span className="mt-0.5 line-clamp-2 block text-[12.5px] leading-snug text-muted-foreground">{s.snippet}</span>}
              </span>
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

// The line above an answer from the web: the sites' icons and "Read 6 sources · apple, gadgets360 and more".
// Tapping it opens the Sources tab.
function ReadLine({ items, onOpen }) {
  const icons = [...new Map(items.map((s) => [s.domain, s])).values()];
  const names = icons.slice(0, 3).map((s) => siteName(s.domain) || s.domain);
  return (
    <button type="button" onClick={onOpen} className="krish-read-line" data-testid="web-read-line">
      <span className="flex shrink-0 -space-x-1.5">
        {icons.slice(0, 5).map((s) => (
          <span key={s.domain} className="krish-read-icon"><SiteIcon domain={s.domain} className="h-3.5 w-3.5" /></span>
        ))}
      </span>
      <span className="min-w-0 truncate">
        Read <b className="font-semibold text-foreground">{plural(items.length, "source")}</b>
        <span className="max-sm:hidden"> · {names.join(", ")}{icons.length > 3 ? " and more" : ""}</span>
      </span>
      <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-60" />
    </button>
  );
}

// An answer that used the web gets tabs, like Perplexity: Answer (the reply, with a line of the sites it read),
// Sources (every page, numbered like the citation chips), and Images or Videos when the search found some.
export function SearchTabs({ sources, images = [], videos = [], searched, id, renderImages, renderVideos, children }) {
  const [tab, setTab] = useState("answer");
  const tabs = [
    { id: "answer", label: "Answer", icon: Sparkles },
    sources.length > 0 && { id: "sources", label: "Sources", icon: ListOrdered, count: sources.length },
    images.length > 0 && { id: "images", label: "Images", icon: ImageIcon, count: images.length },
    videos.length > 0 && { id: "videos", label: "Videos", icon: PlayCircle, count: videos.length },
  ].filter(Boolean);
  return (
    <div data-testid={`search-tabs-${id}`}>
      <div className="krish-tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            data-testid={`search-tab-${t.id}-${id}`} className="krish-tab">
            <t.icon className="h-4 w-4" />{t.label}
            {t.count > 0 && <span className="krish-tab-count">{t.count}</span>}
          </button>
        ))}
      </div>
      {tab === "answer" && (
        <div className="kai-fade-up">
          {sources.length > 0 && <ReadLine items={sources} onOpen={() => setTab("sources")} />}
          {children}
        </div>
      )}
      {tab === "sources" && <div className="kai-fade-up"><SourceList items={sources} queries={searched?.queries || []} id={id} /></div>}
      {tab === "images" && <div className="kai-fade-up">{renderImages?.()}</div>}
      {tab === "videos" && <div className="kai-fade-up">{renderVideos?.()}</div>}
    </div>
  );
}
