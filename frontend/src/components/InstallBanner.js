import { useEffect, useRef, useState } from "react";
import BrandMark from "@/components/BrandMark";
import { Check, Download, Loader2, Maximize2, PlusSquare, Share, Sparkles, X, Zap } from "lucide-react";
import { canInstall, install, isIos, isStandalone, onInstallChange } from "@/lib/pwa";

const DISMISSED = "krish.installDismissed";
const SNOOZED = "krish.installSnoozedUntil";
const DELAY_MS = 20000; // let people look around first
const SNOOZE_MS = 7 * 24 * 60 * 60 * 1000; // "Not now" asks again in a week
const EXIT_MS = 260;

const PERKS = [
  { icon: Maximize2, label: "Full screen" },
  { icon: Zap, label: "Opens instantly" },
  { icon: Sparkles, label: "Daily verse" },
];

function hidden() {
  try {
    if (localStorage.getItem(DISMISSED)) return true;
    return Number(localStorage.getItem(SNOOZED) || 0) > Date.now();
  } catch { return false; }
}

/**
 * "Add Krish to your home screen" card. It springs in near the top, clear of the chat box, a while
 * after the app opens. Install shows progress and a short thank-you; "Not now" asks again in a week;
 * the close button (or Escape, or a swipe away on a phone) stops asking.
 */
export default function InstallBanner() {
  const [ready, setReady] = useState(canInstall());
  const [show, setShow] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | installing | done
  const [drag, setDrag] = useState({ x: 0, y: 0 });
  const start = useRef(null);
  const ios = isIos();

  useEffect(() => onInstallChange(setReady), []);
  useEffect(() => {
    if (hidden() || isStandalone()) return;
    const t = setTimeout(() => setShow(true), DELAY_MS);
    return () => clearTimeout(t);
  }, []);

  const close = (key = DISMISSED) => {
    try { localStorage.setItem(key, key === SNOOZED ? String(Date.now() + SNOOZE_MS) : "1"); } catch { /* optional */ }
    setLeaving(true);
    setTimeout(() => setShow(false), EXIT_MS);
  };

  useEffect(() => {
    if (!show) return;
    const onKey = (e) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [show]); // eslint-disable-line react-hooks/exhaustive-deps

  const onInstall = async () => {
    setStatus("installing");
    const accepted = await install();
    if (!accepted) { setStatus("idle"); close(SNOOZED); return; }
    setStatus("done");
    setTimeout(() => close(), 1600);
  };

  // Swipe sideways or up to throw the card away on a phone.
  const onPointerDown = (e) => { if (e.pointerType !== "mouse") start.current = { x: e.clientX, y: e.clientY }; };
  const onPointerMove = (e) => {
    if (!start.current) return;
    const dx = e.clientX - start.current.x;
    const dy = Math.min(0, e.clientY - start.current.y);
    setDrag(Math.abs(dx) > Math.abs(dy) ? { x: dx, y: 0 } : { x: 0, y: dy });
  };
  const onPointerUp = () => {
    if (!start.current) return;
    start.current = null;
    if (Math.abs(drag.x) > 80 || drag.y < -40) close(); else setDrag({ x: 0, y: 0 });
  };

  const phone = typeof window !== "undefined" && window.matchMedia?.("(max-width: 768px)").matches;
  if (!show || (!ready && !(ios && phone) && status === "idle")) return null;

  const moved = Math.abs(drag.x) + Math.abs(drag.y);
  const dragStyle = moved && !leaving
    ? { transform: `translate(${drag.x}px, ${drag.y}px)`, opacity: Math.max(0, 1 - moved / 220), animation: "none", transition: "none" }
    : undefined;

  return (
    <div
      role="dialog"
      aria-labelledby="install-title"
      className="pointer-events-none fixed inset-x-3 top-[calc(env(safe-area-inset-top)+4rem)] z-50 flex justify-center sm:inset-x-auto sm:right-5 sm:top-20 sm:justify-end"
      data-testid="install-banner"
    >
      <div
        className={`krish-install pointer-events-auto relative w-full max-w-[22rem] touch-pan-y overflow-hidden rounded-2xl border border-border bg-popover text-popover-foreground ${leaving ? "is-leaving" : ""}`}
        style={dragStyle}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <span className="krish-install-glow" aria-hidden="true" />
        <button
          type="button"
          onClick={() => close()}
          aria-label="Close"
          className="absolute right-2.5 top-2.5 z-10 flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          data-testid="install-banner-close"
        >
          <X className="h-3.5 w-3.5" />
        </button>

        {status === "done" ? (
          <div className="relative flex items-center gap-3 p-4 pr-10" data-testid="install-banner-done">
            <span className="krish-install-check flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
              <Check className="h-5 w-5" strokeWidth={2.5} />
            </span>
            <div className="min-w-0 text-sm">
              <p id="install-title" className="font-semibold">Krish is on your home screen</p>
              <p className="text-xs text-muted-foreground">Open it any time, like any other app.</p>
            </div>
          </div>
        ) : (
          <div className="relative p-4">
            <div className="flex items-start gap-3 pr-6">
              <span className="krish-install-icon relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-border bg-background shadow-sm">
                <BrandMark className="h-8 w-8" />
              </span>
              <div className="min-w-0 text-sm">
                <p id="install-title" className="font-semibold leading-tight">Get the Krish app</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {ready ? "Add Krish to your home screen and open it in one tap." : "Add Krish to your home screen in two quick steps."}
                </p>
              </div>
            </div>

            {ready ? (
              <ul className="mt-3 flex flex-wrap gap-1.5">
                {PERKS.map(({ icon: Icon, label }, i) => (
                  <li key={label} className="krish-install-item flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground" style={{ animationDelay: `${180 + i * 70}ms` }}>
                    <Icon className="h-3 w-3 text-primary" /> {label}
                  </li>
                ))}
              </ul>
            ) : (
              <ol className="mt-3 space-y-1.5 text-xs">
                {[
                  { icon: Share, text: <>Tap <b>Share</b> in Safari&apos;s toolbar</> },
                  { icon: PlusSquare, text: <>Choose <b>Add to Home Screen</b></> },
                ].map(({ icon: Icon, text }, i) => (
                  <li key={i} className="krish-install-item flex items-center gap-2.5 rounded-xl bg-muted px-2.5 py-2" style={{ animationDelay: `${180 + i * 90}ms` }}>
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">{i + 1}</span>
                    <span className="flex-1">{text}</span>
                    <Icon className="h-4 w-4 shrink-0 text-primary" />
                  </li>
                ))}
              </ol>
            )}

            <div className="mt-3.5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => close(SNOOZED)}
                className="h-8 rounded-lg px-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                data-testid="install-banner-later"
              >
                {ready ? "Not now" : "Got it"}
              </button>
              {ready && (
                <button
                  type="button"
                  onClick={onInstall}
                  disabled={status === "installing"}
                  className="krish-install-cta inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-xs font-semibold text-primary-foreground shadow-sm transition-transform hover:-translate-y-px active:translate-y-0 active:scale-[0.98] disabled:opacity-80"
                  data-testid="install-banner-button"
                >
                  {status === "installing" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                  {status === "installing" ? "Installing" : "Install"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
