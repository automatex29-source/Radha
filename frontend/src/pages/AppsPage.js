import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { AppWindow, Plus, Loader2, Globe, Trash2 } from "lucide-react";

const TEMPLATES = [
  { id: "blank", name: "HTML, CSS & JS", hint: "Plain web app — the simplest starting point" },
  { id: "react", name: "React + Tailwind", hint: "React components via CDN, styled with Tailwind" },
];

export default function AppsPage() {
  const navigate = useNavigate();
  const [apps, setApps] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", template: "blank" });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/apps");
      setApps(data);
    } catch (e) {
      toast.error(formatApiError(e));
      setApps([]);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post("/apps", form);
      setOpen(false);
      navigate(`/apps/${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (app) => {
    if (!window.confirm(`Delete “${app.name}” and its history? Its published site goes offline too.`)) return;
    try {
      await api.delete(`/apps/${app.id}`);
      setApps((list) => list.filter((a) => a.id !== app.id));
      toast.success("App deleted");
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-6 py-10">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="radha-heading-gradient text-2xl font-extrabold tracking-tighter sm:text-3xl">Apps</h1>
              <p className="mt-1.5 text-sm text-muted-foreground">
                Describe an app and RADHA builds it — with live preview, tests, version history and one-click publishing.
              </p>
            </div>
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button data-testid="new-app-button" className="gap-1.5"><Plus className="h-4 w-4" /> New app</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>New app</DialogTitle>
                  <DialogDescription>You can change everything later by chatting with the builder.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="app-name">Name</Label>
                    <Input id="app-name" data-testid="app-name-input" value={form.name} placeholder="Habit tracker"
                      onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="bg-card" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="app-desc">What should it do? (optional)</Label>
                    <Textarea id="app-desc" data-testid="app-description-input" value={form.description} rows={3}
                      placeholder="Track daily habits with streaks and a weekly chart"
                      onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} className="bg-card" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Starting point</Label>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {TEMPLATES.map((t) => (
                        <button key={t.id} type="button" onClick={() => setForm((f) => ({ ...f, template: t.id }))}
                          data-testid={`template-${t.id}`}
                          className={`rounded-lg border p-3 text-left transition-colors ${form.template === t.id ? "border-primary bg-primary/10" : "border-border bg-card hover:border-primary/40"}`}>
                          <p className="text-sm font-semibold">{t.name}</p>
                          <p className="mt-0.5 text-xs text-muted-foreground">{t.hint}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button onClick={create} disabled={busy || !form.name.trim()} data-testid="create-app-button">
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create app"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          {apps === null ? (
            <div className="mt-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : apps.length === 0 ? (
            <div className="mt-16 flex flex-col items-center text-center" data-testid="apps-empty">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#1D2230]"><AppWindow className="h-7 w-7 text-primary" /></div>
              <p className="mt-4 font-semibold">No apps yet</p>
              <p className="mt-1 max-w-sm text-sm text-muted-foreground">Create one and ask RADHA for a to-do list, a dashboard, a game or a landing page.</p>
            </div>
          ) : (
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {apps.map((a) => (
                <div key={a.id} className="radha-lift group relative rounded-xl border border-border bg-card p-5 hover:border-primary/50" data-testid={`app-card-${a.id}`}>
                  <button onClick={() => navigate(`/apps/${a.id}`)} className="block w-full text-left">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#1D2230] text-primary"><AppWindow className="h-5 w-5" /></div>
                    <p className="mt-3 font-semibold">{a.name}</p>
                    <p className="mt-1 line-clamp-2 min-h-[2.5rem] text-sm text-muted-foreground">{a.description || "No description"}</p>
                    <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
                      {a.published && <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-400"><Globe className="h-3 w-3" /> Live</span>}
                      <span>Updated {new Date(a.updatedAt).toLocaleString()}</span>
                    </div>
                  </button>
                  <button onClick={() => remove(a)} title="Delete app" data-testid={`delete-app-${a.id}`}
                    className="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
