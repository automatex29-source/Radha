import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

// Slides are drawn on a fixed 1280x720 canvas and scaled to fit, so the preview,
// thumbnails, present mode, PDF print and the .pptx (same coordinates) all match.
export const SLIDE_W = 1280;
export const SLIDE_H = 720;
const PAD = 80;

const FONTS_HREF =
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@500;700;800" +
  "&family=Space+Grotesk:wght@500;700&family=DM+Serif+Display&family=Playfair+Display:ital,wght@0,600;0,700;1,500" +
  "&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap";

function loadFonts() {
  if (typeof document === "undefined" || document.getElementById("radha-deck-fonts")) return;
  const link = document.createElement("link");
  link.id = "radha-deck-fonts";
  link.rel = "stylesheet";
  link.href = FONTS_HREF;
  document.head.appendChild(link);
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

function Picture({ image, theme, style }) {
  const [src, setSrc] = useState(image?.url);
  const [failed, setFailed] = useState(false);
  useEffect(() => { setSrc(image?.url); setFailed(false); }, [image?.url]);
  const panel = {
    ...style,
    background: `linear-gradient(135deg, ${c(theme.accent)}, ${c(theme.accent2)})`,
  };
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

export default function Slide({ slide, theme, index = 0, total = 1 }) {
  if (!theme) return <div style={{ width: SLIDE_W, height: SLIDE_H, background: "#111" }} />;
  const t = theme;
  const H = (extra) => ({ fontFamily: `'${t.html_heading}', 'Plus Jakarta Sans', sans-serif`, color: c(t.title),
    fontWeight: t.html_heading.includes("Serif") || t.html_heading.includes("Playfair") ? 600 : 700,
    letterSpacing: "-0.02em", lineHeight: 1.08, margin: 0, ...extra });
  const body = { fontFamily: `'${t.html_body}', 'Plus Jakarta Sans', sans-serif`, color: c(t.text) };
  const muted = { ...body, color: c(t.muted) };
  const bar = (extra) => <div style={{ width: 64, height: 6, borderRadius: 3, background: c(t.accent), ...extra }} />;
  const s = slide || {};
  const L = s.layout;
  const cardBox = { background: c(t.surface), borderRadius: 20, border: t.dark ? "1px solid rgba(255,255,255,.06)" : `1px solid ${c(t.accent)}33`,
    boxShadow: t.dark ? "0 10px 30px rgba(0,0,0,.25)" : "0 10px 30px rgba(0,0,0,.06)" };

  const Heading = ({ x = PAD, w = SLIDE_W - 2 * PAD }) => (
    <div style={{ position: "absolute", left: x, top: 64, width: w, height: 110, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
      <h2 style={H({ fontSize: shrink(44, s.title, 40) })}>{s.title}</h2>
      {bar({ marginTop: 16 })}
    </div>
  );

  const Bullets = ({ items, size = 26, style }) => {
    if (!items?.length) return null;
    const fs = Math.min(size, items.length <= 4 ? 26 : 22);
    return (
      <ul style={{ listStyle: "none", padding: 0, margin: 0, ...style }}>
        {items.map((b, i) => (
          <li key={i} style={{ ...body, fontSize: fs, lineHeight: 1.35, display: "flex", gap: 16, marginBottom: fs * 0.7 }}>
            <span style={{ flex: "none", width: 10, height: 10, borderRadius: 5, background: c(t.accent), marginTop: fs * 0.5 }} />
            <span>{b}</span>
          </li>
        ))}
      </ul>
    );
  };

  let content = null;
  if (L === "cover" || L === "closing" || !L) {
    const img = L === "cover" && s.image;
    const align = img ? "left" : "center";
    const tw = img ? 560 : SLIDE_W - 2 * PAD - 120;
    content = (
      <>
        {img && <Picture image={s.image} theme={t} style={{ position: "absolute", left: 680, top: 0, width: 600, height: SLIDE_H }} />}
        <div style={{ position: "absolute", left: img ? PAD : (SLIDE_W - tw) / 2, top: 150, width: tw, height: 250,
          display: "flex", flexDirection: "column", justifyContent: "flex-end", textAlign: align }}>
          <h1 style={H({ fontSize: shrink(64, s.title, 36), lineHeight: 1.02 })}>{s.title}</h1>
        </div>
        {bar({ position: "absolute", top: 420, left: img ? PAD : (SLIDE_W - 90) / 2, width: 90, height: 7 })}
        <p style={{ ...muted, position: "absolute", left: img ? PAD : (SLIDE_W - tw) / 2, top: 452, width: tw, margin: 0,
          fontSize: shrink(26, s.subtitle || s.body, 110), lineHeight: 1.35, textAlign: align }}>{s.subtitle || s.body}</p>
      </>
    );
  } else if (L === "section") {
    content = (
      <div style={{ position: "absolute", left: PAD, top: 170, width: SLIDE_W - 2 * PAD }}>
        <div style={H({ fontSize: 96, color: c(t.accent), lineHeight: 1 })}>{String(index + 1).padStart(2, "0")}</div>
        <h2 style={H({ fontSize: shrink(56, s.title, 40), marginTop: 30 })}>{s.title}</h2>
        {(s.subtitle || s.body) && <p style={{ ...muted, fontSize: 26, marginTop: 24, maxWidth: 900 }}>{s.subtitle || s.body}</p>}
      </div>
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
        <Picture image={s.image} theme={t} style={{ position: "absolute", top: 0, left: right ? 680 : 0, width: 600, height: SLIDE_H }} />
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
        <div style={{ position: "absolute", left: PAD, top: 220, width: SLIDE_W - 2 * PAD, maxHeight: 420, display: "flex", gap: 28 }}>
          {items.map((it, i) => (
            <div key={i} style={{ ...cardBox, flex: 1, minHeight: 280, padding: 28, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              {it.icon ? <div style={{ fontSize: 44, lineHeight: 1, height: 64 }}>{it.icon}</div>
                : <div style={{ width: 44, height: 44, borderRadius: 22, background: c(t.accent), marginBottom: 20 }} />}
              <h3 style={H({ fontSize: shrink(24, it.title, 26), marginTop: 18 })}>{it.title}</h3>
              <p style={{ ...body, fontSize: shrink(18, it.text, 110), lineHeight: 1.45, marginTop: 14 }}>{it.text}</p>
            </div>
          ))}
        </div>
      </>
    );
  } else if (L === "stats") {
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD, top: 250, width: SLIDE_W - 2 * PAD, display: "flex" }}>
          {(s.stats || []).map((st, i) => (
            <div key={i} style={{ flex: 1, paddingRight: 30 }}>
              <div style={H({ fontSize: shrink(80, st.value, 6), color: c(t.accent), lineHeight: 1.1, height: 120, display: "flex", alignItems: "flex-end" })}>{st.value}</div>
              <div style={{ width: 48, height: 4, borderRadius: 2, background: c(t.accent2), margin: "15px 0 16px" }} />
              <p style={{ ...body, fontSize: 22, lineHeight: 1.35, margin: 0 }}>{st.label}</p>
            </div>
          ))}
        </div>
        {s.body && <p style={{ ...muted, position: "absolute", left: PAD, top: 570, width: SLIDE_W - 2 * PAD, fontSize: 20, margin: 0 }}>{s.body}</p>}
      </>
    );
  } else if (L === "steps") {
    const steps = s.items?.length ? s.items : (s.bullets || []).slice(0, 5).map((b) => ({ title: b, text: "" }));
    const cw = (SLIDE_W - 2 * PAD) / Math.max(1, steps.length);
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD + 28, top: 298, width: cw * (steps.length - 1), height: 4, background: c(t.accent2) }} />
        {steps.map((st, i) => (
          <div key={i} style={{ position: "absolute", left: PAD + i * cw, top: 272, width: cw - 30 }}>
            <div style={{ width: 56, height: 56, borderRadius: 28, background: c(t.accent), color: t.dark ? c(t.bg) : "#fff",
              display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 24, ...H({ color: t.dark ? c(t.bg) : "#fff" }) }}>{i + 1}</div>
            <h3 style={H({ fontSize: shrink(24, st.title, 24), marginTop: 24 })}>{st.title}</h3>
            <p style={{ ...body, fontSize: shrink(18, st.text, 110), lineHeight: 1.45, marginTop: 12 }}>{st.text}</p>
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
          <p style={H({ fontSize: shrink(40, q, 110), fontStyle: "italic", fontWeight: 500, lineHeight: 1.2, textAlign: "center" })}>{q}</p>
        </div>
        {s.author && <p style={{ ...muted, position: "absolute", left: 160, top: 540, width: SLIDE_W - 320, textAlign: "center", fontSize: 22, margin: 0 }}>— {s.author}</p>}
      </>
    );
  } else if (L === "comparison") {
    content = (
      <>
        <Heading />
        <div style={{ position: "absolute", left: PAD, top: 220, width: SLIDE_W - 2 * PAD, height: 420, display: "flex", gap: 32 }}>
          {["left", "right"].map((side, i) => (
            <div key={side} style={{ ...cardBox, flex: 1, overflow: "hidden", position: "relative", padding: "36px 36px" }}>
              <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 8, background: c(i ? t.accent2 : t.accent) }} />
              <h3 style={H({ fontSize: 28, color: c(i ? t.accent2 : t.accent), marginBottom: 26 })}>{s[side]?.title}</h3>
              <Bullets items={s[side]?.bullets} size={20} />
            </div>
          ))}
        </div>
      </>
    );
  }

  const showNumber = total > 1 && !["cover", "closing", "image_right", "image_left"].includes(L);
  return (
    <div style={{ width: SLIDE_W, height: SLIDE_H, position: "relative", overflow: "hidden",
      background: `linear-gradient(135deg, ${c(t.bg)}, ${c(t.bg2)})`, textAlign: "left", ...body }}>
      {content}
      {showNumber && <div style={{ ...muted, position: "absolute", right: PAD, bottom: 26, fontSize: 14 }}>{index + 1} / {total}</div>}
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
