import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAuth } from "@/context/AuthContext";
import MemoryDialog from "@/components/MemoryDialog";
import { useTheme } from "next-themes";
import {
  Plus, Search, ChevronRight, CalendarDays, Archive, MessageSquare, Trash2, Pencil, LogOut, Check, X, PanelLeftClose, Sun, Moon, Brain, LifeBuoy,
} from "lucide-react";
import KrishWordmark from "@/components/KrishWordmark";

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

const GROUP_ICONS = { Today: Sun, Yesterday: Moon, "Previous 7 Days": CalendarDays, Older: Archive };
const GroupIcon = ({ label }) => {
  const Icon = GROUP_ICONS[label] || CalendarDays;
  return <Icon className="h-4 w-4 text-indigo-500 dark:text-indigo-300" />;
};

export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, onRename, onCollapse, newLabel = "New conversation", searchContent = false }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { resolvedTheme, setTheme } = useTheme();
  const dark = resolvedTheme !== "light";
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [deleteId, setDeleteId] = useState(null);
  const [memoryOpen, setMemoryOpen] = useState(false);

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
    <div className="krish-glass flex h-full w-[19rem] flex-col border-r border-white/60 dark:border-border pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)]">
      {/* Brand */}
      <div className="flex items-center justify-between px-5 pb-4 pt-5">
        <div className="flex items-center">
          <div className="leading-none">
            <p className="text-xl leading-none"><KrishWordmark /></p>
            <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.3em] text-muted-foreground">EmpireX</p>
          </div>
        </div>
        <button onClick={onCollapse} data-testid="sidebar-toggle-button" aria-label="Close" className="-mr-2 flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground active:bg-surface lg:hidden">
          <PanelLeftClose className="h-5 w-5" />
        </button>
      </div>

      <div className="px-4">
        <button onClick={onNew} data-testid="new-chat-button"
          className="flex h-11 w-full items-center gap-2 rounded-full bg-gradient-to-r from-indigo-500 via-indigo-500 to-violet-500 px-5 text-sm font-semibold text-white shadow-[0_10px_30px_rgba(99,102,241,0.35)] transition-all hover:shadow-[0_14px_36px_rgba(99,102,241,0.45)] active:scale-[0.99]">
          <Plus className="h-4 w-4" /> {newLabel}
        </button>
      </div>

      <div className="px-4 py-4">
        <div className="relative">
          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input data-testid="conversation-search-input" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder={searchContent ? "Search chats and messages" : "Search conversations"} className="h-10 rounded-full border-white/80 bg-white/80 pl-11 text-sm shadow-sm dark:border-border dark:bg-card" />
        </div>
      </div>

      {/* List */}
      <div className="radha-scroll flex-1 overflow-y-auto px-3 pb-2">
        {filtered.length === 0 && (
          <p className="px-2 py-8 text-center text-xs text-muted-foreground">{query.trim() ? "No chats match your search." : "No conversations yet."}</p>
        )}
        {Object.entries(groups).map(([label, items]) =>
          items.length ? (
            <div key={label} className="mb-4">
              <p className="flex items-center gap-2 px-3 pb-1.5 pt-1 text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/70">
                <GroupIcon label={label} /> {label}
              </p>
              {items.map((c) => (
                <div key={c.id} data-testid={`conversation-item-${c.id}`}
                  onClick={() => editingId !== c.id && onSelect(c.id)}
                  className={`group flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm lg:py-1.5 lg:text-[13px] transition-colors ${
                    activeId === c.id ? "bg-white text-foreground shadow-sm ring-1 ring-indigo-100 dark:bg-surface-strong dark:ring-0" : "text-foreground/75 hover:bg-white/70 hover:text-foreground dark:text-muted-foreground dark:hover:bg-surface"
                  } cursor-pointer`}>
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
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
                      <div className="flex shrink-0 items-center gap-3 opacity-0 transition-opacity group-hover:opacity-100 lg:gap-1">
                        <button data-testid={`rename-conversation-button-${c.id}`} onClick={(e) => { e.stopPropagation(); startRename(c); }} className="hover:text-primary">
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button data-testid={`delete-conversation-button-${c.id}`} onClick={(e) => { e.stopPropagation(); setDeleteId(c.id); }} className="hover:text-destructive">
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
      <div className="p-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button data-testid="user-profile-menu-button" className="flex w-full items-center gap-3 rounded-2xl bg-white/75 px-3 py-2.5 text-left shadow-sm ring-1 ring-white transition-colors hover:bg-white dark:bg-card dark:ring-border">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-sky-400 text-sm font-bold text-white">
                {user?.name?.[0]?.toUpperCase() || "U"}
              </div>
              <div className="min-w-0 flex-1 leading-tight">
                <p className="truncate text-sm font-semibold">{user?.name}</p>
                <p className="truncate text-[11px] text-muted-foreground">{user?.email}</p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <div className="px-2 py-1.5 text-xs text-muted-foreground">Signed in as <span className="font-medium text-foreground">{user?.email}</span></div>
            <DropdownMenuSeparator />
            <DropdownMenuItem data-testid="menu-memory" onClick={() => setMemoryOpen(true)}>
              <Brain className="mr-2 h-4 w-4" /> Memory
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="menu-help" onClick={() => navigate("/help")}>
              <LifeBuoy className="mr-2 h-4 w-4" /> Help & feedback
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="menu-theme-toggle" onClick={() => setTheme(dark ? "light" : "dark")}>
              {dark ? <Sun className="mr-2 h-4 w-4" /> : <Moon className="mr-2 h-4 w-4" />} {dark ? "Light theme" : "Dark theme"}
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="user-logout-button" onClick={logout} className="text-destructive focus:text-destructive">
              <LogOut className="mr-2 h-4 w-4" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <MemoryDialog open={memoryOpen} onOpenChange={setMemoryOpen} />

      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>This permanently removes the conversation and all of its messages. This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete-conversation-button" onClick={() => { onDelete(deleteId); setDeleteId(null); }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
