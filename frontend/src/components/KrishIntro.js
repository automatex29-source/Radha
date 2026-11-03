import { useEffect, useState } from "react";
import BrandMark from "@/components/BrandMark";
import KrishWordmark from "@/components/KrishWordmark";

const BUILD_LINES = [
  "Reading your idea…",
  "Planning the pages and buttons…",
  "Picking colours and fonts…",
  "Writing the code…",
  "Testing every button…",
];
const IDLE_LINES = [
  "Describe your app in the chat.",
  "A shop, a booking page, a game…",
  "Krish builds it in seconds.",
];

/** Typed text that cycles through lines, like someone writing it live. */
function useTyping(lines) {
  const [state, setState] = useState({ i: 0, n: 0, del: false });
  useEffect(() => { setState({ i: 0, n: 0, del: false }); }, [lines]);
  useEffect(() => {
    const line = lines[state.i % lines.length];
    const full = state.n >= line.length;
    const wait = state.del ? 18 : full ? 1500 : 38;
    const t = setTimeout(() => {
      setState((s) => {
        if (!s.del && s.n >= line.length) return { ...s, del: true };
        if (s.del && s.n <= 0) return { i: s.i + 1, n: 0, del: false };
        return { ...s, n: s.n + (s.del ? -1 : 1) };
      });
    }, wait);
    return () => clearTimeout(t);
  }, [state, lines]);
  return lines[state.i % lines.length].slice(0, state.n);
}

/** The preview's start screen while a new app is still the empty starter: the Krish AI chakra, turning
 *  smoothly and faster while Krish builds, with what it is doing typed underneath. */
export default function KrishIntro({ building }) {
  const [burst, setBurst] = useState(0);
  const typed = useTyping(building ? BUILD_LINES : IDLE_LINES);

  return (
    <div data-testid="krish-intro"
      className="krish-intro relative flex h-full w-full select-none flex-col items-center justify-center overflow-hidden">
      <div className="krish-intro-grid" aria-hidden />
      <div className="krish-intro-glow" aria-hidden />
      {Array.from({ length: 18 }).map((_, i) => (
        <span key={i} aria-hidden className="krish-intro-spark"
          style={{ left: `${(i * 53) % 100}%`, animationDelay: `${(i * 0.37) % 6}s`, animationDuration: `${6 + (i % 5)}s` }} />
      ))}

      <button type="button" onClick={() => setBurst((b) => b + 1)} aria-label="Krish AI"
        className="krish-intro-stage relative">
        <div className={`krish-intro-ring r1 ${building ? "fast" : ""}`} />
        <div className={`krish-intro-ring r2 ${building ? "fast" : ""}`} />
        <div className={`krish-intro-ring r3 ${building ? "fast" : ""}`} />
        <div key={burst} className={`krish-intro-logo ${building ? "building" : ""} ${burst ? "burst" : ""}`}>
          <div className="krish-intro-disc" />
          <BrandMark className="relative h-full w-full text-white" thinking={building} />
        </div>
      </button>

      <h2 className="relative mt-10 text-center text-[26px] font-extrabold tracking-tight text-white sm:text-[32px]">
        <KrishWordmark className="krish-intro-word text-[30px] sm:text-[36px]" /> <span>{building ? "is building" : "App Builder"}</span>
      </h2>
      <p className="relative mt-3 h-6 text-center font-mono text-[14px] text-indigo-200/90 sm:text-[15px]" data-testid="krish-intro-typing">
        {typed}<span className="krish-intro-caret" />
      </p>
      {building && (
        <div className="relative mt-6 h-1.5 w-56 overflow-hidden rounded-full bg-white/10" aria-hidden>
          <div className="krish-intro-bar" />
        </div>
      )}
      <p className="relative mt-6 text-[11.5px] text-white/40">Tap the logo</p>
    </div>
  );
}
