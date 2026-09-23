import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, absoluteUrl, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { MediaGallery } from "@/components/ToolSteps";
import PreviewPanel from "@/components/PreviewPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Workflow, Plus, Loader2, Play, Webhook, Clock, Copy, Trash2, CheckCircle2, XCircle, MessageSquare, Pencil } from "lucide-react";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const EXAMPLES = [
  { name: "Morning AI news brief", prompt: "Search the web for the most important AI news from the last 24 hours. Write a short brief with 5 bullet points and source links, then create a PDF report of it.", schedule: { type: "daily", time: "08:00" } },
  { name: "Weekly sales workbook", prompt: "Create an Excel workbook with a weekly sales summary template: columns for day, orders, revenue and average order value, with totals and a bar chart.", schedule: { type: "weekly", time: "09:00", weekday: 0 } },
  { name: "Handle incoming webhook", prompt: "A webhook sent you an event. Summarise what happened in two sentences and list any follow-up actions.", schedule: { type: "manual" } },
];
const localTz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; } };
const blank = () => ({ name: "", prompt: "", schedule: { type: "daily", time: "08:00", weekday: 0, minutes: 60, timezone: localTz() }, model: "" });

export default function AutomationsPage() {
  const [items, setItems] = useState(null);
  const [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(null); // form object or null
  const [models, setModels] = useState([]);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/automations");
      setItems(data);
      setSelected((s) => (s && data.some((a) => a.id === s) ? s : data[0]?.id || null));
    } catch (e) {
      toast.error(formatApiError(e));
      setItems([]);
    }
  }, []);

  useEffect(() => {
    load();
    Promise.all([api.get("/models"), api.get("/capabilities")]).then(([m, c]) =>
      setModels(m.data.models.map((x) => ({ ...x, ok: !!c.data.agent?.[x.id] })))).catch(() => {});
  }, [load]);

  const toggle = async (a, enabled) => {
    try {
      await api.patch(`/automations/${a.id}`, { enabled });
      load();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const current = items?.find((a) => a.id === selected);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <IconRail />
      <div className="flex min-w-0 flex-1">
        <div className="radha-scroll w-full max-w-md shrink-0 overflow-y-auto border-r border-border p-5">
          <div className="flex items-center justify-between">
            <h1 className="radha-heading-gradient text-2xl font-extrabold tracking-tighter">Automations</h1>
            <Button size="sm" onClick={() => setEditing(blank())} data-testid="new-automation" className="gap-1.5"><Plus className="h-4 w-4" /> New</Button>
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground">RADHA runs these agent tasks on a schedule or when a webhook fires — with search, code, files and every other tool.</p>

          {items === null ? <div className="mt-10 flex justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div> : items.length === 0 ? (
            <div className="mt-6 space-y-2" data-testid="automation-examples">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">Start from an example</p>
              {EXAMPLES.map((ex) => (
                <button key={ex.name} onClick={() => setEditing({ ...blank(), ...ex, schedule: { ...blank().schedule, ...ex.schedule } })}
                  className="block w-full rounded-lg border border-border bg-card p-3 text-left hover:border-primary/50">
                  <p className="text-sm font-medium">{ex.name}</p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{ex.prompt}</p>
                </button>
              ))}
            </div>
          ) : (
            <div className="mt-5 space-y-2">
              {items.map((a) => (
                <div key={a.id} onClick={() => setSelected(a.id)} data-testid={`automation-${a.id}`}
                  className={`cursor-pointer rounded-xl border p-3.5 transition-colors ${a.id === selected ? "border-primary/60 bg-primary/5" : "border-border bg-card hover:border-primary/40"}`}>
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">{a.name}</p>
                      <p className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground"><Clock className="h-3 w-3" /> {a.scheduleText}</p>
                    </div>
                    <Switch checked={a.enabled} onCheckedChange={(v) => toggle(a, v)} onClick={(e) => e.stopPropagation()} data-testid={`toggle-${a.id}`} />
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
                    {a.lastStatus && <StatusBadge status={a.lastStatus} />}
                    {a.nextRunAt && <span>Next: {new Date(a.nextRunAt).toLocaleString()}</span>}
                    {a.webhookUrl && <span className="flex items-center gap-1"><Webhook className="h-3 w-3" /> webhook</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          {current ? <AutomationDetail key={current.id} automation={current} onChanged={load}
            onEdit={() => setEditing({ ...current, schedule: { ...blank().schedule, ...current.schedule }, model: current.model || "" })} /> : (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
              <Workflow className="h-10 w-10 text-primary" />
              <p className="mt-3 text-sm">Create an automation to see its runs here.</p>
            </div>
          )}
        </div>
      </div>
      {editing && <AutomationDialog form={editing} models={models} onClose={() => setEditing(null)}
        onSaved={(a) => { setEditing(null); setSelected(a.id); load(); }} />}
    </div>
  );
}

function StatusBadge({ status }) {
  if (status === "running") return <span className="flex items-center gap-1 text-amber-400"><Loader2 className="h-3 w-3 animate-spin" /> Running</span>;
  if (status === "succeeded") return <span className="flex items-center gap-1 text-emerald-400"><CheckCircle2 className="h-3 w-3" /> Succeeded</span>;
  return <span className="flex items-center gap-1 text-rose-400"><XCircle className="h-3 w-3" /> Failed</span>;
}

function AutomationDialog({ form: initial, models, onClose, onSaved }) {
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const setSchedule = (patch) => setForm((f) => ({ ...f, schedule: { ...f.schedule, ...patch } }));
  const s = form.schedule;

  const save = async () => {
    setBusy(true);
    const schedule = { type: s.type, timezone: s.timezone };
    if (s.type === "interval") schedule.minutes = Number(s.minutes);
    if (s.type === "daily" || s.type === "weekly") schedule.time = s.time;
    if (s.type === "weekly") schedule.weekday = Number(s.weekday);
    const body = { name: form.name, prompt: form.prompt, schedule, model: form.model || null };
    try {
      const { data } = form.id ? await api.patch(`/automations/${form.id}`, body) : await api.post("/automations", body);
      toast.success(form.id ? "Automation updated" : "Automation created");
      onSaved(data);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const field = "h-9 w-full rounded-md border border-border bg-card px-2 text-sm";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{form.id ? "Edit automation" : "New automation"}</DialogTitle>
          <DialogDescription>Write the task as you would ask RADHA in chat. It runs in agent mode with all tools.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input value={form.name} onChange={(e) => set({ name: e.target.value })} data-testid="automation-name" className="bg-card" placeholder="Morning news brief" />
          </div>
          <div className="space-y-1.5">
            <Label>Task</Label>
            <Textarea rows={5} value={form.prompt} onChange={(e) => set({ prompt: e.target.value })} data-testid="automation-prompt" className="bg-card"
              placeholder="Search the web for… then create a PDF report…" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>When</Label>
              <select value={s.type} onChange={(e) => setSchedule({ type: e.target.value })} className={field} data-testid="schedule-type">
                <option value="daily">Every day</option>
                <option value="weekly">Every week</option>
                <option value="interval">Every few minutes/hours</option>
                <option value="manual">Only manually / by webhook</option>
              </select>
            </div>
            {s.type === "interval" && (
              <div className="space-y-1.5">
                <Label>Every</Label>
                <select value={s.minutes} onChange={(e) => setSchedule({ minutes: e.target.value })} className={field}>
                  {[15, 30, 60, 120, 180, 360, 720].map((m) => <option key={m} value={m}>{m < 60 ? `${m} minutes` : `${m / 60} hour${m === 60 ? "" : "s"}`}</option>)}
                </select>
              </div>
            )}
            {s.type === "weekly" && (
              <div className="space-y-1.5">
                <Label>Day</Label>
                <select value={s.weekday} onChange={(e) => setSchedule({ weekday: e.target.value })} className={field}>
                  {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </select>
              </div>
            )}
            {(s.type === "daily" || s.type === "weekly") && (
              <div className="space-y-1.5">
                <Label>Time ({s.timezone})</Label>
                <Input type="time" value={s.time} onChange={(e) => setSchedule({ time: e.target.value })} data-testid="schedule-time" className="bg-card" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Model</Label>
              <select value={form.model || ""} onChange={(e) => set({ model: e.target.value })} className={field}>
                <option value="">Default</option>
                {models.map((m) => <option key={m.id} value={m.id} disabled={!m.ok}>{m.label}{m.ok ? "" : " (needs key)"}</option>)}
              </select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="border-border">Cancel</Button>
          <Button onClick={save} disabled={busy || !form.name.trim() || !form.prompt.trim()} data-testid="save-automation">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : form.id ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AutomationDetail({ automation: a, onChanged, onEdit }) {
  const navigate = useNavigate();
  const [runs, setRuns] = useState(null);
  const [preview, setPreview] = useState(null);

  const loadRuns = useCallback(async () => {
    const { data } = await api.get(`/automations/${a.id}/runs`);
    setRuns(data);
    return data;
  }, [a.id]);

  useEffect(() => { loadRuns().catch(() => setRuns([])); }, [loadRuns]);

  // Poll quickly while a run is in progress, and slowly otherwise so scheduled
  // and webhook-triggered runs show up without a reload.
  const running = !!runs?.some((r) => r.status === "running");
  useEffect(() => {
    const t = setInterval(async () => {
      if (document.hidden) return;
      const data = await loadRuns().catch(() => null);
      if (running && data && !data.some((r) => r.status === "running")) onChanged();
    }, running ? 2500 : 8000);
    return () => clearInterval(t);
  }, [running, loadRuns, onChanged]);

  const runNow = async () => {
    try {
      await api.post(`/automations/${a.id}/run`);
      toast.success("Run started");
      loadRuns();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const webhook = async (create) => {
    try {
      if (create) await api.post(`/automations/${a.id}/webhook`);
      else await api.delete(`/automations/${a.id}/webhook`);
      onChanged();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete “${a.name}” and its run history?`)) return;
    await api.delete(`/automations/${a.id}`);
    toast.success("Automation deleted");
    onChanged();
  };

  const hookUrl = a.webhookUrl ? absoluteUrl(a.webhookUrl) : null;
  return (
    <div className="flex h-full">
      <div className="radha-scroll min-w-0 flex-1 overflow-y-auto p-6" data-testid="automation-detail">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-bold tracking-tight">{a.name}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{a.scheduleText}{a.enabled ? "" : " · paused"}</p>
          </div>
          <Button size="sm" variant="outline" onClick={onEdit} className="gap-1.5 border-border bg-card"><Pencil className="h-3.5 w-3.5" /> Edit</Button>
          <Button size="sm" onClick={runNow} data-testid="run-now" className="gap-1.5"><Play className="h-3.5 w-3.5" /> Run now</Button>
          <button onClick={remove} title="Delete" className="rounded-md p-2 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
        </div>
        <p className="mt-4 whitespace-pre-wrap rounded-xl border border-border bg-card p-4 text-sm">{a.prompt}</p>

        <div className="mt-4 rounded-xl border border-border bg-card p-4">
          <p className="flex items-center gap-1.5 text-sm font-semibold"><Webhook className="h-4 w-4 text-primary" /> Webhook trigger</p>
          {hookUrl ? (
            <>
              <p className="mt-1 text-xs text-muted-foreground">POST any JSON to this secret URL to start a run; the payload is passed to the task.</p>
              <div className="mt-2 flex items-center gap-2 rounded-lg border border-border bg-background px-2 py-1.5">
                <code className="truncate text-[11px] text-[#A5B4FC]" data-testid="webhook-url">{hookUrl}</code>
                <button onClick={() => { navigator.clipboard.writeText(hookUrl); toast.success("Webhook URL copied"); }} className="ml-auto text-muted-foreground hover:text-foreground"><Copy className="h-3.5 w-3.5" /></button>
              </div>
              <div className="mt-2 flex gap-3 text-xs">
                <button onClick={() => webhook(true)} className="text-[#A5B4FC] hover:underline">Rotate URL</button>
                <button onClick={() => webhook(false)} className="text-muted-foreground hover:text-destructive">Remove</button>
              </div>
            </>
          ) : (
            <button onClick={() => webhook(true)} data-testid="create-webhook" className="mt-2 text-xs text-[#A5B4FC] hover:underline">Create a webhook URL</button>
          )}
        </div>

        <h3 className="mt-6 text-xs font-bold uppercase tracking-[0.15em] text-muted-foreground">Runs</h3>
        {runs === null ? <Loader2 className="mt-4 h-5 w-5 animate-spin text-primary" /> : runs.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No runs yet. Use Run now to try it.</p>
        ) : (
          <div className="mt-2 space-y-3" data-testid="run-list">
            {runs.map((r) => (
              <div key={r.id} className="rounded-xl border border-border bg-card p-4" data-testid={`run-${r.id}`}>
                <div className="flex items-center gap-2 text-xs">
                  <StatusBadge status={r.status} />
                  <span className="text-muted-foreground">· {r.trigger} · {new Date(r.startedAt).toLocaleString()}</span>
                  <button onClick={() => navigate(`/?conversation=${r.conversationId}`)} className="ml-auto flex items-center gap-1 text-[#A5B4FC] hover:underline">
                    <MessageSquare className="h-3 w-3" /> Open conversation
                  </button>
                </div>
                {r.error && <p className="mt-2 text-xs text-rose-400">{r.error}</p>}
                {r.output && <p className="mt-2 line-clamp-6 whitespace-pre-wrap text-sm text-foreground">{r.output}</p>}
                <MediaGallery items={r.media} onOpen={setPreview} />
              </div>
            ))}
          </div>
        )}
      </div>
      {preview && <PreviewPanel item={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
