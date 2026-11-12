// Formulas in answers: Krish writes maths as $...$ or \( ... \) (LaTeX). This tidies the text so the formula
// plugins can draw it, and loads those plugins only when an answer has a formula (they are large).
import { useEffect, useState } from "react";

const CODE = /(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g;
const LOOKS_LIKE_MATH = /[\\^_={}+*/<>]/;

/** True when the text may hold a formula. */
export function hasMath(text) {
  return /\$[^$]*\$|\\\(|\\\[/.test(text || "");
}

/** Turn \( \) and \[ \] into $ and $$, and keep prices like "$5 to $10" as plain text. Code is left alone. */
export function prepareMath(text) {
  if (!text || !hasMath(text)) return text || "";
  return text.split(CODE).map((part, i) => {
    if (i % 2) return part; // code
    return part
      .replace(/\\\[([\s\S]*?)\\\]/g, (_, m) => `\n$$\n${m.trim()}\n$$\n`)
      .replace(/\\\(([\s\S]*?)\\\)/g, (_, m) => `$${m.trim()}$`)
      // "$5 and $10": a dollar sign before a number, with nothing formula-like before the next dollar sign.
      // "$5$" (closed, no spaces) and "$3 + 4$" stay formulas.
      .replace(/\$(?=\d)([^$\n]*)(?=\$|\n|$)/g, (all, inner, at, whole) => {
        const closed = whole[at + all.length] === "$";
        return LOOKS_LIKE_MATH.test(inner) || (closed && !/\s/.test(inner)) ? all : `\\$${inner}`;
      });
  }).join("");
}

let loading = null;
function loadPlugins() {
  loading = loading || Promise.all([import("remark-math"), import("rehype-katex"), import("katex/dist/katex.min.css")])
    .then(([remark, rehype]) => ({ remark: [remark.default], rehype: [[rehype.default, { throwOnError: false, strict: false }]] }))
    .catch(() => { loading = null; return null; });
  return loading;
}

/** The formula plugins for ReactMarkdown, once loaded; null for text with no formula (or while loading). */
export function useMathPlugins(text) {
  const needed = hasMath(text);
  const [plugins, setPlugins] = useState(null);
  useEffect(() => {
    if (!needed || plugins) return undefined;
    let live = true;
    loadPlugins().then((p) => { if (live && p) setPlugins(p); });
    return () => { live = false; };
  }, [needed, plugins]);
  return needed ? plugins : null;
}
