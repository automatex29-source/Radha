import { useState } from "react";
import { Globe, ChevronDown } from "lucide-react";
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
      <div className="krish-source-row mt-2.5" aria-hidden>
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className="krish-source-card krish-source-skeleton" style={{ animationDelay: `${i * 120}ms` }}>
            <span className="h-3 w-16 rounded-full bg-current opacity-[0.12]" />
            <span className="h-3 w-full rounded-full bg-current opacity-[0.12]" />
            <span className="h-3 w-2/3 rounded-full bg-current opacity-[0.12]" />
          </span>
        ))}
      </div>
    </div>
  );
}

// After the search: the pages the answer used, as a row of small cards (site, title, number), like Perplexity.
// The heading line opens the full list. Numbers match the citation chips in the answer.
export function SearchedSources({ items, searched, id }) {
  const [open, setOpen] = useState(false);
  const queries = searched?.queries || [];
  const label = queries.length > 1 ? `Searched ${plural(queries.length, "query")}` : "Searched the web";
  const cards = items.length > 4 ? items.slice(0, 3) : items;
  const rest = items.slice(cards.length);
  return (
    <div className="mb-4" data-testid={`web-sources-${id}`}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        data-testid={`web-sources-toggle-${id}`} className="krish-search-row">
        <Globe className="h-4 w-4 shrink-0" />
        <span className="shrink-0 font-medium text-foreground/85">{label}</span>
        <span className="shrink-0 text-muted-foreground/60">·</span>
        <span className="shrink-0 tabular-nums">{plural(items.length, "source")}</span>
        <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {!open && (
        <div className="krish-source-row mt-2" data-testid={`web-source-cards-${id}`}>
          {cards.map((s, i) => (
            <a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer" title={s.snippet || s.title}
              data-testid={`web-source-card-${i + 1}`} className="krish-source-card">
              <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] text-muted-foreground">
                <SiteIcon domain={s.domain} className="h-3.5 w-3.5 shrink-0" />
                <span className="min-w-0 truncate">{siteName(s.domain) || s.domain}</span>
                <span className="ml-auto shrink-0 tabular-nums opacity-70">{i + 1}</span>
              </span>
              <span className="line-clamp-2 text-[12.5px] font-medium leading-snug text-foreground">{s.title}</span>
            </a>
          ))}
          {rest.length > 0 && (
            <button type="button" onClick={() => setOpen(true)} data-testid={`web-sources-more-${id}`}
              className="krish-source-card text-left">
              <span className="flex -space-x-1">
                {rest.slice(0, 4).map((s) => (
                  <span key={s.url} className="flex h-5 w-5 items-center justify-center rounded-full bg-card ring-2 ring-card">
                    <SiteIcon domain={s.domain} className="h-3.5 w-3.5" />
                  </span>
                ))}
              </span>
              <span className="text-[12px] text-muted-foreground">+{rest.length} more</span>
            </button>
          )}
        </div>
      )}
      {open && (
        <div className="krish-search-list radha-fade-up" data-testid={`web-sources-list-${id}`}>
          {queries.length > 0 && (
            <div className="flex flex-wrap gap-1.5 border-b border-border px-3 py-2.5">
              {queries.map((q) => (
                <span key={q} className="inline-flex max-w-full items-center gap-1.5 truncate rounded-full bg-surface px-2.5 py-1 text-[12px] text-muted-foreground">
                  <Globe className="h-3 w-3 shrink-0" /><span className="truncate">{q}</span>
                </span>
              ))}
            </div>
          )}
          <ol className="radha-scroll max-h-80 overflow-y-auto py-1">
            {items.map((s, i) => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noopener noreferrer" title={s.snippet || s.title}
                  className="flex min-w-0 items-start gap-3 px-3 py-2.5 transition-colors hover:bg-surface">
                  <SiteIcon domain={s.domain} className="mt-0.5 h-4 w-4 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium text-foreground">{s.title}</span>
                    {s.snippet && <span className="mt-0.5 line-clamp-2 block text-[12px] leading-snug text-muted-foreground">{s.snippet}</span>}
                    <span className="mt-0.5 block truncate text-[11.5px] text-muted-foreground/80">{s.domain}</span>
                  </span>
                  <span className="mt-0.5 w-4 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground/70">{i + 1}</span>
                </a>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
