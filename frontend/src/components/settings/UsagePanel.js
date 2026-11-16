import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { PageTitle } from "@/components/SettingsDialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { api, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import {
  ArrowUpRight, Bot, CalendarDays, Check, Clock, Crown, FileText, Film, Image as ImageIcon, Info, Loader2,
  MessageCircle, MessagesSquare, PauseCircle, Presentation, ShieldCheck, Sparkles, Wand2, X,
} from "lucide-react";

// The Usage page: one meter that follows how heavy each request really is (the tokens the AI reads and writes),
// shown as a share of the plan's session and week, with what this session went on and what things use.

const KINDS = {
  chat: { label: "Chat", dot: "bg-indigo-500" },
  build: { label: "App builds", dot: "bg-violet-500" },
  picture: { label: "Pictures", dot: "bg-fuchsia-500" },
  deck: { label: "Slide decks", dot: "bg-amber-500" },
  video: { label: "Videos", dot: "bg-sky-500" },
};
const PLAN_NAME = { basic: "Basic", pro: "Pro", max: "Max" };

const pctOf = (n, limit) => (limit ? (n / limit) * 100 : 0);
const fmtPct = (p) => (p <= 0 ? "0%" : p < 1 ? "<1%" : `${Math.round(p)}%`);
const fmtTokens = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : `${n}`);

function useNow(ms = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return now;
}

function left(resetsAt, now) {
  const s = Math.max(0, resetsAt * 1000 - now) / 1000;
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.max(1, Math.floor((s % 3600) / 60));
  if (d) return `${d} day${d > 1 ? "s" : ""}${h ? ` ${h} hr` : ""}`;
  if (h) return `${h} hr ${m} min`;
  return `${m} min`;
}

const atTime = (ts, withDay) => new Date(ts * 1000).toLocaleString(undefined, withDay
  ? { weekday: "short", hour: "numeric", minute: "2-digit" } : { hour: "numeric", minute: "2-digit" });

/** A small "i" that explains on hover, and on tap on a phone. */
export function Tip({ children, testid, label = "What's this?" }) {
  const [open, setOpen] = useState(false);
  return (
    <TooltipPrimitive.Provider delayDuration={120}>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <button type="button" aria-label={label} data-testid={testid}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((o) => !o); }}
            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-muted-foreground/70 transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40">
            <Info className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" align="center" collisionPadding={12}
          className="max-w-[272px] rounded-xl border border-border bg-popover px-3.5 py-2.5 text-[12.5px] leading-relaxed text-popover-foreground shadow-xl">
          {children}
        </TooltipContent>
      </Tooltip>
    </TooltipPrimitive.Provider>
  );
}

function Bar({ pct, tall, tone, calm }) {
  const warn = calm ? null : pct >= 90 ? "bg-rose-500" : pct >= 75 ? "bg-amber-500" : null;
  return (
    <div className={`${tall ? "h-3" : "h-2"} w-full overflow-hidden rounded-full bg-muted`} role="progressbar"
      aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full rounded-full transition-[width] duration-700 ease-out ${warn || tone || "bg-gradient-to-r from-indigo-500 to-violet-500"}`}
        style={{ width: `${pct > 0 ? Math.max(Math.min(pct, 100), 1.5) : 0}%` }} />
    </div>
  );
}

/** The session bar split by what used it (chat, builds, pictures…). */
function SplitBar({ kinds, limit }) {
  const parts = Object.entries(kinds).filter(([k, v]) => KINDS[k] && v > 0).sort((a, b) => b[1] - a[1]);
  const total = parts.reduce((n, [, v]) => n + v, 0);
  const full = Math.min(100, pctOf(total, limit));
  return (
    <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={Math.round(full)}
      aria-valuemin={0} aria-valuemax={100}>
      {parts.map(([k, v]) => (
        <div key={k} className={`h-full ${KINDS[k].dot} transition-[width] duration-700 ease-out first:rounded-l-full last:rounded-r-full`}
          style={{ width: `${total ? (v / total) * Math.max(full, 1.5) : 0}%` }} title={KINDS[k].label} />
      ))}
    </div>
  );
}

function Stat({ icon: Icon, title, tip, tipId, part, now, idle, children, testid }) {
  const pct = pctOf(part.used, part.limit);
  return (
    <div className="rounded-2xl border border-border bg-card p-4" data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[13px] font-medium">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span>{title}</span>
        <Tip testid={tipId}>{tip}</Tip>
        <span className="ml-auto font-heading text-[15px] font-semibold tabular-nums">{fmtPct(pct)}</span>
      </div>
      <div className="mt-3"><Bar pct={pct} /></div>
      <p className="mt-2 text-[12px] text-muted-foreground">
        {part.resetsAt ? <>Resets in <b className="font-medium text-foreground">{left(part.resetsAt, now)}</b> · {atTime(part.resetsAt, part.resetsAt * 1000 - now > 20 * 3600 * 1000)}</> : idle}
      </p>
      {children}
    </div>
  );
}

function costRows(data) {
  const { costs } = data;
  const rows = [];
  if (costs.basicChat) {
    rows.push(
      { icon: MessageCircle, label: "A quick question", credits: costs.basicChat[0], tip: "A short question and answer reads and writes about 3,000 tokens, so it uses a sliver." },
      { icon: MessagesSquare, label: "A long chat", credits: costs.basicChat[1], tip: "Each reply in a long chat re-reads what came before, so later messages weigh a little more." },
      { icon: FileText, label: "A chat about a file", credits: costs.basicChat[2], tip: "Reading a PDF or a long document is heavy work. Big files use more than small ones." },
    );
  } else {
    rows.push(
      { icon: MessageCircle, label: "Chat on Krish Basic", free: true, tip: "On your plan, chat on Krish Basic is never counted. Chat as much as you like." },
      { icon: Sparkles, label: "A Krish Pro answer", range: costs.chat, tip: "Premium answers use what they really cost: quick ones on a light model use little, deep Think answers more." },
    );
  }
  rows.push(
    { icon: Wand2, label: "An app build", range: costs.buildRange || costs.build, tip: "Counted by the tokens the build really takes. A small change uses a little, a whole new app much more." },
    { icon: ImageIcon, label: "A picture", credits: costs.picture, tip: "Each picture uses the same amount, whatever you ask for." },
    { icon: Presentation, label: "A slide deck", credits: costs.deck, extra: " + pictures", tip: "The deck itself, plus one picture for each slide that has one." },
  );
  if (data.video) rows.push({ icon: Film, label: "A video", credits: costs.videoSecond, extra: " a second", tip: "Videos use the meter by their length, so a 4 second clip uses half of an 8 second one." });
  return rows;
}

function CostRow({ row, limit }) {
  const lo = row.range ? pctOf(row.range[0], limit) : pctOf(row.credits || 0, limit);
  const hi = row.range ? pctOf(row.range[1], limit) : lo;
  const text = row.free ? "Free" : fmtPct(lo) === fmtPct(hi) ? fmtPct(lo)
    : lo < 1 ? `up to ${fmtPct(hi)}` : `${fmtPct(lo)}–${fmtPct(hi)}`;
  const Icon = row.icon;
  return (
    <li className="flex items-center gap-3 py-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface text-muted-foreground"><Icon className="h-4 w-4" /></span>
      <span className="flex min-w-0 flex-1 items-center gap-1 text-[13.5px]">{row.label}<Tip>{row.tip}</Tip></span>
      <span className="hidden w-24 sm:block">
        <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
          <span className={`block h-full rounded-full ${row.free ? "bg-emerald-500" : "bg-indigo-500/70"}`}
            style={{ width: `${row.free ? 100 : Math.max(4, Math.min(100, hi))}%`, opacity: row.free ? 0.5 : 1 }} />
        </span>
      </span>
      <span className={`w-[92px] shrink-0 text-right text-[13px] tabular-nums ${row.free ? "font-medium text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}>
        {text}{!row.free && <span className="text-[11px]">{row.extra || ""}</span>}
      </span>
    </li>
  );
}

function PlanStrip({ data, onPlans }) {
  const basic = data.plans.find((p) => p.id === "basic");
  const rows = [
    ["Usage each session", (p) => (p.id === "basic" ? "1x" : `${Math.round(p.meter.session / basic.meter.session)}x`)],
    ["Chat on Krish Basic", (p) => (p.id === "basic" ? "Counted" : "Unlimited")],
    ["Krish Pro answers", (p) => (p.premium ? "Yes" : "A taste")],
    ["Automations", (p) => `${p.total.automation}`],
    ["Publish apps", (p) => (p.publish ? <Check className="ml-auto h-4 w-4 text-emerald-500 sm:mx-auto" /> : <X className="ml-auto h-4 w-4 text-muted-foreground/50 sm:mx-auto" />)],
  ];
  return (
    <div className="mt-6 overflow-hidden rounded-2xl border border-border" data-testid="usage-plans">
      <div className="grid grid-cols-[1.3fr_repeat(3,1fr)] border-b border-border bg-surface/60 text-[12.5px]">
        <div className="px-3 py-2.5 font-medium text-muted-foreground sm:px-4">Plans</div>
        {data.plans.map((p) => (
          <div key={p.id} className={`px-2 py-2.5 text-right font-semibold sm:text-center ${p.id === data.plan ? "text-indigo-600 dark:text-indigo-400" : ""}`}>
            {p.name}{p.id === data.plan && <span className="ml-1 hidden rounded-full bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-medium sm:inline">You</span>}
          </div>
        ))}
      </div>
      {rows.map(([label, cell]) => (
        <div key={label} className="grid grid-cols-[1.3fr_repeat(3,1fr)] border-b border-border text-[12.5px] last:border-0">
          <div className="px-3 py-2.5 text-muted-foreground sm:px-4">{label}</div>
          {data.plans.map((p) => (
            <div key={p.id} className={`px-2 py-2.5 text-right tabular-nums sm:text-center ${p.id === data.plan ? "bg-indigo-500/[0.04] font-medium" : ""}`}>{cell(p)}</div>
          ))}
        </div>
      ))}
      {data.plan !== "max" && (
        <button type="button" onClick={onPlans} data-testid="usage-compare"
          className="flex w-full items-center justify-center gap-1.5 border-t border-border py-3 text-[13px] font-medium text-indigo-600 transition-colors hover:bg-surface dark:text-indigo-400">
          Compare plans and prices <ArrowUpRight className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

export default function UsagePanel({ onClose }) {
  const navigate = useNavigate();
  const now = useNow();
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/usage").then(({ data: d }) => setData(d)).catch((e) => { toast.error(formatApiError(e)); setData(false); }); }, []);
  if (data === null) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>;
  if (!data) return null;

  const { meter, plan } = data;
  const session = meter.session;
  const sessionPct = pctOf(session.used, session.limit);
  const kinds = Object.entries(meter.kinds || {}).filter(([k, v]) => KINDS[k] && v > 0).sort((a, b) => b[1] - a[1]);
  const plans = () => { onClose(); navigate("/plans"); };
  const paid = plan !== "basic";
  const intro = "Krish counts how much work each request takes, not how many messages you send. A quick question uses a sliver; a big app build or a long file uses more.";

  return (
    <>
      <PageTitle title="Usage" hint={intro} />
      <p className="mb-4 text-[13px] leading-relaxed text-muted-foreground sm:hidden">{intro}</p>

      {!data.limitsOn && (
        <div className="mb-4 flex items-start gap-3 rounded-2xl border border-emerald-500/25 bg-emerald-500/[0.07] px-4 py-3" data-testid="usage-paused">
          <PauseCircle className="mt-0.5 h-[18px] w-[18px] shrink-0 text-emerald-600 dark:text-emerald-400" />
          <p className="text-[13px] leading-relaxed">
            <b className="font-semibold">Limits are paused for launch.</b>{" "}
            <span className="text-muted-foreground">Nothing is refused right now. The bars show what you've used, so you know where you'd stand.</span>
          </p>
        </div>
      )}

      {/* The session: the main meter */}
      <div className={`relative overflow-hidden rounded-2xl p-5 ${paid ? "bg-gradient-to-br from-indigo-500/[0.09] via-violet-500/[0.06] to-fuchsia-500/[0.05]" : "bg-card"} border border-border`}
        data-testid="usage-session">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              {paid && <Crown className="h-3.5 w-3.5 text-violet-500" />}<span className="hidden sm:inline">Krish {PLAN_NAME[plan]} ·</span> Current session
              <Tip testid="usage-tip-session">
                Your allowance for {session.hours} hours. It starts with your first request and refills in full {session.hours} hours later.
                Everything you make (and on Basic, chat too) uses it by how heavy the work is.
              </Tip>
            </p>
            <p className="mt-2 flex items-baseline gap-2">
              <span className="font-heading text-[40px] font-semibold leading-none tracking-tight tabular-nums">{fmtPct(sessionPct)}</span>
              <span className="text-[13px] text-muted-foreground">used</span>
            </p>
          </div>
          <div className="shrink-0 rounded-xl bg-surface px-3 py-2 text-right">
            <p className="flex items-center justify-end gap-1 text-[11px] text-muted-foreground"><Clock className="h-3 w-3" /> Resets in</p>
            <p className="mt-0.5 text-[14px] font-semibold tabular-nums">{session.resetsAt ? left(session.resetsAt, now) : `${session.hours} hr`}</p>
            {session.resetsAt && <p className="text-[11px] text-muted-foreground">at {atTime(session.resetsAt)}</p>}
          </div>
        </div>
        <div className="mt-4">{kinds.length ? <SplitBar kinds={meter.kinds} limit={session.limit} /> : <Bar pct={sessionPct} tall />}</div>
        {kinds.length > 0 ? (
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[12px]" data-testid="usage-kinds">
            {kinds.map(([k, v]) => (
              <li key={k} className="flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${KINDS[k].dot}`} />
                <span>{KINDS[k].label}</span>
                <span className="tabular-nums text-muted-foreground">{fmtPct(pctOf(v, session.limit))}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-[12px] text-muted-foreground">{session.resetsAt ? "Nothing used yet this session." : "Starts with your first request."}</p>
        )}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Stat icon={CalendarDays} title="This week" part={meter.week} now={now} testid="usage-week" tipId="usage-tip-week"
          idle="Starts with your first request"
          tip={`A weekly cap on top of the sessions, so the month stays fair for everyone. It refills ${meter.week.days || 7} days after your first request of the week.`} />
        {meter.today && (
          <Stat icon={ShieldCheck} title="Daily fair use" part={meter.today} now={now} testid="usage-today" tipId="usage-tip-today"
            idle="Refills every night at 12"
            tip="A safety cap on all AI use, chat included, counted in tokens. Normal use never comes near it. It refills at midnight India time.">
            <p className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">{fmtTokens(meter.today.used)} of {fmtTokens(meter.today.limit)} tokens</p>
          </Stat>
        )}
      </div>

      {/* What things use */}
      <div className="mt-6" data-testid="usage-costs">
        <div className="flex items-center gap-1.5">
          <h3 className="text-[14px] font-semibold">What things use</h3>
          <Tip>Shown as a share of one session on your plan. Real use follows the tokens each request takes, so these are typical amounts.</Tip>
          <span className="ml-auto text-[11.5px] text-muted-foreground">of a session</span>
        </div>
        <ul className="mt-1 divide-y divide-border">
          {costRows(data).map((r) => <CostRow key={r.label} row={r} limit={session.limit} />)}
        </ul>
      </div>

      {/* Automations */}
      <div className="mt-4 flex items-center gap-3 rounded-2xl border border-border bg-card px-4 py-3" data-testid="usage-automations">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface text-muted-foreground"><Bot className="h-4 w-4" /></span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1 text-[13.5px]">Automations
            <Tip>How many automations you can keep at once. Deleting one frees a slot. Each run uses the meter like any other request.</Tip>
          </p>
          <div className="mt-1.5 max-w-[220px]"><Bar calm tone="bg-slate-400 dark:bg-slate-500" pct={pctOf(data.usage.automation.used, data.usage.automation.limit)} /></div>
        </div>
        <span className="text-[13px] tabular-nums text-muted-foreground">{data.usage.automation.used} of {data.usage.automation.limit}</span>
      </div>

      <PlanStrip data={data} onPlans={plans} />

      {plan !== "max" && (
        <Button onClick={plans} data-testid="usage-more"
          className="mt-4 h-10 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow-sm hover:opacity-95">
          <Sparkles className="mr-1.5 h-4 w-4" /> {plan === "basic" ? "Get more usage with Pro" : "Get the most usage with Max"}
        </Button>
      )}
    </>
  );
}
