import { useState } from "react";
import { Globe, ChevronDown } from "lucide-react";
import { faviconUrl } from "@/lib/citations";

export function SiteIcon({ domain, className = "h-3.5 w-3.5" }) {
  const [failed, setFailed] = useState(false);
  if (failed || !domain) return <Globe className={`${className} text-muted-foreground`} />;
  return <img src={faviconUrl(domain)} alt="" loading="lazy" onError={() => setFailed(true)} className={`${className} rounded-sm`} />;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// While the search runs (like Claude): "Searching the web" with the same shine as "Krish is thinking…",
// and what is being looked up.
export function SearchingStatus({ query }) {
  return (
    <div className="krish-search-status mb-3" role="status" data-testid="web-searching">
      <Globe className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="krish-thinking-words shrink-0">Searching the web</span>
      {query && <span className="min-w-0 truncate font-normal text-muted-foreground/75">“{query}”</span>}
    </div>
  );
}

// After the search: one quiet line ("Searched the web · 6 sources") that opens the list of pages the answer
// used. Each page keeps its number, so the [1] chips in the answer match the list.
export function SearchedSources({ items, searched, id }) {
  const [open, setOpen] = useState(false);
  const queries = searched?.queries || [];
  const label = queries.length > 1 ? `Searched ${plural(queries.length, "query")}` : "Searched the web";
  const icons = [...new Map(items.map((s) => [s.domain, s])).values()].slice(0, 4);
  return (
    <div className="mb-3" data-testid={`web-sources-${id}`}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        data-testid={`web-sources-toggle-${id}`} className="krish-search-row group/sr">
        <Globe className="h-4 w-4 shrink-0" />
        <span className="shrink-0 font-medium text-foreground/85">{label}</span>
        <span className="flex shrink-0 -space-x-1" aria-hidden>
          {icons.map((s) => (
            <span key={s.domain} className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-card ring-1 ring-border">
              <SiteIcon domain={s.domain} className="h-3 w-3" />
            </span>
          ))}
        </span>
        <span className="shrink-0 tabular-nums">{plural(items.length, "source")}</span>
        <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
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
                  data-testid={`web-source-card-${i + 1}`}
                  className="flex min-w-0 items-center gap-3 px-3 py-2 transition-colors hover:bg-surface">
                  <SiteIcon domain={s.domain} className="h-4 w-4 shrink-0" />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{s.title}</span>
                  <span className="max-w-[40%] shrink-0 truncate text-[12px] text-muted-foreground max-sm:hidden">{s.domain}</span>
                  <span className="w-4 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground/70">{i + 1}</span>
                </a>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
