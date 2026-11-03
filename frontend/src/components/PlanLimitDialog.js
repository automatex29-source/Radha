import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Clock, Gauge, Sparkles, Check } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { PLAN_LIMIT_EVENT } from "@/lib/planLimits";

function hoursLeft(ms) {
  const mins = Math.max(1, Math.ceil(ms / 60000));
  const h = Math.floor(mins / 60), m = mins % 60;
  if (!h) return `${m} min`;
  return `${h} hour${h === 1 ? "" : "s"}${m ? ` ${m} min` : ""}`;
}

function tokens(n) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`;
  if (n >= 1e3) return `${Math.round(n / 1e3)}k`;
  return String(n);
}

function Meter({ label, used, limit, perCredit, resetsAt, now }) {
  const pct = Math.min(100, Math.round((used / Math.max(1, limit)) * 100));
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-[12.5px]">
        <span className="font-semibold text-foreground">{label}</span>
        <span className="tabular-nums text-muted-foreground">{tokens(used * perCredit)} / {tokens(limit * perCredit)} tokens</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-surface-strong">
        <div className={`h-full rounded-full ${pct >= 100 ? "bg-gradient-to-r from-rose-500 to-orange-400" : "bg-gradient-to-r from-indigo-500 to-violet-500"}`}
          style={{ width: `${pct}%` }} />
      </div>
      {resetsAt && (
        <p className="mt-1 text-[11.5px] text-muted-foreground">
          Refills in {hoursLeft(resetsAt * 1000 - now)}, at {new Date(resetsAt * 1000).toLocaleString([], { weekday: resetsAt * 1000 - now > 20 * 3600e3 ? "short" : undefined, hour: "numeric", minute: "2-digit" })}
        </p>
      )}
    </div>
  );
}

/** Pops up by itself when the user runs out of something on their plan: how much of the meter is used (in
 *  tokens), when it refills (in hours), and what the next plan gives. */
export default function PlanLimitDialog() {
  const navigate = useNavigate();
  const [message, setMessage] = useState(null);
  const [usage, setUsage] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const onLimit = (e) => setMessage(e.detail);
    window.addEventListener(PLAN_LIMIT_EVENT, onLimit);
    return () => window.removeEventListener(PLAN_LIMIT_EVENT, onLimit);
  }, []);

  useEffect(() => {
    if (!message) return undefined;
    setUsage(null);
    api.get("/usage").then(({ data }) => setUsage(data)).catch(() => {});
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, [message]);

  const meter = usage?.meter;
  const perCredit = meter?.tokensPerCredit || 5000;
  const weekFull = meter && meter.week.used >= meter.week.limit;
  const resetsAt = meter && (weekFull ? meter.week.resetsAt : meter.session.resetsAt);
  const plans = usage?.plans || [];
  const at = plans.findIndex((p) => p.id === usage?.plan);
  const next = at >= 0 ? plans[at + 1] : null;
  const current = at >= 0 ? plans[at] : null;
  const times = next && current ? Math.round(next.meter.session / current.meter.session) : null;
  const automation = /automation/i.test(message || "");

  return (
    <Dialog open={!!message} onOpenChange={(o) => !o && setMessage(null)}>
      <DialogContent className="max-w-[25rem] gap-0 overflow-hidden rounded-3xl p-0 max-sm:w-[calc(100%-2rem)]" data-testid="plan-limit-dialog">
        <div className="relative bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 px-6 pb-6 pt-7 text-white">
          <div aria-hidden className="absolute -right-8 -top-10 h-36 w-36 rounded-full bg-white/15 blur-2xl" />
          <DialogHeader className="relative items-center text-center sm:text-center">
            <div className="mb-2 flex h-14 w-14 items-center justify-center rounded-2xl bg-white/20 shadow-lg ring-1 ring-white/30 backdrop-blur">
              {automation ? <Gauge className="h-6 w-6" /> : <Clock className="h-6 w-6" />}
            </div>
            <DialogTitle className="text-[1.3rem] font-extrabold tracking-tight text-white">
              {automation ? "You've reached your automations" : weekFull ? "You've used this week's limit" : "You've used this session's limit"}
            </DialogTitle>
            {resetsAt && !automation ? (
              <p className="pt-1 text-[0.95rem] text-white/90" data-testid="plan-limit-back-in">
                Back in <span className="font-bold">{hoursLeft(resetsAt * 1000 - now)}</span>
              </p>
            ) : null}
          </DialogHeader>
        </div>

        <div className="space-y-4 px-6 pb-6 pt-5">
          {meter && !automation ? (
            <div className="space-y-3" data-testid="plan-limit-meter">
              <Meter label={`This session (${meter.session.hours} hours)`} used={meter.session.used} limit={meter.session.limit}
                perCredit={perCredit} resetsAt={meter.session.resetsAt} now={now} />
              <Meter label="This week" used={meter.week.used} limit={meter.week.limit} perCredit={perCredit}
                resetsAt={weekFull ? meter.week.resetsAt : null} now={now} />
            </div>
          ) : (
            <DialogDescription className="text-center text-[0.9rem] leading-relaxed">{message}</DialogDescription>
          )}
          {meter && !automation && (
            <DialogDescription className="text-[12px] leading-relaxed">
              Usage counts the tokens Krish reads and writes for you. Big app builds use more. Chat on Krish Basic stays unlimited.
            </DialogDescription>
          )}

          {next && (
            <div className="rounded-2xl border border-border bg-surface p-3.5">
              <p className="mb-2 text-[13px] font-semibold text-foreground">
                {next.name}{times > 1 ? ` gives you ${times}× more` : ""}
                <span className="ml-1.5 font-normal text-muted-foreground">₹{next.price}/month</span>
              </p>
              <ul className="space-y-1 text-[12.5px] text-muted-foreground">
                <li className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-emerald-500" /> {tokens(next.meter.session * perCredit)} tokens every {meter?.session.hours || 5} hours</li>
                {next.premium && <li className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-emerald-500" /> Premium models (Claude, GPT) with no waiting</li>}
                {next.publish && <li className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-emerald-500" /> Publish apps with your own domain</li>}
              </ul>
            </div>
          )}

          <div className="flex flex-col gap-2">
            <Button onClick={() => { setMessage(null); navigate("/plans"); }} data-testid="plan-limit-see-plans"
              className="h-11 gap-1.5 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 font-semibold text-white hover:opacity-95">
              <Sparkles className="h-4 w-4" /> {next ? `Upgrade to ${next.name}` : "See plans"}
            </Button>
            <Button variant="ghost" onClick={() => setMessage(null)} className="h-10 rounded-xl text-muted-foreground">
              {resetsAt && !automation ? "I'll wait" : "Maybe later"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
