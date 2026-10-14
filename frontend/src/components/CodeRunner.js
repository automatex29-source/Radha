import { useEffect, useRef, useState } from "react";

// Snippets in chat that can be tried in place: HTML/SVG shows a live preview, JavaScript runs and shows its output.
// Both run in a sandboxed iframe with no same-origin access, so a snippet can't touch Krish AI.
const PREVIEW = new Set(["html", "svg", "xml"]);
const RUN = new Set(["js", "javascript", "mjs"]);

export function runnableKind(lang, text) {
  if (PREVIEW.has(lang) && (lang !== "xml" || /<svg[\s>]/i.test(text))) return "preview";
  if (RUN.has(lang)) return "run";
  return null;
}

const RUNNER = (code, token) => `<!doctype html><meta charset="utf-8"><script>
const send = (kind, args) => parent.postMessage({ token: ${JSON.stringify(token)}, kind,
  text: args.map((a) => { try { return typeof a === "string" ? a : JSON.stringify(a, null, 2); } catch { return String(a); } }).join(" ") }, "*");
["log", "info", "warn", "error"].forEach((k) => { console[k] = (...a) => send(k, a); });
addEventListener("error", (e) => send("error", [e.message]));
addEventListener("unhandledrejection", (e) => send("error", [String(e.reason)]));
</script><script type="module">${code.replace(/<\/script/gi, "<\\/script")}
parent.postMessage({ token: ${JSON.stringify(token)}, kind: "done" }, "*");</script>`;

export default function CodeRunner({ kind, code }) {
  const frame = useRef(null);
  const [lines, setLines] = useState([]);
  const [token] = useState(() => Math.random().toString(36).slice(2));

  useEffect(() => {
    if (kind !== "run") return undefined;
    const onMessage = (e) => {
      if (e.source !== frame.current?.contentWindow || e.data?.token !== token) return;
      if (e.data.kind === "done") setLines((l) => (l.length ? l : [{ kind: "info", text: "Finished with no output." }]));
      else setLines((l) => [...l, { kind: e.data.kind, text: String(e.data.text).slice(0, 4000) }].slice(-200));
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [kind, token]);

  if (kind === "preview") {
    return (
      <iframe title="Code preview" sandbox="allow-scripts allow-forms allow-modals" data-testid="code-preview"
        className="mt-2 h-72 w-full rounded-lg border border-border bg-white" srcDoc={code} />
    );
  }
  return (
    <div className="mt-2 rounded-lg border border-border bg-sunken p-3 font-mono text-xs" data-testid="code-output">
      <iframe ref={frame} title="Code runner" sandbox="allow-scripts" className="hidden" srcDoc={RUNNER(code, token)} />
      {lines.length === 0 ? <p className="text-muted-foreground">Running…</p> : lines.map((l, i) => (
        <div key={i} className={`whitespace-pre-wrap break-words ${l.kind === "error" ? "text-rose-600 dark:text-rose-400" : l.kind === "warn" ? "text-amber-600 dark:text-amber-400" : "text-foreground"}`}>{l.text}</div>
      ))}
    </div>
  );
}
