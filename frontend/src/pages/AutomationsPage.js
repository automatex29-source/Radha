import { useCallback, useEffect, useState } from "react";
import PageHero from "@/components/PageHero";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, absoluteUrl, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { MediaGallery } from "@/components/ToolSteps";
import PreviewPanel from "@/components/PreviewPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { AppLogo } from "@/components/BrandLogos";
import { openSettings } from "@/lib/settingsNav";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  Workflow, Plus, Loader2, Play, Webhook, Clock, Copy, Trash2, CheckCircle2, XCircle, MessageSquare, Pencil, ArrowLeft,
  Sparkles, Brain, Gauge, Mail, Send, ChevronDown, ChevronUp, Check, Square, PauseCircle, Lock, Hand, Inbox, ShieldCheck,
  CalendarClock, Repeat, MousePointerClick, Timer, Zap, ListChecks,
  Plug,
} from "lucide-react";
import ScrollTable from "@/components/ScrollTable";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
// Ready-made jobs. `events` ones start on new email (Pro and Max); `apps` are the connections they work best with.
const EXAMPLES = [
  { name: "My daily briefing", emoji: "☀️", prompt: "1. Use what you remember about me (my work, city and interests).\n2. Search the web for today's top news that matters to me, plus the weather in my city.\n3. Add one useful tip or idea for my work today.\n4. Write a short morning briefing: 5 bullet points with source links, weather in one line, then the tip.", schedule: { type: "daily", time: "07:30" }, emailResult: true },
  { name: "Daily progress report", emoji: "📈", apps: ["google_sheets"], prompt: "1. Read my Google Sheet (paste its link here) and find today's rows.\n2. Add up today's numbers and compare them with yesterday and with last week.\n3. Write my daily progress in 5 short lines: what went up, what went down, and one thing to do tomorrow.", schedule: { type: "daily", time: "19:00" } },
  { name: "Log new orders to a sheet", emoji: "🧾", events: true, apps: ["gmail", "google_sheets"], prompt: "1. Read each new order email.\n2. Note the customer, item, amount and order number.\n3. Add one row per order to my Google Sheet (paste its link here).\n4. Reply with a one-line summary of what you added.", schedule: { type: "email", query: "subject:order" } },
  { name: "Reply to new leads", emoji: "✉️", events: true, apps: ["gmail"], prompt: "1. Read each new enquiry email.\n2. Write a friendly, short reply that thanks them, answers their question and offers a call.\n3. Send it from my Gmail (I approve each one first).\n4. List who you replied to.", schedule: { type: "email", query: "subject:(enquiry OR quote OR pricing)" } },
  { name: "Meeting prep", emoji: "🗓️", apps: ["google_calendar"], prompt: "1. Check my calendar for today's meetings.\n2. For each one, search the web for the company or person.\n3. Write 3 bullet points per meeting: who they are, what they may want, one good question to ask.", schedule: { type: "daily", time: "08:00" } },
  { name: "Competitor price watch", emoji: "🏷️", prompt: "1. Search the web for the current prices and offers of the top 5 AI chat apps in India.\n2. Open their pricing pages to confirm.\n3. Compare with last time and point out any change.\n4. Create an Excel sheet with app, plan, price in INR and notes, plus a bar chart.", schedule: { type: "weekly", time: "09:00", weekday: 0 } },
  { name: "Weekly social media pack", emoji: "📣", prompt: "1. Search for this week's trending topics about AI and small businesses.\n2. Write 5 ready-to-post LinkedIn and Instagram captions with hashtags.\n3. Generate one eye-catching image for the best post.\n4. Put the captions in a Word document.", schedule: { type: "weekly", time: "10:00", weekday: 0 } },
  { name: "Lead research", emoji: "🔎", prompt: "1. Find 10 small companies in Mumbai that could use AI automation (web search).\n2. For each: name, website, what they do, and why they might need AI.\n3. Don't repeat companies from last time.\n4. Create an Excel sheet with the list.", schedule: { type: "weekly", time: "09:30", weekday: 2 } },
];
const APP_NAMES = { gmail: "Gmail", google_sheets: "Google Sheets", google_calendar: "Google Calendar", google_drive: "Google Drive" };
const localTz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; } };
const tomorrow = () => { const d = new Date(Date.now() + 86400000); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
// Short, human times: "in 8 min", "Today, 7:00 PM", "Tomorrow, 7:30 AM", "Mon 16 Nov, 9:00 AM", "12 min ago".
function when(iso, now = Date.now()) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = t - now, mins = Math.round(Math.abs(diff) / 60000);
  if (mins < 1) return diff >= 0 ? "in under a minute" : "just now";
  if (mins < 60) return diff >= 0 ? `in ${mins} min` : `${mins} min ago`;
  const d = new Date(t), clock = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const day = (x) => new Date(x).toDateString();
  if (day(t) === day(now)) return `Today, ${clock}`;
  if (day(t) === day(now + 86400000)) return `Tomorrow, ${clock}`;
  if (day(t) === day(now - 86400000)) return `Yesterday, ${clock}`;
  return `${d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}, ${clock}`;
}
const took = (r) => {
  if (!r.finishedAt || !r.startedAt) return "";
  const s = Math.max(0, Math.round((new Date(r.finishedAt) - new Date(r.startedAt)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
};
const TRIGGERS = { schedule: "On schedule", manual: "Run now", webhook: "Webhook", email: "New email" };
// The icon and colour for how a job starts.
const KINDS = {
  email: { icon: Inbox, tint: "bg-sky-500/10 text-sky-600 dark:text-sky-400" },
  daily: { icon: Clock, tint: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  weekly: { icon: CalendarClock, tint: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
  interval: { icon: Repeat, tint: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  once: { icon: Timer, tint: "bg-rose-500/10 text-rose-600 dark:text-rose-400" },
  manual: { icon: MousePointerClick, tint: "bg-slate-500/10 text-slate-600 dark:text-slate-300" },
};
const kindOf = (a) => KINDS[a?.schedule?.type] || KINDS.manual;
// Quick ideas that fill the Tell Krish box.
const ASK_IDEAS = [
  "Every night at 9, total today's orders from my Gmail and send me the numbers on Telegram",
  "When a new enquiry email arrives, write a reply and ask me before sending it",
  "Every Monday at 9, compare competitor prices and make an Excel sheet",
];
const blank = () => ({
  name: "", prompt: "", schedule: { type: "daily", time: "08:00", weekday: 0, minutes: 60, date: tomorrow(), timezone: localTz() }, model: "",
  memory: true, thorough: false, emailResult: false, notifyUrl: "", sendTo: [], askFirst: true,
});

export default function AutomationsPage() {
  const [items, setItems] = useState(null);
  const [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(null); // form object or null
  const [models, setModels] = useState([]);
  const [options, setOptions] = useState({ email: false, planner: false, rules: null });
  const [phoneDetail, setPhoneDetail] = useState(false); // phones show the list or one automation, not both

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
    api.get("/automations/options").then(({ data }) => setOptions(data)).catch(() => {});
  }, [load]);

  const toggle = async (a, enabled) => {
    try {
      await api.patch(`/automations/${a.id}`, { enabled });
      load();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };
  const fresh = () => {
    const f = blank();
    // Basic runs daily or weekly; a plan's shortest repeat is the default interval.
    if (options.rules?.minInterval) f.schedule.minutes = Math.max(60, options.rules.minInterval);
    return f;
  };

  const current = items?.find((a) => a.id === selected);
  const [approvals, setApprovals] = useState([]);
  const loadApprovals = useCallback(() => api.get("/automations/approvals").then(({ data }) => setApprovals(Array.isArray(data) ? data : [])).catch(() => {}), []);
  useEffect(() => {
    loadApprovals();
    const t = setInterval(() => { if (!document.hidden) loadApprovals(); }, 15000);
    return () => clearInterval(t);
  }, [loadApprovals]);
  const pickExample = (ex) => {
    const f = fresh();
    setEditing({ ...f, ...ex, schedule: { ...f.schedule, ...ex.schedule } });
  };
  const [ask, setAsk] = useState("");
  const [asking, setAsking] = useState(false);
  const tellKrish = async () => {
    setAsking(true);
    try {
      const { data } = await api.post("/automations/plan", { goal: ask, timezone: localTz() });
      const f = fresh();
      setEditing({ ...f, name: data.name, prompt: data.prompt, schedule: { ...f.schedule, ...data.schedule },
        emailResult: !!data.emailResult && options.email, sendTo: data.sendTo || [], fromAsk: true });
      setAsk("");
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <div className="flex min-h-0 min-w-0 flex-1">
        <div className={`radha-scroll w-full max-w-md shrink-0 overflow-y-auto border-r border-border p-5 max-md:max-w-none max-md:border-r-0 max-md:p-4 ${phoneDetail ? "max-md:hidden" : ""}`}>
          <PageHero compact scene="automations" icon={Workflow} title="Automations"
            subtitle="Jobs Krish does for you on time, or when an email comes in.">
            <Button size="sm" onClick={() => setEditing(fresh())} data-testid="new-automation" className="gap-1.5 bg-white font-semibold text-slate-900 shadow-lg hover:bg-white/90"><Plus className="h-4 w-4" /> New</Button>
          </PageHero>

          {options.planner && (
            <div className="mt-5 rounded-xl border border-primary/30 bg-primary/5 p-3" data-testid="tell-krish">
              <Label className="flex items-center gap-1.5 text-sm"><Sparkles className="h-3.5 w-3.5 text-primary" /> Tell Krish what to do</Label>
              <Textarea rows={3} value={ask} onChange={(e) => setAsk(e.target.value)} className="mt-1.5 bg-card" data-testid="tell-krish-input"
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && ask.trim().length >= 3 && !asking) { e.preventDefault(); tellKrish(); } }}
                placeholder="Every evening at 7, check my Gmail for new orders, add them to my sheet and send me the day's progress on Telegram" />
              <div className="mt-2 flex items-center gap-2">
                <Button size="sm" onClick={tellKrish} disabled={asking || ask.trim().length < 3} className="gap-1.5" data-testid="tell-krish-go">
                  {asking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Set it up
                </Button>
                <p className="text-[11px] text-muted-foreground">You check the steps before it's saved.</p>
              </div>
              {!ask && items?.length === 0 && (
                <div className="mt-2.5 flex flex-col gap-1.5" data-testid="ask-ideas">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">Try one</p>
                  {ASK_IDEAS.map((idea) => (
                    <button key={idea} type="button" onClick={() => setAsk(idea)}
                      className="flex items-start gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground">
                      <Zap className="mt-px h-3 w-3 shrink-0 text-primary" /> {idea}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {approvals.length > 0 && <Approvals items={approvals} hideOnWide={current?.id} onDone={() => { loadApprovals(); load(); }} />}

          {items === null ? <div className="mt-10 flex justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div> : items.length === 0 ? (
            <div className="mt-6 space-y-2" data-testid="automation-examples">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">Or start from a ready-made job</p>
              {EXAMPLES.map((ex) => <ExampleCard key={ex.name} ex={ex} rules={options.rules} onPick={() => pickExample(ex)} />)}
            </div>
          ) : (
            <div className="mt-5 space-y-2">
              <Summary items={items} approvals={approvals} options={options} />
              <IdeasRow rules={options.rules} onPick={pickExample} />
              {items.map((a) => (
                <div key={a.id} onClick={() => { setSelected(a.id); setPhoneDetail(true); }} data-testid={`automation-${a.id}`}
                  className={`cursor-pointer rounded-xl border p-3.5 transition-colors ${a.id === selected ? "border-primary/60 bg-primary/5" : "border-border bg-card hover:border-primary/40"}`}>
                  <div className="flex items-start gap-3">
                    <KindIcon a={a} />
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-sm font-semibold max-md:break-words md:truncate">{a.name}</p>
                      <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">{a.scheduleText}</p>
                    </div>
                    <Switch checked={a.enabled} onCheckedChange={(v) => toggle(a, v)} onClick={(e) => e.stopPropagation()} data-testid={`toggle-${a.id}`} />
                  </div>
                  {a.triggerError && a.enabled && (
                    <p className="mt-2 flex items-start gap-1 pl-12 text-[11px] text-rose-600 dark:text-rose-400"><XCircle className="mt-px h-3 w-3 shrink-0" /> {a.triggerError}</p>
                  )}
                  {a.pausedReason && (
                    <p className="mt-2 flex items-start gap-1 pl-12 text-[11px] text-amber-700 dark:text-amber-400" data-testid={`paused-${a.id}`}>
                      <PauseCircle className="mt-px h-3 w-3 shrink-0" /> {a.pausedReason}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 pl-12 text-[11px] text-muted-foreground">
                    {a.lastStatus ? <StatusBadge status={a.lastStatus} /> : <span>Not run yet</span>}
                    {a.nextRunAt && <span className="flex items-center gap-1" title={new Date(a.nextRunAt).toLocaleString()}><Clock className="h-3 w-3" /> {a.schedule?.type === "email" ? "Checks inbox" : "Next"} {when(a.nextRunAt)}</span>}
                    {approvals.some((p) => p.automationId === a.id) && <span className="flex items-center gap-1 font-medium text-amber-700 dark:text-amber-400"><Hand className="h-3 w-3" /> Needs your OK</span>}
                    {a.webhookUrl && <span className="flex items-center gap-1"><Webhook className="h-3 w-3" /> webhook</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className={`min-w-0 flex-1 ${phoneDetail ? "" : "max-md:hidden"}`}>
          {current ? <AutomationDetail key={current.id} automation={current} onChanged={load} onBack={() => setPhoneDetail(false)}
            approvals={approvals.filter((p) => p.automationId === current.id)} onApprovalsDone={() => { loadApprovals(); load(); }}
            onEdit={() => setEditing({ ...current, schedule: { ...blank().schedule, ...current.schedule }, model: current.model || "", notifyUrl: current.notifyUrl || "", sendTo: current.sendTo || [], askFirst: current.askFirst !== false })} /> : (
            <HowItWorks />
          )}
        </div>
      </div>
      {editing && <AutomationDialog form={editing} models={models} options={options} onClose={() => setEditing(null)}
        onSaved={(a) => { setEditing(null); setSelected(a.id); setPhoneDetail(true); load(); }} />}
    </div>
  );
}

function KindIcon({ a, size = "h-9 w-9" }) {
  const { icon: Icon, tint } = kindOf(a);
  return <span className={`flex ${size} shrink-0 items-center justify-center rounded-xl ${tint} ${a.enabled === false ? "opacity-50" : ""}`}><Icon className="h-4 w-4" /></span>;
}

function Summary({ items, approvals, options }) {
  const on = items.filter((a) => a.enabled).length;
  const failing = items.filter((a) => a.enabled && a.lastStatus === "failed").length;
  const next = items.filter((a) => a.enabled && a.nextRunAt && a.schedule?.type !== "email")
    .sort((x, y) => new Date(x.nextRunAt) - new Date(y.nextRunAt))[0];
  const tiles = [
    { label: options.limit ? `of ${options.limit} jobs on ${options.planName || "your plan"}` : "jobs", value: options.limit ? items.length : on, tone: "" },
    { label: "need your OK", value: approvals.length, tone: approvals.length ? "text-amber-600 dark:text-amber-400" : "" },
    { label: failing === 1 ? "job failing" : "jobs failing", value: failing, tone: failing ? "text-rose-600 dark:text-rose-400" : "" },
  ];
  return (
    <div className="mb-3" data-testid="automation-summary">
      <div className="grid grid-cols-3 gap-2">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl border border-border bg-card px-3 py-2">
            <p className={`text-lg font-bold tabular-nums leading-tight ${t.tone}`}>{t.value}</p>
            <p className="text-[10px] leading-tight text-muted-foreground">{t.label}</p>
          </div>
        ))}
      </div>
      {next && <p className="mt-2 flex items-center gap-1 px-1 text-[11px] text-muted-foreground"><Clock className="h-3 w-3" /> Up next: <span className="font-medium text-foreground">{next.name}</span> {when(next.nextRunAt)}</p>}
    </div>
  );
}

function HowItWorks() {
  const steps = [
    { icon: Sparkles, title: "Say what you want", text: "Type it in plain words, or pick a ready-made job. Krish writes the steps and picks the time." },
    { icon: CalendarClock, title: "Krish does it for you", text: "On time (daily, weekly, every hour) or when a new email comes in. It searches, reads your apps and makes files." },
    { icon: ShieldCheck, title: "You get the result", text: "By email, Telegram or WhatsApp. Emails it writes wait for your OK before they are sent." },
  ];
  return (
    <div className="flex h-full items-center justify-center p-8 max-md:hidden" data-testid="how-it-works">
      <div className="w-full max-w-md">
        <Workflow className="h-9 w-9 text-primary" />
        <h2 className="mt-3 text-xl font-bold tracking-tight">How automations work</h2>
        <ol className="mt-5 space-y-4">
          {steps.map((s, i) => (
            <li key={s.title} className="flex gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-bold text-primary">{i + 1}</span>
              <div>
                <p className="flex items-center gap-1.5 text-sm font-semibold"><s.icon className="h-3.5 w-3.5 text-primary" /> {s.title}</p>
                <p className="mt-0.5 text-[13px] text-muted-foreground">{s.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function needsPro(ex, rules) {
  return !!(ex.events && rules && !rules.events);
}

function ExampleCard({ ex, rules, onPick }) {
  const locked = needsPro(ex, rules);
  return (
    <button onClick={onPick} data-testid={`example-${ex.name}`}
      className="flex w-full items-start gap-3 rounded-xl border border-border bg-card p-3 text-left transition-colors hover:border-primary/50">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-lg">{ex.emoji}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-sm font-medium">{ex.name}
          {ex.events && <span className="rounded-full bg-primary/10 px-1.5 py-px text-[10px] font-semibold text-primary">{locked ? "Pro" : "On new email"}</span>}
        </span>
        <span className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{ex.prompt.replace(/\n/g, " ")}</span>
        {ex.apps && <span className="mt-1 block text-[11px] text-muted-foreground">Uses {ex.apps.map((a) => APP_NAMES[a]).join(" + ")}</span>}
      </span>
    </button>
  );
}

function IdeasRow({ rules, onPick }) {
  return (
    <div className="-mx-1 mb-2" data-testid="ideas-row">
      <p className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">Ready-made jobs</p>
      <div className="radha-scroll flex gap-2 overflow-x-auto px-1 pb-1">
        {EXAMPLES.map((ex) => (
          <button key={ex.name} onClick={() => onPick(ex)} title={ex.prompt}
            className="flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-card py-1.5 pl-2 pr-3 text-xs hover:border-primary/50">
            <span>{ex.emoji}</span> {ex.name}
            {needsPro(ex, rules) && <Lock className="h-3 w-3 text-muted-foreground" />}
          </button>
        ))}
      </div>
    </div>
  );
}

function Approvals({ items, onDone, hideOnWide, inDetail = false }) {
  const [busy, setBusy] = useState(null);
  const [open, setOpen] = useState(null);
  const decide = async (ap, approve) => {
    setBusy(ap.id);
    try {
      await api.post(`/automations/approvals/${ap.id}`, { approve });
      toast.success(approve ? (ap.kind === "gmail_send" ? "Email sent" : "Done") : (ap.kind === "gmail_send" ? "Declined. Nothing was sent." : "Declined. Nothing was done."));
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy(null);
      onDone();
    }
  };
  return (
    <div className={`rounded-xl border border-amber-500/40 bg-amber-500/5 p-3 ${inDetail ? "mt-4" : "mt-5"} ${hideOnWide && items.every((ap) => ap.automationId === hideOnWide) ? "md:hidden" : ""}`}
      data-testid={inDetail ? "detail-approvals" : "approvals"}>
      <p className="flex items-center gap-1.5 text-sm font-semibold"><Hand className="h-4 w-4 text-amber-600 dark:text-amber-400" /> {inDetail ? "This job is waiting for your OK" : "Waiting for your OK"} ({items.length})</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">Krish asks before it sends anything or changes things in your apps. Read it, then say yes or no.</p>
      <div className="mt-2 space-y-2">
        {items.map((ap) => (
          <div key={ap.id} className={`rounded-lg border border-border bg-card p-3 ${hideOnWide === ap.automationId ? "md:hidden" : ""}`} data-testid={`approval-${ap.id}`}>
            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">{ap.kind === "gmail_send" ? <Mail className="h-3 w-3" /> : <Plug className="h-3 w-3" />} {ap.automationName} · {when(ap.createdAt)}</p>
            {ap.detail?.to ? (
              <>
                <p className="mt-1 text-sm"><span className="text-muted-foreground">To</span> <span className="font-medium">{ap.detail.to}</span></p>
                <p className="text-sm font-medium">{ap.detail.subject || "(no subject)"}</p>
                <p className={`mt-1 whitespace-pre-wrap text-xs text-muted-foreground ${open === ap.id ? "" : "line-clamp-3"}`}>{ap.detail.body}</p>
                {(ap.detail.body || "").length > 160 && (
                  <button onClick={() => setOpen(open === ap.id ? null : ap.id)} className="mt-0.5 text-[11px] text-brand hover:underline">{open === ap.id ? "Show less" : "Read all"}</button>
                )}
              </>
            ) : ap.detail?.app ? (
              <>
                <p className="mt-1 text-sm"><span className="font-medium">{ap.detail.app}</span> <span className="text-muted-foreground">·</span> {ap.detail.action}</p>
                <pre className={`mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-sunken p-2 font-mono text-[11px] text-muted-foreground ${open === ap.id ? "" : "line-clamp-4"}`}>{ap.detail.body}</pre>
                {(ap.detail.body || "").length > 160 && (
                  <button onClick={() => setOpen(open === ap.id ? null : ap.id)} className="mt-0.5 text-[11px] text-brand hover:underline">{open === ap.id ? "Show less" : "Read all"}</button>
                )}
              </>
            ) : <p className="mt-1 text-sm">{ap.summary}</p>}
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => decide(ap, true)} disabled={!!busy} className="h-8 gap-1.5" data-testid={`approve-${ap.id}`}>
                {busy === ap.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} {ap.kind === "gmail_send" ? "Send it" : "Do it"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => decide(ap, false)} disabled={!!busy} className="h-8 border-border">{ap.kind === "gmail_send" ? "Don't send" : "Don't do it"}</Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  if (status === "running") return <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400"><Loader2 className="h-3 w-3 animate-spin" /> Running</span>;
  if (status === "succeeded") return <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400"><CheckCircle2 className="h-3 w-3" /> Succeeded</span>;
  if (status === "stopped") return <span className="flex items-center gap-1 text-muted-foreground"><Square className="h-3 w-3" /> Stopped</span>;
  if (status === "skipped") return <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400"><PauseCircle className="h-3 w-3" /> Skipped</span>;
  return <span className="flex items-center gap-1 text-rose-600 dark:text-rose-400"><XCircle className="h-3 w-3" /> Failed</span>;
}

function AutomationDialog({ form: initial, models, options, onClose, onSaved }) {
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [goal, setGoal] = useState("");
  const [planning, setPlanning] = useState(false);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const setSchedule = (patch) => setForm((f) => ({ ...f, schedule: { ...f.schedule, ...patch } }));
  const s = form.schedule;
  const rules = options.rules || {};
  const planName = options.planName || "your";
  const intervals = [15, 30, 60, 120, 180, 360, 720].filter((m) => !rules.minInterval || m >= rules.minInterval);
  const lockedInterval = options.rules && rules.minInterval == null;
  const [apps, setApps] = useState(null); // connected Telegram, WhatsApp, Slack and Discord (Settings > Connectors)
  const [gmail, setGmail] = useState(true);
  useEffect(() => {
    api.get("/connectors").then(({ data }) => {
      const linked = data.connectors.filter((c) => c.category === "messaging" && c.connected);
      setGmail(data.connectors.some((c) => c.id === "gmail" && c.connected));
      setApps(linked);
      // Steps Krish wrote may ask for an app that isn't connected yet; keep only the connected ones.
      setForm((f) => ({ ...f, sendTo: (f.sendTo || []).filter((id) => linked.some((c) => c.id === id)) }));
    }).catch(() => setApps([]));
  }, []);
  const toggleApp = (id) => set({ sendTo: (form.sendTo || []).includes(id) ? form.sendTo.filter((x) => x !== id) : [...(form.sendTo || []), id] });

  const save = async () => {
    setBusy(true);
    const schedule = { type: s.type, timezone: s.timezone };
    if (s.type === "interval") schedule.minutes = Number(s.minutes);
    if (s.type === "daily" || s.type === "weekly") schedule.time = s.time;
    if (s.type === "weekly") schedule.weekday = Number(s.weekday);
    if (s.type === "once") { schedule.time = s.time; schedule.date = s.date; }
    if (s.type === "email") schedule.query = (s.query || "").trim();
    const body = {
      name: form.name, prompt: form.prompt, schedule, model: form.model || null,
      memory: form.memory, thorough: form.thorough, emailResult: form.emailResult, notifyUrl: form.notifyUrl.trim(),
      sendTo: form.sendTo || [], askFirst: form.askFirst !== false,
    };
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

  const writePlan = async () => {
    setPlanning(true);
    try {
      const { data } = await api.post("/automations/plan", { goal, timezone: s.timezone || localTz() });
      setForm((f) => ({ ...f, name: data.name, prompt: data.prompt, schedule: { ...f.schedule, ...data.schedule },
        emailResult: f.emailResult || (!!data.emailResult && options.email),
        sendTo: [...new Set([...(f.sendTo || []), ...(data.sendTo || []).filter((id) => (apps || []).some((c) => c.id === id))])] }));
      toast.success("Steps written. Check them, then save.");
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setPlanning(false);
    }
  };

  const field = "h-9 w-full rounded-md border border-border bg-card px-2 text-sm";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="radha-scroll max-h-[92dvh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{form.id ? "Edit automation" : "New automation"}</DialogTitle>
          <DialogDescription>An agent that plans its own steps and uses every tool. Describe the goal, or write the steps yourself.</DialogDescription>
          {options.rules && (
            <p className="text-[11px] text-muted-foreground" data-testid="plan-rules">
              {planName} plan: {options.limit ? `${options.limit} automation${options.limit === 1 ? "" : "s"}, ` : ""}
              {rules.minInterval == null ? "runs once a day or once a week" : `repeats as often as every ${rules.minInterval >= 60 ? "hour" : `${rules.minInterval} minutes`}`}.
              {" "}<a href="/plans" className="font-medium text-primary hover:underline">See plans</a>
            </p>
          )}
        </DialogHeader>
        <div className="space-y-4">
          {form.fromAsk && (
            <p className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3 text-[13px]" data-testid="from-ask">
              Krish wrote the steps and picked the time. Check them, change anything, then press Create.
            </p>
          )}
          {options.planner && !form.fromAsk && (
            <div className="space-y-1.5 rounded-xl border border-primary/30 bg-primary/5 p-3" data-testid="automation-planner">
              <Label className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-primary" /> Describe your goal in simple words</Label>
              <Textarea rows={2} value={goal} onChange={(e) => setGoal(e.target.value)} className="bg-card" data-testid="automation-goal"
                placeholder="Every morning, find new companies in Pune that need a website and send me a list" />
              <Button size="sm" variant="outline" onClick={writePlan} disabled={planning || goal.trim().length < 3}
                className="gap-1.5 border-border bg-card" data-testid="write-plan">
                {planning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Write the steps for me
              </Button>
            </div>
          )}
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input value={form.name} onChange={(e) => set({ name: e.target.value })} data-testid="automation-name" className="bg-card" placeholder="Morning news brief" />
          </div>
          <div className="space-y-1.5">
            <Label>Agent steps</Label>
            <Textarea rows={6} value={form.prompt} onChange={(e) => set({ prompt: e.target.value })} data-testid="automation-prompt" className="bg-card"
              placeholder={"1. Search the web for…\n2. Compare with last time…\n3. Create a PDF report…"} />
          </div>
          <div className="space-y-1.5">
            <Label>When should it run?</Label>
            <div className="grid grid-cols-3 gap-1.5 max-sm:grid-cols-2" role="radiogroup" data-testid="schedule-type">
              {[
                { id: "daily", label: "Every day" }, { id: "weekly", label: "Every week" },
                { id: "interval", label: rules.minInterval >= 60 || lockedInterval ? "Every few hours" : "Every few min", locked: lockedInterval, need: "Pro" },
                { id: "email", label: "On new email", locked: options.rules && !rules.events, need: "Pro" },
                { id: "once", label: "Just once" }, { id: "manual", label: "Only when I say" },
              ].map((o) => {
                const Icon = KINDS[o.id].icon, on = s.type === o.id, off = o.locked && !on;
                return (
                  <button key={o.id} type="button" role="radio" aria-checked={on} disabled={off} onClick={() => setSchedule({ type: o.id })}
                    data-testid={`when-${o.id}`} title={off ? `Part of the ${o.need} and Max plans` : undefined}
                    className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-left text-[13px] transition-colors ${on ? "border-primary bg-primary/10 font-medium text-foreground" : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground"} ${off ? "cursor-not-allowed opacity-50" : ""}`}>
                    <Icon className={`h-3.5 w-3.5 shrink-0 ${on ? "text-primary" : ""}`} />
                    <span className="min-w-0 truncate">{o.label}</span>
                    {o.locked && <Lock className="ml-auto h-3 w-3 shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {s.type === "interval" && (
              <div className="space-y-1.5">
                <Label>Every</Label>
                <select value={s.minutes} onChange={(e) => setSchedule({ minutes: e.target.value })} className={field}>
                  {intervals.map((m) => <option key={m} value={m}>{m < 60 ? `${m} minutes` : `${m / 60} hour${m === 60 ? "" : "s"}`}</option>)}
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
            {s.type === "email" && (
              <div className="col-span-2 space-y-1.5" data-testid="email-trigger">
                <Label className="flex items-center gap-1.5"><Inbox className="h-3.5 w-3.5 text-primary" /> Which emails? (Gmail search)</Label>
                <Input value={s.query || ""} onChange={(e) => setSchedule({ query: e.target.value })} className="bg-card" data-testid="schedule-query"
                  placeholder="from:orders@myshop.com  or  subject:invoice" />
                <p className="text-[11px] text-muted-foreground">Krish looks in your Gmail every 10 minutes and runs once with the new emails. Leave it empty for every new email.{!gmail && " Connect Gmail in Settings > Connectors first."}</p>
              </div>
            )}
            {s.type === "once" && (
              <div className="space-y-1.5">
                <Label>Date</Label>
                <Input type="date" value={s.date || ""} onChange={(e) => setSchedule({ date: e.target.value })} data-testid="schedule-date" className="bg-card" />
              </div>
            )}
            {(s.type === "daily" || s.type === "weekly" || s.type === "once") && (
              <div className="space-y-1.5">
                <Label>Time ({s.timezone})</Label>
                <Input type="time" value={s.time} onChange={(e) => setSchedule({ time: e.target.value })} data-testid="schedule-time" className="bg-card" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Model</Label>
              <select value={form.model || ""} onChange={(e) => set({ model: e.target.value })} className={field}>
                <option value="">Default</option>
                {models.map((m) => {
                  const locked = m.pro && options.rules && !rules.premiumModels;
                  return <option key={m.id} value={m.id} disabled={!m.ok || locked}>{m.label}{!m.ok ? " (needs key)" : locked ? " (Pro and Max)" : ""}</option>;
                })}
              </select>
            </div>
          </div>
          <p className="flex items-start gap-1.5 rounded-lg bg-surface px-3 py-2 text-[12px] text-muted-foreground" data-testid="schedule-preview">
            <CalendarClock className="mt-px h-3.5 w-3.5 shrink-0 text-primary" /> {schedulePreview(s)}
          </p>
          <div className="space-y-3 rounded-xl border border-border bg-card p-3">
            <OptionRow icon={Brain} title="Remember previous runs" hint="Sees what it found last time, skips repeats and reports changes."
              checked={form.memory} onChange={(v) => set({ memory: v })} testid="opt-memory" />
            <OptionRow icon={Gauge} title="Thorough mode"
              hint={options.rules && !rules.thorough ? "More steps for long jobs. Part of the Max plan." : "More steps for long jobs such as research plus several files."}
              checked={form.thorough} disabled={options.rules && !rules.thorough && !form.thorough} locked={options.rules && !rules.thorough}
              onChange={(v) => set({ thorough: v })} testid="opt-thorough" />
            <OptionRow icon={ShieldCheck} title="Ask me before sending emails"
              hint={options.rules && !rules.noAsk ? "Every email Krish writes waits for your OK. Sending without asking is part of the Max plan." : "Every email waits for your OK. Turn off to let this job send on its own."}
              checked={form.askFirst !== false} disabled={options.rules && !rules.noAsk && form.askFirst !== false} locked={options.rules && !rules.noAsk}
              onChange={(v) => set({ askFirst: v })} testid="opt-ask-first" />
            <OptionRow icon={Mail} title="Email me the result"
              hint={options.email ? "Sent to your account email after each run." : "Email isn't set up on the server yet."}
              checked={form.emailResult} disabled={!options.email && !form.emailResult} onChange={(v) => set({ emailResult: v })} testid="opt-email" />
            <div className="space-y-1.5" data-testid="opt-send-to">
              <Label className="flex items-center gap-1.5 text-sm"><Send className="h-3.5 w-3.5 text-primary" /> Send the result to my apps</Label>
              {apps === null ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : apps.length ? (
                <div className="flex flex-wrap gap-2">
                  {apps.map((c) => {
                    const on = (form.sendTo || []).includes(c.id);
                    return (
                      <button key={c.id} type="button" onClick={() => toggleApp(c.id)} aria-pressed={on} data-testid={`opt-send-${c.id}`}
                        className={`flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-sm transition-colors ${on ? "border-primary bg-primary/10" : "border-border hover:bg-surface"}`}>
                        <AppLogo id={c.id} size="sm" className="!h-6 !w-6 rounded-full" /> {c.name}{on && <Check className="h-3.5 w-3.5 text-primary" />}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[12px] text-muted-foreground">
                  <button type="button" onClick={() => { onClose(); openSettings("connectors"); }} className="font-medium text-primary hover:underline">Connect Telegram, WhatsApp, Slack or Discord</button> to get results there.
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="flex items-center gap-1.5 text-sm"><Send className="h-3.5 w-3.5 text-primary" /> Or post to any webhook (optional)</Label>
              <Input value={form.notifyUrl} onChange={(e) => set({ notifyUrl: e.target.value })} className="bg-background" data-testid="opt-notify-url"
                placeholder="https://discord.com/api/webhooks/…" />
              <p className="text-[11px] text-muted-foreground">Paste a channel webhook link and every result is posted there.</p>
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

function schedulePreview(s) {
  const at = s.time ? new Date(`2000-01-01T${s.time}`).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
  if (s.type === "daily") return `Runs every day at ${at}, your time (${s.timezone}).`;
  if (s.type === "weekly") return `Runs every ${DAYS[Number(s.weekday) || 0]} at ${at}, your time (${s.timezone}).`;
  if (s.type === "interval") { const m = Number(s.minutes); return `Runs every ${m < 60 ? `${m} minutes` : m === 60 ? "hour" : `${m / 60} hours`}, all day.`; }
  if (s.type === "email") return `Looks in your Gmail every 10 minutes and runs once for the new emails${(s.query || "").trim() ? ` matching “${s.query.trim()}”` : ""}.`;
  if (s.type === "once") return s.date ? `Runs once on ${new Date(`${s.date}T00:00`).toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" })} at ${at}, then turns itself off.` : "Pick a date.";
  return "Runs only when you press Run now (or a webhook calls it).";
}

function OptionRow({ icon: Icon, title, hint, checked, onChange, disabled, locked, testid }) {
  return (
    <div className="flex items-start gap-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1 text-sm font-medium">{title}{locked && <Lock className="h-3 w-3 text-muted-foreground" />}</p>
        <p className="text-[11px] text-muted-foreground">{hint}</p>
      </div>
      <Switch checked={!!checked} onCheckedChange={onChange} disabled={disabled} data-testid={testid} />
    </div>
  );
}

function RunCard({ run: r, onOpen, onPreview, onStop }) {
  const [open, setOpen] = useState(false);
  const steps = Array.isArray(r.steps) ? r.steps : [];
  const long = (r.output || "").length > 600;
  return (
    <div className="rounded-xl border border-border bg-card p-4" data-testid={`run-${r.id}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <StatusBadge status={r.status} />
        <span className="text-muted-foreground" title={new Date(r.startedAt).toLocaleString()}>· {TRIGGERS[r.trigger] || r.trigger} · {when(r.startedAt)}{took(r) ? ` · took ${took(r)}` : ""}</span>
        {r.status === "running" && (
          <button onClick={onStop} data-testid={`stop-${r.id}`}
            className="ml-auto flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-muted-foreground hover:border-rose-500/50 hover:text-rose-600">
            <Square className="h-3 w-3" /> Stop
          </button>
        )}
        <button onClick={onOpen} className={`${r.status === "running" ? "" : "ml-auto "}flex items-center gap-1 text-brand hover:underline`}>
          <MessageSquare className="h-3 w-3" /> Open conversation
        </button>
      </div>
      {steps.length > 0 && (
        <ol className="mt-3 space-y-1 border-l border-border pl-3" data-testid="run-steps">
          {steps.map((s, i) => (
            <li key={i} className="flex items-start gap-1.5 text-xs">
              {s.status === "error" ? <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-rose-500" /> : <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />}
              <span className="font-medium">{s.label}</span>
              {s.summary && <span className="min-w-0 truncate text-muted-foreground">· {s.summary}</span>}
            </li>
          ))}
        </ol>
      )}
      {r.waiting > 0 && (
        <p className="mt-2 flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400"><Hand className="h-3 w-3" /> {r.waiting} action{r.waiting === 1 ? "" : "s"} waiting for your OK (see above)</p>
      )}
      {r.error && r.status !== "stopped" && <p className={`mt-2 text-xs ${r.status === "skipped" ? "text-amber-700 dark:text-amber-400" : "text-rose-600 dark:text-rose-400"}`}>{r.error}</p>}
      {r.output && (
        <div className={`radha-prose mt-3 min-w-0 text-sm ${open || !long ? "" : "max-h-40 overflow-hidden [mask-image:linear-gradient(to_bottom,black_60%,transparent)]"}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: ScrollTable }}>{r.output}</ReactMarkdown>
        </div>
      )}
      {long && (
        <button onClick={() => setOpen((o) => !o)} className="mt-1 flex items-center gap-1 text-xs text-brand hover:underline">
          {open ? <><ChevronUp className="h-3 w-3" /> Show less</> : <><ChevronDown className="h-3 w-3" /> Show full result</>}
        </button>
      )}
      <MediaGallery items={r.media} onOpen={onPreview} />
      {(r.delivery || []).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
          {r.delivery.map((d) => (
            <span key={d.channel} title={d.error || ""}
              className={`flex items-center gap-1 rounded-full border px-2 py-0.5 ${d.ok ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400" : "border-rose-500/40 text-rose-600 dark:text-rose-400"}`}>
              {d.channel === "email" ? <Mail className="h-3 w-3" /> : <Send className="h-3 w-3" />}
              {d.ok ? `Sent by ${d.channel}` : `${d.channel} failed: ${d.error}`}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function AutomationDetail({ automation: a, onChanged, onEdit, onBack, approvals = [], onApprovalsDone }) {
  const [advanced, setAdvanced] = useState(!!a.webhookUrl);
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

  const stop = async (r) => {
    try {
      await api.post(`/automations/${a.id}/runs/${r.id}/stop`);
      toast.success("Stopping the run");
      setTimeout(() => { loadRuns().catch(() => {}); onChanged(); }, 800);
    } catch (e) {
      toast.error(formatApiError(e));
      loadRuns().catch(() => {});
    }
  };

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
      <div className="radha-scroll min-w-0 flex-1 overflow-y-auto p-4 sm:p-6" data-testid="automation-detail">
        <button onClick={onBack} className="mb-3 flex items-center gap-1.5 py-1 text-sm text-muted-foreground hover:text-foreground md:hidden" data-testid="automation-back">
          <ArrowLeft className="h-4 w-4" /> All automations
        </button>
        <div className="flex flex-wrap items-start gap-3">
          <KindIcon a={a} size="h-11 w-11" />
          <div className="min-w-0 flex-1 max-sm:basis-[calc(100%-3.5rem)]">
            <h2 className="text-xl font-bold tracking-tight">{a.name}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{a.scheduleText}{a.enabled ? "" : " · paused"}</p>
            {a.pausedReason && <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{a.pausedReason}</p>}
            <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]" data-testid="automation-features">
              {a.memory && <Feature icon={Brain} text="Remembers past runs" />}
              {a.thorough && <Feature icon={Gauge} text="Thorough" />}
              {a.emailResult && <Feature icon={Mail} text="Emails you" />}
              {a.notifyUrl && <Feature icon={Send} text="Posts to webhook" />}
              {a.askFirst !== false ? <Feature icon={ShieldCheck} text="Asks before sending" /> : <Feature icon={Send} text="Sends on its own" />}
              {(a.sendTo || []).map((id) => <Feature key={id} icon={Send} text={`Sends to ${({ telegram: "Telegram", whatsapp: "WhatsApp", slack: "Slack", discord: "Discord" })[id]}`} />)}
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={onEdit} className="gap-1.5 border-border bg-card"><Pencil className="h-3.5 w-3.5" /> Edit</Button>
          <Button size="sm" onClick={runNow} disabled={running} data-testid="run-now" className="gap-1.5">{running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} {running ? "Running" : "Run now"}</Button>
          <button onClick={remove} title="Delete" className="rounded-md p-2 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
        </div>
        <Stats a={a} runs={runs} />
        {approvals.length > 0 && <Approvals items={approvals} onDone={onApprovalsDone} inDetail />}
        <Steps text={a.prompt} />

        <div className="mt-4 rounded-xl border border-border bg-card">
          <button onClick={() => setAdvanced((o) => !o)} className="flex w-full items-center gap-1.5 px-4 py-3 text-left text-sm font-semibold" data-testid="advanced-toggle">
            <Webhook className="h-4 w-4 text-primary" /> Start it from another app (webhook)
            <span className="ml-auto text-xs font-normal text-muted-foreground">{hookUrl ? "On" : "Optional"}</span>
            {advanced ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
          </button>
          {advanced && (
            <div className="border-t border-border px-4 pb-4 pt-3">
              {hookUrl ? (
                <>
                  <p className="text-xs text-muted-foreground">Send any JSON to this secret link to start a run. What you send is given to the job.</p>
                  <div className="mt-2 flex items-center gap-2 rounded-lg border border-border bg-background px-2 py-1.5">
                    <code className="truncate text-[11px] text-brand" data-testid="webhook-url">{hookUrl}</code>
                    <button onClick={() => { navigator.clipboard.writeText(hookUrl); toast.success("Webhook URL copied"); }} className="ml-auto text-muted-foreground hover:text-foreground"><Copy className="h-3.5 w-3.5" /></button>
                  </div>
                  <div className="mt-2 flex gap-3 text-xs">
                    <button onClick={() => webhook(true)} className="text-brand hover:underline">Rotate URL</button>
                    <button onClick={() => webhook(false)} className="text-muted-foreground hover:text-destructive">Remove</button>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-xs text-muted-foreground">For website forms, Zapier or your own code: they call a secret link and this job runs.</p>
                  <button onClick={() => webhook(true)} data-testid="create-webhook" className="mt-2 text-xs font-medium text-brand hover:underline">Create a webhook URL</button>
                </>
              )}
            </div>
          )}
        </div>

        <h3 className="mt-6 text-xs font-bold uppercase tracking-[0.15em] text-muted-foreground">Runs</h3>
        {runs === null ? <Loader2 className="mt-4 h-5 w-5 animate-spin text-primary" /> : runs.length === 0 ? (
          <div className="mt-2 rounded-xl border border-dashed border-border p-5 text-center">
            <p className="text-sm text-muted-foreground">No runs yet. Press <span className="font-medium text-foreground">Run now</span> to try it and see the result here.</p>
          </div>
        ) : (
          <div className="mt-2 space-y-3" data-testid="run-list">
            {runs.map((r) => (
              <RunCard key={r.id} run={r} onPreview={setPreview} onStop={() => stop(r)} onOpen={() => navigate(`/?conversation=${r.conversationId}`)} />
            ))}
          </div>
        )}
      </div>
      {preview && <PreviewPanel item={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

function Stats({ a, runs }) {
  const done = (runs || []).filter((r) => r.status === "succeeded" || r.status === "failed");
  const ok = done.filter((r) => r.status === "succeeded").length;
  const last = (runs || [])[0];
  const cells = [
    { label: "Last run", value: last ? when(last.startedAt) : "Not yet" },
    { label: a.schedule?.type === "email" ? "Next check" : "Next run", value: a.enabled ? (a.nextRunAt ? when(a.nextRunAt) : a.schedule?.type === "manual" ? "When you press Run" : "None") : "Paused" },
    { label: "Worked", value: done.length ? `${ok} of ${done.length}` : "–", tone: done.length && ok < done.length ? "text-amber-600 dark:text-amber-400" : "" },
  ];
  return (
    <div className="mt-4 grid grid-cols-3 gap-2" data-testid="automation-stats">
      {cells.map((c) => (
        <div key={c.label} className="min-w-0 rounded-xl border border-border bg-card px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{c.label}</p>
          <p className={`mt-0.5 truncate text-sm font-semibold ${c.tone || ""}`}>{c.value}</p>
        </div>
      ))}
    </div>
  );
}

// The job's steps: a numbered list when written as "1. … 2. …", otherwise the text as written.
function Steps({ text }) {
  const lines = (text || "").split(/\n+/).map((l) => l.trim()).filter(Boolean);
  const numbered = lines.length > 1 && lines.every((l) => /^\d+[.)]\s/.test(l));
  return (
    <div className="mt-4 rounded-xl border border-border bg-card p-4" data-testid="automation-steps">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground"><ListChecks className="h-3.5 w-3.5 text-primary" /> What it does</p>
      {numbered ? (
        <ol className="mt-2 space-y-1.5">
          {lines.map((l, i) => (
            <li key={i} className="flex gap-2.5 text-sm">
              <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">{i + 1}</span>
              <span className="min-w-0">{l.replace(/^\d+[.)]\s*/, "")}</span>
            </li>
          ))}
        </ol>
      ) : <p className="mt-2 whitespace-pre-wrap text-sm">{text}</p>}
    </div>
  );
}

function Feature({ icon: Icon, text }) {
  return <span className="flex items-center gap-1 rounded-full border border-primary/30 bg-primary/5 px-2 py-0.5 text-foreground"><Icon className="h-3 w-3 text-primary" /> {text}</span>;
}
