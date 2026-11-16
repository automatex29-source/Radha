import { useEffect, useRef, useState } from "react";
import ThinkingShape from "@/components/ThinkingShape";

/**
 * What the chat shows while Krish makes or edits a picture: a frame in the picture's own shape that takes turns
 * between contour lines rippling out and saffron and green brush strokes painting in, with
 * "Creating image · setting the scene" above it and a % counter in the corner. The other animations stay here
 * for LoadingCanvas (the App Builder uses "Gathering light").
 * The finished picture then fades in from a blur in the same spot (see PictureGallery).
 */

const SAF = [255, 138, 30], DEEP = [232, 90, 12], GRN = [19, 138, 75], LG = [63, 191, 127], GOLD = [255, 200, 110];
const mix = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const hash = (x, y) => { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s); };

// Each draws one frame: (ctx, width, height, seconds, background [r,g,b], dark).
export const ANIMATIONS = [
  ["Rangoli dots", (c, w, h, t, bg) => {
    fill(c, w, h, bg); const N = 22, g = w / N; const cx = w * (0.5 + 0.22 * Math.sin(t * 0.7)), cy = h * (0.5 + 0.18 * Math.cos(t * 0.55));
    for (let i = 0; i < N; i++) for (let j = 0; j < Math.ceil(h / g); j++) {
      const x = (i + 0.5) * g, y = (j + 0.5) * g; const d = Math.hypot(x - cx, y - cy) / w;
      const wv = 0.5 + 0.5 * Math.sin(d * 14 - t * 3.2); const env = clamp(1.25 - d * 1.9);
      c.fillStyle = rgba(mix(SAF, GRN, clamp((x / w) * 1.1 - 0.05)), 0.18 + 0.75 * wv * env);
      c.beginPath(); c.arc(x, y, g * (0.1 + 0.36 * wv * env), 0, 7); c.fill();
    }
  }],
  ["Shape shift tiles", (c, w, h, t, bg) => {
    fill(c, w, h, bg); const N = 11, g = w / N, s = g * 0.62;
    for (let i = 0; i < N; i++) for (let j = 0; j < Math.ceil(h / g); j++) {
      const m = 0.5 + 0.5 * Math.sin((i + j) * 0.42 - t * 2.6);
      c.save(); c.translate((i + 0.5) * g, (j + 0.5) * g); c.rotate((m * Math.PI) / 2); c.beginPath();
      round(c, -s / 2, -s / 2, s, s, (m * s) / 2); c.fillStyle = rgba((i * 7 + j * 3) % 9 === 0 ? GRN : SAF, 0.08 + 0.55 * m); c.fill(); c.restore();
    }
  }],
  ["Ink bloom", (c, w, h, t, bg) => {
    fill(c, w, h, bg); c.save(); c.filter = `blur(${w * 0.06}px)`;
    for (const [col, r, a, b, o] of [[SAF, 0.3, 0.6, 1.1, 0], [GOLD, 0.26, 0.9, 0.7, 2], [GRN, 0.22, 0.5, 0.9, 4], [DEEP, 0.18, 1.2, 0.6, 1], [LG, 0.2, 0.8, 1.3, 3]]) {
      const x = w * (0.5 + 0.28 * Math.sin(t * a * 0.6 + o)), y = h * (0.5 + 0.28 * Math.cos(t * b * 0.6 + o * 1.3));
      const R = Math.max(w, h) * (r + 0.05 * Math.sin(t + o)); const gr = c.createRadialGradient(x, y, 0, x, y, R);
      gr.addColorStop(0, rgba(col, 0.85)); gr.addColorStop(1, rgba(col, 0)); c.fillStyle = gr; c.fillRect(0, 0, w, h);
    }
    c.restore();
  }],
  ["Woven lines", (c, w, h, t, bg, dark) => {
    fill(c, w, h, bg); const sp = w / 34; const scan = ((t * 0.22) % 1.15) * h;
    for (let y = sp; y < h; y += sp) {
      const k = y / h, done = y < scan; c.beginPath();
      for (let x = 0; x <= w; x += 4) { const yy = y + Math.sin((x / w) * 9 + t * 2 + k * 6) * sp * 0.28; x ? c.lineTo(x, yy) : c.moveTo(x, yy); }
      c.strokeStyle = rgba(mix(SAF, GRN, k), done ? 0.75 : dark ? 0.2 : 0.12); c.lineWidth = done ? w * 0.006 : w * 0.003; c.stroke();
    }
    const gr = c.createLinearGradient(0, scan - 30, 0, scan + 6); gr.addColorStop(0, rgba(SAF, 0)); gr.addColorStop(1, rgba(SAF, 0.35));
    c.fillStyle = gr; c.fillRect(0, scan - 30, w, 36); c.fillStyle = rgba(DEEP, 0.9); c.fillRect(0, scan, w, w * 0.006);
  }],
  ["Mandala sketch", (c, w, h, t, bg, dark) => {
    fill(c, w, h, bg); const cx = w / 2, cy = h / 2, u = Math.min(w, h); const cyc = (t * 0.32) % 1.25;
    for (let k = 1; k <= 6; k++) {
      const R = u * 0.07 * k, n = 6 + k * 3, fr = clamp((cyc - k * 0.12) * 3.2); if (fr <= 0) continue;
      c.save(); c.translate(cx, cy); c.rotate((k % 2 ? 1 : -1) * t * 0.15); c.strokeStyle = rgba(k % 2 ? SAF : GRN, 0.75); c.lineWidth = u * 0.004;
      for (let i = 0; i < Math.ceil(n * fr); i++) { const a = (i / n) * Math.PI * 2; c.beginPath(); c.ellipse(Math.cos(a) * R, Math.sin(a) * R, u * 0.035, u * 0.012, a, 0, Math.PI * 2); c.stroke(); }
      c.beginPath(); c.arc(0, 0, R + u * 0.035, 0, Math.PI * 2 * fr); c.strokeStyle = dark ? "rgba(255,255,255,.12)" : "rgba(30,30,40,.12)"; c.stroke(); c.restore();
    }
    const m = 0.5 + 0.5 * Math.sin(t * 2.6), s = u * 0.075;
    c.save(); c.translate(cx, cy); c.rotate(m * Math.PI); c.beginPath(); round(c, -s / 2, -s / 2, s, s, (m * s) / 2);
    c.strokeStyle = dark ? "#ECEDF3" : "#12141F"; c.lineWidth = u * 0.008; c.stroke(); c.restore();
    c.fillStyle = rgba(SAF, 1); c.beginPath(); c.arc(cx, cy, s * 0.17, 0, 7); c.fill();
  }],
  ["Pixels to picture", (c, w, h, t, bg) => {
    const cyc = (t * 0.28) % 1; const b = Math.max(w / 48, (w / 5) * Math.pow(1 - cyc, 1.6));
    for (let y = 0; y < h; y += b) for (let x = 0; x < w; x += b) {
      const k = (y + b / 2) / h;
      let col = k < 0.55 ? mix([60, 60, 120], [255, 150, 90], k / 0.55) : k < 0.66 ? mix([255, 190, 110], [110, 60, 90], (k - 0.55) / 0.11) : mix([230, 140, 90], [50, 50, 95], (k - 0.66) / 0.34);
      const sun = Math.hypot(x + b / 2 - w * 0.62, y + b / 2 - h * 0.55) / w; if (sun < 0.18) col = mix([255, 240, 200], col, sun / 0.18);
      const n = (hash(Math.floor(x / b) + Math.floor(t * 6), Math.floor(y / b)) - 0.5) * 60 * (1 - cyc);
      c.fillStyle = `rgb(${col.map((v) => clamp(v + n, 0, 255) | 0)})`; c.fillRect(x, y, b + 1, b + 1);
    }
    c.fillStyle = rgba(bg, 0.55 * (1 - cyc)); c.fillRect(0, 0, w, h);
  }],
  ["Contour ripples", (c, w, h, t, bg) => {
    fill(c, w, h, bg); const cx = w * 0.5, cy = h * 0.52, max = Math.max(w, h) * 0.75;
    for (let i = 0; i < 16; i++) {
      const r = ((i * max) / 16 + t * w * 0.05) % max; const al = Math.sin((r / max) * Math.PI) * 0.8; c.beginPath();
      for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.05) {
        const rr = r + w * 0.03 * Math.sin(a * 3 + t * 0.8 + r * 0.02) + w * 0.015 * Math.sin(a * 5 - t);
        const x = cx + Math.cos(a) * rr, y = cy + Math.sin(a) * rr * 0.9; a ? c.lineTo(x, y) : c.moveTo(x, y);
      }
      c.closePath(); c.strokeStyle = rgba(mix(SAF, GRN, r / max), al); c.lineWidth = w * 0.005; c.stroke();
    }
  }],
  ["Gathering light", (c, w, h, t, bg) => {
    fill(c, w, h, bg); const cx = w / 2, cy = h / 2, u = Math.max(w, h);
    for (let i = 0; i < 340; i++) {
      const ph = (t * 0.35 + hash(i, 1)) % 1, r = u * 0.62 * (1 - ph), a = hash(i, 2) * Math.PI * 2 + ph * 3.2;
      c.fillStyle = rgba(i % 4 === 0 ? GRN : i % 3 === 0 ? GOLD : SAF, clamp(ph * 1.6) * 0.85 * (1 - ph * 0.6));
      c.beginPath(); c.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, Math.min(u * (0.003 + 0.007 * hash(i, 3)), 3 + 6 * hash(i, 3)) * (1.2 - ph * 0.6), 0, 7); c.fill();
    }
    const gr = c.createRadialGradient(cx, cy, 0, cx, cy, u * 0.16); gr.addColorStop(0, rgba(GOLD, 0.55 + 0.2 * Math.sin(t * 3))); gr.addColorStop(1, rgba(SAF, 0));
    c.fillStyle = gr; c.fillRect(0, 0, w, h);
  }],
  ["Brush strokes", (c, w, h, t, bg) => {
    fill(c, w, h, bg); const cyc = (t * 0.24) % 1; c.lineCap = "round";
    [[GOLD, 0.18], [SAF, 0.32], [DEEP, 0.44], [LG, 0.6], [GRN, 0.72], [SAF, 0.84], [GOLD, 0.95]].forEach(([col, y], i) => {
      const pr = clamp((cyc - i * 0.1) / 0.28); if (pr <= 0) return; c.beginPath();
      const x0 = -w * 0.1, x1 = x0 + w * 1.2 * pr;
      for (let x = x0; x <= x1; x += 6) { const yy = h * y + Math.sin((x / w) * 4 + i) * h * 0.04; x === x0 ? c.moveTo(x, yy) : c.lineTo(x, yy); }
      c.strokeStyle = rgba(col, 0.5); c.lineWidth = Math.min(w, h) * (0.09 + 0.03 * Math.sin(i * 2)); c.stroke();
    });
    if (cyc > 0.9) { c.fillStyle = rgba(bg, (cyc - 0.9) * 10); c.fillRect(0, 0, w, h); }
  }],
  ["Aurora sweep", (c, w, h, t, bg, dark) => {
    fill(c, w, h, bg); c.save(); c.filter = `blur(${w * 0.05}px)`;
    [[SAF, 0.35, 0], [GRN, 0.6, 2], [GOLD, 0.8, 4]].forEach(([col, y, o]) => {
      c.beginPath(); c.moveTo(0, h);
      for (let x = 0; x <= w; x += 8) c.lineTo(x, h * y + Math.sin((x / w) * 5 + t * 1.1 + o) * h * 0.08 + Math.sin((x / w) * 2 - t * 0.6) * h * 0.06);
      c.lineTo(w, h); c.closePath(); c.fillStyle = rgba(col, 0.38); c.fill();
    });
    c.restore(); const sx = (((t * 0.35) % 1.6) - 0.3) * w; const gr = c.createLinearGradient(sx - w * 0.2, 0, sx + w * 0.2, h * 0.3);
    const shine = dark ? 0.12 : 0.65; gr.addColorStop(0, "rgba(255,255,255,0)"); gr.addColorStop(0.5, `rgba(255,255,255,${shine})`); gr.addColorStop(1, "rgba(255,255,255,0)");
    c.fillStyle = gr; c.fillRect(0, 0, w, h);
  }],
  ["Painted ripples", (c, w, h, t, bg, dark) => {
    // Brush strokes keep painting in and softly fading, with contour lines flowing out over them.
    fill(c, w, h, bg); c.save(); c.lineCap = "round"; c.filter = `blur(${Math.max(1, w * 0.01)}px)`;
    const BR = [[GOLD, 0.16], [SAF, 0.3], [DEEP, 0.43], [LG, 0.57], [GRN, 0.7], [SAF, 0.83], [GOLD, 0.95]];
    BR.forEach(([col, y], i) => {
      const ph = (t / 6.5 + i / BR.length) % 1; const pr = clamp(ph / 0.45);
      const al = 0.46 * (ph < 0.72 ? 1 : 1 - (ph - 0.72) / 0.28);
      const x0 = -w * 0.15, x1 = x0 + w * 1.3 * pr, dir = i % 2 ? -1 : 1; c.beginPath();
      for (let x = x0; x <= x1; x += 6) {
        const px = dir > 0 ? x : w - x; const yy = h * y + Math.sin((x / w) * 3.6 + i * 1.7 + t * 0.25) * h * 0.05;
        x === x0 ? c.moveTo(px, yy) : c.lineTo(px, yy);
      }
      c.strokeStyle = rgba(col, al); c.lineWidth = Math.min(w, h) * (0.1 + 0.035 * Math.sin(i * 2.3)); c.stroke();
    });
    c.restore();
    const cx = w * 0.5, cy = h * 0.5, max = Math.max(w, h) * 0.78;
    for (let i = 0; i < 13; i++) {
      const r = ((i * max) / 13 + t * w * 0.045) % max; const al = Math.sin((r / max) * Math.PI) * (dark ? 0.75 : 0.6); c.beginPath();
      for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.05) {
        const rr = r + w * 0.03 * Math.sin(a * 3 + t * 0.8 + r * 0.02) + w * 0.015 * Math.sin(a * 5 - t);
        const x = cx + Math.cos(a) * rr * (w / Math.max(w, h)) * 1.1, y = cy + Math.sin(a) * rr * (h / Math.max(w, h)) * 1.05; a ? c.lineTo(x, y) : c.moveTo(x, y);
      }
      c.closePath(); c.strokeStyle = dark ? rgba(mix(GOLD, LG, r / max), al) : rgba(mix(DEEP, GRN, r / max), al); c.lineWidth = Math.max(1, w * 0.0035); c.stroke();
    }
  }],
];

function fill(c, w, h, bg) { if (!bg) { c.clearRect(0, 0, w, h); return; } c.fillStyle = rgba(bg, 1); c.fillRect(0, 0, w, h); }
function round(c, x, y, w, h, r) { if (c.roundRect) c.roundRect(x, y, w, h, r); else c.rect(x, y, w, h); }

// Pictures take turns: contour ripples, then brush strokes, crossfading. The App Builder uses "Gathering light".
const PICTURE_ANIMATIONS = ["Contour ripples", "Brush strokes"].map((name) => ANIMATIONS.find(([n]) => n === name)[1]);
const SEGMENT = 4.2; // seconds each plays: one full painting of the brush strokes
const FADE = 0.8;
const STAGES = [[0, "reading your idea"], [2.5, "setting the scene"], [7, "adding light and colour"], [14, "final touches"]];
const EDIT_STAGES = [[0, "looking at your picture"], [3, "making the change"], [12, "final touches"]];

// When each picture started, kept across re-renders and remounts so the % never jumps back.
const started = new Map();

export function pictureShape(size) {
  const [w, h] = String(size || "1024x1024").split("x").map(Number);
  return w > 0 && h > 0 ? w / h : 1;
}

export function frameWidth(ratio) {
  return ratio > 1.15 ? "min(100%, 34rem)" : ratio < 0.87 ? "min(100%, 21rem)" : "min(100%, 26rem)";
}

export default function PictureMaking({ step }) {
  const id = step?.id || "picture";
  if (!started.has(id)) started.set(id, performance.now());
  const editing = step?.name === "edit_image";
  const ratio = editing ? 1 : pictureShape(step?.args?.size);
  const canvasRef = useRef(null);
  const [secs, setSecs] = useState(() => (performance.now() - started.get(id)) / 1000);

  useEffect(() => {
    const cv = canvasRef.current; if (!cv) return undefined;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const ctx = cv.getContext("2d");
    const a = document.createElement("canvas"), b = document.createElement("canvas");
    let raf = 0, lastTick = 0;
    const draw = (now) => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const W = Math.round(cv.clientWidth * dpr), H = Math.round(cv.clientHeight * dpr);
      if (!W || !H) { raf = requestAnimationFrame(draw); return; }
      for (const x of [cv, a, b]) if (x.width !== W || x.height !== H) { x.width = W; x.height = H; }
      const dark = document.documentElement.classList.contains("dark");
      const bg = dark ? [14, 16, 23] : [251, 250, 248];
      const t = (now - started.get(id)) / 1000;
      const k = Math.floor(t / SEGMENT), local = t - k * SEGMENT, n = PICTURE_ANIMATIONS.length;
      PICTURE_ANIMATIONS[k % n](a.getContext("2d"), W, H, local, bg, dark);
      ctx.globalAlpha = 1; ctx.drawImage(a, 0, 0);
      if (!still && local > SEGMENT - FADE) {
        PICTURE_ANIMATIONS[(k + 1) % n](b.getContext("2d"), W, H, local - SEGMENT, bg, dark);
        ctx.globalAlpha = (local - (SEGMENT - FADE)) / FADE; ctx.drawImage(b, 0, 0); ctx.globalAlpha = 1;
      }
      if (now - lastTick > 250) { lastTick = now; setSecs(t); }
      if (!still) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [id]);

  const stages = editing ? EDIT_STAGES : STAGES;
  const stage = [...stages].reverse().find(([at]) => secs >= at)[1];
  // Eases towards 97% and waits there: free pictures can take 10 to 40 seconds.
  const pct = Math.min(97, Math.round(100 * (1 - Math.exp(-secs / 11))));

  return (
    <div className="mb-3" role="status" aria-label={editing ? "Changing your picture" : "Creating your picture"} data-testid="picture-making">
      <div className="mb-2 flex items-center gap-2 text-[13px] text-muted-foreground">
        <ThinkingShape size={13} />
        <span className="font-medium text-foreground">{editing ? "Changing your picture" : "Creating image"}</span>
        <span className="truncate">· {stage}</span>
      </div>
      <div className="krish-pic-frame" style={{ aspectRatio: ratio, width: frameWidth(ratio) }}>
        <canvas ref={canvasRef} className="block h-full w-full" />
        <span className="krish-pic-pct" data-testid="picture-making-percent">{pct}%</span>
      </div>
    </div>
  );
}

/**
 * One of the animations on its own, filling its box: the App Builder uses "Gathering light" while Krish writes code.
 * `transparent` leaves the background clear so it can sit over a coloured screen.
 */
export function LoadingCanvas({ name = "Gathering light", transparent = false, className = "" }) {
  const ref = useRef(null);
  useEffect(() => {
    const cv = ref.current; if (!cv) return undefined;
    const draw = (ANIMATIONS.find(([n]) => n === name) || ANIMATIONS.find(([n]) => n === "Gathering light"))[1];
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const ctx = cv.getContext("2d"); const t0 = performance.now(); let raf = 0;
    const frame = (now) => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const W = Math.round(cv.clientWidth * dpr), H = Math.round(cv.clientHeight * dpr);
      if (W && H) {
        if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
        const dark = document.documentElement.classList.contains("dark");
        const bg = dark ? [14, 16, 23] : [251, 250, 248];
        draw(ctx, W, H, (now - t0) / 1000 + 1.2, transparent ? null : bg, dark);
      }
      if (!still) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [name, transparent]);
  return <canvas ref={ref} aria-hidden="true" className={`block ${className}`} />;
}
