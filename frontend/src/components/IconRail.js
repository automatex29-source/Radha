import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import ThemeToggle from "@/components/ThemeToggle";
import { MessageSquare, FolderKanban, AppWindow, Workflow, Presentation, HeartHandshake, LifeBuoy, FileText, Compass, LayoutGrid, Crown } from "lucide-react";
import BrandMark from "@/components/BrandMark";
import BottomSheet from "@/components/BottomSheet";
import { useT } from "@/lib/i18n";

const ITEMS = [
  { icon: MessageSquare, label: "Chat", key: "chat", to: "/", match: (p) => p === "/" },
  { icon: HeartHandshake, label: "Counsellor", key: "counsellor", to: "/counsellor", match: (p) => p.startsWith("/counsellor") },
  { icon: FolderKanban, label: "Projects", key: "projects", to: "/projects", match: (p) => p.startsWith("/projects") },
  { icon: AppWindow, label: "Apps", key: "apps", to: "/apps", match: (p) => p.startsWith("/apps") },
  { icon: FileText, label: "Docs", key: "docs", to: "/docs", match: (p) => p.startsWith("/docs") },
  { icon: Presentation, label: "Decks", key: "decks", to: "/decks", match: (p) => p.startsWith("/decks") },
  { icon: Workflow, label: "Automations", key: "automations", short: "automate", to: "/automations", match: (p) => p.startsWith("/automations") },
  { icon: Compass, label: "Discover", key: "discover", to: "/discover", match: (p) => p.startsWith("/discover") },
];

// Phones show the first three as tabs; everything else sits in the More sheet, so each tab has room.
const PHONE_TABS = 3;
const MORE_ITEMS = [
  ...ITEMS.slice(PHONE_TABS),
  { icon: Crown, label: "Plans", key: "plans", to: "/plans", match: (p) => p.startsWith("/plans") },
  { icon: LifeBuoy, label: "Help", key: "helpCenter", to: "/help", match: (p) => p.startsWith("/help") },
];

/** Side rail on tablets and desktops; a bottom tab bar on phones (unless mobileBar is false).
 *  The page container is a row that turns into a column on phones, so the bar sits last. */
export default function IconRail({ mobileBar = true }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const t = useT();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreActive = MORE_ITEMS.some((it) => it.match(pathname));

  return (
    <>
      <div className="hidden h-full w-[68px] shrink-0 flex-col items-center border-r border-white/60 bg-white/35 py-5 backdrop-blur-xl dark:border-border dark:bg-background/40 md:flex">
        <BrandMark className="mb-6 h-9 w-9" />
        <nav className="flex flex-col gap-2.5">
          {ITEMS.map((it) => {
            const active = it.match(pathname);
            return (
              <button key={it.to} onClick={() => navigate(it.to)} data-testid={`nav-${it.label.toLowerCase()}`}
                title={t(it.key)}
                className={`flex h-11 w-11 items-center justify-center rounded-2xl transition-all ${
                  active ? "bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_8px_22px_rgba(99,102,241,0.45)]"
                    : "text-muted-foreground hover:-translate-y-0.5 hover:bg-white/80 hover:text-primary hover:shadow-sm dark:hover:bg-surface"
                }`}>
                <it.icon className="h-5 w-5" />
              </button>
            );
          })}
        </nav>
        <button onClick={() => navigate("/help")} data-testid="nav-help" title={t("helpCenter")} aria-label={t("helpCenter")}
          className={`mt-auto mb-2.5 flex h-11 w-11 items-center justify-center rounded-2xl transition-all ${
            pathname.startsWith("/help") ? "bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_8px_22px_rgba(99,102,241,0.45)]"
              : "text-muted-foreground hover:-translate-y-0.5 hover:bg-white/80 hover:text-primary hover:shadow-sm dark:hover:bg-surface"
          }`}>
          <LifeBuoy className="h-5 w-5" />
        </button>
        <ThemeToggle />
      </div>

      {mobileBar && (
        <nav data-testid="mobile-tab-bar"
          className="krish-tabbar order-last flex shrink-0 border-t border-border/70 bg-background/85 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden">
          {ITEMS.slice(0, PHONE_TABS).map((it) => (
            <Tab key={it.to} icon={it.icon} label={t(it.key)} active={it.match(pathname)} onClick={() => navigate(it.to)}
              testId={`tab-${it.label.toLowerCase()}`} />
          ))}
          <Tab icon={LayoutGrid} label={t("more")} active={moreActive} onClick={() => setMoreOpen(true)} testId="tab-more" />
        </nav>
      )}
      {mobileBar && (
        <BottomSheet open={moreOpen} onOpenChange={setMoreOpen} title="More from Krish" testId="more-sheet">
          <div className="grid grid-cols-3 gap-2.5">
            {MORE_ITEMS.map((it) => {
              const active = it.match(pathname);
              return (
                <button key={it.to} onClick={() => { setMoreOpen(false); navigate(it.to); }} data-testid={`more-${it.label.toLowerCase()}`}
                  aria-current={active ? "page" : undefined}
                  className={`flex h-[88px] flex-col items-center justify-center gap-2 rounded-2xl text-[13px] font-medium transition-colors active:scale-[0.98] ${
                    active ? "bg-primary/12 text-brand ring-1 ring-primary/40" : "bg-surface text-foreground"}`}>
                  <it.icon className="h-6 w-6 text-brand" />
                  <span className="max-w-full truncate px-1">{t(it.short || it.key)}</span>
                </button>
              );
            })}
          </div>
        </BottomSheet>
      )}
    </>
  );
}

function Tab({ icon: Icon, label, active, onClick, testId }) {
  return (
    <button onClick={onClick} data-testid={testId} aria-current={active ? "page" : undefined}
      className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 pb-1.5 pt-2 text-[11px] font-medium transition-colors ${
        active ? "text-brand" : "text-muted-foreground active:text-foreground"}`}>
      <span className={`flex h-8 w-14 items-center justify-center rounded-full transition-colors ${active ? "bg-primary/12" : ""}`}>
        <Icon className="h-[22px] w-[22px]" strokeWidth={active ? 2.2 : 1.8} />
      </span>
      <span className={`max-w-full truncate tracking-tight ${active ? "font-semibold" : ""}`}>{label}</span>
    </button>
  );
}
