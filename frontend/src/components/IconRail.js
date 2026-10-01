import { useNavigate, useLocation } from "react-router-dom";
import ThemeToggle from "@/components/ThemeToggle";
import { MessageSquare, FolderKanban, AppWindow, Workflow, Presentation, HeartHandshake, LifeBuoy } from "lucide-react";
import BrandMark from "@/components/BrandMark";

const ITEMS = [
  { icon: MessageSquare, label: "Chat", to: "/", match: (p) => p === "/" },
  { icon: HeartHandshake, label: "Counsellor", to: "/counsellor", match: (p) => p.startsWith("/counsellor") },
  { icon: FolderKanban, label: "Projects", to: "/projects", match: (p) => p.startsWith("/projects") },
  { icon: AppWindow, label: "Apps", to: "/apps", match: (p) => p.startsWith("/apps") },
  { icon: Presentation, label: "Decks", to: "/decks", match: (p) => p.startsWith("/decks") },
  { icon: Workflow, label: "Automations", short: "Automate", to: "/automations", match: (p) => p.startsWith("/automations") },
];

/** Side rail on tablets and desktops; a bottom tab bar on phones (unless mobileBar is false).
 *  The page container is a row that turns into a column on phones, so the bar sits last. */
export default function IconRail({ mobileBar = true }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <>
      <div className="hidden h-full w-[68px] shrink-0 flex-col items-center border-r border-white/60 bg-white/35 py-5 backdrop-blur-xl dark:border-border dark:bg-background/40 md:flex">
        <BrandMark className="mb-6 h-9 w-9" />
        <nav className="flex flex-col gap-2.5">
          {ITEMS.map((it) => {
            const active = it.match(pathname);
            return (
              <button key={it.to} onClick={() => navigate(it.to)} data-testid={`nav-${it.label.toLowerCase()}`}
                title={it.label}
                className={`flex h-11 w-11 items-center justify-center rounded-2xl transition-all ${
                  active ? "bg-white text-primary shadow-[0_6px_20px_rgba(99,102,241,0.22)] ring-1 ring-indigo-100 dark:bg-surface-strong dark:ring-0"
                    : "text-muted-foreground hover:bg-white/70 hover:text-foreground dark:hover:bg-surface"
                }`}>
                <it.icon className="h-5 w-5" />
              </button>
            );
          })}
        </nav>
        <button onClick={() => navigate("/help")} data-testid="nav-help" title="Help Center" aria-label="Help Center"
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
          {ITEMS.map((it) => {
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
                <span className="max-w-full truncate px-0.5">{it.short || it.label}</span>
              </button>
            );
          })}
        </nav>
      )}
    </>
  );
}
