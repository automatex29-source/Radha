import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

function waitText(ms) {
  const mins = Math.max(1, Math.ceil(ms / 60000));
  const h = Math.floor(mins / 60), m = mins % 60;
  if (!h) return `${m} min`;
  return `${h} hr${m ? ` ${m} min` : ""}`;
}

/** A quiet notice in place of the reply when the free AI's usage limit is hit: when it works again, and a
 *  plain Upgrade link. */
export default function AiLimitCard({ limit, id }) {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  const resets = limit?.resetsAt ? limit.resetsAt * 1000 : null;
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!resets || resets <= Date.now()) return undefined;
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, [resets]);

  const ready = resets && resets <= now;
  const at = resets ? new Date(resets).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
  const next = user?.plan === "pro" ? "Max" : user?.plan === "max" ? null : "Pro";
  const when = ready ? "You can send your message again."
    : at ? `Resets at ${at} (in ${waitText(resets - now)}).`
    : limit?.daily ? "Resets once a day, in a few hours." : "Try again in about a minute.";

  return (
    <div data-testid={`ai-limit-card-${id}`}
      className="mt-1 flex flex-col gap-3 rounded-xl border border-border bg-surface px-4 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1 text-[13.5px] leading-relaxed">
        <p className="font-medium text-foreground">
          {ready ? "Krish AI is available again." : limit?.daily ? "You've reached today's free usage limit." : "You've reached the free usage limit."}
        </p>
        <p className="text-muted-foreground" data-testid="ai-limit-when">{when} You can also switch models from the menu.</p>
      </div>
      {next && !ready && (
        <button onClick={() => navigate("/plans")} data-testid="ai-limit-upgrade"
          className="h-8 shrink-0 self-start rounded-lg border border-border-strong bg-card px-3 text-[13px] font-medium text-foreground transition-colors hover:bg-surface-strong sm:self-center">
          Upgrade to {next}
        </button>
      )}
    </div>
  );
}
