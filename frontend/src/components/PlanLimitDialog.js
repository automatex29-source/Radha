import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { PLAN_LIMIT_EVENT } from "@/lib/planLimits";

function waitText(ms) {
  const mins = Math.max(1, Math.ceil(ms / 60000));
  const h = Math.floor(mins / 60), m = mins % 60;
  if (!h) return `${m} min`;
  return `${h} hr${m ? ` ${m} min` : ""}`;
}

function timeText(sec, now) {
  const ms = sec * 1000;
  return new Date(ms).toLocaleString([], { weekday: ms - now > 20 * 3600e3 ? "long" : undefined, hour: "numeric", minute: "2-digit" });
}

function Meter({ label, used, limit, note }) {
  const pct = Math.min(100, Math.round((used / Math.max(1, limit)) * 100));
  const [shown, setShown] = useState(0); // the bar fills up when the popup opens
  useEffect(() => { const t = setTimeout(() => setShown(pct), 80); return () => clearTimeout(t); }, [pct]);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-[13px]">
        <span className="text-foreground">{label}</span>
        <span className="tabular-nums text-muted-foreground">{pct}% used</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-strong">
        <div className="h-full rounded-full bg-foreground/80 transition-[width] duration-700 ease-out" style={{ width: `${shown}%` }} />
      </div>
      {note && <p className="mt-1.5 text-[12px] text-muted-foreground">{note}</p>}
    </div>
  );
}

/** Opens by itself when the user runs out of something on their plan: when the meter resets, how much of it is
 *  used, and a plain way to upgrade. */
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
    setNow(Date.now());
    api.get("/usage").then(({ data }) => setUsage(data)).catch(() => {});
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, [message]);

  const meter = usage?.meter;
  const automation = /automation/i.test(message || "");
  const weekFull = meter && meter.week.used >= meter.week.limit;
  const resetsAt = meter && !automation ? (weekFull ? meter.week.resetsAt : meter.session.resetsAt) : null;
  const plans = usage?.plans || [];
  const at = plans.findIndex((p) => p.id === usage?.plan);
  const next = at >= 0 ? plans[at + 1] : null;
  const times = next && at >= 0 ? Math.round(next.meter.session / plans[at].meter.session) : null;

  return (
    <Dialog open={!!message} onOpenChange={(o) => !o && setMessage(null)}>
      <DialogContent className="max-w-[26rem] gap-0 rounded-2xl p-6 max-sm:w-[calc(100%-2rem)]" data-testid="plan-limit-dialog">
        <DialogHeader className="space-y-1.5 text-left sm:text-left">
          <DialogTitle className="font-heading text-[1.15rem] font-semibold tracking-tight">
            {automation ? "Automation limit reached" : weekFull ? "Weekly usage limit reached" : "Usage limit reached"}
          </DialogTitle>
          <DialogDescription className="text-[14px] leading-relaxed" data-testid="plan-limit-back-in">
            {resetsAt
              ? <>Your limit resets at <span className="font-medium text-foreground">{timeText(resetsAt, now)}</span>, in {waitText(resetsAt * 1000 - now)}.{" "}
                  {next ? `Upgrade to ${next.name} to keep going now.` : ""}</>
              : message}
          </DialogDescription>
        </DialogHeader>

        {meter && !automation && (
          <div className="mt-5 space-y-4 border-t border-border pt-5" data-testid="plan-limit-meter">
            <Meter label={`Current session (${meter.session.hours} hours)`} used={meter.session.used} limit={meter.session.limit} />
            <Meter label="This week" used={meter.week.used} limit={meter.week.limit}
              note={weekFull && meter.week.resetsAt ? `Resets ${timeText(meter.week.resetsAt, now)}` : null} />
            <p className="text-[12px] leading-relaxed text-muted-foreground">
              Usage is based on the tokens Krish reads and writes, so larger app builds use more. Chat on Krish Basic is always unlimited.
            </p>
          </div>
        )}

        {next && (
          <p className="mt-5 text-[13px] text-muted-foreground">
            <span className="font-medium text-foreground">{next.name}</span> · ₹{next.price}/month
            {times > 1 ? ` · ${times}× more usage` : ""}{next.premium ? " · premium models" : ""}
          </p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setMessage(null)} className="h-9 rounded-lg px-4 text-muted-foreground">
            {resetsAt ? "Wait" : "Close"}
          </Button>
          <Button onClick={() => { setMessage(null); navigate("/plans"); }} data-testid="plan-limit-see-plans"
            className="h-9 rounded-lg px-4 font-medium transition-transform active:scale-[0.97]">
            {next ? `Upgrade to ${next.name}` : "See plans"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
