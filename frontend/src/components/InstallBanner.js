import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import BrandMark from "@/components/BrandMark";
import { X } from "lucide-react";
import { canInstall, install, isIos, isStandalone, onInstallChange } from "@/lib/pwa";

const DISMISSED = "krish.installDismissed";
const DELAY_MS = 20000; // let people look around first

/** A small "Add Krish to your home screen" card, shown once a while after opening the app, until closed. */
export default function InstallBanner() {
  const [ready, setReady] = useState(canInstall());
  const [show, setShow] = useState(false);
  const ios = isIos();

  useEffect(() => onInstallChange(setReady), []);
  useEffect(() => {
    let dismissed = false;
    try { dismissed = Boolean(localStorage.getItem(DISMISSED)); } catch { /* optional */ }
    if (dismissed || isStandalone()) return;
    const t = setTimeout(() => setShow(true), DELAY_MS);
    return () => clearTimeout(t);
  }, []);

  const close = () => {
    setShow(false);
    try { localStorage.setItem(DISMISSED, "1"); } catch { /* optional */ }
  };

  const phone = typeof window !== "undefined" && window.matchMedia?.("(max-width: 768px)").matches;
  if (!show || (!ready && !(ios && phone))) return null;

  return (
    <div className="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-50 mx-auto max-w-md radha-fade-up" data-testid="install-banner">
      <div className="krish-glass flex items-center gap-3 rounded-2xl border border-border p-3 shadow-[0_12px_40px_rgba(15,23,42,0.18)]">
        <BrandMark className="h-10 w-10 shrink-0" />
        <div className="min-w-0 flex-1 text-sm">
          <p className="font-semibold">Add Krish to your home screen</p>
          <p className="text-xs text-muted-foreground">
            {ready ? "Open it like an app, full screen, in one tap." : <>Tap <b>Share</b>, then <b>Add to Home Screen</b>.</>}
          </p>
        </div>
        {ready && <Button size="sm" onClick={async () => { await install(); close(); }} data-testid="install-banner-button">Install</Button>}
        <button type="button" onClick={close} aria-label="Close" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
