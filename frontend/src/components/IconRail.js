import { useNavigate, useLocation } from "react-router-dom";
import { MessageSquare, FolderKanban, Sparkles } from "lucide-react";

const ITEMS = [
  { icon: MessageSquare, label: "Chat", to: "/", match: (p) => p === "/" },
  { icon: FolderKanban, label: "Projects", to: "/projects", match: (p) => p.startsWith("/projects") },
];

export default function IconRail() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <div className="flex h-full w-[60px] shrink-0 flex-col items-center border-r border-border bg-[#07080B] py-4">
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
                active ? "bg-[#1D2230] text-primary" : "text-muted-foreground hover:bg-[#171B26] hover:text-foreground"
              }`}>
              <it.icon className="h-5 w-5" />
            </button>
          );
        })}
      </nav>
    </div>
  );
}
