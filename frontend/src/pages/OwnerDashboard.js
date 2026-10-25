import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import {
  AlertTriangle, ArrowDown, ArrowUp, ChevronDown, ChevronUp, Clock, Download, Eye, EyeOff, Lightbulb, Loader2, Minus,
  Pencil, Search, ShieldCheck, ThumbsDown, TrendingDown, TrendingUp, Users,
} from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const RANGES = [["24h", "24 hours", "24h"], ["7d", "7 days", "7d"], ["30d", "30 days", "30d"], ["90d", "90 days", "90d"], ["1y", "1 year", "1y"]];
const PREV = { "24h": "previous 24 hours", "7d": "previous 7 days", "30d": "previous 30 days", "90d": "previous 90 days", "1y": "previous year" };
const METRICS = [["active", "Active people"], ["messages", "Messages"], ["revenue", "Revenue"], ["logins", "Sign-ins"], ["signups", "Sign-ups"]];
const PLAN_STYLE = {
  basic: { label: "Basic", dot: "bg-slate-400 dark:bg-slate-500" },
  pro: { label: "Pro", dot: "bg-[var(--viz-1)]" },
  max: { label: "Max", dot: "bg-[var(--viz-2)]" },
};
const COST_FIELDS = [
  ["hostingMonthly", "Hosting per month (₹)"], ["paymentFeePercent", "Razorpay fee (%)"], ["chat", "Chat message"],
  ["counsellor", "Counsellor message"], ["web", "Web search"], ["voice", "Voice"], ["think", "Think"],
  ["build", "App build"], ["picture", "Picture"], ["deck", "Deck"], ["video", "Video"],
];
const METHOD = { password: "Email", google: "Google", signup: "New account", reset: "Password reset", "": "Sign-in" };
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const inr = (n, digits = 0) => `${n < 0 ? "−" : ""}₹${Math.abs(Number(n || 0)).toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
const num = (n) => Number(n || 0).toLocaleString("en-IN");
const pct = (n, d) => (d ? `${Math.round((n / d) * 100)}%` : "–");
const change = (v, p) => (p ? ((v - p) / Math.abs(p)) * 100 : null);

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

function longTick(t, bucket) {
  return bucket === "hour"
    ? new Date(t).toLocaleString(undefined, { weekday: "short", hour: "numeric", day: "numeric", month: "short" })
    : new Date(`${t}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function Panel({ title, subtitle, action, children, className = "", testId, flush }) {
  return (
    <section className={`rounded-xl border border-border/80 bg-card shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${className}`} data-testid={testId}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-border/60 px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[11.5px] text-muted-foreground">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

function Delta({ value, prev, invert, small }) {
  const c = change(value, prev);
  if (c === null) {
    return <span className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 font-semibold text-muted-foreground ${small ? "text-[10.5px]" : "text-[11px]"} bg-muted`}>{value ? "New" : <Minus className="h-3 w-3" />}</span>;
  }
  const good = invert ? c <= 0 : c >= 0;
  const Icon = c >= 0 ? ArrowUp : ArrowDown;
  return (
    <span className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 font-semibold tabular-nums ${small ? "text-[10.5px]" : "text-[11px]"} ${good ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-rose-500/10 text-rose-700 dark:text-rose-400"}`}>
      <Icon className="h-3 w-3" />{Math.abs(c) >= 1000 ? ">999" : Math.abs(c).toFixed(Math.abs(c) < 10 ? 1 : 0)}%
    </span>
  );
}

function Spark({ data, k }) {
  return (
    <div className="h-10 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`spark-${k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--viz-1)" stopOpacity={0.22} />
              <stop offset="100%" stopColor="var(--viz-1)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area type="linear" dataKey={k} stroke="var(--viz-1)" strokeWidth={1.5} fill={`url(#spark-${k})`} isAnimationActive={false} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function Kpi({ label, value, kpi, foot, series, k, invert }) {
  return (
    <div className="flex flex-col rounded-xl border border-border/80 bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
        {kpi && <Delta {...kpi} invert={invert} />}
      </div>
      <p className="mt-1.5 text-[26px] font-bold leading-none tabular-nums tracking-tight">{value}</p>
      <p className="mt-1.5 text-[11.5px] text-muted-foreground">{foot}</p>
      {series && <div className="mt-2"><Spark data={series} k={k} /></div>}
    </div>
  );
}

function Stat({ label, value, hint, kpi, invert }) {
  return (
    <div className="min-w-0 px-4 py-3">
      <p className="truncate text-[11px] font-medium text-muted-foreground" title={hint}>{label}</p>
      <div className="mt-1 flex items-baseline gap-1.5">
        <p className="text-lg font-bold tabular-nums tracking-tight">{value}</p>
        {kpi && <Delta {...kpi} invert={invert} small />}
      </div>
    </div>
  );
}

function ChartTip({ active, payload, label, bucket, money, rows }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-40 rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-muted-foreground">{longTick(label, bucket)}</p>
      {rows.map(([key, name, cls]) => {
        const p = payload.find((x) => x.dataKey === key);
        if (!p) return null;
        return (
          <p key={key} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5"><span className={`h-0.5 w-3 rounded ${cls}`} />{name}</span>
            <span className="font-semibold tabular-nums text-foreground">{money ? inr(p.value, 0) : num(p.value)}</span>
          </p>
        );
      })}
    </div>
  );
}

function ShareBar({ value, max, color = "bg-[var(--viz-1)]" }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${max ? Math.max(value ? 2 : 0, (value / max) * 100) : 0}%` }} />
    </div>
  );
}

function Th({ children, right, sort, onSort, active, dir }) {
  return (
    <th className={`whitespace-nowrap px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground ${right ? "text-right" : "text-left"}`}>
      {onSort ? (
        <button type="button" onClick={() => onSort(sort)} className={`inline-flex items-center gap-0.5 hover:text-foreground ${active ? "text-foreground" : ""}`}>
          {children}{active && (dir === "desc" ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />)}
        </button>
      ) : children}
    </th>
  );
}

function PlanTag({ plan }) {
  const s = PLAN_STYLE[plan] || PLAN_STYLE.basic;
  return <span className="inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />{s.label}</span>;
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
    <form onSubmit={save} className="border-t border-border/60 p-4" data-testid="owner-costs-form">
      <p className="mb-3 text-xs text-muted-foreground">Put in your real bills. AI costs are rupees for each request.</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
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

/** Plain sentences on what changed and what stands out, worked out from the numbers on the page. */
function insightsFrom(d, range) {
  const out = [];
  const k = d.kpis;
  const r = d.ratios;
  const rev = change(k.revenue.value, k.revenue.prev);
  const paidCount = d.plans.checkoutsPaid;
  if (k.revenue.value) {
    out.push({ tone: rev === null || rev >= 0 ? "up" : "down",
      text: `Revenue is ${inr(k.revenue.value)} from ${paidCount} payment${paidCount === 1 ? "" : "s"} (average ${inr(r.avgOrder)})${rev === null ? "" : `, ${rev >= 0 ? "up" : "down"} ${Math.abs(Math.round(rev))}% on the ${PREV[range]}`}.` });
  } else {
    out.push({ tone: "warn", text: `No payments in this period${k.revenue.prev ? ` (${inr(k.revenue.prev)} in the ${PREV[range]})` : ""}.` });
  }
  if (r.margin !== null) out.push({ tone: r.margin >= 0 ? "up" : "down", text: `Profit margin is ${r.margin}% after Razorpay fees, hosting and AI costs.` });
  else if (d.money.profit < 0) out.push({ tone: "down", text: `Running costs are ${inr(-d.money.profit)} with no revenue to cover them yet.` });
  const act = change(k.activeUsers.value, k.activeUsers.prev);
  if (k.activeUsers.value) {
    out.push({ tone: act === null || act >= 0 ? "up" : "down",
      text: `${num(k.activeUsers.value)} people used Krish: ${num(r.newActive)} new, ${num(r.returningActive)} returning${r.retention !== null ? `. ${r.retention}% of the ${PREV[range]}'s people came back` : ""}.` });
  }
  if (r.peak) out.push({ tone: "info", text: `Busiest ${d.bucket === "hour" ? "hour" : "day"}: ${longTick(r.peak, d.bucket)}, with ${num(r.peakActive)} active people.` });
  if (r.checkoutConversion !== null && r.checkoutConversion < 60) {
    const left = d.plans.checkoutsStarted - d.plans.checkoutsPaid;
    out.push({ tone: "warn", text: `${left} checkout${left === 1 ? "" : "s"} started but not paid (${r.checkoutConversion}% paid). Worth a reminder email or an offer code.` });
  }
  const top = [...d.money.aiBreakdown].sort((a, b) => b.cost - a.cost)[0];
  if (top?.cost && d.money.aiCost) out.push({ tone: "info", text: `${top.label} is the biggest AI cost: ${inr(top.cost)}, ${pct(top.cost, d.money.aiCost)} of AI spend.` });
  const topic = d.asks.topics.find((t) => t.name !== "Other");
  if (topic) out.push({ tone: "info", text: `People ask most about ${topic.name.toLowerCase()} (${pct(topic.count, d.asks.total)} of questions).` });
  const sub = d.subscriptions;
  if (sub.renewalsDueCount) out.push({ tone: "warn", text: `${sub.renewalsDueCount} paid plan${sub.renewalsDueCount === 1 ? "" : "s"} run out in the next 7 days (${inr(sub.renewalsDueValue)} a month). Remind them to renew.` });
  if (sub.lapsedCount) out.push({ tone: "down", text: `${sub.lapsedCount} paid plan${sub.lapsedCount === 1 ? "" : "s"} ran out in this period without renewing.` });
  if (d.quality.satisfaction !== null) out.push({ tone: d.quality.satisfaction >= 80 ? "up" : "warn", text: `${d.quality.satisfaction}% of rated answers got a thumbs up (${d.quality.up} up, ${d.quality.down} down).` });
  if (d.health.total) out.push({ tone: "warn", text: `${d.health.total} error${d.health.total === 1 ? "" : "s"} in this period (${d.health.app} in the app, ${d.health.server} on the server).` });
  return out.slice(0, 10);
}

const TONE = {
  up: [TrendingUp, "text-emerald-600 dark:text-emerald-400"], down: [TrendingDown, "text-rose-600 dark:text-rose-400"],
  warn: [AlertTriangle, "text-amber-600 dark:text-amber-400"], info: [Lightbulb, "text-[var(--viz-1)]"],
};

function Heatmap({ heat }) {
  const max = Math.max(1, ...heat.flat());
  const total = heat.flat().reduce((a, b) => a + b, 0);
  if (!total) return <p className="py-8 text-center text-sm text-muted-foreground">Fills in as people use Krish after this update.</p>;
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[560px]">
        <div className="grid grid-cols-[36px_repeat(24,minmax(0,1fr))] gap-[2px]">
          {heat.map((row, d) => (
            <div key={d} className="contents">
              <span className="pr-1 text-[10.5px] leading-[18px] text-muted-foreground">{DAYS[d]}</span>
              {row.map((n, h) => (
                <span key={h} className="h-[18px] rounded-[3px]" title={`${DAYS[d]} ${h}:00 – ${num(n)} requests`}
                  style={{ background: n ? `color-mix(in oklab, var(--viz-1) ${12 + Math.round((n / max) * 88)}%, transparent)` : "var(--viz-grid)" }} />
              ))}
            </div>
          ))}
          <span />
          {Array.from({ length: 24 }, (_, h) => <span key={h} className="pt-1 text-center text-[9.5px] text-muted-foreground">{h % 3 === 0 ? h : ""}</span>)}
        </div>
        <div className="mt-2 flex items-center justify-end gap-1.5 text-[10.5px] text-muted-foreground">
          Fewer {[12, 34, 56, 78, 100].map((p) => <span key={p} className="h-2.5 w-4 rounded-[2px]" style={{ background: `color-mix(in oklab, var(--viz-1) ${p}%, transparent)` }} />)} More · India time
        </div>
      </div>
    </div>
  );
}

const LANG = (() => { try { return new Intl.DisplayNames(["en"], { type: "language" }); } catch { return null; } })();
const langName = (c) => { try { return LANG?.of(c) || c; } catch { return c; } };

function SectionTitle({ id, children, note }) {
  return (
    <div id={id} className="mt-8 mb-3 flex scroll-mt-16 items-baseline justify-between gap-3 border-b border-border/70 pb-2">
      <h2 className="text-sm font-bold uppercase tracking-wider">{children}</h2>
      {note && <p className="text-[11.5px] text-muted-foreground">{note}</p>}
    </div>
  );
}

function StatStrip({ children, cols = "lg:grid-cols-6", testId }) {
  return (
    <div className={`grid grid-cols-2 divide-x divide-y divide-border/60 overflow-hidden rounded-xl border border-border/80 bg-card shadow-[0_1px_2px_rgba(15,23,42,0.04)] sm:grid-cols-3 ${cols} lg:divide-y-0`} data-testid={testId}>
      {children}
    </div>
  );
}

function PeopleList({ rows, empty, right }) {
  if (!rows.length) return <p className="py-8 text-center text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y divide-border/40">
      {rows.map((p, i) => (
        <li key={i} className="flex items-center justify-between gap-3 px-4 py-2 text-[13px]">
          <div className="min-w-0"><p className="truncate font-medium">{p.name}</p><p className="truncate text-[11px] text-muted-foreground">{p.email}</p></div>
          <div className="shrink-0 text-right">{right(p)}</div>
        </li>
      ))}
    </ul>
  );
}

const SECTIONS = [["overview", "Overview"], ["money", "Money"], ["customers", "Customers"], ["usage", "Usage"], ["content", "Content"], ["quality", "Quality"], ["growth", "Growth"], ["people", "People"]];

function downloadCsv(name, rows) {
  const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export default function OwnerDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [range, setRange] = useState("24h");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [metric, setMetric] = useState("active");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState(["messages", "desc"]);
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
    const rows = term ? all.filter((p) => `${p.name} ${p.email}`.toLowerCase().includes(term)) : all;
    const [key, dir] = sort;
    const val = (p) => (key === "lastSeenAt" ? p.lastSeenAt || "" : key === "name" ? p.name.toLowerCase() : p[key]);
    return [...rows].sort((a, b) => (val(a) < val(b) ? -1 : val(a) > val(b) ? 1 : 0) * (dir === "desc" ? -1 : 1));
  }, [data, q, sort]);

  if (!user?.isOwner) return <Navigate to="/" replace />;

  const onSort = (key) => setSort(([k, d]) => [key, k === key && d === "desc" ? "asc" : "desc"]);
  const k = data?.kpis;
  const m = data?.money;
  const r = data?.ratios;
  const metricName = METRICS.find(([id]) => id === metric)[1];
  const prevKey = `prev${metric[0].toUpperCase()}${metric.slice(1)}`;
  const subs = data?.plans.subscribers;
  const subsTotal = subs ? subs.basic + subs.pro + subs.max : 0;
  const rangeLabel = RANGES.find(([id]) => id === range)[1].toLowerCase();
  const insights = data ? insightsFrom(data, range) : [];
  const aiMax = data ? Math.max(...m.aiBreakdown.map((a) => a.cost)) : 0;
  const soldMax = data ? Math.max(...data.plans.sold.map((p) => p.revenue)) : 0;
  const topicMax = data?.asks.topics[0]?.count || 0;

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background max-md:flex-col">
      <IconRail />
      <main className="owner-viz min-h-0 flex-1 overflow-y-auto bg-[var(--viz-page)]">
        <div className="mx-auto w-full max-w-[1280px] px-4 pb-14 pt-6 sm:px-6">
          <header className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5" /> Owner analytics
              </p>
              <h1 className="mt-1 text-xl font-bold tracking-tight sm:text-2xl">Business overview</h1>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground" data-testid="owner-dash-updated">
                <span className="inline-flex items-center gap-1.5"><span className="relative flex h-1.5 w-1.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-60" /><span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" /></span>Live</span>
                <span>Updated {data ? ago(data.generatedAt).toLowerCase() : "…"}</span>
                <span>·</span><span>Last {rangeLabel} vs {PREV[range]}</span>
              </p>
            </div>
            <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
              <div className="flex flex-1 rounded-lg border border-border bg-card p-0.5 sm:flex-none" role="tablist" data-testid="owner-dash-range">
                {RANGES.map(([id, label, short]) => (
                  <button key={id} type="button" role="tab" aria-selected={range === id} onClick={() => setRange(id)}
                    className={`flex-1 rounded-md px-2.5 py-1.5 text-xs font-semibold transition-colors sm:flex-none ${range === id ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}>
                    <span className="lg:hidden">{short}</span><span className="max-lg:hidden">{label}</span>
                  </button>
                ))}
              </div>
              <Button variant="outline" size="sm" className="h-8" onClick={() => navigate("/admin/users")} data-testid="owner-dash-all-users">
                <Users className="mr-1.5 h-3.5 w-3.5" /> Users & problems
              </Button>
            </div>
          </header>

          <nav className="sticky top-0 z-10 -mx-4 mt-4 flex gap-1 overflow-x-auto border-b border-border/70 bg-[var(--viz-page)]/95 px-4 py-2 backdrop-blur sm:-mx-6 sm:px-6" data-testid="owner-dash-sections">
            {SECTIONS.map(([id, label]) => (
              <a key={id} href={`#${id}`} onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); }}
                className="shrink-0 rounded-md px-2.5 py-1 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground">{label}</a>
            ))}
          </nav>

          {error && !data ? <p className="mt-10 text-center text-sm text-destructive">{error}</p> : !data ? (
            <div className="flex justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : (
            <>
              <div id="overview" className="mt-5 grid scroll-mt-16 grid-cols-2 gap-3 lg:grid-cols-4" data-testid="owner-dash-kpis">
                <Kpi label="Revenue" value={inr(k.revenue.value)} kpi={k.revenue} series={data.series} k="revenue" foot={`${inr(k.revenue.prev)} in the ${PREV[range]}`} />
                <Kpi label="Profit (est.)" value={inr(k.profit.value)} kpi={k.profit} series={data.series.map((s) => ({ ...s, profit: s.revenue - s.cost }))} k="profit"
                  foot={r.margin !== null ? `${r.margin}% margin · costs ${inr(m.revenue - m.profit)}` : `Costs ${inr(m.revenue - m.profit)}`} />
                <Kpi label="Active people" value={num(k.activeUsers.value)} kpi={k.activeUsers} series={data.series} k="active" foot={`${num(k.onlineNow)} online now · ${num(k.totalUsers)} accounts`} />
                <Kpi label="Messages" value={num(k.messages.value)} kpi={k.messages} series={data.series} k="messages" foot={`${r.messagesPerActive} per active person`} />
              </div>

              <div className="mt-3 grid grid-cols-2 divide-x divide-y divide-border/60 overflow-hidden rounded-xl border border-border/80 bg-card shadow-[0_1px_2px_rgba(15,23,42,0.04)] sm:grid-cols-4 lg:grid-cols-8 lg:divide-y-0 [&>*:nth-child(2n+1)]:max-sm:border-l-0" data-testid="owner-dash-stats">
                <Stat label="Sign-ins" value={num(k.logins.value)} kpi={k.logins} />
                <Stat label="New sign-ups" value={num(k.signups.value)} kpi={k.signups} />
                <Stat label="Paying people" value={num(k.paidUsers)} hint="People on Pro or Max right now" />
                <Stat label="Monthly recurring" value={inr(k.mrr)} hint="Pro and Max plans running now × their monthly price" />
                <Stat label="Revenue / active" value={inr(r.arpu, 2)} hint="Revenue divided by active people (ARPU)" />
                <Stat label="Cost / active" value={inr(r.costPerActive, 2)} hint="AI and hosting cost divided by active people" />
                <Stat label="Checkout → paid" value={r.checkoutConversion === null ? "–" : `${r.checkoutConversion}%`} hint="Payments finished out of checkouts started" />
                <Stat label="Came back" value={r.retention === null ? "–" : `${r.retention}%`} hint={`People active in the ${PREV[range]} who were active again`} />
              </div>

              <Panel className="mt-3" title="Key insights" subtitle="Worked out from the numbers below" testId="owner-dash-insights">
                <ul className="grid gap-x-6 gap-y-2.5 md:grid-cols-2">
                  {insights.map((it, i) => {
                    const [Icon, cls] = TONE[it.tone];
                    return <li key={i} className="flex gap-2.5 text-[13px] leading-snug"><Icon className={`mt-0.5 h-4 w-4 shrink-0 ${cls}`} /><span>{it.text}</span></li>;
                  })}
                </ul>
              </Panel>

              <SectionTitle id="money" note={`Last ${rangeLabel}`}>Trends and money</SectionTitle>
              <div className="grid gap-3 lg:grid-cols-3">
                <Panel className="lg:col-span-2" title={`${metricName} over time`} subtitle={`${data.bucket === "hour" ? "Each hour" : "Each day (India time)"}, compared with the ${PREV[range]}`}
                  testId="owner-dash-activity"
                  action={
                    <div className="flex max-w-full gap-0.5 overflow-x-auto rounded-lg border border-border p-0.5">
                      {METRICS.map(([id, label]) => (
                        <button key={id} type="button" onClick={() => setMetric(id)}
                          className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold ${metric === id ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}>{label}</button>
                      ))}
                    </div>
                  }>
                  <div className="mb-2 flex gap-4 text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-[var(--viz-1)]" />This period</span>
                    <span className="flex items-center gap-1.5"><span className="h-0 w-4 border-t-2 border-dashed border-[var(--viz-axis)]" />{PREV[range][0].toUpperCase() + PREV[range].slice(1)}</span>
                  </div>
                  <div className="h-60">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={data.series} margin={{ top: 6, right: 6, left: -12, bottom: 0 }}>
                        <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
                        <XAxis dataKey="t" tickFormatter={(t) => tick(t, data.bucket)} tick={{ fontSize: 11, fill: "var(--viz-axis)" }} tickLine={false} axisLine={{ stroke: "var(--viz-grid)" }} minTickGap={28} />
                        <YAxis allowDecimals={false} tickFormatter={(v) => (metric === "revenue" ? `₹${v}` : v)} tick={{ fontSize: 11, fill: "var(--viz-axis)" }} tickLine={false} axisLine={false} width={46} />
                        <Tooltip content={<ChartTip bucket={data.bucket} money={metric === "revenue"} rows={[[metric, "This period", "bg-[var(--viz-1)]"], [prevKey, "Before", "bg-[var(--viz-axis)]"]]} />} cursor={{ stroke: "var(--viz-axis)", strokeDasharray: "3 3" }} />
                        <Line type="linear" dataKey={prevKey} stroke="var(--viz-axis)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} activeDot={false} isAnimationActive={false} />
                        <Line type="linear" dataKey={metric} stroke="var(--viz-1)" strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--viz-surface)" }} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>

                <Panel title="Profit and loss" subtitle={`Last ${rangeLabel}`} testId="owner-dash-profit" flush
                  action={<Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setEditCosts((v) => !v)}><Pencil className="mr-1 h-3.5 w-3.5" /> Edit costs</Button>}>
                  <table className="w-full text-[13px] tabular-nums">
                    <thead><tr className="border-b border-border/60"><Th>Line</Th><Th right>Amount</Th><Th right>% of rev.</Th></tr></thead>
                    <tbody>
                      {[["Revenue", m.revenue, true], ["Razorpay fees", -m.paymentFees], ["Hosting", -m.hostingCost], ["AI requests", -m.aiCost]].map(([label, v, bold]) => (
                        <tr key={label} className="border-b border-border/40">
                          <td className={`px-4 py-2 ${bold ? "font-semibold" : "text-muted-foreground"}`}>{label}</td>
                          <td className={`px-4 py-2 text-right ${bold ? "font-semibold" : ""}`}>{inr(v, 2)}</td>
                          <td className="px-4 py-2 text-right text-muted-foreground">{m.revenue ? `${Math.round((Math.abs(v) / m.revenue) * 100)}%` : "–"}</td>
                        </tr>
                      ))}
                      <tr>
                        <td className="px-4 py-2.5 font-bold">Profit</td>
                        <td className={`px-4 py-2.5 text-right font-bold ${m.profit < 0 ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"}`}>{inr(m.profit, 2)}</td>
                        <td className="px-4 py-2.5 text-right font-semibold">{r.margin === null ? "–" : `${r.margin}%`}</td>
                      </tr>
                    </tbody>
                  </table>
                  <div className="h-28 px-2 pb-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={data.series} margin={{ top: 8, right: 4, left: 4, bottom: 0 }} barGap={1}>
                        <XAxis dataKey="t" hide />
                        <Tooltip content={<ChartTip bucket={data.bucket} money rows={[["revenue", "Revenue", "bg-[var(--viz-1)]"], ["cost", "Costs", "bg-[var(--viz-2)]"]]} />} cursor={{ fill: "var(--viz-grid)" }} />
                        <Bar dataKey="revenue" fill="var(--viz-1)" radius={[2, 2, 0, 0]} maxBarSize={10} isAnimationActive={false} />
                        <Bar dataKey="cost" fill="var(--viz-2)" radius={[2, 2, 0, 0]} maxBarSize={10} isAnimationActive={false} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex gap-4 px-4 pb-3 text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[var(--viz-1)]" />Revenue</span>
                    <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[var(--viz-2)]" />Costs</span>
                    <span className="ml-auto">Costs are estimates</span>
                  </div>
                  {editCosts && <CostsForm costs={data.costs} onClose={() => setEditCosts(false)} onSaved={() => { setEditCosts(false); load(); }} />}
                </Panel>
              </div>

              <SectionTitle id="customers" note="Plans, payments and renewals">Customers</SectionTitle>
              <StatStrip testId="owner-dash-customers">
                <Stat label="New customers" value={num(data.subscriptions.newCustomers)} hint="First payment ever in this period" />
                <Stat label="Repeat customers" value={num(data.subscriptions.returningCustomers)} hint="Paid before, and paid again in this period" />
                <Stat label="Customers ever" value={num(data.subscriptions.customersEver)} />
                <Stat label="Lifetime revenue" value={inr(data.subscriptions.lifetimeRevenue)} />
                <Stat label="Lifetime value" value={inr(data.subscriptions.ltv)} hint="Lifetime revenue per paying customer (LTV)" />
                <Stat label="Due in 7 days" value={inr(data.subscriptions.renewalsDueValue)} hint="Monthly value of paid plans that run out in the next 7 days" />
              </StatStrip>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <Panel title="Plans" subtitle="Sales in this period and people on each plan now" testId="owner-dash-plans" flush>
                  <table className="w-full text-[13px] tabular-nums">
                    <thead><tr className="border-b border-border/60"><Th>Plan</Th><Th right>Price</Th><Th right>Sold</Th><Th right>Revenue</Th><Th right>On plan now</Th></tr></thead>
                    <tbody>
                      {["basic", ...data.plans.sold.map((p) => p.plan)].map((plan) => {
                        const s = data.plans.sold.find((p) => p.plan === plan);
                        return (
                          <tr key={plan} className="border-b border-border/40 last:border-0">
                            <td className="px-4 py-2.5"><span className="flex items-center gap-2 font-medium"><span className={`h-2 w-2 rounded-full ${PLAN_STYLE[plan].dot}`} />{PLAN_STYLE[plan].label}</span>
                              {s && <div className="mt-1.5 w-24"><ShareBar value={s.revenue} max={soldMax} color={PLAN_STYLE[plan].dot} /></div>}</td>
                            <td className="px-4 py-2.5 text-right text-muted-foreground">{s ? inr(s.price) : "Free"}</td>
                            <td className="px-4 py-2.5 text-right">{s ? num(s.count) : "–"}</td>
                            <td className="px-4 py-2.5 text-right font-semibold">{s ? inr(s.revenue) : "–"}</td>
                            <td className="px-4 py-2.5 text-right">{num(subs[plan])} <span className="text-muted-foreground">({pct(subs[plan], subsTotal)})</span></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <div className="grid grid-cols-3 divide-x divide-border/60 border-t border-border/60">
                    <Stat label="Checkouts started" value={num(data.plans.checkoutsStarted)} />
                    <Stat label="Paid" value={num(data.plans.checkoutsPaid)} />
                    <Stat label="Average order" value={inr(r.avgOrder)} />
                  </div>
                </Panel>

                <Panel title="Latest payments" subtitle="Through Razorpay" testId="owner-dash-payments" flush>
                  {!data.plans.recentPayments.length ? <p className="py-10 text-center text-sm text-muted-foreground">No payments in this period yet.</p> : (
                    <table className="w-full text-[13px] tabular-nums">
                      <thead><tr className="border-b border-border/60"><Th>Customer</Th><Th>Plan</Th><Th right>Amount</Th><Th right>When</Th></tr></thead>
                      <tbody>
                        {data.plans.recentPayments.slice(0, 7).map((p, i) => (
                          <tr key={i} className="border-b border-border/40 last:border-0">
                            <td className="max-w-[180px] px-4 py-2"><p className="truncate font-medium">{p.name}</p><p className="truncate text-[11px] text-muted-foreground">{p.email}</p></td>
                            <td className="px-4 py-2"><PlanTag plan={p.plan} />{p.promoCode && <p className="text-[10.5px] text-muted-foreground">{p.promoCode}</p>}</td>
                            <td className="px-4 py-2 text-right font-semibold">{inr(p.amount)}</td>
                            <td className="whitespace-nowrap px-4 py-2 text-right text-muted-foreground">{ago(p.at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Panel>
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <Panel title="Renewals due" subtitle={`${num(data.subscriptions.renewalsDueCount)} paid plans run out in the next 7 days`} testId="owner-dash-renewals" flush>
                  <PeopleList rows={data.subscriptions.renewalsDue} empty="No paid plans run out in the next 7 days."
                    right={(p) => <><PlanTag plan={p.plan} /><p className="text-[11px] text-muted-foreground">{new Date(p.expiresAt).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</p></>} />
                </Panel>
                <Panel title="Plans that ran out" subtitle={`${num(data.subscriptions.lapsedCount)} in this period, not renewed`} testId="owner-dash-lapsed" flush>
                  <PeopleList rows={data.subscriptions.lapsed} empty="No paid plans ran out in this period."
                    right={(p) => <><PlanTag plan={p.plan} /><p className="text-[11px] text-muted-foreground">{ago(p.expiresAt)}</p></>} />
                </Panel>
              </div>

              <SectionTitle id="usage" note="Engagement, timing and what people use">Usage</SectionTitle>
              <StatStrip testId="owner-dash-engagement">
                <Stat label="Active today" value={num(data.engagement.dau)} hint="Daily active people (DAU), India time" />
                <Stat label="Active this week" value={num(data.engagement.wau)} hint="Weekly active people (WAU), last 7 days" />
                <Stat label="Active this month" value={num(data.engagement.mau)} hint="Monthly active people (MAU), last 30 days" />
                <Stat label="Average per day" value={num(data.engagement.avgDau)} hint="Average daily active people over 30 days" />
                <Stat label="Stickiness" value={data.engagement.stickiness === null ? "–" : `${data.engagement.stickiness}%`} hint="Today's active people out of this month's (DAU / MAU)" />
                <Stat label="Sign-ins per person" value={num(data.engagement.signinsPerPerson)} hint="Average sign-ins per account, all time" />
              </StatStrip>
              <div className="mt-3 grid gap-3 lg:grid-cols-5">
                <Panel className="lg:col-span-3" title="When people use Krish" subtitle="Requests by weekday and hour, in this period" testId="owner-dash-heatmap">
                  <Heatmap heat={data.heat} />
                </Panel>
                <Panel className="lg:col-span-2" title="Audience" subtitle="Who the active people are" testId="owner-dash-audience">
                  {[["New this period", r.newActive], ["Returning", r.returningActive]].map(([label, v]) => (
                    <div key={label} className="mb-3">
                      <div className="mb-1 flex justify-between text-[13px]"><span>{label}</span><span className="tabular-nums text-muted-foreground">{num(v)} · {pct(v, k.activeUsers.value)}</span></div>
                      <ShareBar value={v} max={k.activeUsers.value} />
                    </div>
                  ))}
                  <div className="mb-3">
                    <div className="mb-1 flex justify-between text-[13px]"><span>On a paid plan</span><span className="tabular-nums text-muted-foreground">{r.payingShare}%</span></div>
                    <ShareBar value={r.payingShare} max={100} color="bg-[var(--viz-2)]" />
                  </div>
                  <p className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Accounts by plan</p>
                  <div className="flex h-2 gap-0.5 overflow-hidden rounded-full">
                    {["basic", "pro", "max"].map((p) => subs[p] ? <div key={p} className={PLAN_STYLE[p].dot} style={{ width: `${(subs[p] / subsTotal) * 100}%`, minWidth: 3 }} /> : null)}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 text-[11.5px] text-muted-foreground">
                    {["basic", "pro", "max"].map((p) => <span key={p} className="flex items-center gap-1.5"><span className={`h-2 w-2 rounded-full ${PLAN_STYLE[p].dot}`} />{PLAN_STYLE[p].label} {num(subs[p])}</span>)}
                  </div>
                </Panel>
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <Panel title="Feature use and AI cost" subtitle="Requests in this period and what they cost" testId="owner-dash-features" flush>
                  <table className="w-full text-[13px] tabular-nums">
                    <thead><tr className="border-b border-border/60"><Th>Feature</Th><Th right>Requests</Th><Th right>Cost</Th><Th right>Share</Th></tr></thead>
                    <tbody>
                      {[...m.aiBreakdown].sort((a, b) => b.cost - a.cost || b.count - a.count).map((a) => (
                        <tr key={a.kind} className="border-b border-border/40 last:border-0">
                          <td className="px-4 py-2"><p>{a.label}</p><div className="mt-1 w-28"><ShareBar value={a.cost} max={aiMax} /></div></td>
                          <td className="px-4 py-2 text-right">{num(a.count)}</td>
                          <td className="px-4 py-2 text-right">{inr(a.cost, 2)}</td>
                          <td className="px-4 py-2 text-right text-muted-foreground">{pct(a.cost, m.aiCost)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Panel>

                <Panel title="What people ask about" subtitle={`${num(data.asks.total)} questions by topic. Counsellor chats are private and never included.`} testId="owner-dash-asks" flush
                  action={<Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => setShowAsks((v) => !v)} data-testid="owner-dash-show-asks">
                    {showAsks ? <EyeOff className="mr-1 h-3.5 w-3.5" /> : <Eye className="mr-1 h-3.5 w-3.5" />}{showAsks ? "Hide questions" : "Latest questions"}
                  </Button>}>
                  {!data.asks.total ? <p className="py-10 text-center text-sm text-muted-foreground">No questions in this period yet.</p> : (
                    <>
                      <table className="w-full text-[13px] tabular-nums">
                        <thead><tr className="border-b border-border/60"><Th>Topic</Th><Th right>Questions</Th><Th right>Share</Th></tr></thead>
                        <tbody>
                          {data.asks.topics.slice(0, 8).map((t) => (
                            <tr key={t.name} className="border-b border-border/40 last:border-0">
                              <td className="px-4 py-2"><p>{t.name}</p><div className="mt-1 w-28"><ShareBar value={t.count} max={topicMax} /></div></td>
                              <td className="px-4 py-2 text-right">{num(t.count)}</td>
                              <td className="px-4 py-2 text-right text-muted-foreground">{pct(t.count, data.asks.total)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {!!data.asks.words.length && (
                        <div className="border-t border-border/60 px-4 py-3">
                          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Most used words</p>
                          <div className="flex flex-wrap gap-1.5">
                            {data.asks.words.map((w) => <span key={w.word} className="rounded border border-border/70 px-2 py-0.5 text-xs">{w.word} <span className="tabular-nums text-muted-foreground">{w.count}</span></span>)}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                  {showAsks && (
                    <ul className="max-h-80 divide-y divide-border/50 overflow-y-auto border-t border-border/60" data-testid="owner-dash-recent-asks">
                      {data.asks.recent.map((a, i) => (
                        <li key={i} className="px-4 py-2.5 text-[13px]">
                          <p className="flex flex-wrap gap-x-2 text-[11px] text-muted-foreground"><span className="font-semibold text-foreground">{a.name}</span>{a.topic} · {a.where} · {ago(a.at)}</p>
                          <p className="mt-0.5 break-words">{a.text}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
              </div>

              <SectionTitle id="content" note="Everything people made with Krish">Content</SectionTitle>
              <Panel title="Content created" subtitle={`In the last ${rangeLabel}, and all time`} testId="owner-dash-content" flush>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[480px] text-[13px] tabular-nums">
                    <thead><tr className="border-b border-border/60"><Th>Type</Th><Th right>This period</Th><Th right>Change</Th><Th right>All time</Th></tr></thead>
                    <tbody>
                      {data.content.map((c) => (
                        <tr key={c.key} className="border-b border-border/40 last:border-0">
                          <td className="px-4 py-2">{c.label}</td>
                          <td className="px-4 py-2 text-right font-semibold">{num(c.period)}</td>
                          <td className="px-4 py-2 text-right"><Delta value={c.period} prev={c.prev} small /></td>
                          <td className="px-4 py-2 text-right text-muted-foreground">{num(c.total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>

              <SectionTitle id="quality" note="Answer ratings and errors">Quality and health</SectionTitle>
              <div className="grid gap-3 lg:grid-cols-2">
                <Panel title="Answer ratings" subtitle="Thumbs up and down on Krish's answers" testId="owner-dash-quality" flush>
                  <div className="grid grid-cols-3 divide-x divide-border/60 border-b border-border/60">
                    <Stat label="Satisfaction" value={data.quality.satisfaction === null ? "–" : `${data.quality.satisfaction}%`} hint="Thumbs up out of all ratings" />
                    <Stat label="Thumbs up" value={num(data.quality.up)} kpi={{ value: data.quality.up, prev: data.quality.prevUp }} />
                    <Stat label="Thumbs down" value={num(data.quality.down)} kpi={{ value: data.quality.down, prev: data.quality.prevDown }} invert />
                  </div>
                  {!data.quality.disliked.length ? <p className="py-8 text-center text-sm text-muted-foreground">No answers marked thumbs down in this period.</p> : (
                    <ul className="max-h-80 divide-y divide-border/40 overflow-y-auto">
                      {data.quality.disliked.map((f, i) => (
                        <li key={i} className="px-4 py-2.5 text-[13px]">
                          <p className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground"><ThumbsDown className="h-3 w-3 text-rose-500" /><span className="font-semibold text-foreground">{f.name}</span>{f.model ? `${f.model} · ` : ""}{ago(f.at)}</p>
                          <p className="mt-0.5 font-medium">{f.question || "(question not found)"}</p>
                          <p className="mt-0.5 line-clamp-2 text-muted-foreground">{f.answer}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
                <Panel title="App health" subtitle="Crashes in the app and errors on the server" testId="owner-dash-health" flush>
                  <div className="grid grid-cols-3 divide-x divide-border/60 border-b border-border/60">
                    <Stat label="Errors" value={num(data.health.total)} kpi={{ value: data.health.total, prev: data.health.prev }} invert />
                    <Stat label="In the app" value={num(data.health.app)} />
                    <Stat label="On the server" value={num(data.health.server)} />
                  </div>
                  {!data.health.common.length ? <p className="py-8 text-center text-sm text-muted-foreground">No errors in this period.</p> : (
                    <table className="w-full text-[13px] tabular-nums">
                      <thead><tr className="border-b border-border/60"><Th>Most common</Th><Th right>Times</Th></tr></thead>
                      <tbody>
                        {data.health.common.map((e, i) => (
                          <tr key={i} className="border-b border-border/40 last:border-0">
                            <td className="max-w-0 truncate px-4 py-2 font-mono text-xs" title={e.message}>{e.message || "(no message)"}</td>
                            <td className="px-4 py-2 text-right">{num(e.count)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Panel>
              </div>

              <SectionTitle id="growth" note="Invites, offer codes, sign-up methods and languages">Growth</SectionTitle>
              <StatStrip cols="lg:grid-cols-4" testId="owner-dash-growth">
                <Stat label="Friends invited" value={num(data.growth.invited)} hint="People who joined from an invite link in this period" />
                <Stat label="Invites rewarded" value={num(data.growth.invitedRewarded)} />
                <Stat label="Sign-ups with Google" value={pct(data.growth.signupMethods.google, data.growth.signupMethods.google + data.growth.signupMethods.email)} hint="New accounts in this period made with Google" />
                <Stat label="Accounts with Google" value={pct(data.growth.accountMethods.google, k.totalUsers)} hint="All accounts that sign in with Google" />
              </StatStrip>
              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                <Panel title="Offer codes" subtitle="Uses so far" testId="owner-dash-codes" flush>
                  {!data.growth.codes.length ? <p className="py-8 text-center text-sm text-muted-foreground">No offer codes yet.</p> : (
                    <table className="w-full text-[13px] tabular-nums">
                      <thead><tr className="border-b border-border/60"><Th>Code</Th><Th right>Off</Th><Th right>Used</Th></tr></thead>
                      <tbody>
                        {data.growth.codes.map((c) => (
                          <tr key={c.code} className={`border-b border-border/40 last:border-0 ${c.active ? "" : "text-muted-foreground"}`}>
                            <td className="px-4 py-2 font-mono text-xs font-semibold">{c.code}{!c.active && " (off)"}</td>
                            <td className="px-4 py-2 text-right">{c.percentOff}%</td>
                            <td className="px-4 py-2 text-right">{num(c.uses)}{c.maxUses ? ` / ${num(c.maxUses)}` : ""}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Panel>
                <Panel title="Top inviters" subtitle="Friends who joined in this period" testId="owner-dash-inviters" flush>
                  <PeopleList rows={data.growth.topInviters} empty="No one joined from an invite in this period."
                    right={(p) => <span className="font-semibold tabular-nums">{num(p.count)}</span>} />
                </Panel>
                <Panel title="Languages" subtitle="App language of all accounts" testId="owner-dash-languages">
                  {data.growth.languages.map((l) => (
                    <div key={l.code} className="mb-2.5">
                      <div className="mb-1 flex justify-between text-[13px]"><span>{langName(l.code)}</span><span className="tabular-nums text-muted-foreground">{num(l.count)} · {pct(l.count, k.totalUsers)}</span></div>
                      <ShareBar value={l.count} max={data.growth.languages[0].count} />
                    </div>
                  ))}
                </Panel>
              </div>

              <SectionTitle id="people" note="Everyone active or paying in this period">People</SectionTitle>
              <Panel title="Use per person" subtitle={`${num(people.length)} people active or paying in this period. Tap a column to sort.`} testId="owner-dash-people" flush
                action={
                  <div className="flex w-full items-center gap-2 sm:w-auto">
                    <div className="relative flex-1 sm:w-56 sm:flex-none"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or email" className="h-8 pl-8 text-xs" /></div>
                    <Button variant="outline" size="sm" className="h-8 px-2.5 text-xs" data-testid="owner-dash-export"
                      onClick={() => downloadCsv(`krish-people-${range}.csv`, [["Name", "Email", "Plan", "Messages", "App builds", "Pictures/decks/videos", "AI cost (INR)", "Paid (INR)", "Last active"],
                        ...people.map((p) => [p.name, p.email, p.plan, p.messages, p.builds, p.made, p.cost, p.paid, p.lastSeenAt])])}>
                      <Download className="mr-1 h-3.5 w-3.5" /> CSV
                    </Button>
                  </div>
                }>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-[13px] tabular-nums">
                    <thead className="border-b border-border/60">
                      <tr>
                        {[["name", "Person"], ["messages", "Messages", 1], ["builds", "App builds", 1], ["made", "Media made", 1], ["cost", "AI cost", 1], ["paid", "Paid", 1], ["lastSeenAt", "Last active"]].map(([key, label, right]) => (
                          <Th key={key} right={right} sort={key} onSort={onSort} active={sort[0] === key} dir={sort[1]}>{label}</Th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {people.slice(0, 50).map((p) => (
                        <tr key={p.userId} className="border-b border-border/40 last:border-0 hover:bg-muted/40">
                          <td className="px-4 py-2">
                            <p className="flex items-center gap-2 font-medium">{p.name}{p.online && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" title="Online now" />}</p>
                            <p className="flex items-center gap-2 text-[11px] text-muted-foreground">{p.email}<PlanTag plan={p.plan} /></p>
                          </td>
                          <td className="px-4 py-2 text-right">{num(p.messages)}</td>
                          <td className="px-4 py-2 text-right">{num(p.builds)}</td>
                          <td className="px-4 py-2 text-right">{num(p.made)}</td>
                          <td className="px-4 py-2 text-right text-muted-foreground">{inr(p.cost, 2)}</td>
                          <td className="px-4 py-2 text-right font-semibold">{p.paid ? inr(p.paid) : "–"}</td>
                          <td className="whitespace-nowrap px-4 py-2 text-muted-foreground">{ago(p.lastSeenAt)}</td>
                        </tr>
                      ))}
                      {!people.length && <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">{q ? "No one matches that search." : "No one used Krish in this period yet."}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </Panel>

              <Panel className="mt-3" title="Sign-in log" subtitle="Latest first" testId="owner-dash-logins" flush>
                {!data.logins.length ? <p className="py-8 text-center text-sm text-muted-foreground">No sign-ins in this period.</p> : (
                  <div className="max-h-96 overflow-auto">
                    <table className="w-full min-w-[520px] text-[13px]">
                      <thead className="sticky top-0 border-b border-border/60 bg-card"><tr><Th>Person</Th><Th>Method</Th><Th>Plan</Th><Th right>Time</Th></tr></thead>
                      <tbody>
                        {data.logins.slice(0, 50).map((x, i) => (
                          <tr key={i} className="border-b border-border/40 last:border-0">
                            <td className="px-4 py-2"><p className="font-medium">{x.name}</p><p className="text-[11px] text-muted-foreground">{x.email}</p></td>
                            <td className="px-4 py-2 text-muted-foreground">{METHOD[x.method] ?? "Sign-in"}</td>
                            <td className="px-4 py-2"><PlanTag plan={x.plan} /></td>
                            <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums text-muted-foreground" title={new Date(x.at).toLocaleString()}>
                              {new Date(x.at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>
              <p className="mt-4 flex items-start gap-1.5 text-[11.5px] text-muted-foreground"><Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />Hour-by-hour use, the sign-in log, the usage heatmap and use per person count from this update on. Revenue, sign-ups and daily numbers include everything before it.</p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
