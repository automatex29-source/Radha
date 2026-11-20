import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, mediaUrl } from "@/lib/api";

// Slides are drawn on a fixed 1280x720 canvas and scaled to fit, so the preview,
// thumbnails, present mode, PDF print and the .pptx (same coordinates) all match.
export const SLIDE_W = 1280;
export const SLIDE_H = 720;
const PAD = 80;

const FONTS_HREF =
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@500;700;800" +
  "&family=Space+Grotesk:wght@500;700&family=DM+Serif+Display&family=Playfair+Display:ital,wght@0,600;0,700;1,500" +
  "&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap";

// Present mode builds each slide in like the .pptx does: the content rises in, one piece after another.
const MOTION_CSS = "@keyframes deckRise{from{opacity:0;transform:translateY(28px)}to{opacity:1;transform:none}}" +
  "@keyframes deckFade{from{opacity:0}to{opacity:1}}" +
  "@media (prefers-reduced-motion: reduce){.deck-motion *{animation:none!important}}";

function loadFonts() {
  if (typeof document === "undefined" || document.getElementById("radha-deck-fonts")) return;
  const link = document.createElement("link");
  link.id = "radha-deck-fonts";
  link.rel = "stylesheet";
  link.href = FONTS_HREF;
  document.head.appendChild(link);
  const style = document.createElement("style");
  style.id = "radha-deck-motion";
  style.textContent = MOTION_CSS;
  document.head.appendChild(style);
}

let themesPromise = null;
export function loadThemes() {
  if (!themesPromise) {
    themesPromise = api.get("/decks/themes").then(({ data }) => data.themes).catch((e) => {
      themesPromise = null;
      throw e;
    });
  }
  return themesPromise;
}

export function useDeckThemes() {
  const [themes, setThemes] = useState([]);
  useEffect(() => {
    loadFonts();
    loadThemes().then(setThemes).catch(() => setThemes([]));
  }, []);
  return themes;
}

export const findTheme = (themes, id) => themes.find((t) => t.id === id) || themes[0];

const c = (hex) => `#${hex}`;

// AI-made and uploaded pictures live in Krish AI's own storage and need the sign-in token.
export const pictureSrc = (url) => (url && url.startsWith("/api/") ? mediaUrl(url) : url);

function Picture({ image, theme, style, pending }) {
  const [src, setSrc] = useState(pictureSrc(image?.url));
  const [failed, setFailed] = useState(false);
  useEffect(() => { setSrc(pictureSrc(image?.url)); setFailed(false); }, [image?.url]);
  const panel = {
    ...style,
    background: `linear-gradient(135deg, ${c(theme.accent)}, ${c(theme.accent2)})`,
  };
  if (!image && pending) {
    return (
      <div style={{ ...panel, display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.85 }}>
        <div className="animate-pulse" style={{ color: "#fff", fontSize: 26, fontWeight: 600, fontFamily: "Inter, sans-serif",
          textShadow: "0 2px 8px rgba(0,0,0,.35)" }}>Making picture…</div>
      </div>
    );
  }
  if (!image || failed) return <div style={panel} />;
  return (
    <div style={{ ...style, overflow: "hidden", background: c(theme.surface) }}>
      <img src={src} alt="" referrerPolicy="no-referrer" crossOrigin={undefined} draggable={false}
        onError={() => (src !== image.thumb && image.thumb ? setSrc(image.thumb) : setFailed(true))}
        style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
      {image.credit && (
        <div style={{ position: "absolute", right: 12, bottom: 10, fontSize: 11, color: "#fff", opacity: 0.75,
          textShadow: "0 1px 3px rgba(0,0,0,.8)", maxWidth: "90%", whiteSpace: "nowrap", overflow: "hidden",
          textOverflow: "ellipsis" }}>{image.credit}</div>
      )}
    </div>
  );
}

function shrink(size, text, soft) {
  const n = (text || "").length;
  if (n <= soft) return size;
  return Math.max(size * 0.62, size * Math.sqrt(soft / n));
}

function mix(a, b, k) {
  const pa = [0, 2, 4].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [0, 2, 4].map((i) => parseInt(b.slice(i, i + 2), 16));
  return pa.map((x, i) => Math.round(x + (pb[i] - x) * k).toString(16).padStart(2, "0")).join("");
}

/** Same colours as deck_render.palette, so the .pptx chart matches. */
export const chartPalette = (t) => [t.accent, t.accent2, mix(t.accent, t.title, 0.45), mix(t.accent2, t.bg, 0.35),
  mix(t.accent, t.accent2, 0.5), t.muted, mix(t.accent, t.bg, 0.5), mix(t.accent2, t.title, 0.5)];

const fmt = (v) => (Math.abs(v) >= 1000 ? v.toLocaleString("en", { maximumFractionDigits: 0 }) : String(Math.round(v * 10) / 10));

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v);
}

function Chart({ chart, theme: t, width, height }) {
  const colors = chartPalette(t).map(c);
  const font = { fontFamily: `'${t.html_body}', sans-serif` };
  const { labels, series, type } = chart;
  const multi = series.length > 1;
  if (type === "pie" || type === "doughnut") {
    const vals = series[0].values.map((v) => Math.max(0, v));
    const sum = vals.reduce((a, b) => a + b, 0) || 1;
    const r = Math.min(height, width * 0.55) / 2 - 10;
    const cx = r + 10, cy = height / 2;
    let angle = -Math.PI / 2;
    const arcs = vals.map((v, i) => {
      const a0 = angle, a1 = angle + (v / sum) * Math.PI * 2;
      angle = a1;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      const p = (a) => `${cx + r * Math.cos(a)} ${cy + r * Math.sin(a)}`;
      const mid = (a0 + a1) / 2;
      const d = vals.filter((x) => x > 0).length === 1 && v > 0
        ? `M ${cx - r} ${cy} A ${r} ${r} 0 1 1 ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx - r} ${cy} Z`
        : `M ${cx} ${cy} L ${p(a0)} A ${r} ${r} 0 ${large} 1 ${p(a1)} Z`;
      return { d, color: colors[i % colors.length], pct: Math.round((v / sum) * 100), lx: cx + r * 0.68 * Math.cos(mid), ly: cy + r * 0.68 * Math.sin(mid) };
    });
    return (
      <svg width={width} height={height} style={font}>
        {arcs.map((a, i) => <path key={i} d={a.d} fill={a.color} stroke={c(t.bg)} strokeWidth={3} />)}
        {type === "doughnut" && <circle cx={cx} cy={cy} r={r * 0.55} fill={c(t.bg)} />}
        {arcs.map((a, i) => a.pct >= 5 && (
          <text key={i} x={type === "doughnut" ? cx + (a.lx - cx) * 1.15 : a.lx} y={(type === "doughnut" ? cy + (a.ly - cy) * 1.15 : a.ly) + 7}
            textAnchor="middle" fontSize={20} fontWeight={700} fill="#fff">{a.pct}%</text>
        ))}
        {labels.map((l, i) => (
          <g key={i} transform={`translate(${2 * r + 50}, ${cy - (labels.length * 38) / 2 + i * 38})`}>
            <rect width={18} height={18} rx={4} fill={colors[i % colors.length]} y={2} />
            <text x={30} y={17} fontSize={20} fill={c(t.text)}>{l}</text>
          </g>
        ))}
      </svg>
    );
  }
  const top = multi ? 44 : 20, left = 70, bottom = 50;
  const w = width - left - 10, h = height - top - bottom;
  const all = series.flatMap((sr) => sr.values);
  const max = niceMax(Math.max(...all, 0));
  const min = Math.min(0, ...all);
  const y = (v) => top + h - ((v - min) / (max - min || 1)) * h;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((k) => min + (max - min) * k);
  const band = w / labels.length;
  return (
    <svg width={width} height={height} style={font}>
      {multi && series.map((sr, i) => (
        <g key={i} transform={`translate(${left + i * 180}, 6)`}>
          <rect width={16} height={16} rx={4} fill={colors[i % colors.length]} y={2} />
          <text x={24} y={16} fontSize={17} fill={c(t.text)}>{sr.name}</text>
        </g>
      ))}
      {ticks.map((v, i) => (
        <g key={i}>
          <line x1={left} x2={left + w} y1={y(v)} y2={y(v)} stroke={c(t.muted)} strokeOpacity={0.25} />
          <text x={left - 12} y={y(v) + 6} textAnchor="end" fontSize={16} fill={c(t.muted)}>{fmt(v)}</text>
        </g>
      ))}
      {labels.map((l, i) => (
        <text key={i} x={left + band * (i + 0.5)} y={top + h + 32} textAnchor="middle" fontSize={17} fill={c(t.muted)}>{l}</text>
      ))}
      {type === "line" ? series.map((sr, si) => {
        const pts = sr.values.map((v, i) => [left + band * (i + 0.5), y(v)]);
        return (
          <g key={si}>
            <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={colors[si % colors.length]} strokeWidth={5} strokeLinejoin="round" />
            {pts.map(([px, py], i) => <circle key={i} cx={px} cy={py} r={7} fill={colors[si % colors.length]} stroke={c(t.bg)} strokeWidth={3} />)}
            {!multi && pts.map(([px, py], i) => <text key={`t${i}`} x={px} y={py - 16} textAnchor="middle" fontSize={18} fontWeight={700} fill={c(t.title)}>{fmt(sr.values[i])}</text>)}
          </g>
        );
      }) : labels.map((_, i) => {
        const gw = band * 0.7, bw = gw / series.length;
        return series.map((sr, si) => {
          const v = sr.values[i];
          const x = left + band * i + (band - gw) / 2 + si * bw;
          const y0 = y(Math.max(0, v)), y1 = y(Math.min(0, v));
          return (
            <g key={`${i}-${si}`}>
              <rect x={x + 3} y={y0} width={bw - 6} height={Math.max(1, y1 - y0)} rx={6}
                fill={multi || labels.length < 2 ? colors[si % colors.length] : c(mix(t.accent, t.bg, 0.55 * (1 - (i + 1) / labels.length)))} />
              {!multi && <text x={x + bw / 2} y={y0 - 10} textAnchor="middle" fontSize={18} fontWeight={700} fill={c(t.title)}>{fmt(v)}</text>}
            </g>
          );
        });
      })}
    </svg>
  );
}

/** Section slides count their own parts: the 2nd section of a deck is "02", whatever its slide number. */
export const partNumber = (slides, index) => (slides || []).slice(0, index + 1).filter((x) => x?.layout === "section").length || 1;

const alpha = (hex, a) => `#${hex}${Math.round(a * 255).toString(16).padStart(2, "0")}`;

function Decor({ t, layout, index }) {
  const soft = t.dark ? 0.1 : 0.08;
  const dot = (x, y, d, color, o = 0.8) => ({ position: "absolute", left: x, top: y, width: d, height: d, borderRadius: "50%", background: alpha(color, o) });
  if (layout === "cover" || layout === "closing" || !layout) {
    return (
      <>
        <div style={dot(SLIDE_W - 420, -220, 640, t.accent, soft + 0.06)} />
        <div style={dot(-240, SLIDE_H - 260, 480, t.accent2, soft + 0.02)} />
        <div style={{ ...dot(SLIDE_W - 250, SLIDE_H - 230, 300, t.accent2, 0), border: `2px solid ${c(t.accent2)}` }} />
        <div style={dot(120, 90, 18, t.accent2)} />
        <div style={dot(SLIDE_W - 200, 560, 12, t.accent)} />
      </>
    );
  }
  if (layout === "image_right" || layout === "image_left") {
    return <div style={dot(layout === "image_right" ? 520 : 1080, SLIDE_H - 140, 240, t.accent, soft)} />;
  }
  // the .pptx counts slides from 1, so its "odd" slides are our even indexes
  return index % 2 === 0 ? (
    <>
      <div style={dot(SLIDE_W - 230, -170, 400, t.accent, soft)} />
      <div style={dot(SLIDE_W - 120, 150, 14, t.accent2, 0.7)} />
    </>
  ) : (
    <>
      <div style={dot(-170, SLIDE_H - 210, 380, t.accent2, soft)} />
      <div style={dot(SLIDE_W - 150, 70, 14, t.accent, 0.7)} />
    </>
  );
}

export default function Slide({ slide, theme, index = 0, total = 1, pending = false, animate = false, deckTitle = "", part = 1 }) {
  if (!theme) return <div style={{ width: SLIDE_W, height: SLIDE_H, background: "#111" }} />;
  const t = theme;
  // entrance animation for the n-th piece of content (present mode only)
  const step = (n, kind = "deckRise", gap = 180) => (animate
    ? { animation: `${kind} ${kind === "deckRise" ? 0.6 : 0.5}s cubic-bezier(.2,.7,.2,1) ${0.35 + n * gap / 1000}s both` } : {});
  const onAccent = t.dark ? c(t.bg) : "#fff";
  const H = (extra) => ({ fontFamily: `'${t.html_heading}', 'Plus Jakarta Sans', sans-serif`, color: c(t.title),
    fontWeight: t.html_heading.includes("Serif") || t.html_heading.includes("Playfair") ? 600 : 700,
    letterSpacing: "-0.02em", lineHeight: 1.08, margin: 0, ...extra });
  const body = { fontFamily: `'${t.html_body}', 'Plus Jakarta Sans', sans-serif`, color: c(t.text) };
  const muted = { ...body, color: c(t.muted) };
  const bar = (extra) => <div style={{ width: 64, height: 6, borderRadius: 3, background: c(t.accent), ...extra }} />;
  const s = slide || {};
  const L = s.layout;
  const cardBox = { background: c(t.surface), borderRadius: 20, border: t.dark ? "1px solid rgba(255,255,255,.06)" : `1px solid ${c(mix(t.accent, t.bg, 0.75))}`,
    boxShadow: t.dark ? "0 10px 30px rgba(0,0,0,.25)" : "0 10px 30px rgba(0,0,0,.06)" };

  const Heading = ({ x = PAD, w = SLIDE_W - 2 * PAD }) => (
    <div style={{ position: "absolute", left: x, top: 64, width: w, height: 110, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
      <h2 style={H({ fontSize: shrink(44, s.title, 40) })}>{s.title}</h2>
      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>{bar()}<div style={{ width: 14, height: 6, borderRadius: 3, background: c(t.accent2) }} /></div>
    </div>
  );

  const Bullets = ({ items, size = 26, style, staggered = true }) => {
    if (!items?.length) return null;
    const fs = Math.min(size, items.length <= 4 ? 26 : 22);
    return (
      <ul style={{ listStyle: "none", padding: 0, margin: 0, ...style }}>
        {items.map((b, i) => (
          <li key={i} style={{ ...body, fontSize: fs, lineHeight: 1.35, display: "flex", gap: 16, marginBottom: fs * 0.7, ...(staggered ? step(i, "deckFade", 160) : {}) }}>
            <span style={{ flex: "none", width: 10, height: 10, borderRadius: 5, background: c(i % 2 ? t.accent2 : t.accent), marginTop: fs * 0.5 }} />
            <span>{b}</span>
          </li>
        ))}
      </ul>
    );
  };

  const Badge = ({ label, color, d = 72, size }) => (
    <div style={{ width: d, height: d, borderRadius: "50%", background: alpha(color, t.dark ? 0.2 : 0.14), flex: "none",
      display: "flex", alignItems: "center", justifyContent: "center", ...H({ fontSize: size || d * 0.46, color: c(color), lineHeight: 1 }) }}>{label}</div>
  );
  const tone = (i) => (i % 2 ? t.accent2 : t.accent);

  let content = null;
  if (L === "cover" || L === "closing" || !L) {
    const img = L === "cover" && (s.image || (pending && s.image_query));
    const align = img ? "left" : "center";
    const tw = img ? 560 : SLIDE_W - 2 * PAD - 120;
    content = (
      <>
        {img && <Picture image={s.image} theme={t} pending={pending} style={{ position: "absolute", left: 680, top: 0, width: 600, height: SLIDE_H }} />}
        <div style={{ position: "absolute", left: img ? PAD : (SLIDE_W - tw) / 2, top: 150, width: tw, height: 250,
          display: "flex", flexDirection: "column", justifyContent: "flex-end", textAlign: align }}>
          <h1 style={H({ fontSize: shrink(64, s.title, 36), lineHeight: 1.02 })}>{s.title}</h1>
        </div>
        {bar({ position: "absolute", top: 420, left: img ? PAD : (SLIDE_W - 90) / 2, width: 90, height: 7, ...step(0, "deckFade") })}
        <p style={{ ...muted, position: "absolute", left: img ? PAD : (SLIDE_W - tw) / 2, top: 452, width: tw, margin: 0,
          fontSize: shrink(26, s.subtitle || s.body, 110), lineHeight: 1.35, textAlign: align, ...step(1) }}>{s.subtitle || s.body}</p>
      </>
    );
  } else if (L === "section") {
    const d = 460, dx = SLIDE_W - PAD - d + 40, dy = (SLIDE_H - d) / 2;
    content = (
      <>
        <div style={{ position: "absolute", left: dx, top: dy, width: d, height: d, borderRadius: "50%", border: `2px solid ${c(t.accent)}`, ...step(0, "deckFade") }} />
        <div style={{ position: "absolute", left: dx + 60, top: dy + 60, width: d - 120, height: d - 120, borderRadius: "50%",
          background: `linear-gradient(135deg, ${c(t.accent)}, ${c(t.accent2)})`, display: "flex", alignItems: "center", justifyContent: "center", ...step(1) }}>
          <span style={H({ fontSize: 150, color: onAccent, lineHeight: 1 })}>{String(part).padStart(2, "0")}</span>
        </div>
        <div style={H({ position: "absolute", left: PAD, top: 140, fontSize: 18, color: c(t.accent), letterSpacing: "0.12em" })}>PART</div>
        <div style={{ position: "absolute", left: PAD, top: 190, width: 600, height: 250, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
          <h2 style={H({ fontSize: shrink(56, s.title, 30), lineHeight: 1.02 })}>{s.title}</h2>
        </div>
        {bar({ position: "absolute", left: PAD, top: 462, width: 90, height: 7 })}
        {(s.subtitle || s.body) && <p style={{ ...muted, position: "absolute", left: PAD, top: 494, width: 600, margin: 0,
          fontSize: shrink(24, s.subtitle || s.body, 120), lineHeight: 1.35, ...step(2) }}>{s.subtitle || s.body}</p>}
      </>
    );
  } else if (L === "agenda") {
    const entries = (s.bullets?.length ? s.bullets : (s.items || []).map((it) => it.title).filter(Boolean)).slice(0, 6);
    const cols = entries.length > 3 ? 2 : 1;
    const perCol = Math.max(1, Math.ceil(entries.length / cols));
    const gap = 40, cw = (SLIDE_W - 2 * PAD - gap * (cols - 1)) / cols;
    const rowH = Math.min(130, (SLIDE_H - 220 - 70) / perCol);
    content = (
      <>
        <Heading />
        {entries.map((e, i) => {
          const col = Math.floor(i / perCol), row = i % perCol;
          return (
            <div key={i} style={{ ...cardBox, boxShadow: "none", position: "absolute", left: PAD + col * (cw + gap), top: 215 + row * rowH, width: cw,
              height: rowH - 18, borderRadius: 16, display: "flex", alignItems: "center", gap: 20, padding: "0 20px", boxSizing: "border-box", ...step(i, "deckRise", 150) }}>
              <Badge label={String(i + 1).padStart(2, "0")} color={tone(i)} d={56} size={22} />
              <span style={H({ fontSize: shrink(cols === 1 ? 26 : 23, e, 34), fontWeight: 500, lineHeight: 1.2 })}>{e}</span>
            </div>
          );
        })}
      </>
    );
  } else if (L === "bullets") {
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD, top: 200, width: SLIDE_W - 2 * PAD }}>
          {s.body && <p style={{ ...muted, fontSize: shrink(24, s.body, 160), lineHeight: 1.4, margin: "0 0 28px" }}>{s.body}</p>}
          <Bullets items={s.bullets} />
        </div>
      </>
    );
  } else if (L === "image_right" || L === "image_left") {
    const right = L === "image_right";
    const tx = right ? PAD : 680;
    content = (
      <>
        <Picture image={s.image} theme={t} pending={pending} style={{ position: "absolute", top: 0, left: right ? 680 : 0, width: 600, height: SLIDE_H, ...step(0, "deckFade") }} />
        <Heading x={tx} w={520} />
        <div style={{ position: "absolute", left: tx, top: 200, width: 520 }}>
          {s.body && <p style={{ ...muted, fontSize: shrink(22, s.body, 150), lineHeight: 1.45, margin: "0 0 26px" }}>{s.body}</p>}
          <Bullets items={s.bullets} size={22} />
        </div>
      </>
    );
  } else if (L === "cards") {
    const items = s.items?.length ? s.items : (s.bullets || []).slice(0, 4).map((b) => ({ title: b, text: "", icon: "" }));
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD, top: 220, width: SLIDE_W - 2 * PAD, maxHeight: 430, display: "flex", gap: 28 }}>
          {items.map((it, i) => (
            <div key={i} style={{ ...cardBox, flex: 1, minHeight: 330, padding: 28, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative", ...step(i, "deckRise", 200) }}>
              <div style={{ position: "absolute", left: 28, top: 0, width: 56, height: 5, background: c(tone(i)) }} />
              <div style={{ marginTop: 4 }}><Badge label={it.icon || i + 1} color={tone(i)} size={it.icon ? 34 : 30} /></div>
              <h3 style={H({ fontSize: shrink(24, it.title, 24), marginTop: 22 })}>{it.title}</h3>
              <p style={{ ...body, fontSize: shrink(19, it.text, 110), lineHeight: 1.45, marginTop: 14 }}>{it.text}</p>
            </div>
          ))}
        </div>
      </>
    );
  } else if (L === "chart") {
    const cw = s.body ? 780 : SLIDE_W - 2 * PAD;
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD, top: 205, width: cw, height: 450, ...step(0, "deckFade") }}>
          {s.chart ? <Chart chart={s.chart} theme={t} width={cw} height={450} />
            : <p style={{ ...muted, fontSize: 22 }}>Add numbers to show a chart here.</p>}
        </div>
        {s.body && (
          <div style={{ ...cardBox, boxShadow: "none", borderRadius: 18, position: "absolute", left: PAD + cw + 40, top: 215, width: SLIDE_W - 2 * PAD - cw - 40,
            height: 330, boxSizing: "border-box", padding: "25px 24px 0 28px", overflow: "hidden", ...step(1, "deckRise", 350) }}>
            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 6, background: c(t.accent) }} />
            <div style={H({ fontSize: 13, color: c(t.accent), letterSpacing: "0.1em" })}>KEY POINT</div>
            <p style={{ ...body, fontSize: shrink(22, s.body, 150), lineHeight: 1.4, margin: "14px 0 0" }}>{s.body}</p>
          </div>
        )}
      </>
    );
  } else if (L === "stats") {
    const stats = s.stats || [];
    const gap = 28, cw = (SLIDE_W - 2 * PAD - gap * (Math.max(1, stats.length) - 1)) / Math.max(1, stats.length);
    const fitW = (size, v, w) => Math.max(20, Math.min(size, w / (Math.max(1, (v || "").length) * 0.6)));
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD, top: 225, width: SLIDE_W - 2 * PAD, display: "flex", gap }}>
          {stats.map((st, i) => (
            <div key={i} style={{ ...cardBox, flex: 1, height: 300, padding: "35px 32px 0", boxSizing: "border-box", position: "relative", overflow: "hidden", ...step(i, "deckRise", 200) }}>
              <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 6, background: c(tone(i)) }} />
              <div style={H({ fontSize: fitW(80, st.value, cw - 64), color: c(tone(i)), lineHeight: 1, height: 120, display: "flex", alignItems: "flex-end" })}>{st.value}</div>
              <div style={{ width: 48, height: 4, borderRadius: 2, background: c(t.dark ? t.muted : t.title), margin: "15px 0 16px" }} />
              <p style={{ ...body, fontSize: shrink(21, st.label, 50), lineHeight: 1.3, margin: 0 }}>{st.label}</p>
            </div>
          ))}
        </div>
        {s.body && <p style={{ ...muted, position: "absolute", left: PAD, top: 560, width: SLIDE_W - 2 * PAD, fontSize: 19, margin: 0, ...step(stats.length) }}>{s.body}</p>}
      </>
    );
  } else if (L === "steps") {
    const steps = s.items?.length ? s.items : (s.bullets || []).slice(0, 5).map((b) => ({ title: b, text: "" }));
    const cw = (SLIDE_W - 2 * PAD) / Math.max(1, steps.length);
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD + 28, top: 298, width: cw * (steps.length - 1), height: 4, background: alpha(t.accent2, 0.6), ...step(0, "deckFade") }} />
        {steps.map((st, i) => (
          <div key={i} style={{ position: "absolute", left: PAD + i * cw, top: 272, width: cw - 30, ...step(i + 1, "deckRise", 220) }}>
            <div style={{ position: "absolute", left: -8, top: -8, width: 72, height: 72, borderRadius: 36, background: alpha(t.accent, 0.22) }} />
            <div style={{ position: "relative", width: 56, height: 56, borderRadius: 28, background: c(tone(i)),
              display: "flex", alignItems: "center", justifyContent: "center", ...H({ fontSize: 24, color: onAccent }) }}>{i + 1}</div>
            <h3 style={H({ fontSize: shrink(24, st.title, 24), marginTop: 32 })}>{st.title}</h3>
            <p style={{ ...body, fontSize: shrink(18, st.text, 110), lineHeight: 1.45, marginTop: 12 }}>{st.text}</p>
          </div>
        ))}
      </>
    );
  } else if (L === "timeline") {
    const events = s.items?.length ? s.items : (s.bullets || []).slice(0, 6).map((b) => ({ title: b, text: "" }));
    const cw = (SLIDE_W - 2 * PAD) / Math.max(1, events.length);
    const fitW = (size, v, w) => Math.max(20, Math.min(size, w / (Math.max(1, (v || "").length) * 0.58)));
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD, top: 398, width: SLIDE_W - 2 * PAD, height: 4, background: alpha(t.accent2, 0.5), ...step(0, "deckFade") }} />
        {events.map((ev, i) => (
          <div key={i} style={{ position: "absolute", left: PAD + i * cw, top: 300, width: cw, height: 340, ...step(i + 1, "deckRise", 220) }}>
            <div style={H({ position: "absolute", left: 10, right: 10, top: 0, height: 70, display: "flex", alignItems: "flex-end", justifyContent: "center",
              fontSize: fitW(34, ev.title, cw - 20), color: c(tone(i)), textAlign: "center" })}>{ev.title}</div>
            <div style={{ position: "absolute", left: cw / 2 - 20, top: 80, width: 40, height: 40, borderRadius: 20, background: alpha(tone(i), 0.25) }} />
            <div style={{ position: "absolute", left: cw / 2 - 11, top: 89, width: 22, height: 22, borderRadius: 11, background: c(tone(i)) }} />
            <p style={{ ...body, position: "absolute", left: 12, right: 12, top: 140, margin: 0, textAlign: "center", fontSize: shrink(18, ev.text, 90), lineHeight: 1.4 }}>{ev.text}</p>
          </div>
        ))}
      </>
    );
  } else if (L === "quote") {
    const q = s.quote || s.title;
    content = (
      <>
        <div style={H({ position: "absolute", left: PAD, top: 60, fontSize: 200, color: c(t.accent), lineHeight: 1 })}>“</div>
        <div style={{ position: "absolute", left: 160, top: 200, width: SLIDE_W - 320, height: 300, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <p style={H({ fontSize: shrink(40, q, 110), fontStyle: "italic", fontWeight: 500, lineHeight: 1.2, textAlign: "center", ...step(0, "deckFade") })}>{q}</p>
        </div>
        {s.author && <p style={{ ...muted, position: "absolute", left: 160, top: 540, width: SLIDE_W - 320, textAlign: "center", fontSize: 22, margin: 0, ...step(1, "deckRise", 400) }}>— {s.author}</p>}
      </>
    );
  } else if (L === "comparison") {
    const most = Math.max(...["left", "right"].map((side) => (s[side]?.bullets || []).reduce((n, b) => n + 1 + Math.floor(b.length / 46), 0)));
    const boxH = Math.min(420, Math.max(260, 150 + most * 44));
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD, top: 220, width: SLIDE_W - 2 * PAD, height: boxH, display: "flex", gap: 32 }}>
          {["left", "right"].map((side, i) => (
            <div key={side} style={{ ...cardBox, flex: 1, overflow: "hidden", position: "relative", padding: "36px 36px", ...step(i, "deckRise", 250) }}>
              <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 8, background: c(i ? t.accent2 : t.accent) }} />
              <h3 style={H({ fontSize: 28, color: c(i ? t.accent2 : t.accent), marginBottom: 26 })}>{s[side]?.title}</h3>
              <Bullets items={s[side]?.bullets} size={22} staggered={false} />
            </div>
          ))}
        </div>
        <div style={{ position: "absolute", left: (SLIDE_W - 64) / 2, top: 220 + boxH / 2 - 32, width: 64, height: 64, borderRadius: 32,
          background: c(t.dark ? t.accent : t.title), display: "flex", alignItems: "center", justifyContent: "center",
          ...H({ fontSize: 20, color: c(t.dark ? t.bg : "FFFFFF") }), ...step(2, "deckFade", 200) }}>VS</div>
      </>
    );
  } else if (L === "table") {
    const tb = s.table;
    const rows = tb ? [...(tb.columns?.length ? [tb.columns] : []), ...(tb.rows || [])] : [];
    const head = !!tb?.columns?.length;
    const top = s.body ? 280 : 210;
    const rowH = rows.length ? Math.min(52, (SLIDE_H - top - 70) / rows.length) : 52;
    const fs = rowH >= 46 && (rows[0]?.length || 0) <= 4 ? 20 : rowH >= 38 ? 17 : 15;
    const isNum = (v) => /^[-+₹$€£]?\s?[\d.,]+\s?(%|x|Cr|L|K|M|B)?$/.test(v || "");
    const numCol = (ci) => ci > 0 && (tb?.rows || []).filter((r) => isNum(r[ci])).length * 2 > (tb?.rows || []).length;
    content = (
      <>
        <Heading />
        {s.body && <p style={{ ...muted, position: "absolute", left: PAD, top: 200, width: SLIDE_W - 2 * PAD, fontSize: 22, margin: 0 }}>{s.body}</p>}
        {tb ? (
          <table style={{ position: "absolute", left: PAD, top, width: SLIDE_W - 2 * PAD, borderCollapse: "collapse", fontSize: fs, ...step(0, "deckFade") }}>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} style={{ height: rowH, background: c(ri === 0 && head ? t.accent : ri % 2 ? t.surface : t.bg2) }}>
                  {row.map((v, ci) => (
                    <td key={ci} style={{ padding: "4px 18px", textAlign: numCol(ci) ? "center" : "left",
                      fontWeight: (ri === 0 && head) || ci === 0 ? 700 : 400,
                      color: c(ri === 0 && head ? (t.dark ? t.bg : "FFFFFF") : ci === 0 ? t.title : t.text) }}>{v}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Bullets items={s.bullets} style={{ position: "absolute", left: PAD, top: 220, width: SLIDE_W - 2 * PAD }} />}
      </>
    );
  }

  const showNumber = total > 1 && !["cover", "closing", "image_right", "image_left"].includes(L);
  return (
    <div className={animate ? "deck-motion" : undefined} style={{ width: SLIDE_W, height: SLIDE_H, position: "relative", overflow: "hidden",
      background: `linear-gradient(135deg, ${c(t.bg)}, ${c(t.bg2)})`, textAlign: "left", ...body, ...(animate ? { animation: "deckFade .45s ease both" } : {}) }}>
      <Decor t={t} layout={L} index={index} />
      {content}
      {showNumber && <div style={{ ...muted, position: "absolute", right: PAD, bottom: 26, fontSize: 14 }}>{index + 1} / {total}</div>}
      {showNumber && deckTitle && L !== "section" && (
        <div style={{ ...muted, position: "absolute", left: PAD, bottom: 26, fontSize: 14, maxWidth: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{deckTitle}</div>
      )}
    </div>
  );
}

/** A slide scaled to the width of its container (or to fit inside it with `fit`). */
export function ScaledSlide({ fit = false, className = "", style, ...props }) {
  const ref = useRef(null);
  const [scale, setScale] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      setScale(fit && h ? Math.min(w / SLIDE_W, h / SLIDE_H) : w / SLIDE_W);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [fit]);
  return (
    <div ref={ref} className={className} style={{ position: "relative", overflow: "hidden", ...(fit ? {} : { aspectRatio: "16 / 9" }), ...style }}>
      {scale > 0 && (
        <div style={{ position: "absolute", left: "50%", top: "50%", width: SLIDE_W, height: SLIDE_H,
          transform: `translate(-50%, -50%) scale(${scale})`, transformOrigin: "center" }}>
          <Slide {...props} />
        </div>
      )}
    </div>
  );
}
