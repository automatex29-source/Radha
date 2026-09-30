import { useNavigate, useLocation } from "react-router-dom";
import ThemeToggle from "@/components/ThemeToggle";
import { MessageSquare, FolderKanban, Sparkles, AppWindow, Workflow, Presentation, HeartHandshake } from "lucide-react";

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
      <div className="hidden h-full w-[60px] shrink-0 flex-col items-center border-r border-border bg-background py-4 md:flex">
        <div className="mb-6 flex h-9 w-9 items-center justify-center rounded-lg bg-primary shadow-[0_0_20px_rgba(99,102,241,0.4)]">
          <Sparkles className="h-5 w-5 text-white" />
        </div>
        <nav className="flex flex-col gap-2">
          {ITEMS.map((it) => {
            const active = it.match(pathname);
            return (
              <button key={it.to} onClick={() => navigate(it.to)} data-testid={`nav-${it.label.toLowerCase()}`}
                title={it.label}
                className={`flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
                  active ? "bg-surface-strong text-primary" : "text-muted-foreground hover:bg-surface hover:text-foreground"
                }`}>
                <it.icon className="h-5 w-5" />
              </button>
            );
          })}
        </nav>
        <ThemeToggle className="mt-auto" />
      </div>

      {mobileBar && (
        <nav data-testid="mobile-tab-bar"
          className="krish-tabbar order-last flex shrink-0 border-t border-border bg-background/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden">
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
