import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAuth } from "@/context/AuthContext";
import {
  Plus, Search, Sparkles, MessageSquare, Trash2, Pencil, LogOut, Check, X, PanelLeftClose,
} from "lucide-react";

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

export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, onRename, onCollapse }) {
  const { user, logout } = useAuth();
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [deleteId, setDeleteId] = useState(null);

  const filtered = conversations.filter((c) => c.title.toLowerCase().includes(query.toLowerCase()));
  const groups = groupByDate(filtered);

  const startRename = (c) => { setEditingId(c.id); setEditValue(c.title); };
  const commitRename = (id) => {
    if (editValue.trim()) onRename(id, editValue.trim());
    setEditingId(null);
  };

  return (
    <div className="flex h-full w-72 flex-col border-r border-border bg-[#0B0D12]">
      {/* Brand */}
      <div className="flex items-center justify-between px-4 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary shadow-[0_0_20px_rgba(99,102,241,0.4)]">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <div className="leading-none">
            <p className="text-sm font-extrabold tracking-tight">RADHA</p>
            <p className="text-[9px] font-bold uppercase tracking-[0.2em] text-muted-foreground">A.utomateX</p>
          </div>
        </div>
        <button onClick={onCollapse} data-testid="sidebar-toggle-button" className="text-muted-foreground hover:text-foreground lg:hidden">
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>

      <div className="px-3">
        <Button onClick={onNew} data-testid="new-chat-button" className="w-full justify-start gap-2 font-semibold">
          <Plus className="h-4 w-4" /> New conversation
        </Button>
      </div>

      <div className="px-3 py-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input data-testid="conversation-search-input" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations" className="h-9 bg-card pl-9 text-sm" />
        </div>
      </div>

      {/* List */}
      <div className="radha-scroll flex-1 overflow-y-auto px-3 pb-2">
        {filtered.length === 0 && (
          <p className="px-2 py-8 text-center text-xs text-muted-foreground">No conversations yet.</p>
        )}
        {Object.entries(groups).map(([label, items]) =>
          items.length ? (
            <div key={label} className="mb-3">
              <p className="px-2 py-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">{label}</p>
              {items.map((c) => (
                <div key={c.id} data-testid={`conversation-item-${c.id}`}
                  onClick={() => editingId !== c.id && onSelect(c.id)}
                  className={`group flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                    activeId === c.id ? "bg-[#1D2230] text-foreground" : "text-muted-foreground hover:bg-[#171B26] hover:text-foreground"
                  } cursor-pointer`}>
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                  {editingId === c.id ? (
                    <div className="flex flex-1 items-center gap-1">
                      <input autoFocus value={editValue} onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") commitRename(c.id); if (e.key === "Escape") setEditingId(null); }}
                        onClick={(e) => e.stopPropagation()}
                        className="flex-1 rounded border border-primary/50 bg-background px-1.5 py-0.5 text-xs focus:outline-none" />
                      <button onClick={(e) => { e.stopPropagation(); commitRename(c.id); }}><Check className="h-3.5 w-3.5 text-emerald-400" /></button>
                      <button onClick={(e) => { e.stopPropagation(); setEditingId(null); }}><X className="h-3.5 w-3.5" /></button>
                    </div>
                  ) : (
                    <>
                      <span className="flex-1 truncate">{c.title}</span>
                      <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
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
      <div className="border-t border-border p-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button data-testid="user-profile-menu-button" className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-[#171B26]">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-cyan-500 text-sm font-bold text-white">
                {user?.name?.[0]?.toUpperCase() || "U"}
              </div>
              <div className="min-w-0 flex-1 leading-tight">
                <p className="truncate text-sm font-semibold">{user?.name}</p>
                <p className="truncate text-[11px] text-muted-foreground">{user?.email}</p>
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <div className="px-2 py-1.5 text-xs text-muted-foreground">Signed in as <span className="font-medium text-foreground">{user?.email}</span></div>
            <DropdownMenuSeparator />
            <DropdownMenuItem data-testid="user-logout-button" onClick={logout} className="text-destructive focus:text-destructive">
              <LogOut className="mr-2 h-4 w-4" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

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
