import { useNavigate, useLocation } from "react-router-dom";
import { MessageSquare, FolderKanban, AppWindow, Workflow, Presentation, HeartHandshake, FileText, Compass } from "lucide-react";
import { useT } from "@/lib/i18n";
import { accentStyle } from "@/components/PageHero";

/** The app's sections. The desktop rail shows them as icons; the phone menu lists them with their names. */
export const NAV_ITEMS = [
  { icon: MessageSquare, label: "Chat", key: "chat", to: "/", match: (p) => p === "/" },
  { icon: HeartHandshake, label: "Counsellor", key: "counsellor", to: "/counsellor", match: (p) => p.startsWith("/counsellor") },
  { icon: FolderKanban, label: "Projects", key: "projects", to: "/projects", match: (p) => p.startsWith("/projects") },
  { icon: AppWindow, label: "Apps", key: "apps", to: "/apps", match: (p) => p.startsWith("/apps") },
  { icon: FileText, label: "Docs", key: "docs", to: "/docs", match: (p) => p.startsWith("/docs") },
  { icon: Presentation, label: "Decks", key: "decks", to: "/decks", match: (p) => p.startsWith("/decks") },
  { icon: Workflow, label: "Automations", key: "automations", to: "/automations", match: (p) => p.startsWith("/automations") },
  { icon: Compass, label: "Discover", key: "discover", to: "/discover", match: (p) => p.startsWith("/discover") },
];

/** A plain list of the sections (icon and name), the way the phone menu shows them. */
export default function NavList({ onNavigate, className = "" }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const t = useT();

  return (
    <nav data-testid="phone-nav" className={`flex flex-col gap-0.5 ${className}`}>
      {NAV_ITEMS.map((it) => {
        const active = it.match(pathname);
        return (
          <button key={it.to} data-testid={`menu-nav-${it.label.toLowerCase()}`} aria-current={active ? "page" : undefined}
            style={accentStyle(it.key)}
            onClick={() => { onNavigate?.(); if (!active) navigate(it.to); }}
            className={`flex h-12 items-center gap-4 rounded-xl px-3 text-left text-[15px] transition-colors ${
              active ? "bg-white font-semibold text-foreground shadow-sm ring-1 ring-black/5 dark:bg-surface-strong dark:ring-0"
                : "text-foreground/80 active:bg-white/70 dark:active:bg-surface"
            }`}>
            <it.icon className={`h-5 w-5 shrink-0 ${active ? "text-[var(--ka1)]" : "text-foreground/60"}`} strokeWidth={1.75} />
            {t(it.key)}
          </button>
        );
      })}
    </nav>
  );
}
