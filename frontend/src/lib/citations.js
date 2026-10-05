// Perplexity-style answers: [1] citations that link to web sources, and the "Related:" follow-up line.

// Hides the model's trailing "Related: a | b | c" line while it streams (the server removes it when done).
export function hideRelatedLine(text) {
  const t = text || "";
  const at = t.search(/(^|\n)[ \t>*_#-]*\**Related\**:[^\n]*$/i);
  if (at >= 0) return t.slice(0, at).replace(/\s+$/, "");
  // The line is still arriving: "Rel", "Relat"...
  const last = t.slice(t.lastIndexOf("\n") + 1).replace(/^[\s*_#>-]+/, "");
  if (last.length >= 2 && t.includes("\n") && "related:".startsWith(last.toLowerCase())) {
    return t.slice(0, t.lastIndexOf("\n")).replace(/\s+$/, "");
  }
  return t;
}

const safeUrl = (url) => url.replace(/ /g, "%20").replace(/\(/g, "%28").replace(/\)/g, "%29");

// Turns [1] into a link to web source 1 (only numbers that exist), outside code.
export function linkCitations(text, web) {
  if (!web?.length || !text) return text;
  return text.split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/).map((part, i) => (i % 2 ? part
    : part.replace(/\[(\d{1,2})\](?![(:])/g, (whole, n) => {
      const src = web[Number(n) - 1];
      return src ? `[${n}](${safeUrl(src.url)} "cite")` : whole;
    }))).join("");
}

export const faviconUrl = (domain) => `https://icons.duckduckgo.com/ip3/${domain}.ico`;
