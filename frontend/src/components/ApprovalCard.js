import { useEffect, useState } from "react";
import { Check, Loader2, ShieldCheck, X } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { LetterLogo } from "@/components/BrandLogos";

// An "Ask first" app action in a chat: the user allows it once, always, or denies it (custom_connectors.py).
function value(v) {
  if (v === null || v === undefined) return "";
  return typeof v === "string" ? v : JSON.stringify(v);
}

export default function ApprovalCard({ card, onAsk }) {
  const [status, setStatus] = useState(card.status);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (card.status !== "pending") return;
    api.get(`/connectors/custom/approvals/${card.id}`).then(({ data }) => setStatus(data.status)).catch(() => {});
  }, [card.id, card.status]);

  const decide = async (decision) => {
    setBusy(decision); setError("");
    try {
      const { data } = await api.post(`/connectors/custom/approvals/${card.id}`, { decision });
      setStatus(data.status);
      if (data.status === "allowed" && onAsk) onAsk(decision === "always" ? `Allowed (always for ${card.label}). Go ahead.` : "Allowed. Go ahead.");
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setBusy("");
    }
  };
  const args = Object.entries(card.args || {}).filter(([, v]) => value(v));
  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-border-strong bg-card" data-testid={`approval-${card.id}`}>
      <div className="flex items-start gap-3 px-4 pt-3.5">
        <LetterLogo name={card.app} color={card.color} kind="mcp" size="sm" />
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-semibold text-foreground">Krish wants to use {card.app}</p>
          <p className="text-[12.5px] text-muted-foreground">{card.label}</p>
        </div>
      </div>
      {args.length > 0 && (
        <dl className="mx-4 mt-3 space-y-1 rounded-lg bg-sunken px-3 py-2 text-[12px]">
          {args.slice(0, 8).map(([k, v]) => (
            <div key={k} className="flex gap-2"><dt className="shrink-0 font-mono text-muted-foreground">{k}</dt>
              <dd className="min-w-0 break-words text-foreground">{value(v).slice(0, 300)}</dd></div>
          ))}
        </dl>
      )}
      {status === "pending" ? (
        <div className="flex flex-wrap gap-2 px-4 py-3">
          <button type="button" onClick={() => decide("once")} disabled={!!busy} data-testid="approval-once"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-[13px] font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-60">
            {busy === "once" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Allow once</button>
          <button type="button" onClick={() => decide("always")} disabled={!!busy} data-testid="approval-always"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border-strong px-3.5 text-[13px] font-medium text-foreground hover:bg-surface disabled:opacity-60">
            {busy === "always" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />} Always allow</button>
          <button type="button" onClick={() => decide("deny")} disabled={!!busy} data-testid="approval-deny"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-muted-foreground hover:bg-surface hover:text-foreground disabled:opacity-60">
            {busy === "deny" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />} Deny</button>
          {error && <p className="w-full text-[12px] text-destructive">{error}</p>}
        </div>
      ) : (
        <p className={`px-4 py-3 text-[12.5px] font-medium ${status === "denied" ? "text-muted-foreground" : "text-emerald-600 dark:text-emerald-400"}`} data-testid="approval-status">
          {status === "denied" ? "You denied this." : status === "used" ? "Allowed and done." : "Allowed."}
        </p>
      )}
    </div>
  );
}
