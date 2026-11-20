import { useEffect, useState } from "react";
import { Block, PageTitle } from "@/components/SettingsDialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { canInstall, install, onInstallChange } from "@/lib/pwa";
import { toast } from "sonner";
import { AppWindow, Check, Download, Keyboard, Link2, Loader2, Power, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";

// Installers are built by .github/workflows/desktop.yml and kept on one GitHub release, so these links never change.
const RELEASE = "https://github.com/automatex29-source/Radha/releases/download/desktop-latest";
const PLATFORMS = {
  windows: { name: "Windows", file: `${RELEASE}/Krish-AI-Setup.exe`, note: "Windows 10 and 11", shortcut: "Ctrl + Alt + K" },
  mac: { name: "Mac", file: `${RELEASE}/Krish-AI-Mac.dmg`, note: "Apple silicon and Intel, macOS 11 or newer", shortcut: "Option + Command + K" },
  linux: { name: "Linux", file: `${RELEASE}/Krish-AI-Linux.AppImage`, note: "AppImage for most Linux computers", shortcut: "Ctrl + Alt + K" },
};

function detect() {
  const ua = navigator.userAgent || "";
  const platform = (navigator.userAgentData?.platform || navigator.platform || "").toLowerCase();
  const phone = /android|iphone|ipad|ipod|mobile/i.test(ua) || (platform === "macintel" && navigator.maxTouchPoints > 1);
  if (phone) return "phone";
  if (platform.includes("mac") || /mac os x/i.test(ua)) return "mac";
  if (platform.includes("linux") || /linux|cros/i.test(ua)) return "linux";
  return "windows";
}

const FIRST_OPEN = {
  windows: <>If Windows shows <b>"Windows protected your PC"</b>, click <b>More info</b>, then <b>Run anyway</b>. You only see this once.</>,
  mac: <>Open the downloaded file and drag <b>Krish AI</b> into <b>Applications</b>. The first time you open it, if your Mac says it can't check the app,
    go to <b>System Settings</b>, then <b>Privacy &amp; Security</b>, scroll down and click <b>Open Anyway</b>.</>,
  linux: <>Right-click the downloaded file, open <b>Properties</b>, allow it to run as a program, then double-click it.</>,
};

/** Settings > Desktop app: download Krish for the computer, or, inside the app, its version and options. */
export default function DesktopAppPanel() {
  const inApp = typeof window !== "undefined" && window.krishDesktop?.isDesktop;
  return (
    <>
      <PageTitle title="Desktop app" hint="Krish in its own window on your computer, one shortcut away." />
      {inApp ? <InsideApp /> : <GetApp />}
    </>
  );
}

function GetApp() {
  const os = detect();
  const main = PLATFORMS[os] || PLATFORMS.windows;
  const others = Object.entries(PLATFORMS).filter(([id]) => id !== os);
  const [pwaReady, setPwaReady] = useState(canInstall());
  useEffect(() => onInstallChange(setPwaReady), []);

  const copyLink = async () => {
    try { await navigator.clipboard.writeText("https://krishai.net"); toast.success("Link copied. Open it on your computer to download Krish."); }
    catch { toast.error("Couldn't copy. The address is krishai.net"); }
  };

  return (
    <>
      <div className="relative mb-2 overflow-hidden rounded-2xl border border-border bg-card p-5 sm:p-6" data-testid="desktop-app-hero">
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-orange-400/15 blur-3xl" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center">
          <img src="/desktop-app-icon.png" alt="" width={72} height={72} className="h-[72px] w-[72px] shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="font-heading text-[18px] font-semibold tracking-tight">
              {os === "phone" ? "Krish for your computer" : `Krish for ${main.name}`}
            </p>
            <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
              {os === "phone"
                ? "The desktop app is for laptops and computers. Open krishai.net on your computer and come back to this page to download it."
                : "Open Krish from anywhere with one shortcut, keep it in the taskbar, and get new features without doing anything."}
            </p>
          </div>
          {os === "phone" ? (
            <Button type="button" variant="outline" onClick={copyLink} className="h-10 shrink-0 gap-2" data-testid="desktop-copy-link">
              <Link2 className="h-4 w-4" /> Copy link
            </Button>
          ) : (
            <div className="flex shrink-0 flex-col items-stretch gap-1.5 sm:items-end">
              <Button asChild className="h-10 gap-2 px-5" data-testid="desktop-download">
                <a href={main.file} download><Download className="h-4 w-4" /> Download for {main.name}</a>
              </Button>
              <span className="text-center text-[11.5px] text-muted-foreground sm:text-right">{main.note}</span>
            </div>
          )}
        </div>
        <p className="relative mt-4 text-[12.5px] text-muted-foreground">
          {os === "phone" ? "Available for " : "Also for "}
          {(os === "phone" ? Object.entries(PLATFORMS) : others).map(([id, p], i, list) => (
            <span key={id}>
              <a href={p.file} download className="font-medium text-foreground underline-offset-4 hover:underline" data-testid={`desktop-download-${id}`}>{p.name}</a>
              {i < list.length - 2 ? ", " : i === list.length - 2 ? " and " : ""}
            </span>
          ))}
          .
        </p>
      </div>

      <Block title="What you get" icon={Sparkles} testid="desktop-features">
        <ul className="grid gap-2.5 sm:grid-cols-2">
          {[
            [Keyboard, `Press ${os === "mac" ? PLATFORMS.mac.shortcut : PLATFORMS.windows.shortcut} anywhere to open or hide Krish`],
            [AppWindow, "Its own window, separate from your browser tabs"],
            [Power, "Starts with your computer and waits quietly in the tray"],
            [RefreshCw, "Updates itself when there's something new"],
          ].map(([Icon, text]) => (
            <li key={text} className="flex items-start gap-2.5 rounded-xl bg-surface px-3 py-2.5 text-[13px] leading-snug">
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> {text}
            </li>
          ))}
        </ul>
      </Block>

      {os !== "phone" && (
        <Block title="Opening it the first time" icon={ShieldCheck} testid="desktop-first-open"
          hint="Krish is new, so it doesn't have a paid publisher certificate yet. Your computer may ask you once to confirm.">
          <p className="rounded-xl bg-surface px-3.5 py-3 text-[13px] leading-relaxed">{FIRST_OPEN[os]}</p>
        </Block>
      )}

      {pwaReady && (
        <Block title="Or install from your browser" icon={Download} testid="desktop-pwa"
          hint="A lighter version, added by your browser in one click. No download needed."
          right={<Button type="button" variant="outline" onClick={install} className="h-9 shrink-0" data-testid="desktop-pwa-install">Install</Button>} />
      )}
    </>
  );
}

const UPDATE_TEXT = {
  idle: null,
  checking: "Checking for updates…",
  none: "You have the newest version.",
  available: "A new version is ready to download.",
  downloading: "Downloading an update…",
  ready: "An update is ready. Restart Krish to finish.",
  error: "Couldn't check for updates. Check your internet connection.",
};

function InsideApp() {
  const bridge = window.krishDesktop;
  const [info, setInfo] = useState(null);
  const [update, setUpdate] = useState({ status: "idle" });

  useEffect(() => {
    bridge.info().then((i) => { if (i) { setInfo(i); setUpdate(i.update || { status: "idle" }); } }).catch(() => {});
    return bridge.onUpdate?.(setUpdate);
  }, [bridge]);

  if (!info) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>;

  const toggleLogin = async (on) => {
    const now = await bridge.setStartAtLogin(on);
    setInfo((i) => ({ ...i, startAtLogin: Boolean(now) }));
  };
  const status = update.status === "downloading" && update.percent ? `Downloading an update… ${update.percent}%` : UPDATE_TEXT[update.status];

  return (
    <>
      <div className="mb-2 flex items-center gap-4 rounded-2xl border border-border bg-card p-5" data-testid="desktop-in-app">
        <img src="/desktop-app-icon.png" alt="" width={56} height={56} className="h-14 w-14 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-heading text-[16px] font-semibold"><Check className="h-4 w-4 text-emerald-500" /> You're using the desktop app</p>
          <p className="mt-0.5 text-[12.5px] text-muted-foreground">Krish AI version {info.version}</p>
        </div>
      </div>
      <Block title="Updates" icon={RefreshCw} testid="desktop-updates" hint={status || "Krish checks for updates by itself every few hours."}
        right={update.status === "ready" || (update.status === "available" && info.platform === "darwin")
          ? <Button type="button" onClick={() => bridge.installUpdate()} className="h-9 shrink-0">{info.platform === "darwin" ? "Download" : "Restart now"}</Button>
          : <Button type="button" variant="outline" disabled={update.status === "checking" || update.status === "downloading"}
              onClick={() => bridge.checkForUpdates()} className="h-9 shrink-0" data-testid="desktop-check-updates">Check now</Button>} />
      <Block title="Keyboard shortcut" icon={Keyboard} testid="desktop-shortcut"
        hint="Opens or hides Krish from any app."
        right={<kbd className="shrink-0 rounded-lg border border-border bg-surface px-2.5 py-1 font-mono text-[12px]">{info.shortcut}</kbd>} />
      {info.platform !== "linux" && (
        <Block title="Start with my computer" icon={Power} testid="desktop-start-at-login"
          hint="Krish opens quietly in the tray when you turn on your computer."
          right={<Switch checked={info.startAtLogin} onCheckedChange={toggleLogin} aria-label="Start with my computer" />} />
      )}
    </>
  );
}
