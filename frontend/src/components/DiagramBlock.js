// Pictures inside an answer. Krish draws a labelled diagram as SVG in a ```diagram block, and a split of money,
// time or marks as a small ```chart block (JSON). Here they are shown as a picture and a budget-style card.
// A diagram is shown as an image, which can't run scripts or load anything from the web, so a drawing can never
// act on the page; a chart is plain numbers and labels.
import { createContext, useContext, useMemo } from "react";
import { Loader2 } from "lucide-react";

const BLOCK = /```(?:diagram|chart)[^\n]*\n[\s\S]*?(?:```|$)/g;
const KINDS = { "language-diagram": "diagram", "language-chart": "chart" };
const COLORS = ["#16a34a", "#3b82f6", "#f59e0b", "#a855f7", "#ef4444", "#14b8a6", "#64748b", "#ec4899"];

/** True while the answer is still being written, so a half-written picture shows "Drawing…" instead of nothing. */
export const AnswerStreaming = createContext(false);

/** The answer text without its pictures (for Copy and for reading aloud). */
export function withoutDiagrams(text) {
  return (text || "").replace(BLOCK, "").replace(/\n{3,}/g, "\n\n").trim();
}

/** { kind: "diagram" | "chart", source } when a markdown <pre> node is one of Krish's pictures, otherwise null. */
export function visualSource(node) {
  const code = node?.children?.[0];
  if (code?.tagName !== "code") return null;
  const kind = (code.properties?.className || []).map((c) => KINDS[c]).find(Boolean);
  return kind ? { kind, source: (code.children || []).map((c) => c.value || "").join("") } : null;
}

function toImage(svg) {
  const start = svg.indexOf("<svg");
  const end = svg.lastIndexOf("</svg>");
  if (start < 0 || end < 0) return null;
  let picture = svg.slice(start, end + 6);
  if (!/^<svg[^>]*xmlns=/.test(picture)) picture = picture.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(picture)}`;
}

function Drawing() {
  const streaming = useContext(AnswerStreaming);
  if (!streaming) return null; // the answer ended without a complete picture: show the words alone
  return (
    <div data-testid="visual-drawing" className="my-3 flex h-32 max-w-xl items-center justify-center gap-2 rounded-2xl border border-border bg-card text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> Drawing a picture…
    </div>
  );
}

function DiagramBlock({ source }) {
  const src = useMemo(() => toImage(source), [source]);
  if (!src) return <Drawing />;
  return (
    <figure data-testid="diagram" className="my-3 max-w-xl overflow-hidden rounded-2xl border border-border bg-white">
      <img src={src} alt="Diagram for this answer" className="block h-auto w-full" />
    </figure>
  );
}

/** {title, total, unit, items: [{label, note, value}]} from the block, or null while it is incomplete or wrong. */
export function parseChart(source) {
  let data;
  try { data = JSON.parse(source); } catch { return null; }
  const items = (Array.isArray(data?.items) ? data.items : [])
    .map((it) => ({ label: String(it?.label ?? "").slice(0, 60), note: String(it?.note ?? "").slice(0, 80), value: Number(it?.value) }))
    .filter((it) => it.label && Number.isFinite(it.value) && it.value > 0)
    .slice(0, 8);
  if (items.length < 2) return null;
  const sum = items.reduce((a, it) => a + it.value, 0);
  return { title: String(data.title ?? "").slice(0, 80), total: String(data.total ?? "").slice(0, 40),
    unit: String(data.unit ?? "").slice(0, 6), items, sum };
}

function amount(value, unit) {
  const n = value.toLocaleString("en-IN", { maximumFractionDigits: 1 });
  return /^[₹$€£]$/.test(unit) ? `${unit}${n}` : unit ? `${n} ${unit}` : n;
}

function ChartBlock({ source }) {
  const chart = useMemo(() => parseChart(source), [source]);
  if (!chart) return <Drawing />;
  return (
    <figure data-testid="chart" className="my-3 max-w-xl rounded-2xl border border-border bg-card p-4">
      {chart.title && <figcaption className="text-xs font-medium text-muted-foreground">{chart.title}</figcaption>}
      {chart.total && <p className="!my-0.5 text-2xl font-bold text-emerald-600 dark:text-emerald-400">{chart.total}</p>}
      <div className="mt-2 flex h-3 gap-0.5 overflow-hidden rounded-full">
        {chart.items.map((it, i) => (
          <span key={i} style={{ width: `${(it.value / chart.sum) * 100}%`, background: COLORS[i % COLORS.length] }} />
        ))}
      </div>
      <ul className="!my-0 mt-3 !list-none space-y-2 !pl-0">
        {chart.items.map((it, i) => (
          <li key={i} className="!my-0 flex items-start gap-2.5 text-sm">
            <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-foreground">{it.label}</span>
              <span className="block text-xs text-muted-foreground">{Math.round((it.value / chart.sum) * 100)}%{it.note ? ` · ${it.note}` : ""}</span>
            </span>
            <span className="shrink-0 font-semibold tabular-nums text-foreground">{amount(it.value, chart.unit)}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

/** The picture for a block found by visualSource. */
export default function AnswerVisual({ kind, source }) {
  return kind === "chart" ? <ChartBlock source={source} /> : <DiagramBlock source={source} />;
}

/** For pages that show answers without the chat's code tools: pictures as pictures, other code as usual. */
export function DiagramPre({ node, children }) {
  const visual = visualSource(node);
  return visual ? <AnswerVisual {...visual} /> : <pre>{children}</pre>;
}
