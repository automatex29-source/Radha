import { useNavigate, useLocation } from "react-router-dom";
import ThemeToggle from "@/components/ThemeToggle";
import { MessageSquare, FolderKanban, AppWindow, Workflow, Presentation, HeartHandshake, LifeBuoy, FileText, Compass } from "lucide-react";
import BrandMark from "@/components/BrandMark";
import { useT } from "@/lib/i18n";

const ITEMS = [
  { icon: MessageSquare, label: "Chat", key: "chat", to: "/", match: (p) => p === "/" },
  // Phones reach Discover from the chat home ("Today's top stories"), so the tab bar stays at 7.
  { icon: Compass, label: "Discover", key: "discover", to: "/discover", match: (p) => p.startsWith("/discover"), desktopOnly: true },
  { icon: HeartHandshake, label: "Counsellor", key: "counsellor", to: "/counsellor", match: (p) => p.startsWith("/counsellor") },
  { icon: FolderKanban, label: "Projects", key: "projects", to: "/projects", match: (p) => p.startsWith("/projects") },
  { icon: AppWindow, label: "Apps", key: "apps", to: "/apps", match: (p) => p.startsWith("/apps") },
  { icon: FileText, label: "Docs", key: "docs", to: "/docs", match: (p) => p.startsWith("/docs") },
  { icon: Presentation, label: "Decks", key: "decks", to: "/decks", match: (p) => p.startsWith("/decks") },
  { icon: Workflow, label: "Automations", key: "automations", short: "automate", to: "/automations", match: (p) => p.startsWith("/automations") },
];

/** Side rail on tablets and desktops; a bottom tab bar on phones (unless mobileBar is false).
 *  The page container is a row that turns into a column on phones, so the bar sits last. */
export default function IconRail({ mobileBar = true }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const t = useT();

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
                  active ? "bg-white text-primary shadow-[0_6px_20px_rgba(99,102,241,0.22)] ring-1 ring-indigo-100 dark:bg-surface-strong dark:ring-0"
                    : "text-muted-foreground hover:bg-white/70 hover:text-foreground dark:hover:bg-surface"
                }`}>
                <it.icon className="h-5 w-5" />
              </button>
            );
          })}
        </nav>
        <button onClick={() => navigate("/help")} data-testid="nav-help" title={t("helpCenter")} aria-label={t("helpCenter")}
          className={`mt-auto mb-2.5 flex h-11 w-11 items-center justify-center rounded-2xl transition-all ${
            pathname.startsWith("/help") ? "bg-white text-primary shadow-[0_6px_20px_rgba(99,102,241,0.22)] ring-1 ring-indigo-100 dark:bg-surface-strong dark:ring-0"
              : "text-muted-foreground hover:bg-white/70 hover:text-foreground dark:hover:bg-surface"
          }`}>
          <LifeBuoy className="h-5 w-5" />
        </button>
        <ThemeToggle />
      </div>

      {mobileBar && (
        <nav data-testid="mobile-tab-bar"
          className="krish-tabbar order-last flex shrink-0 border-t border-white/70 bg-white/80 dark:border-border dark:bg-background/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden">
          {ITEMS.filter((it) => !it.desktopOnly).map((it) => {
            const active = it.match(pathname);
            return (
              <button key={it.to} onClick={() => navigate(it.to)} data-testid={`tab-${it.label.toLowerCase()}`}
                aria-current={active ? "page" : undefined}
                className={`flex min-w-0 flex-1 flex-col items-center gap-1 pb-1.5 pt-2 text-[10px] font-semibold transition-colors ${
                  active ? "text-primary" : "text-muted-foreground active:text-foreground"
                }`}>
                <span className={`flex h-7 w-12 items-center justify-center rounded-full transition-colors ${active ? "bg-surface-strong" : ""}`}>
                  <it.icon className="h-5 w-5" />
                </span>
                <span className="max-w-full truncate px-0.5">{t(it.short || it.key)}</span>
              </button>
            );
          })}
        </nav>
      )}
    </>
  );
}
