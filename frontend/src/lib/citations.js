// Perplexity-style answers: [1] citations that link to web sources, and the "Related:" follow-up line.

// Hides the model's trailing "Related: a | b | c" line (or the Counsellor's "Replies: ...") while it streams
// (the server removes it when done).
export function hideRelatedLine(text) {
  const t = text || "";
  const at = t.search(/(^|\n)[ \t>*_#-]*\**(?:Related|Replies)\**:[^\n]*$/i);
  if (at >= 0) return t.slice(0, at).replace(/\s+$/, "");
  // The line is still arriving: "Rel", "Relat", "Repl"...
  const last = t.slice(t.lastIndexOf("\n") + 1).replace(/^[\s*_#>-]+/, "");
  if (last.length >= 2 && t.includes("\n") && ["related:", "replies:"].some((w) => w.startsWith(last.toLowerCase()))) {
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

// A site's short name for chips and cards: "economictimes.indiatimes.com" -> "economictimes",
// "en.wikipedia.org" -> "wikipedia", "uidai.gov.in" -> "uidai".
const SECOND_LEVEL = new Set(["co", "com", "gov", "ac", "org", "net", "edu", "nic", "res", "ind"]);
const UMBRELLA = new Set(["indiatimes", "blogspot", "wordpress", "substack", "medium", "github", "gitbook", "notion", "tumblr"]);
export const siteName = (domain) => {
  const parts = (domain || "").replace(/^(www|en|m|amp|mobile)\./, "").split(".").filter(Boolean);
  if (parts.length < 2) return parts[0] || "";
  const sld = parts.length > 2 && parts[parts.length - 1].length === 2 && SECOND_LEVEL.has(parts[parts.length - 2]);
  const at = parts.length - (sld ? 3 : 2);
  // On umbrella domains the subdomain is the site: economictimes.indiatimes.com, someone.substack.com.
  return at > 0 && UMBRELLA.has(parts[at]) ? parts[at - 1] : parts[at];
};
