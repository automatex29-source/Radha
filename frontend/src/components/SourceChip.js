import { faviconUrl, sourceDomain } from "@/lib/citations";

// A cited source inside an answer: a small chip with the site's icon and name, plus "+1" when several
// sources back the same sentence (like ChatGPT). Plain links in the answer stay ordinary links.
export default function SourceChip({ href, title, children, node, ...rest }) {
  if (!title?.startsWith("cite")) {
    return <a href={href} title={title} target="_blank" rel="noopener noreferrer" {...rest}>{children}</a>;
  }
  const domain = sourceDomain(href);
  const more = title.slice(4).trim();
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" title={domain} data-testid="citation-link"
      className="krish-cite mx-1 inline-flex max-w-[11rem] items-center gap-1 rounded-full bg-surface-strong py-0.5 pl-1 pr-2 align-[0.1em] text-[11px] font-medium leading-none text-muted-foreground no-underline transition-colors hover:bg-primary hover:text-primary-foreground">
      {domain && <img src={faviconUrl(domain)} alt="" loading="lazy" className="h-3.5 w-3.5 shrink-0 rounded-full bg-white" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
      <span className="truncate">{domain || children}</span>
      {more && <span className="shrink-0 opacity-70">{more}</span>}
    </a>
  );
}
