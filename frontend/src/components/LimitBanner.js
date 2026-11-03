import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { clock, timeOf, trackBanner, useLimit } from "@/lib/limitState";

const NAMES = { basic: "Basic", pro: "Pro", max: "Max" };

/** A quiet line on top of the message box while a usage limit is being waited out: when it's back, a live
 *  countdown and Upgrade (Basic and Pro). Gone by itself once the limit resets. */
export default function LimitBanner() {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  const { info, now } = useLimit();
  useEffect(() => trackBanner(), []);
  if (!info) return null;

  const plan = info.plan || user?.plan || "basic";
  const next = plan === "basic" ? "Pro" : plan === "pro" ? "Max" : null;
  const what = info.kind === "plan" ? `${info.daily ? "Daily" : info.week ? "Weekly" : NAMES[plan] || "Plan"} limit` : info.daily ? "Daily free limit" : "Free limit";

  return (
    <div data-testid="limit-banner"
      className="radha-fade-up mx-auto mb-2 flex w-full max-w-3xl items-center gap-2.5 rounded-xl border border-border bg-surface px-3.5 py-2 text-[13px] text-muted-foreground">
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
      </span>
      <span className="min-w-0 truncate">
        {what}
        {info.resetsAt ? <> · back <span className="font-medium text-foreground">{timeOf(info.resetsAt)}</span></> : " · back soon"}
      </span>
      {info.resetsAt && (
        <span className="shrink-0 rounded-md bg-background px-1.5 py-0.5 font-mono text-[12px] tabular-nums text-foreground" data-testid="limit-banner-clock">
          {clock(info.resetsAt * 1000 - now)}
        </span>
      )}
      {next && (
        <button onClick={() => navigate("/plans")} data-testid="limit-banner-upgrade"
          className="group ml-auto flex shrink-0 items-center gap-1 font-medium text-primary hover:underline">
          Upgrade
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </button>
      )}
    </div>
  );
}
