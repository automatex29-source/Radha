import { useNavigate, useLocation } from "react-router-dom";
import ThemeToggle from "@/components/ThemeToggle";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { LifeBuoy, LayoutDashboard, PanelLeft, SquarePen } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import KrishWordmark from "@/components/KrishWordmark";
import { NAV_ITEMS as ITEMS } from "@/components/NavList";
import { useAuth } from "@/context/AuthContext";
import BrandMark from "@/components/BrandMark";
import { useT } from "@/lib/i18n";
import { accentStyle } from "@/components/PageHero";


/** Side rail on tablets and desktops. On phones (unless mobileBar is false) a slim top bar whose
 *  menu button opens the sidebar: the sections, then recent chats, like the chat page's drawer.
 *  The page container is a row that turns into a column on phones, so the bar sits on top. */
export default function IconRail({ mobileBar = true }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const t = useT();
  const { user } = useAuth();

  return (
    <>
      <div className="hidden h-full w-[68px] shrink-0 flex-col items-center border-r border-white/60 bg-white/35 py-5 backdrop-blur-xl dark:border-border dark:bg-background/40 md:flex">
        <BrandMark className="mb-6 h-9 w-9" />
        <nav className="flex flex-col gap-2.5">
          {ITEMS.map((it) => {
            const active = it.match(pathname);
            return (
              <button key={it.to} onClick={() => navigate(it.to)} data-testid={`nav-${it.label.toLowerCase()}`}
                title={t(it.key)} style={accentStyle(it.key)}
                className={`flex h-11 w-11 items-center justify-center rounded-2xl transition-all ${
                  active ? "kb-tab-on text-white"
                    : "text-muted-foreground hover:-translate-y-0.5 hover:bg-white/80 hover:text-primary hover:shadow-sm dark:hover:bg-surface"
                }`}>
                <it.icon className="h-5 w-5" />
              </button>
            );
          })}
        </nav>
        {user?.isOwner && (
          <button onClick={() => navigate("/admin")} data-testid="nav-owner-dashboard" title="Owner dashboard" aria-label="Owner dashboard"
            className={`mt-auto mb-2.5 flex h-11 w-11 items-center justify-center rounded-2xl transition-all ${
              pathname.startsWith("/admin") ? "bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_8px_22px_rgba(99,102,241,0.45)]"
                : "text-muted-foreground hover:-translate-y-0.5 hover:bg-white/80 hover:text-primary hover:shadow-sm dark:hover:bg-surface"
            }`}>
            <LayoutDashboard className="h-5 w-5" />
          </button>
        )}
        <button onClick={() => navigate("/help")} data-testid="nav-help" title={t("helpCenter")} aria-label={t("helpCenter")}
          className={`${user?.isOwner ? "" : "mt-auto "}mb-2.5 flex h-11 w-11 items-center justify-center rounded-2xl transition-all ${
            pathname.startsWith("/help") ? "bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_8px_22px_rgba(99,102,241,0.45)]"
              : "text-muted-foreground hover:-translate-y-0.5 hover:bg-white/80 hover:text-primary hover:shadow-sm dark:hover:bg-surface"
          }`}>
          <LifeBuoy className="h-5 w-5" />
        </button>
        <ThemeToggle />
      </div>

      {mobileBar && <PhoneMenu />}
    </>
  );
}

/** The phone top bar and its sidebar drawer, for pages outside the chat. */
function PhoneMenu() {
  const navigate = useNavigate();
  const t = useT();
  const [open, setOpen] = useState(false);
  const [conversations, setConversations] = useState([]);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    api.get("/conversations").then(({ data }) => { if (live) setConversations(data); }).catch(() => {});
    return () => { live = false; };
  }, [open]);

  const remove = async (id) => {
    try {
      await api.delete(`/conversations/${id}`);
      setConversations((c) => c.filter((x) => x.id !== id));
    } catch (e) { toast.error(formatApiError(e)); }
  };
  const rename = async (id, title) => {
    try {
      const { data } = await api.patch(`/conversations/${id}`, { title });
      setConversations((c) => c.map((x) => (x.id === id ? { ...x, title: data.title } : x)));
    } catch (e) { toast.error(formatApiError(e)); }
  };

  return (
    <>
      <header data-testid="phone-top-bar" className="flex shrink-0 items-center justify-between px-2 pb-1 pt-[max(0.5rem,env(safe-area-inset-top))] md:hidden">
        <button onClick={() => setOpen(true)} data-testid="open-menu-button" aria-label="Menu"
          className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground active:bg-surface">
          <PanelLeft className="h-5 w-5" />
        </button>
        <span className="text-lg leading-none"><KrishWordmark /></span>
        <button onClick={() => navigate("/")} data-testid="phone-new-chat-button" aria-label={t("newChat")}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground active:bg-surface">
          <SquarePen className="h-5 w-5" />
        </button>
      </header>

      {open && (
        <div className="fixed inset-0 z-50 md:hidden" data-testid="mobile-drawer">
          <div className="krish-fade-in absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]" onClick={() => setOpen(false)} />
          <div className="krish-drawer-in krish-canvas absolute left-0 top-0 h-full max-w-[86vw] shadow-2xl">
            <Sidebar conversations={conversations} activeId={null}
              onSelect={(id) => { setOpen(false); navigate(`/?conversation=${id}`); }}
              onNew={() => { setOpen(false); navigate("/"); }}
              onDelete={remove} onRename={rename} onCollapse={() => setOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
