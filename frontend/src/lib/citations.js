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

export const sourceDomain = (url) => {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
};

// A run of citations like [1], [2][3] or [1, 2] (not a markdown link or a reference definition).
const CITE_RUN = /\[\d{1,2}(?:\s*,\s*\d{1,2})*\](?:[ \t]*\[\d{1,2}(?:\s*,\s*\d{1,2})*\])*(?![(:])/g;

// Turns [1] into a link to web source 1 (only numbers that exist), outside code. A run like [1][2] becomes one
// link to the first source, titled "cite +1", which the chat draws as a "domain +1" chip (like ChatGPT).
export function linkCitations(text, web) {
  if (!web?.length || !text) return text;
  return text.split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/).map((part, i) => (i % 2 ? part
    : part.replace(CITE_RUN, (whole) => {
      const urls = [];
      for (const n of whole.match(/\d{1,2}/g)) {
        const src = web[Number(n) - 1];
        if (src && !urls.includes(src.url)) urls.push(src.url);
      }
      if (!urls.length) return whole;
      const label = sourceDomain(urls[0]) || "source";
      return `[${label}](${safeUrl(urls[0])} "cite${urls.length > 1 ? ` +${urls.length - 1}` : ""}")`;
    }))).join("");
}

export const faviconUrl = (domain) => `https://icons.duckduckgo.com/ip3/${domain}.ico`;
