import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAuth } from "@/context/AuthContext";
import MemoryDialog from "@/components/MemoryDialog";
import { openSettings } from "@/lib/settingsNav";
import InviteDialog from "@/components/InviteDialog";
import { INVITES_ON } from "@/lib/referral";
import { useT } from "@/lib/i18n";
import { useTheme } from "next-themes";
import {
  Plus, Search, Loader2, CalendarDays, Archive, MessageSquare, Trash2, Pencil, LogOut, Check, X, PanelLeftClose, Sun, Moon, Brain, LifeBuoy, Settings, Crown, Users, Gift,
  LayoutDashboard, Sparkles, ArrowUpRight, Monitor, ChevronsUpDown,
} from "lucide-react";
import KrishWordmark from "@/components/KrishWordmark";
import NavList from "@/components/NavList";

function groupByDate(convs) {
  const groups = { Today: [], Yesterday: [], "Previous 7 Days": [], Older: [] };
  const now = new Date();
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = startOfDay(now);
  const day = 86400000;
  convs.forEach((c) => {
    const t = startOfDay(new Date(c.updatedAt));
    if (t === today) groups.Today.push(c);
    else if (t === today - day) groups.Yesterday.push(c);
    else if (t >= today - 7 * day) groups["Previous 7 Days"].push(c);
    else groups.Older.push(c);
  });
  return groups;
}

const GROUP_KEYS = { Today: "today", Yesterday: "yesterday", "Previous 7 Days": "previous7", Older: "older" };
const GROUP_ICONS = { Today: Sun, Yesterday: Moon, "Previous 7 Days": CalendarDays, Older: Archive };
const GroupIcon = ({ label }) => {
  const Icon = GROUP_ICONS[label] || CalendarDays;
  return <Icon className="h-4 w-4 text-indigo-500 dark:text-indigo-300" />;
};

const ITEM = "cursor-pointer gap-3 rounded-lg px-2.5 py-2 text-[13.5px] text-foreground/90 focus:bg-black/[0.045] focus:text-foreground dark:focus:bg-white/[0.07] max-md:py-2.5 max-md:text-[15px]";
const ICON = "h-[17px] w-[17px] text-muted-foreground";
const THEMES = ["light", "dark", "system"];
const PLAN_LABEL = { basic: "Basic", pro: "Pro", max: "Max" };
const PLAN_BADGE = {
  basic: "bg-muted text-muted-foreground ring-1 ring-black/5 dark:ring-white/10",
  pro: "bg-gradient-to-r from-indigo-500 to-sky-400 text-white shadow-sm",
  max: "bg-gradient-to-r from-amber-400 to-orange-500 text-white shadow-sm",
};
const MOD = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "⌘" : "Ctrl";
const MenuDivider = () => <div className="mx-2.5 my-1 h-px bg-gradient-to-r from-transparent via-border to-transparent" role="separator" />;
const Kbd = ({ children }) => (
  <kbd className="ml-0.5 hidden min-w-[1.25rem] rounded-[5px] border border-border bg-muted/60 px-1 py-px text-center font-sans text-[10.5px] font-medium leading-4 text-muted-foreground md:inline-block">{children}</kbd>
);

export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, onRename, onCollapse, newLabel, searchContent = false, busyIds = null }) {
  const { user, logout } = useAuth();
  const t = useT();
  const navigate = useNavigate();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const dark = resolvedTheme !== "light";
  const themeNow = THEMES.includes(theme) ? theme : (dark ? "dark" : "light");
  const plan = PLAN_LABEL[user?.plan] ? user.plan : "basic";
  const nextPlan = plan === "max" ? null : plan === "pro" ? "Max" : "Pro";
  const initial = user?.name?.[0]?.toUpperCase() || "U";

  // Ctrl/⌘ + , opens Settings, as the menu shows.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key === ",") { e.preventDefault(); openSettings(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [deleteId, setDeleteId] = useState(null);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  // Phones keep the search box behind an icon, so the menu opens on the sections and recent chats.
  const [searchOpen, setSearchOpen] = useState(false);

  // Search also looks inside messages (server side), with a short snippet of where the words appear.
  const [hits, setHits] = useState(null); // { [conversationId]: snippet }
  useEffect(() => {
    const q = query.trim();
    if (!searchContent || q.length < 2) { setHits(null); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      api.get("/conversations/search", { params: { q } })
        .then(({ data }) => { if (live) setHits(Object.fromEntries(data.map((h) => [h.id, h.snippet]))); })
        .catch(() => { if (live) setHits(null); });
    }, 300);
    return () => { live = false; clearTimeout(t); };
  }, [query, searchContent]);

  const filtered = conversations.filter((c) => c.title.toLowerCase().includes(query.toLowerCase()) || (hits && c.id in hits));
  const groups = groupByDate(filtered);

  const startRename = (c) => { setEditingId(c.id); setEditValue(c.title); };
  const commitRename = (id) => {
    if (editValue.trim()) onRename(id, editValue.trim());
    setEditingId(null);
  };

  return (
    <div className="krish-glass flex h-full w-[19rem] max-md:w-[86vw] flex-col border-r border-white/60 dark:border-border pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)]">
      {/* Brand */}
      <div className="flex items-center justify-between px-5 pb-4 pt-5">
        <div className="flex items-center">
          <div className="leading-none">
            <p className="text-xl leading-none"><KrishWordmark /></p>
            <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.3em] text-muted-foreground">EmpireX</p>
          </div>
        </div>
        <div className="-mr-2 flex items-center">
          <button onClick={() => setSearchOpen((o) => !o)} data-testid="sidebar-search-toggle" aria-label="Search" aria-expanded={searchOpen}
            className={`flex h-10 w-10 items-center justify-center rounded-lg hover:text-foreground active:bg-surface md:hidden ${searchOpen ? "text-foreground" : "text-muted-foreground"}`}>
            <Search className="h-5 w-5" />
          </button>
          <button onClick={onCollapse} data-testid="sidebar-toggle-button" aria-label="Close" className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground active:bg-surface lg:hidden">
            <PanelLeftClose className="h-5 w-5" />
          </button>
        </div>
      </div>

      <div className="px-4 max-md:hidden">
        <button onClick={onNew} data-testid="new-chat-button"
          className="flex h-11 w-full items-center gap-2 rounded-full bg-gradient-to-r from-indigo-500 via-indigo-500 to-violet-500 px-5 text-sm font-semibold text-white shadow-[0_10px_30px_rgba(99,102,241,0.35)] transition-all hover:shadow-[0_14px_36px_rgba(99,102,241,0.45)] active:scale-[0.99]">
          <Plus className="h-4 w-4" /> {newLabel || t("newConversation")}
        </button>
      </div>

      <div className={`px-4 py-4 max-md:pt-0 ${searchOpen || query ? "" : "max-md:hidden"}`}>
        <div className="relative">
          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input data-testid="conversation-search-input" autoFocus={searchOpen} value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder={t(searchContent ? "searchChats" : "searchConversations")} className="h-10 rounded-full border-white/80 bg-white/80 pl-11 text-sm shadow-sm dark:border-border dark:bg-card" />
        </div>
      </div>

      {/* List */}
      <div className="radha-scroll flex-1 overflow-y-auto px-3 pb-2">
        {/* Phones have no side rail or tab bar: the sections sit at the top of the menu. */}
        {!query.trim() && (
          <div className="md:hidden">
            <NavList onNavigate={onCollapse} />
            <div className="mx-3 my-3 h-px bg-foreground/10" />
            {filtered.length > 0 && <p className="px-3 pb-1 pt-1 text-[13px] font-medium text-muted-foreground">{t("recents")}</p>}
          </div>
        )}
        {filtered.length === 0 && (
          <div className="flex flex-col items-center px-4 py-10 text-center max-md:py-6">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-100 to-violet-100 text-primary dark:from-indigo-500/20 dark:to-violet-500/20">
              {query.trim() ? <Search className="h-5 w-5" /> : <MessageSquare className="h-5 w-5" />}
            </span>
            <p className="mt-3 text-xs text-muted-foreground">{t(query.trim() ? "noMatch" : "noConversations")}</p>
          </div>
        )}
        {Object.entries(groups).map(([label, items]) =>
          items.length ? (
            <div key={label} className="mb-4 max-md:mb-0">
              <p className="flex items-center gap-2 px-3 pb-1.5 pt-1 text-[11px] max-md:hidden font-bold uppercase tracking-[0.14em] text-foreground/70">
                <GroupIcon label={label} /> {t(GROUP_KEYS[label])}
              </p>
              {items.map((c) => (
                <div key={c.id} data-testid={`conversation-item-${c.id}`}
                  onClick={() => editingId !== c.id && onSelect(c.id)}
                  className={`group flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm max-md:gap-4 max-md:text-[15px] lg:py-1.5 lg:text-[13px] transition-colors ${
                    activeId === c.id ? "bg-white text-foreground shadow-sm ring-1 ring-indigo-100 dark:bg-surface-strong dark:ring-0" : "text-foreground/75 hover:bg-white/70 hover:text-foreground dark:text-muted-foreground dark:hover:bg-surface"
                  } cursor-pointer`}>
                  {busyIds?.has(c.id)
                    ? <Loader2 data-testid={`conversation-busy-${c.id}`} aria-label="Writing a reply" className="h-3.5 w-3.5 shrink-0 animate-spin text-primary max-md:h-4 max-md:w-4" />
                    : <MessageSquare className="h-3.5 w-3.5 shrink-0 max-md:h-4 max-md:w-4 max-md:text-foreground/50" />}
                  {editingId === c.id ? (
                    <div className="flex flex-1 items-center gap-1">
                      <input autoFocus value={editValue} onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") commitRename(c.id); if (e.key === "Escape") setEditingId(null); }}
                        onClick={(e) => e.stopPropagation()}
                        className="flex-1 rounded border border-primary/50 bg-background px-1.5 py-0.5 text-xs focus:outline-none" />
                      <button onClick={(e) => { e.stopPropagation(); commitRename(c.id); }}><Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" /></button>
                      <button onClick={(e) => { e.stopPropagation(); setEditingId(null); }}><X className="h-3.5 w-3.5" /></button>
                    </div>
                  ) : (
                    <>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{c.title}</span>
                        {hits?.[c.id] && <span className="line-clamp-2 text-[11px] leading-snug text-muted-foreground" data-testid={`search-snippet-${c.id}`}>{hits[c.id]}</span>}
                      </span>
                      {/* Phones show rename and delete only on the open chat, so the list stays clean. */}
                      <div className={`-my-2 -mr-2 flex shrink-0 items-center opacity-0 transition-opacity group-hover:opacity-100 lg:my-0 lg:mr-0 lg:gap-1 ${activeId === c.id ? "" : "max-md:hidden"}`}>
                        <button data-testid={`rename-conversation-button-${c.id}`} onClick={(e) => { e.stopPropagation(); startRename(c); }} aria-label="Rename"
                          className="flex h-9 w-9 items-center justify-center rounded-lg hover:text-primary lg:h-auto lg:w-auto">
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button data-testid={`delete-conversation-button-${c.id}`} onClick={(e) => { e.stopPropagation(); setDeleteId(c.id); }} aria-label="Delete"
                          className="flex h-9 w-9 items-center justify-center rounded-lg hover:text-destructive lg:h-auto lg:w-auto">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          ) : null
        )}
      </div>

      {/* User */}
      {/* On phones: your picture (opens the account menu) and a New chat button, like the Claude app. */}
      <div className="flex items-center gap-3 p-3 max-md:px-4 max-md:pb-4">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button data-testid="user-profile-menu-button" aria-label={user?.name || "Account"}
              className="flex w-full items-center gap-3 rounded-2xl bg-white/75 px-3 py-2.5 text-left shadow-sm ring-1 ring-white transition-colors hover:bg-white dark:bg-card dark:ring-border max-md:w-auto max-md:rounded-full max-md:bg-transparent max-md:p-0 max-md:shadow-none max-md:ring-0 dark:max-md:bg-transparent">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-sky-400 text-sm font-bold text-white max-md:h-11 max-md:w-11 max-md:text-base">
                {initial}
              </div>
              <div className="min-w-0 flex-1 leading-tight max-md:hidden">
                <p className="truncate text-sm font-semibold">{user?.name}</p>
                <p className="truncate text-[11px] text-muted-foreground">{user?.email}</p>
              </div>
              <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground max-md:hidden" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" sideOffset={8} data-testid="account-menu"
            className="w-[min(18.5rem,calc(100vw-2rem))] rounded-2xl border-black/5 bg-popover p-1.5 shadow-[0_18px_50px_-12px_rgba(15,23,42,0.28)] backdrop-blur-xl dark:border-white/10 dark:shadow-[0_18px_50px_-12px_rgba(0,0,0,0.7)]">
            {/* Header: picture, name, email and plan */}
            <div className="flex items-center gap-3 px-2.5 pb-2.5 pt-2">
              <div className="relative shrink-0">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-sky-400 text-[15px] font-bold text-white shadow-sm ring-2 ring-white dark:ring-white/10">
                  {initial}
                </div>
              </div>
              <div className="min-w-0 flex-1 leading-tight">
                <div className="flex items-center gap-1.5">
                  <p className="truncate text-[14px] font-semibold text-foreground">{user?.name || "Your account"}</p>
                  <span data-testid="account-plan-badge" className={`shrink-0 rounded-full px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide ${PLAN_BADGE[plan]}`}>{PLAN_LABEL[plan]}</span>
                </div>
                <p className="mt-0.5 truncate text-[12px] text-muted-foreground" title={user?.email}>{user?.email}</p>
              </div>
            </div>
            {nextPlan && (
              <DropdownMenuItem data-testid="menu-upgrade" onClick={() => navigate("/plans")}
                className="group mx-0.5 mb-1 cursor-pointer gap-3 rounded-xl border border-indigo-500/15 bg-gradient-to-r from-indigo-500/[0.09] via-sky-400/[0.07] to-transparent px-2.5 py-2 focus:bg-indigo-500/[0.12] dark:border-indigo-400/20 dark:from-indigo-400/[0.14] dark:via-sky-400/[0.08]">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-sky-400 text-white shadow-sm"><Sparkles className="h-3.5 w-3.5" /></span>
                <span className="min-w-0 flex-1 leading-tight">
                  <span className="block text-[13px] font-semibold text-foreground">Upgrade to {nextPlan}</span>
                  <span className="block text-[11px] text-muted-foreground">More of Krish, every day</span>
                </span>
                <ArrowUpRight className="h-4 w-4 text-indigo-500 transition-transform group-focus:-translate-y-px group-focus:translate-x-px dark:text-indigo-300" />
              </DropdownMenuItem>
            )}
            <MenuDivider />
            <DropdownMenuItem data-testid="menu-memory" onClick={() => setMemoryOpen(true)} className={ITEM}>
              <Brain className={ICON} /> {t("memory")}
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="menu-plans" onClick={() => navigate("/plans")} className={ITEM}>
              <Crown className={ICON} /> {t("plans")}
            </DropdownMenuItem>
            {INVITES_ON && (
              <DropdownMenuItem data-testid="menu-invite" onClick={() => setInviteOpen(true)} className={ITEM}>
                <Gift className={ICON} /> Invite friends
              </DropdownMenuItem>
            )}
            <DropdownMenuItem data-testid="menu-settings" onClick={() => openSettings()} className={ITEM}>
              <Settings className={ICON} /> <span className="flex-1">{t("settings")}</span>
              <Kbd>{MOD}</Kbd><Kbd>,</Kbd>
            </DropdownMenuItem>
            {user?.isOwner && (
              <>
                <MenuDivider />
                <p className="px-2.5 pb-1 pt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">Owner</p>
                <DropdownMenuItem data-testid="menu-owner-dashboard" onClick={() => navigate("/admin")} className={ITEM}>
                  <LayoutDashboard className={ICON} /> Dashboard
                </DropdownMenuItem>
                <DropdownMenuItem data-testid="menu-admin-users" onClick={() => navigate("/admin/users")} className={ITEM}>
                  <Users className={ICON} /> Users
                </DropdownMenuItem>
              </>
            )}
            <MenuDivider />
            {/* Theme: pick Light, Dark or System; the row itself cycles them from the keyboard. */}
            <DropdownMenuItem data-testid="menu-theme-toggle" onSelect={(e) => { e.preventDefault(); setTheme(THEMES[(THEMES.indexOf(themeNow) + 1) % THEMES.length]); }}
              className={`${ITEM} pr-1.5`}>
              {dark ? <Moon className={ICON} /> : <Sun className={ICON} />} <span className="flex-1">Theme</span>
              <span role="radiogroup" aria-label="Theme" className="flex items-center rounded-full bg-muted p-0.5 ring-1 ring-black/5 dark:bg-white/5 dark:ring-white/10">
                {[["light", Sun, "Light"], ["dark", Moon, "Dark"], ["system", Monitor, "System"]].map(([v, Icon, label]) => (
                  <button key={v} type="button" role="radio" aria-checked={themeNow === v} aria-label={label} title={label} data-testid={`theme-${v}`}
                    onClick={(e) => { e.stopPropagation(); e.preventDefault(); setTheme(v); }}
                    className={`flex h-6 w-7 items-center justify-center rounded-full transition-all ${themeNow === v
                      ? "bg-background text-foreground shadow-sm ring-1 ring-black/5 dark:bg-white/15 dark:ring-white/10"
                      : "text-muted-foreground hover:text-foreground"}`}>
                    <Icon className="h-3.5 w-3.5" />
                  </button>
                ))}
              </span>
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="menu-help" onClick={() => navigate("/help")} className={ITEM}>
              <LifeBuoy className={ICON} /> {t("helpFeedback")}
            </DropdownMenuItem>
            <MenuDivider />
            <DropdownMenuItem data-testid="user-logout-button" onClick={logout}
              className={`${ITEM} text-red-600 focus:bg-red-500/10 focus:text-red-600 dark:text-red-400 dark:focus:bg-red-500/15 dark:focus:text-red-300`}>
              <LogOut className="h-[17px] w-[17px] opacity-90" /> {t("logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <button onClick={onNew} data-testid="phone-menu-new-chat"
          className="ml-auto flex h-11 items-center gap-2 rounded-full bg-foreground px-5 text-[15px] font-semibold text-background shadow-lg active:scale-[0.98] md:hidden">
          <Plus className="h-4 w-4" /> {newLabel || t("newChat")}
        </button>
      </div>

      <MemoryDialog open={memoryOpen} onOpenChange={setMemoryOpen} />
      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} />

      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("deleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("deleteBody")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete-conversation-button" onClick={() => { onDelete(deleteId); setDeleteId(null); }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90">{t("delete")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
