import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, BellRing, Check, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import BrandMark from "@/components/BrandMark";
import { clock, timeOf, useLimit } from "@/lib/limitState";

const NAMES = { basic: "Basic", pro: "Pro", max: "Max" };

/** In place of a reply when a usage limit is hit: the free AI's own limit, or the user's Basic, Pro or Max plan
 *  meter. The Krish AI mark, a live countdown to the reset, a bar from when the wait began to when it ends,
 *  Notify me and Upgrade. A plan limit fills its times in from the shared limit state. */
export default function AiLimitCard({ limit, id }) {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  const { info } = useLimit();
  const shared = limit?.kind === "plan" && info?.kind === "plan" ? info : null;
  const resetsAt = limit?.resetsAt || shared?.resetsAt || null;
  const resets = resetsAt ? resetsAt * 1000 : null;
  const [opened] = useState(() => Date.now());
  const since = (shared?.since || limit?.since) ? (shared?.since || limit.since) * 1000 : opened;
  const [now, setNow] = useState(Date.now());
  const [notify, setNotify] = useState(false);
  const notified = useRef(false);

  useEffect(() => {
    if (!resets || resets <= Date.now()) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [resets]);

  const ready = !!resets && resets <= now;
  useEffect(() => {
    if (!ready || !notify || notified.current) return;
    notified.current = true;
    try {
      if (typeof Notification !== "undefined" && Notification.permission === "granted") {
        new Notification("Krish AI is ready again", { body: "You can send your message now.", icon: "/icon-192.png" });
      }
    } catch { /* the toast below still shows */ }
    toast.success("Krish AI is ready again. Send your message.");
  }, [ready, notify]);

  const askNotify = async () => {
    try {
      if (typeof Notification !== "undefined" && Notification.permission === "default") await Notification.requestPermission();
    } catch { /* not supported: the toast still works */ }
    setNotify(true);
    toast("We'll let you know when Krish AI is ready.");
  };

  const plan = limit?.kind === "plan" ? (shared?.plan || user?.plan || "basic") : (user?.plan || "basic");
  const next = plan === "basic" ? "Pro" : plan === "pro" ? "Max" : null;
  const week = !!shared?.week;
  const progress = ready ? 100 : resets ? Math.min(100, Math.max(2, ((now - since) / Math.max(1, resets - since)) * 100)) : 8;

  const title = ready ? "Krish AI is ready again"
    : limit?.kind === "plan" ? `You've reached your ${week ? "weekly" : NAMES[plan] || ""} limit`
    : limit?.daily ? "You've used today's free limit" : "You've used your free limit";
  const sub = ready ? "Send your message again to continue."
    : resets ? <>Back at <span className="font-medium text-foreground">{timeOf(resetsAt)}</span></>
    : limit?.daily ? "Back in a few hours" : "Back in a moment";

  return (
    <div data-testid={`ai-limit-card-${id}`}
      className="krish-limit radha-fade-up mt-1 max-w-[30rem] overflow-hidden rounded-2xl border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,0.04),0_12px_32px_-20px_rgba(0,0,0,0.25)]">
      <div className="flex items-center gap-3.5 p-4 pb-3.5">
        <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-surface">
          <BrandMark className="h-8 w-8" thinking={!ready} />
          {ready && <span className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 ring-2 ring-card"><Check className="h-3 w-3 text-white" /></span>}
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-heading text-[15px] font-semibold tracking-tight text-foreground">{title}</p>
          <p className="mt-0.5 text-[13px] text-muted-foreground" data-testid="ai-limit-when">{sub}</p>
        </div>
        {resets && !ready && (
          <div className="shrink-0 text-right" data-testid="ai-limit-clock">
            <p key={Math.ceil((resets - now) / 1000)} className="krish-limit-digit font-mono text-[22px] font-semibold leading-none tabular-nums tracking-tight text-foreground">
              {clock(resets - now)}
            </p>
            <p className="mt-1 text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">left</p>
          </div>
        )}
      </div>

      <div className="px-4">
        <div className="h-1 overflow-hidden rounded-full bg-surface-strong">
          <div className={`h-full rounded-full transition-[width] duration-1000 ease-linear ${ready ? "bg-emerald-500" : "bg-gradient-to-r from-orange-500 to-amber-400"}`}
            style={{ width: `${progress}%` }} />
        </div>
        {resets && (
          <div className="mt-1.5 flex justify-between text-[11px] tabular-nums text-muted-foreground">
            <span>Limit reached {timeOf(since / 1000)}</span><span>Back {timeOf(resetsAt)}</span>
          </div>
        )}
      </div>

      {!ready && (
        <div className="mt-3.5 flex items-center gap-2 border-t border-border bg-surface/60 px-4 py-3">
          {resets && (
            <button onClick={askNotify} disabled={notify} data-testid="ai-limit-notify"
              className="flex h-9 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border border-border-strong bg-card px-3 text-[13px] font-medium text-foreground transition-colors hover:bg-surface-strong disabled:opacity-70">
              {notify ? <BellRing className="h-3.5 w-3.5 text-amber-500" /> : <Bell className="h-3.5 w-3.5" />}
              {notify ? "Notifying" : "Notify me"}
            </button>
          )}
          {next && (
            <button onClick={() => navigate("/plans")} data-testid="ai-limit-upgrade"
              className="group flex h-9 flex-1 items-center justify-center gap-1 whitespace-nowrap rounded-lg bg-foreground px-3 text-[13px] font-semibold text-background transition-transform hover:opacity-90 active:scale-[0.97]">
              Upgrade to {next} <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
