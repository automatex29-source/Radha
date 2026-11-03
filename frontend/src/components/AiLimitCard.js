import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Clock, Sparkles, Zap, Check } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

function left(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${String(sec).padStart(2, "0")}s`;
  return `${sec}s`;
}

/** Shown in place of the reply when the free AI's usage limit is hit: when it works again (a live countdown),
 *  and Upgrade to Pro, whose premium models have no free-tier waits. */
export default function AiLimitCard({ limit, id }) {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  const resets = limit?.resetsAt ? limit.resetsAt * 1000 : null;
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!resets || resets <= Date.now()) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [resets]);

  const ready = resets && resets <= now;
  const at = resets ? new Date(resets).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
  const next = user?.plan === "pro" ? "Max" : user?.plan === "max" ? null : "Pro";
  const title = ready ? "Krish AI is ready again" : limit?.daily ? "You've used today's free AI" : "Free AI is taking a short break";
  const when = ready ? "Send your message again to continue."
    : at ? `Back at ${at}` : limit?.daily ? "Back in a few hours (it resets once a day)" : "Back in about a minute";

  return (
    <div data-testid={`ai-limit-card-${id}`}
      className="relative mt-1 overflow-hidden rounded-2xl border border-indigo-200/70 bg-gradient-to-br from-indigo-50 via-white to-violet-50 p-4 shadow-[0_12px_40px_-18px_rgba(99,102,241,0.55)] dark:border-indigo-400/25 dark:from-indigo-500/15 dark:via-transparent dark:to-violet-500/10 sm:p-5">
      <div aria-hidden className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-violet-400/20 blur-2xl" />
      <div className="relative flex items-start gap-3.5">
        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white shadow-[0_8px_20px_-6px_rgba(99,102,241,0.6)] ${ready ? "bg-gradient-to-br from-emerald-500 to-teal-500" : "bg-gradient-to-br from-indigo-500 to-violet-500"}`}>
          {ready ? <Check className="h-5 w-5" /> : <Clock className="h-5 w-5" />}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-bold tracking-tight text-foreground">{title}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-muted-foreground" data-testid="ai-limit-when">
            <span>{when}</span>
            {resets && !ready && (
              <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 font-mono text-[12px] font-semibold tabular-nums text-indigo-600 dark:text-indigo-300">
                in {left(resets - now)}
              </span>
            )}
          </p>
        </div>
      </div>
      {next && !ready && (
        <div className="relative mt-4 flex flex-col gap-3 rounded-xl border border-border bg-card/80 p-3 backdrop-blur">
          <div className="flex min-w-0 flex-1 items-center gap-2 text-[13px] text-foreground">
            <Zap className="h-4 w-4 shrink-0 text-amber-500" />
            <span><span className="font-semibold">No waiting on {next}.</span> <span className="text-muted-foreground">Premium models, bigger apps and higher limits.</span></span>
          </div>
          <button onClick={() => navigate("/plans")} data-testid="ai-limit-upgrade"
            className="krish-unlock flex h-10 shrink-0 items-center self-start justify-center gap-1.5 rounded-full px-4 text-[13px] font-semibold text-white">
            <Sparkles className="h-4 w-4" /> Upgrade to {next}
          </button>
        </div>
      )}
      <p className="relative mt-3 text-[11.5px] text-muted-foreground">Or pick another model from the menu at the top.</p>
    </div>
  );
}
