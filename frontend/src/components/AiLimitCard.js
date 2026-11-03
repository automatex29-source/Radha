import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Check } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

function waitText(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return `${h} hr ${m} min`;
  if (m) return `${m} min ${String(sec).padStart(2, "0")} s`;
  return `${sec} s`;
}

/** A ring that drains as the reset time comes closer. */
function Ring({ progress, ready }) {
  const r = 17, c = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 40 40" className="h-10 w-10 shrink-0 -rotate-90" aria-hidden>
      <circle cx="20" cy="20" r={r} fill="none" strokeWidth="3" className="stroke-border" />
      <circle cx="20" cy="20" r={r} fill="none" strokeWidth="3" strokeLinecap="round"
        className={`transition-[stroke-dashoffset] duration-1000 ease-linear ${ready ? "stroke-emerald-500" : "stroke-primary"}`}
        strokeDasharray={c} strokeDashoffset={c * (1 - progress)} />
    </svg>
  );
}

/** In place of the reply when the free AI's usage limit is hit: a live countdown to when it works again, and
 *  Upgrade. Calm and simple, like the rest of the chat. */
export default function AiLimitCard({ limit, id }) {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  const resets = limit?.resetsAt ? limit.resetsAt * 1000 : null;
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!resets || resets <= Date.now()) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [resets]);

  const ready = !!resets && resets <= now;
  // Full when the limit is hit, then it drains to empty as the reset comes; green when it's ready.
  const progress = ready ? 1 : resets ? Math.min(1, Math.max(0.03, (resets - now) / Math.max(1, resets - start))) : 0.85;
  const at = resets ? new Date(resets).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
  const next = user?.plan === "pro" ? "Max" : user?.plan === "max" ? null : "Pro";

  const title = ready ? "Krish AI is ready again" : limit?.daily ? "You've reached today's free limit" : "You've reached the free limit";
  const sub = ready ? "Send your message again to continue."
    : at ? <>Available again at <span className="whitespace-nowrap font-medium text-foreground">{at}</span></>
    : limit?.daily ? "Available again in a few hours." : "Available again in about a minute.";

  return (
    <div data-testid={`ai-limit-card-${id}`}
      className="radha-fade-up group mt-1 max-w-[34rem] rounded-2xl border border-border bg-card p-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-shadow hover:shadow-[0_6px_24px_-12px_rgba(0,0,0,0.18)]">
      <div className="flex items-center gap-3.5">
        <div className="relative">
          <Ring progress={progress} ready={ready} />
          {ready && <Check className="absolute inset-0 m-auto h-4 w-4 text-emerald-500" />}
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-heading text-[15px] font-semibold tracking-tight text-foreground">{title}</p>
          <p className="mt-0.5 text-[13.5px] text-muted-foreground" data-testid="ai-limit-when">
            {sub}
            {resets && !ready && <span className="ml-1.5 whitespace-nowrap tabular-nums text-muted-foreground/80">· {waitText(resets - now)}</span>}
          </p>
        </div>
      </div>
      {next && !ready && (
        <div className="mt-3.5 flex items-center justify-between gap-3 border-t border-border pt-3.5">
          <p className="text-[13px] text-muted-foreground">
            <span className="font-medium text-foreground">{next}</span> has no waiting and premium models.
          </p>
          <button onClick={() => navigate("/plans")} data-testid="ai-limit-upgrade"
            className="group/btn flex h-8 shrink-0 items-center gap-1.5 rounded-lg bg-foreground px-3.5 text-[13px] font-medium text-background transition-all hover:gap-2.5 hover:opacity-90 active:scale-[0.97]">
            Upgrade <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover/btn:translate-x-0.5" />
          </button>
        </div>
      )}
    </div>
  );
}
