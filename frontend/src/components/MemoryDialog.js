import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Brain, Loader2, Plus, Trash2 } from "lucide-react";

/** What RADHA remembers about the user across chats: view, add, delete, turn learning on or off. */
export default function MemoryDialog({ open, onOpenChange }) {
  const [items, setItems] = useState(null);
  const [auto, setAuto] = useState(true);
  const [text, setText] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);

  useEffect(() => {
    if (!open) return;
    setConfirmClear(false);
    Promise.all([api.get("/memory"), api.get("/memory/settings")])
      .then(([m, s]) => { setItems(m.data); setAuto(s.data.auto); })
      .catch((e) => { toast.error(formatApiError(e)); setItems([]); });
  }, [open]);

  const add = async () => {
    const content = text.trim();
    if (!content) return;
    try {
      const { data } = await api.post("/memory", { content });
      setItems((list) => [data, ...(list || [])]);
      setText("");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/memory/${id}`);
      setItems((list) => list.filter((m) => m.id !== id));
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const clearAll = async () => {
    try {
      await api.delete("/memory");
      setItems([]);
      setConfirmClear(false);
      toast.success("RADHA forgot everything");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const toggleAuto = async (value) => {
    setAuto(value);
    try { await api.put("/memory/settings", { auto: value }); }
    catch (e) { setAuto(!value); toast.error(formatApiError(e)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="memory-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Brain className="h-4 w-4 text-primary" /> Memory</DialogTitle>
          <DialogDescription>What RADHA remembers about you in every chat. Delete anything you don't want kept.</DialogDescription>
        </DialogHeader>

        <label className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface px-3 py-2.5">
          <span className="text-sm">
            <span className="font-medium">Learn from my chats</span>
            <span className="block text-xs text-muted-foreground">Saves things like your name, business and how you like answers.</span>
          </span>
          <Switch checked={auto} onCheckedChange={toggleAuto} data-testid="memory-auto-switch" />
        </label>

        <div className="flex gap-2">
          <Input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="e.g. I run a bakery in Pune" className="bg-card" data-testid="global-memory-input" />
          <Button onClick={add} variant="outline" className="gap-1.5 border-border bg-card" data-testid="global-memory-add">
            <Plus className="h-4 w-4" /> Add
          </Button>
        </div>

        <div className="radha-scroll max-h-72 space-y-2 overflow-y-auto">
          {items === null && <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>}
          {items?.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">Nothing yet. Tell RADHA about yourself in a chat, or add a fact above.</p>
          )}
          {items?.map((m) => (
            <div key={m.id} data-testid={`global-memory-item-${m.id}`} className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5">
              <p className="flex-1 text-sm">{m.content}</p>
              {m.source === "auto" && <span className="rounded-full bg-surface-strong px-2 py-0.5 text-[10px] text-muted-foreground">learned</span>}
              <button onClick={() => remove(m.id)} title="Forget this" data-testid={`global-memory-delete-${m.id}`}
                className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>

        {items?.length > 0 && (
          <div className="flex justify-end">
            {confirmClear ? (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Forget everything?</span>
                <Button size="sm" variant="ghost" onClick={() => setConfirmClear(false)}>Cancel</Button>
                <Button size="sm" variant="destructive" onClick={clearAll} data-testid="memory-clear-confirm">Forget all</Button>
              </div>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setConfirmClear(true)} className="text-muted-foreground hover:text-destructive">
                Forget everything
              </Button>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
