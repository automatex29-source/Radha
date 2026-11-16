import { createContext, useContext } from "react";
import { faviconUrl, sourceDomain, siteName } from "@/lib/citations";

// The answer's web sources, so a citation chip can show the page it points to.
export const SourcesContext = createContext([]);

// A cited source inside an answer: a small chip with the site's icon and name, plus "+1" when several
// sources back the same sentence (like ChatGPT). Hovering it (on a laptop) previews the page, like Perplexity.
// Plain links in the answer stay ordinary links.
export default function SourceChip({ href, title, children, node, ...rest }) {
  const sources = useContext(SourcesContext);
  if (!title?.startsWith("cite")) {
    return <a href={href} title={title} target="_blank" rel="noopener noreferrer" {...rest}>{children}</a>;
  }
  const domain = sourceDomain(href);
  const more = title.slice(4).trim();
  const at = sources.findIndex((s) => s.url === href || s.url.replace(/ /g, "%20").replace(/\(/g, "%28").replace(/\)/g, "%29") === href);
  const src = at >= 0 ? sources[at] : null;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label={src?.title || domain} data-testid="citation-link"
      className="krish-cite group/cite relative ml-1 mr-0.5 inline-flex max-w-[9rem] items-center gap-1 rounded-full bg-surface-strong py-[3px] pl-1 pr-2 align-[0.12em] text-[10.5px] font-medium leading-none text-muted-foreground no-underline transition-colors hover:bg-primary hover:text-primary-foreground">
      {domain && <img src={faviconUrl(domain)} alt="" loading="lazy" className="h-3.5 w-3.5 shrink-0 rounded-full bg-white" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
      <span className="truncate">{siteName(domain) || children}</span>
      {more && <span className="shrink-0 opacity-70">{more}</span>}
      {src && (
        <span className="krish-cite-card" role="tooltip">
          <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <img src={faviconUrl(domain)} alt="" className="h-3.5 w-3.5 rounded-sm" onError={(e) => { e.currentTarget.style.display = "none"; }} />
            <span className="truncate">{domain}</span>
            <span className="ml-auto tabular-nums opacity-70">{at + 1}</span>
          </span>
          <span className="mt-1.5 line-clamp-2 text-[13px] font-semibold leading-snug text-foreground">{src.title}</span>
          {src.snippet && <span className="mt-1 line-clamp-3 text-[12px] font-normal leading-snug text-muted-foreground">{src.snippet}</span>}
        </span>
      )}
    </a>
  );
}
