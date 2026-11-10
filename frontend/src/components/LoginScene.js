import { useEffect, useState } from "react";
import { MessageSquare, Code2, FileText, Presentation, Image as ImageIcon, CalendarCheck, Mic, Sparkles } from "lucide-react";
import BrandMark from "@/components/BrandMark";
import Mascot from "@/components/Mascot";
import "./login-scene.css";

/**
 * Animated art for the login screen. `look` picks one of three concepts:
 *  - "aurora": drifting colour light and twinkling stars behind the form.
 *  - "orbit":  the chakra in the middle, with Krish's tools circling it.
 *  - "demo":   a little chat that plays itself, so people see Krish working.
 */

/* ---------- Backdrops (fill the whole page, behind everything) ---------- */
export function SceneBackdrop({ look }) {
  if (look === "aurora") {
    return (
      <div className="ls-backdrop" aria-hidden="true">
        <span className="ls-blob ls-blob-a" />
        <span className="ls-blob ls-blob-b" />
        <span className="ls-blob ls-blob-c" />
        <span className="ls-blob ls-blob-d" />
        <div className="ls-stars">
          {STARS.map((s, i) => <i key={i} style={{ left: `${s[0]}%`, top: `${s[1]}%`, animationDelay: `${s[2]}s`, width: s[3], height: s[3] }} />)}
        </div>
        <div className="ls-grain" />
      </div>
    );
  }
  if (look === "orbit") {
    return (
      <div className="ls-backdrop" aria-hidden="true">
        <span className="ls-sun" />
        <div className="ls-rays" />
      </div>
    );
  }
  if (look === "demo") {
    return (
      <div className="ls-backdrop" aria-hidden="true">
        <div className="ls-dots" />
        <div className="ls-sweep" />
      </div>
    );
  }
  return null;
}

/* ---------- Big art for the left half on laptops ---------- */
export function SceneHero({ look }) {
  if (look === "orbit") return <Orbit size="lg" />;
  if (look === "demo") return <ChatDemo />;
  return <Mascot className="krish-float -ml-2 mb-6 h-36 w-auto" />;
}

/* ---------- Small art above the form on phones ---------- */
export function SceneMobile({ look }) {
  if (look === "orbit") return <div className="mb-2 flex justify-center lg:hidden"><Orbit size="sm" /></div>;
  if (look === "demo") return <div className="mb-5 lg:hidden"><PromptTicker /></div>;
  return null;
}

/* ---------- Orbit ---------- */
const TOOLS = [
  { icon: MessageSquare, label: "Chat", tone: "#6366F1" },
  { icon: Code2, label: "Code", tone: "#0EA5E9" },
  { icon: Presentation, label: "Decks", tone: "#F97316" },
  { icon: FileText, label: "Docs", tone: "#10B981" },
  { icon: ImageIcon, label: "Images", tone: "#EC4899" },
  { icon: CalendarCheck, label: "Plans", tone: "#8B5CF6" },
];

function Orbit({ size }) {
  const lg = size === "lg";
  return (
    <div className={`ls-orbit ${lg ? "ls-orbit-lg" : "ls-orbit-sm"}`} aria-hidden="true">
      <span className="ls-ring ls-ring-1" />
      <span className="ls-ring ls-ring-2" />
      {lg && <span className="ls-ring ls-ring-3" />}
      <div className="ls-orbit-core">
        <span className="ls-core-glow" />
        <BrandMark className="ls-core-mark" thinking />
      </div>
      <div className="ls-orbit-track ls-track-outer">
        {TOOLS.slice(0, lg ? 6 : 4).map((t, i, arr) => (
          <span key={t.label} className="ls-planet" style={{ "--a": `${(360 / arr.length) * i}deg`, "--tone": t.tone }}>
            <span className="ls-planet-inner">
              <t.icon className="h-4 w-4" />
              {lg && <em>{t.label}</em>}
            </span>
          </span>
        ))}
      </div>
      {lg && (
        <div className="ls-orbit-track ls-track-inner">
          {[0, 120, 240].map((a) => <span key={a} className="ls-moon" style={{ "--a": `${a}deg` }} />)}
        </div>
      )}
    </div>
  );
}

/* ---------- Self-playing chat ---------- */
const SCRIPTS = [
  { q: "Plan a 3-day Goa trip under ₹15,000", a: ["Day 1 · North Goa beaches, Fort Aguada sunset", "Day 2 · Old Goa churches, spice farm lunch", "Day 3 · Palolem kayaking, back by 7 pm"], chip: "Trip plan ready" },
  { q: "Write a landing page for my bakery", a: ["Hero: “Fresh from our oven, every morning”", "Menu grid with today's specials", "WhatsApp order button"], chip: "App built" },
  { q: "Explain photosynthesis for class 8", a: ["Plants catch sunlight in chlorophyll", "They mix water + CO₂ into glucose", "Oxygen is what they breathe out"], chip: "Notes saved" },
];

function useLoop(steps, ms) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { setI(steps - 1); return; }
    const t = setInterval(() => setI((n) => (n + 1) % steps), ms);
    return () => clearInterval(t);
  }, [steps, ms]);
  return i;
}

function ChatDemo() {
  // 0 typing question · 1 sent · 2 thinking · 3-5 answer lines · 6 chip · 7 hold
  const tick = useLoop(SCRIPTS.length * 9, 900);
  const s = SCRIPTS[Math.floor(tick / 9)];
  const step = tick % 9;
  return (
    <div className="ls-demo mb-8" aria-hidden="true">
      <div className="ls-demo-bar"><span /><span /><span /><b>Krish AI</b></div>
      <div className="ls-demo-body">
        <div className={`ls-bubble ls-bubble-me ${step >= 1 ? "is-in" : ""}`}>{s.q}</div>
        <div className="ls-ai-row">
          <BrandMark className="h-7 w-7 shrink-0" thinking={step === 2} />
          <div className="ls-bubble ls-bubble-ai">
            {step === 2 && <span className="ls-typing"><i /><i /><i /></span>}
            {step >= 3 && s.a.map((line, n) => (
              <p key={line} className={step >= 3 + n ? "is-in" : ""}>{line}</p>
            ))}
            {step >= 6 && <span className="ls-chip"><Sparkles className="h-3 w-3" /> {s.chip}</span>}
          </div>
        </div>
      </div>
      <div className="ls-demo-input">
        <span className="ls-caret-text">{step === 0 ? <Typed text={s.q} key={s.q} /> : "Ask Krish anything…"}</span>
        <span className="ls-demo-mic"><Mic className="h-3.5 w-3.5" /></span>
      </div>
    </div>
  );
}

function Typed({ text }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setN((v) => Math.min(text.length, v + 2)), 35);
    return () => clearInterval(t);
  }, [text]);
  return <>{text.slice(0, n)}<span className="ls-caret" /></>;
}

function PromptTicker() {
  const i = useLoop(SCRIPTS.length, 3200);
  return (
    <div className="ls-ticker" aria-hidden="true">
      <BrandMark className="h-6 w-6 shrink-0" thinking />
      <span key={i} className="ls-ticker-text">“{SCRIPTS[i].q}”</span>
    </div>
  );
}

const STARS = Array.from({ length: 34 }, (_, i) => {
  const r = (n) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1;
  return [Math.round(r(1) * 100), Math.round(r(2) * 100), +(r(3) * 6).toFixed(1), r(4) > 0.75 ? 3 : 2];
});
