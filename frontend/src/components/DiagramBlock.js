// A picture inside an answer. Krish draws a labelled diagram as SVG in a ```diagram block; here it is shown as
// an image. An image can't run scripts or load anything from the web, so a drawing can never act on the page.
import { useMemo } from "react";
import { Loader2 } from "lucide-react";

const BLOCK = /```diagram[^\n]*\n[\s\S]*?(?:```|$)/g;

/** The answer text without its drawings (for Copy and for reading aloud). */
export function withoutDiagrams(text) {
  return (text || "").replace(BLOCK, "").replace(/\n{3,}/g, "\n\n").trim();
}

/** The SVG text when a markdown <pre> node is a ```diagram block, otherwise null. */
export function diagramSource(node) {
  const code = node?.children?.[0];
  const classes = code?.properties?.className || [];
  if (code?.tagName !== "code" || !classes.includes("language-diagram")) return null;
  return (code.children || []).map((c) => c.value || "").join("");
}

function toImage(svg) {
  const start = svg.indexOf("<svg");
  const end = svg.lastIndexOf("</svg>");
  if (start < 0 || end < 0) return null;
  let picture = svg.slice(start, end + 6);
  if (!/^<svg[^>]*xmlns=/.test(picture)) picture = picture.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(picture)}`;
}

export default function DiagramBlock({ source }) {
  const src = useMemo(() => toImage(source), [source]);
  if (!src) {
    return (
      <div data-testid="diagram-drawing" className="my-3 flex h-40 max-w-xl items-center justify-center gap-2 rounded-2xl border border-border bg-card text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Drawing a picture…
      </div>
    );
  }
  return (
    <figure data-testid="diagram" className="my-3 max-w-xl overflow-hidden rounded-2xl border border-border bg-white">
      <img src={src} alt="Diagram for this answer" className="block h-auto w-full" />
    </figure>
  );
}

/** For pages that show answers without the chat's code tools: drawings as pictures, other code as usual. */
export function DiagramPre({ node, children }) {
  const source = diagramSource(node);
  return source === null ? <pre>{children}</pre> : <DiagramBlock source={source} />;
}
