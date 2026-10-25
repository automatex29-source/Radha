import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import {
  ArrowDownRight, ArrowUpRight, Crown, Eye, EyeOff, IndianRupee, Loader2, LogIn, MessageSquare, Pencil, Radio,
  Search, ShieldCheck, TrendingUp, UserPlus, Users, Wallet,
} from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const RANGES = [["24h", "24 hours", "24h"], ["7d", "7 days", "7d"], ["30d", "30 days", "30d"], ["90d", "90 days", "90d"], ["1y", "1 year", "1y"]];
const PREV = { "24h": "the 24 hours before", "7d": "the week before", "30d": "the 30 days before", "90d": "the 90 days before", "1y": "the year before" };
const METRICS = [["active", "Active people"], ["messages", "Messages"], ["logins", "Sign-ins"], ["signups", "Sign-ups"]];
const PLAN_STYLE = {
  basic: { label: "Basic", dot: "bg-slate-400 dark:bg-slate-500", chip: "bg-slate-500/10 text-slate-600 dark:text-slate-300" },
  pro: { label: "Pro", dot: "bg-[var(--viz-1)]", chip: "bg-[var(--viz-1)]/12 text-[var(--viz-1)]" },
  max: { label: "Max", dot: "bg-[var(--viz-2)]", chip: "bg-[var(--viz-2)]/12 text-[var(--viz-2)]" },
};
const COST_FIELDS = [
  ["hostingMonthly", "Hosting per month (₹)"], ["paymentFeePercent", "Razorpay fee (%)"], ["chat", "Chat message"],
  ["counsellor", "Counsellor message"], ["web", "Web search"], ["voice", "Voice"], ["think", "Think"],
  ["build", "App build"], ["picture", "Picture"], ["deck", "Deck"], ["video", "Video"],
];
const METHOD = { password: "Email", google: "Google", signup: "New account", reset: "Password reset", "": "Sign-in" };

const inr = (n, digits = 0) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
const num = (n) => Number(n || 0).toLocaleString("en-IN");

function ago(iso) {
  if (!iso) return "Not yet";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString();
}

function tick(t, bucket) {
  if (bucket === "hour") return new Date(t).toLocaleTimeString(undefined, { hour: "numeric" });
  return new Date(`${t}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function Panel({ title, subtitle, action, children, className = "", testId }) {
  return (
    <section className={`rounded-2xl border border-border/70 bg-card/85 p-4 shadow-sm sm:p-5 ${className}`} data-testid={testId}>
      {(title || action) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-[15px] font-bold tracking-tight">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

function Delta({ value, prev, money, range }) {
  if (!prev && !value) return <span className="text-xs text-muted-foreground">No change</span>;
  if (!prev) return <span className="text-xs text-muted-foreground">New vs {PREV[range]}</span>;
  const pct = Math.round(((value - prev) / Math.abs(prev)) * 100);
  const up = pct >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-semibold ${up ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}
      title={`${money ? inr(prev) : num(prev)} in ${PREV[range]}`}>
      <Icon className="h-3.5 w-3.5" />{Math.abs(pct)}%<span className="ml-1 font-normal text-muted-foreground">vs before</span>
    </span>
  );
}

function Kpi({ icon: Icon, label, value, delta, foot, live }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card/85 p-4 shadow-sm">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Icon className="h-3.5 w-3.5" /> {label}
        {live && <span className="relative ml-auto flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" /></span>}
      </p>
      <p className="mt-1.5 text-2xl font-extrabold tabular-nums tracking-tight sm:text-[26px]">{value}</p>
      <div className="mt-1 min-h-4">{delta || <span className="text-xs text-muted-foreground">{foot}</span>}</div>
    </div>
  );
}

function ChartTip({ active, payload, label, bucket, money, name }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="text-muted-foreground">{bucket === "hour" ? new Date(label).toLocaleString(undefined, { hour: "numeric", day: "numeric", month: "short" }) : new Date(`${label}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}</p>
      <p className="mt-0.5 font-semibold tabular-nums text-foreground">{name}: {money ? inr(payload[0].value) : num(payload[0].value)}</p>
    </div>
  );
}

function HBars({ rows, valueKey = "count", labelKey = "label", format = num }) {
  const max = Math.max(1, ...rows.map((r) => r[valueKey]));
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r[labelKey]} className="text-sm">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate">{r[labelKey]}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">{format(r[valueKey])}</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted/70">
            <div className="h-full rounded-full bg-[var(--viz-1)]" style={{ width: `${Math.max(r[valueKey] ? 2 : 0, (r[valueKey] / max) * 100)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function PlanChip({ plan }) {
  const s = PLAN_STYLE[plan] || PLAN_STYLE.basic;
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${s.chip}`}>{s.label}</span>;
}

function CostsForm({ costs, onSaved, onClose }) {
  const [form, setForm] = useState(() => Object.fromEntries(COST_FIELDS.map(([k]) => [k, String(costs[k] ?? "")])));
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.put("/admin/dashboard/costs", Object.fromEntries(Object.entries(form).map(([k, v]) => [k, Number(v || 0)])));
      toast.success("Costs saved. Profit is worked out again.");
      onSaved();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={save} className="mt-4 rounded-xl border border-border/70 bg-background/60 p-3" data-testid="owner-costs-form">
      <p className="mb-3 text-xs text-muted-foreground">Put in your real bills. AI costs are rupees for each request.</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {COST_FIELDS.map(([k, label]) => (
          <label key={k} className="text-[11px] font-medium text-muted-foreground">{label}
            <Input type="number" step="any" min={0} value={form[k]} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} className="mt-1 h-8 text-sm" />
          </label>
        ))}
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <Button type="submit" size="sm" disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save costs"}</Button>
      </div>
    </form>
  );
}

export default function OwnerDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [range, setRange] = useState("24h");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [metric, setMetric] = useState("active");
  const [q, setQ] = useState("");
  const [showAsks, setShowAsks] = useState(false);
  const [editCosts, setEditCosts] = useState(false);
  const [, setNow] = useState(0);

  const load = useCallback(() => {
    api.get("/admin/dashboard", { params: { range } }).then(({ data }) => { setData(data); setError(""); })
      .catch((e) => setError(formatApiError(e)));
  }, [range]);

  useEffect(() => {
    if (!user?.isOwner) return undefined;
    load();
    const every = setInterval(() => { if (document.visibilityState === "visible") load(); }, 30000);
    const clock = setInterval(() => setNow((n) => n + 1), 10000);
    return () => { clearInterval(every); clearInterval(clock); };
  }, [user, load]);

  const people = useMemo(() => {
    const term = q.trim().toLowerCase();
    const all = data?.people || [];
    return term ? all.filter((p) => `${p.name} ${p.email}`.toLowerCase().includes(term)) : all;
  }, [data, q]);

  if (!user?.isOwner) return <Navigate to="/" replace />;

  const k = data?.kpis;
  const m = data?.money;
  const metricName = METRICS.find(([id]) => id === metric)[1];
  const subs = data?.plans.subscribers;
  const subsTotal = subs ? subs.basic + subs.pro + subs.max : 0;

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <main className="owner-viz min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl px-4 pb-14 pt-8 sm:px-6">
          <header className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-card/70 px-3 py-1 text-xs font-medium text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5 text-primary" /> Owner only
              </span>
              <h1 className="mt-3 text-2xl font-extrabold tracking-tight sm:text-3xl">Dashboard</h1>
              <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground" data-testid="owner-dash-updated">
                <Radio className="h-3.5 w-3.5 text-emerald-500" /> Live · updated {data ? ago(data.generatedAt).toLowerCase() : "…"}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => navigate("/admin/users")} data-testid="owner-dash-all-users">
              <Users className="mr-1.5 h-4 w-4" /> All users, problems and codes
            </Button>
          </header>

          <div className="mt-5 flex gap-1 overflow-x-auto rounded-xl border border-border bg-card p-1" role="tablist" data-testid="owner-dash-range">
            {RANGES.map(([id, label, short]) => (
              <button key={id} type="button" role="tab" aria-selected={range === id} onClick={() => setRange(id)}
                className={`shrink-0 flex-1 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${range === id ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
                <span className="sm:hidden">{short}</span><span className="max-sm:hidden">{label}</span>
              </button>
            ))}
          </div>

          {error && !data ? <p className="mt-10 text-center text-sm text-destructive">{error}</p> : !data ? (
            <div className="flex justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : (
            <>
              <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="owner-dash-kpis">
                <Kpi icon={IndianRupee} label="Revenue" value={inr(k.revenue.value)} delta={<Delta {...k.revenue} money range={range} />} />
                <Kpi icon={TrendingUp} label="Profit (estimate)" value={inr(k.profit.value)} delta={<Delta {...k.profit} money range={range} />} />
                <Kpi icon={Users} label="Active people" value={num(k.activeUsers.value)} delta={<Delta {...k.activeUsers} range={range} />} />
                <Kpi icon={Radio} label="Online now" value={num(k.onlineNow)} foot="In the last 10 minutes" live />
                <Kpi icon={LogIn} label="Sign-ins" value={num(k.logins.value)} delta={<Delta {...k.logins} range={range} />} />
                <Kpi icon={UserPlus} label="New sign-ups" value={num(k.signups.value)} delta={<Delta {...k.signups} range={range} />} />
                <Kpi icon={MessageSquare} label="Messages" value={num(k.messages.value)} delta={<Delta {...k.messages} range={range} />} />
                <Kpi icon={Crown} label="Paying people" value={num(k.paidUsers)} foot={`${inr(k.mrr)} a month · ${num(k.totalUsers)} accounts`} />
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                <Panel className="lg:col-span-2" title={metricName} subtitle={data.bucket === "hour" ? "Each hour, last 24 hours" : "Each day, India time"}
                  testId="owner-dash-activity"
                  action={
                    <div className="flex gap-1 rounded-lg bg-muted/60 p-0.5">
                      {METRICS.map(([id, label]) => (
                        <button key={id} type="button" onClick={() => setMetric(id)}
                          className={`rounded-md px-2 py-1 text-[11px] font-semibold ${metric === id ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"}`}>{label}</button>
                      ))}
                    </div>
                  }>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={data.series} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
                        <defs>
                          <linearGradient id="ownerArea" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--viz-1)" stopOpacity={0.28} />
                            <stop offset="100%" stopColor="var(--viz-1)" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
                        <XAxis dataKey="t" tickFormatter={(t) => tick(t, data.bucket)} tick={{ fontSize: 11, fill: "var(--viz-axis)" }} tickLine={false} axisLine={false} minTickGap={24} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--viz-axis)" }} tickLine={false} axisLine={false} width={40} />
                        <Tooltip content={<ChartTip bucket={data.bucket} name={metricName} />} cursor={{ stroke: "var(--viz-axis)", strokeDasharray: "3 3" }} />
                        <Area type="linear" dataKey={metric} stroke="var(--viz-1)" strokeWidth={2} fill="url(#ownerArea)" activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--viz-surface)" }} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>

                <Panel title="Revenue" subtitle={`${inr(m.revenue)} in ${RANGES.find(([id]) => id === range)[1].toLowerCase()}`} testId="owner-dash-revenue-chart">
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={data.series} margin={{ top: 6, right: 4, left: -12, bottom: 0 }}>
                        <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
                        <XAxis dataKey="t" tickFormatter={(t) => tick(t, data.bucket)} tick={{ fontSize: 11, fill: "var(--viz-axis)" }} tickLine={false} axisLine={false} minTickGap={24} />
                        <YAxis tickFormatter={(v) => `₹${v}`} tick={{ fontSize: 11, fill: "var(--viz-axis)" }} tickLine={false} axisLine={false} width={46} />
                        <Tooltip content={<ChartTip bucket={data.bucket} name="Revenue" money />} cursor={{ fill: "var(--viz-grid)" }} />
                        <Bar dataKey="revenue" fill="var(--viz-1)" radius={[4, 4, 0, 0]} maxBarSize={18} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                <Panel title="Profit" subtitle="Revenue minus what it cost to run" testId="owner-dash-profit"
                  action={<Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setEditCosts((v) => !v)}><Pencil className="mr-1 h-3.5 w-3.5" /> Edit costs</Button>}>
                  <dl className="space-y-2 text-sm tabular-nums">
                    <div className="flex justify-between"><dt>Revenue</dt><dd className="font-semibold">{inr(m.revenue, 2)}</dd></div>
                    <div className="flex justify-between text-muted-foreground"><dt>Razorpay fees</dt><dd>− {inr(m.paymentFees, 2)}</dd></div>
                    <div className="flex justify-between text-muted-foreground"><dt>Hosting</dt><dd>− {inr(m.hostingCost, 2)}</dd></div>
                    <div className="flex justify-between text-muted-foreground"><dt>AI requests</dt><dd>− {inr(m.aiCost, 2)}</dd></div>
                    <div className={`flex justify-between border-t border-border/70 pt-2 text-base font-extrabold ${m.profit < 0 ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                      <dt>Profit</dt><dd>{m.profit < 0 ? "−" : ""}{inr(Math.abs(m.profit), 2)}</dd>
                    </div>
                  </dl>
                  {editCosts ? <CostsForm costs={data.costs} onClose={() => setEditCosts(false)} onSaved={() => { setEditCosts(false); load(); }} />
                    : <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">Costs are estimates. Tap Edit costs to put in your Render bill and what each AI request really costs.</p>}
                </Panel>

                <Panel title="Plans" subtitle="Sold in this period, and who is on each plan now" testId="owner-dash-plans">
                  <div className="grid grid-cols-2 gap-2">
                    {data.plans.sold.map((p) => (
                      <div key={p.plan} className="rounded-xl border border-border/70 p-3">
                        <p className="flex items-center gap-1.5 text-xs font-semibold"><span className={`h-2 w-2 rounded-full ${PLAN_STYLE[p.plan].dot}`} />{p.name} · {inr(p.price)}</p>
                        <p className="mt-1 text-xl font-extrabold tabular-nums">{num(p.count)} <span className="text-xs font-medium text-muted-foreground">sold</span></p>
                        <p className="text-xs tabular-nums text-muted-foreground">{inr(p.revenue)}</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    {num(data.plans.checkoutsPaid)} of {num(data.plans.checkoutsStarted)} checkouts paid
                    {data.plans.checkoutsStarted ? ` (${Math.round((data.plans.checkoutsPaid / data.plans.checkoutsStarted) * 100)}%)` : ""}
                  </p>
                  <div className="mt-3 flex h-2.5 gap-0.5 overflow-hidden rounded-full" aria-label="People on each plan now">
                    {["basic", "pro", "max"].map((p) => subs[p] ? <div key={p} className={PLAN_STYLE[p].dot} style={{ width: `${(subs[p] / subsTotal) * 100}%`, minWidth: 4 }} title={`${PLAN_STYLE[p].label}: ${subs[p]}`} /> : null)}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {["basic", "pro", "max"].map((p) => (
                      <span key={p} className="flex items-center gap-1.5"><span className={`h-2 w-2 rounded-full ${PLAN_STYLE[p].dot}`} />{PLAN_STYLE[p].label} {num(subs[p])}</span>
                    ))}
                  </div>
                </Panel>

                <Panel title="Latest payments" subtitle="Paid through Razorpay" testId="owner-dash-payments">
                  {!data.plans.recentPayments.length ? <p className="py-6 text-center text-sm text-muted-foreground">No payments in this period yet.</p> : (
                    <ul className="divide-y divide-border/50">
                      {data.plans.recentPayments.slice(0, 6).map((p, i) => (
                        <li key={i} className="flex items-center justify-between gap-2 py-2 text-sm">
                          <div className="min-w-0">
                            <p className="truncate font-semibold">{p.name}</p>
                            <p className="truncate text-xs text-muted-foreground">{ago(p.at)}{p.promoCode ? ` · ${p.promoCode}` : ""}</p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2"><PlanChip plan={p.plan} /><span className="font-semibold tabular-nums">{inr(p.amount)}</span></div>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                <Panel title="What people use" subtitle="Requests in this period" testId="owner-dash-features">
                  <HBars rows={[...data.features].sort((a, b) => b.count - a.count)} />
                </Panel>
                <Panel className="lg:col-span-2" title="What people ask about" subtitle={`${num(data.asks.total)} questions, grouped by topic. Counsellor chats are private and never shown.`}
                  testId="owner-dash-asks"
                  action={<Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => setShowAsks((v) => !v)} data-testid="owner-dash-show-asks">
                    {showAsks ? <EyeOff className="mr-1 h-3.5 w-3.5" /> : <Eye className="mr-1 h-3.5 w-3.5" />}{showAsks ? "Hide questions" : "Show latest questions"}
                  </Button>}>
                  {!data.asks.total ? <p className="py-6 text-center text-sm text-muted-foreground">No questions in this period yet.</p> : (
                    <div className="grid gap-5 sm:grid-cols-2">
                      <HBars rows={data.asks.topics.slice(0, 8)} labelKey="name" />
                      <div>
                        <p className="mb-2 text-xs font-medium text-muted-foreground">Words people use most</p>
                        <div className="flex flex-wrap gap-1.5">
                          {data.asks.words.map((w) => (
                            <span key={w.word} className="rounded-full border border-border/70 bg-background/60 px-2.5 py-1 text-xs">{w.word} <span className="tabular-nums text-muted-foreground">{w.count}</span></span>
                          ))}
                          {!data.asks.words.length && <span className="text-xs text-muted-foreground">Not enough questions yet.</span>}
                        </div>
                      </div>
                    </div>
                  )}
                  {showAsks && (
                    <ul className="mt-4 max-h-80 divide-y divide-border/50 overflow-y-auto rounded-xl border border-border/70" data-testid="owner-dash-recent-asks">
                      {data.asks.recent.map((r, i) => (
                        <li key={i} className="px-3 py-2.5 text-sm">
                          <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground"><span className="font-semibold text-foreground">{r.name}</span>{r.topic} · {r.where} · {ago(r.at)}</p>
                          <p className="mt-0.5 break-words">{r.text}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
              </div>

              <Panel className="mt-3" title="Use per person" subtitle="Who used Krish in this period, busiest first" testId="owner-dash-people"
                action={<div className="relative w-full sm:w-60"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or email" className="h-8 pl-8 text-sm" /></div>}>
                <div className="-mx-4 overflow-x-auto sm:-mx-5">
                  <table className="w-full min-w-[720px] text-left text-sm">
                    <thead className="border-y border-border/70 text-xs text-muted-foreground">
                      <tr>
                        <th className="px-4 py-2.5 font-medium sm:px-5">Person</th>
                        <th className="px-3 py-2.5 text-right font-medium">Messages</th>
                        <th className="px-3 py-2.5 text-right font-medium">App builds</th>
                        <th className="px-3 py-2.5 text-right font-medium">Pictures, decks, videos</th>
                        <th className="px-3 py-2.5 text-right font-medium">AI cost</th>
                        <th className="px-3 py-2.5 text-right font-medium">Paid</th>
                        <th className="px-4 py-2.5 font-medium sm:px-5">Last active</th>
                      </tr>
                    </thead>
                    <tbody className="tabular-nums">
                      {people.slice(0, 50).map((p) => (
                        <tr key={p.userId} className="border-b border-border/50 last:border-0">
                          <td className="px-4 py-2.5 sm:px-5">
                            <p className="flex items-center gap-2 font-semibold">{p.online && <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" title="Online now" />}{p.name}<PlanChip plan={p.plan} /></p>
                            <p className="text-xs text-muted-foreground">{p.email}</p>
                          </td>
                          <td className="px-3 py-2.5 text-right">{num(p.messages)}</td>
                          <td className="px-3 py-2.5 text-right">{num(p.builds)}</td>
                          <td className="px-3 py-2.5 text-right">{num(p.made)}</td>
                          <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(p.cost, 2)}</td>
                          <td className="px-3 py-2.5 text-right font-semibold">{p.paid ? inr(p.paid) : "–"}</td>
                          <td className="px-4 py-2.5 sm:px-5">{ago(p.lastSeenAt)}</td>
                        </tr>
                      ))}
                      {!people.length && <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">{q ? "No one matches that search." : "No one used Krish in this period yet."}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </Panel>

              <Panel className="mt-3" title="Who signed in" subtitle="Latest first" testId="owner-dash-logins">
                {!data.logins.length ? <p className="py-6 text-center text-sm text-muted-foreground">No sign-ins in this period.</p> : (
                  <ul className="grid gap-x-6 sm:grid-cols-2">
                    {data.logins.slice(0, 20).map((x, i) => (
                      <li key={i} className="flex items-center justify-between gap-3 border-b border-border/50 py-2 text-sm">
                        <div className="min-w-0">
                          <p className="truncate font-semibold">{x.name}</p>
                          <p className="truncate text-xs text-muted-foreground">{x.email}</p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="text-xs font-medium">{METHOD[x.method] ?? "Sign-in"}</p>
                          <p className="text-xs text-muted-foreground" title={new Date(x.at).toLocaleString()}>{ago(x.at)}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
              <p className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground"><Wallet className="h-3.5 w-3.5" />Hour-by-hour use, sign-ins and use per person are counted from this update on. Revenue and sign-ups include everything before it.</p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
