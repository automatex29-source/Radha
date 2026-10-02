import KIT_CSS from "./krish-ui.css?raw";

// Turns the code blocks in an AI reply into project files, a previewable page and a ZIP.

const FILE_RE = /([\w\-./]*[\w-]\.(?:html?|s?css|m?js|cjs|jsx|tsx?|json|md|py|svg|txt|xml|csv|tsv|ya?ml|toml|ini|env|sql|sh|bat|java|kt|c|h|cpp|hpp|cs|go|rs|rb|php|swift|dart|vue|r|lua))\b/i;
const DEFAULT_NAMES = {
  html: "index.html", htm: "index.html", css: "style.css", js: "app.js", javascript: "app.js", mjs: "app.js",
  jsx: "App.jsx", ts: "app.ts", typescript: "app.ts", json: "data.json", py: "main.py", python: "main.py",
  svg: "image.svg", csv: "data.csv", sql: "query.sql", sh: "script.sh", bash: "script.sh", yaml: "config.yaml",
  yml: "config.yaml", java: "Main.java", c: "main.c", cpp: "main.cpp", go: "main.go", rust: "main.rs",
  php: "index.php", ruby: "main.rb",
};

function cleanName(name) {
  const n = name.replace(/^\.?\/+/, "").trim();
  return n && !n.split("/").includes("..") ? n : null;
}

/** Files from the fenced code blocks of a markdown reply: [{ path, lang, content }].
 * `partial` (while the reply is still streaming) also returns the file being written, before its block closes. */
export function extractFiles(markdown, partial = false) {
  if (partial && ((markdown || "").match(/(^|\n)[ \t]*```/g) || []).length % 2) markdown += "\n```";
  const files = [];
  const spans = [];
  const seen = new Set();
  // A file that itself contains ``` is fenced with four or more backticks.
  const re = /(^|\n)[ \t]*(`{3,})([^\n`]*)\n([\s\S]*?)\n[ \t]*\2(?!`)/g;
  let m;
  while ((m = re.exec(markdown || ""))) {
    const info = m[3].trim();
    const content = m[4];
    const [langRaw = "", ...rest] = info.split(/[\s:]+/);
    let lang = langRaw.toLowerCase();
    let name = null;
    const infoName = rest.join(" ").match(FILE_RE) || (FILE_RE.test(langRaw) && langRaw.match(FILE_RE));
    if (infoName) {
      name = infoName[1];
      if (FILE_RE.test(langRaw)) lang = langRaw.split(".").pop().toLowerCase();
    } else {
      // "**index.html**", "### style.css" or "`app.js`:" on the line just above the block
      const before = markdown.slice(0, m.index + m[1].length).trimEnd().split("\n").pop() || "";
      const hit = before.length < 120 && before.match(FILE_RE);
      if (hit) name = hit[1];
    }
    if (!name && DEFAULT_NAMES[lang]) name = DEFAULT_NAMES[lang];
    name = name && cleanName(name);
    if (!name || !content.trim()) continue;
    const span = [m.index + m[1].length, re.lastIndex];
    if (seen.has(name)) {
      const i = files.findIndex((f) => f.path === name);
      files[i] = { path: name, lang, content, span }; // a later block replaces an earlier one
    } else {
      seen.add(name);
      files.push({ path: name, lang, content, span });
    }
    spans.push(span);
  }
  files.allSpans = spans;
  return files;
}

// AI pictures: the AI links https://krish-image.invalid/<what it shows>.jpg?w=800&h=600 and Krish AI's server
// makes them (backend/site_images.py). Mirrors site_images.rewrite.
const IMAGE_LINK_RE = /https?:\/\/krish-image\.invalid\/([^\s"'()<>?#]+?)(?:\.(?:jpe?g|png|webp))?(?:\?([^\s"'()<>#]*))?(?=[\s"'()<>#]|$)/g;
const snap = (v, d) => Math.max(64, Math.min(1600, Math.round((Number(v) || d) / 8) * 8));

export function rewriteImages(text) {
  if (!text || !text.includes("krish-image.invalid")) return text;
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return text.replace(IMAGE_LINK_RE, (_, what, query = "") => {
    const params = Object.fromEntries(query.split("&").filter((p) => p.includes("=")).map((p) => p.split("=")));
    const prompt = decodeURIComponent(what.replace(/\+/g, " ")).replace(/[-_]+/g, " ").replace(/[^\w\s,.'&]/g, " ").replace(/\s+/g, " ").trim().slice(0, 200);
    return `${origin}/api/site-image?prompt=${encodeURIComponent(prompt)}&w=${snap(params.w, 800)}&h=${snap(params.h, 600)}`;
  });
}

export const withImages = (files) => files.map((f) => ({ ...f, content: rewriteImages(f.content) }));

/** The files plus the built-in design kit (krish-ui.css) when a page links it and the reply didn't include it. */
export function withKit(files) {
  const linked = files.some((f) => /\.html?$/i.test(f.path) && /href=["'](?:\.\/)?krish-ui\.css["']/i.test(f.content));
  if (!linked || files.some((f) => f.path === "krish-ui.css")) return files;
  return [...files, { path: "krish-ui.css", lang: "css", content: KIT_CSS }];
}

/** The reply's text without its file code blocks (the side panel shows those), e.g. "Here is your site." */
export function stripFileBlocks(markdown, partial = false) {
  let text = markdown || "";
  const spans = extractFiles(text, partial).allSpans || [];
  for (const [a, b] of [...spans].sort((x, y) => y[0] - x[0])) text = text.slice(0, a) + text.slice(b);
  return text.replace(/\n{3,}/g, "\n\n").trim();
}

export function entryFile(files) {
  return files.find((f) => f.path.toLowerCase() === "index.html") || files.find((f) => /\.html?$/i.test(f.path));
}

const escapeScript = (s) => s.replace(/<\/script/gi, "<\\/script");
const escapeStyle = (s) => s.replace(/<\/style/gi, "<\\/style");
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// The preview iframe has an opaque origin, where touching localStorage throws; give it an in-memory one.
const STORAGE_SHIM = `<script>(function(){try{window.localStorage.getItem("x")}catch(e){function S(){var m={};return{getItem:function(k){return Object.prototype.hasOwnProperty.call(m,k)?m[k]:null},setItem:function(k,v){m[k]=String(v)},removeItem:function(k){delete m[k]},clear:function(){m={}},key:function(i){return Object.keys(m)[i]||null},get length(){return Object.keys(m).length}}}try{Object.defineProperty(window,"localStorage",{value:S(),configurable:true});Object.defineProperty(window,"sessionStorage",{value:S(),configurable:true})}catch(e){}}})();</script>`;

/** One self-contained HTML page with the project's CSS and JS files inlined. */
export function buildPreview(files) {
  files = withImages(withKit(files));
  const entry = entryFile(files);
  if (!entry) return null;
  let html = entry.content;
  const used = new Set([entry.path]);
  for (const f of files) {
    const base = f.path.split("/").pop();
    const ref = `(?:\\./)?(?:${escapeRe(f.path)}|${escapeRe(base)})`;
    if (/\.css$/i.test(f.path)) {
      const linkRe = new RegExp(`<link\\b[^>]*href=["']${ref}["'][^>]*>`, "gi");
      if (linkRe.test(html)) {
        used.add(f.path);
        html = html.replace(linkRe, () => `<style>\n${escapeStyle(f.content)}\n</style>`);
      }
    } else if (/\.m?js$/i.test(f.path)) {
      const scriptRe = new RegExp(`<script\\b([^>]*?)\\s*src=["']${ref}["']([^>]*)>\\s*</script>`, "gi");
      if (scriptRe.test(html)) {
        used.add(f.path);
        html = html.replace(scriptRe, (_, a, b) => `<script${a}${b}>\n${escapeScript(f.content)}\n</script>`);
      }
    }
  }
  // Files the page doesn't reference yet still belong to it.
  const css = files.filter((f) => !used.has(f.path) && /\.css$/i.test(f.path));
  const js = files.filter((f) => !used.has(f.path) && /\.m?js$/i.test(f.path));
  if (css.length) {
    const tag = css.map((f) => `<style>\n${escapeStyle(f.content)}\n</style>`).join("\n");
    html = /<\/head>/i.test(html) ? html.replace(/<\/head>/i, () => `${tag}\n</head>`) : tag + html;
  }
  if (js.length) {
    const tag = js.map((f) => `<script>\n${escapeScript(f.content)}\n</script>`).join("\n");
    html = /<\/body>/i.test(html) ? html.replace(/<\/body>(?![\s\S]*<\/body>)/i, () => `${tag}\n</body>`) : html + tag;
  }
  return /<head(\s[^>]*)?>/i.test(html) ? html.replace(/<head(\s[^>]*)?>/i, (h) => h + STORAGE_SHIM) : STORAGE_SHIM + html;
}

// ---- minimal ZIP writer (stored, no compression) ----
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** A ZIP archive (Uint8Array) of [{ path, content }]. */
export function makeZip(files, folder = "") {
  const enc = new TextEncoder();
  const chunks = [];
  const central = [];
  let offset = 0;
  const now = new Date();
  const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
  const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
  for (const f of files) {
    const name = enc.encode((folder ? `${folder}/` : "") + f.path);
    const data = enc.encode(f.content);
    const crc = crc32(data);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0x0800, true); // UTF-8 names
    local.setUint16(10, dosTime, true);
    local.setUint16(12, dosDate, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true);
    local.setUint32(22, data.length, true);
    local.setUint16(26, name.length, true);
    chunks.push(new Uint8Array(local.buffer), name, data);
    const cen = new DataView(new ArrayBuffer(46));
    cen.setUint32(0, 0x02014b50, true);
    cen.setUint16(4, 20, true);
    cen.setUint16(6, 20, true);
    cen.setUint16(8, 0x0800, true);
    cen.setUint16(12, dosTime, true);
    cen.setUint16(14, dosDate, true);
    cen.setUint32(16, crc, true);
    cen.setUint32(20, data.length, true);
    cen.setUint32(24, data.length, true);
    cen.setUint16(28, name.length, true);
    cen.setUint32(42, offset, true);
    central.push(new Uint8Array(cen.buffer), name);
    offset += 30 + name.length + data.length;
  }
  const size = central.reduce((n, c) => n + c.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.length, true);
  end.setUint16(10, files.length, true);
  end.setUint32(12, size, true);
  end.setUint32(16, offset, true);
  const parts = [...chunks, ...central, new Uint8Array(end.buffer)];
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let pos = 0;
  for (const p of parts) {
    out.set(p, pos);
    pos += p.length;
  }
  return out;
}

export function projectName(files, markdown) {
  const title = (entryFile(files)?.content.match(/<title>([^<]{1,60})<\/title>/i) || [])[1];
  const heading = ((markdown || "").match(/^#{1,3}\s+(.{1,60})$/m) || [])[1];
  return (title || heading || "My App").replace(/[*_`#]/g, "").trim() || "My App";
}
