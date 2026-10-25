import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import IconRail from "@/components/IconRail";
import { Input } from "@/components/ui/input";
import { Check, Loader2, Search, Users, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { AnswersTab, OfferCodesTab, ProblemsTab, UsageTab } from "@/components/OwnerInsights";

const TABS = [["users", "Users"], ["payments", "Payments"], ["usage", "Usage"], ["answers", "Answers"], ["problems", "Problems"], ["codes", "Offer codes"]];

function ago(iso) {
  if (!iso) return "Not yet";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString();
}

function when(iso) {
  return iso ? new Date(iso).toLocaleString() : "";
}

/** UPI payments people say they made: check each one in your bank or UPI app, then approve or reject it. */
function PaymentsTab() {
  const [status, setStatus] = useState("pending");
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState("");
  const load = (s = status) => api.get(`/admin/payments?status=${s}`).then(({ data }) => setRows(data.payments))
    .catch((e) => toast.error(formatApiError(e)));
  useEffect(() => { setRows(null); load(status); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  const decide = async (p, approve) => {
    if (!approve && !window.confirm(`Reject ₹${p.amount} from ${p.email}? They won't get ${p.planName}.`)) return;
    setBusy(p.orderId);
    try {
      await api.post(`/admin/payments/${p.orderId}`, { approve });
      toast.success(approve ? `${p.name || p.email} is on ${p.planName} now` : "Rejected");
      load();
    } catch (e) { toast.error(formatApiError(e)); } finally { setBusy(""); }
  };

  return (
    <section className="mt-6" data-testid="owner-payments">
      <p className="text-sm text-muted-foreground">Open your bank or UPI app and find a payment with the same amount and UPI reference. Approve only when you can see the money arrived.</p>
      <div className="mt-3 flex gap-1.5">
        {[["pending", "To check"], ["paid", "Approved"], ["rejected", "Rejected"]].map(([id, label]) => (
          <button key={id} type="button" onClick={() => setStatus(id)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${status === id ? "border-primary bg-primary text-white" : "border-border text-muted-foreground"}`}>{label}</button>
        ))}
      </div>
      {!rows ? <div className="flex justify-center py-14"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
        : !rows.length ? <p className="py-14 text-center text-sm text-muted-foreground">{status === "pending" ? "No payments waiting." : "None yet."}</p>
        : (
          <ul className="mt-4 space-y-2">
            {rows.map((p) => (
              <li key={p.orderId} className="flex flex-wrap items-center gap-3 rounded-2xl border border-border/70 bg-card/80 px-4 py-3 shadow-sm" data-testid="owner-payment">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">₹{p.amount} · {p.planName}{p.promoCode ? ` · ${p.promoCode}` : ""}</p>
                  <p className="text-xs text-muted-foreground">{p.name} · {p.email} · {when(p.createdAt)}</p>
                  <p className="mt-0.5 font-mono text-sm tracking-wide">UPI ref {p.utr}</p>
                </div>
                {status === "pending" && (
                  <div className="flex gap-1.5">
                    <Button size="sm" disabled={busy === p.orderId} onClick={() => decide(p, true)} data-testid="owner-payment-approve">
                      {busy === p.orderId ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Check className="mr-1 h-4 w-4" /> Approve</>}
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy === p.orderId} onClick={() => decide(p, false)}><X className="mr-1 h-4 w-4" /> Reject</Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
    </section>
  );
}

export default function AdminUsersPage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [tab, setTab] = useState("users");

  useEffect(() => {
    if (!user?.isOwner) return;
    api.get("/admin/users").then(({ data }) => setData(data)).catch((e) => setError(formatApiError(e)));
  }, [user]);

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    const all = data?.users || [];
    return term ? all.filter((u) => `${u.name} ${u.email}`.toLowerCase().includes(term)) : all;
  }, [data, q]);

  const today = useMemo(() => {
    const dayAgo = Date.now() - 86400 * 1000;
    return (data?.users || []).filter((u) => u.lastSeenAt && new Date(u.lastSeenAt).getTime() > dayAgo).length;
  }, [data]);

  if (!user?.isOwner) return <Navigate to="/" replace />;

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl px-4 pb-12 pt-10 sm:px-6">
          <header className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-card/70 px-3 py-1 text-xs font-medium text-muted-foreground">
                <Users className="h-3.5 w-3.5 text-primary" /> Owner only
              </span>
              <h1 className="mt-3 text-2xl font-extrabold tracking-tight sm:text-3xl">Users</h1>
              {data && (
                <p className="mt-1 text-sm text-muted-foreground" data-testid="admin-users-summary">
                  {data.total} account{data.total === 1 ? "" : "s"} · {today} active in the last 24 hours
                </p>
              )}
            </div>
            {tab === "users" && <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or email" className="pl-9" data-testid="admin-users-search" />
            </div>}
          </header>

          <div className="mt-6 flex gap-1 overflow-x-auto rounded-xl border border-border bg-card p-1" role="tablist" data-testid="owner-tabs">
            {TABS.map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)} data-testid={`owner-tab-${id}`}
                className={`shrink-0 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors ${tab === id ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
                {label}
              </button>
            ))}
          </div>

          {tab === "payments" ? <PaymentsTab /> : tab === "usage" ? <UsageTab /> : tab === "answers" ? <AnswersTab /> : tab === "problems" ? <ProblemsTab />
            : tab === "codes" ? <OfferCodesTab /> : error ? (
            <p className="mt-10 text-center text-sm text-destructive">{error}</p>
          ) : !data ? (
            <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : (
            <div className="mt-6 overflow-x-auto rounded-2xl border border-border/70 bg-card/80 shadow-sm" data-testid="admin-users-table">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="border-b border-border/70 text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Last active</th>
                    <th className="px-4 py-3 font-medium">Last sign-in</th>
                    <th className="px-4 py-3 font-medium">Sign-ins</th>
                    <th className="px-4 py-3 font-medium">Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((u) => (
                    <tr key={u.id} className="border-b border-border/50 last:border-0">
                      <td className="px-4 py-3">
                        <p className="font-semibold">{u.name}</p>
                        <p className="text-xs text-muted-foreground">{u.email}{u.plan !== "basic" ? ` · ${u.plan}` : ""}</p>
                      </td>
                      <td className="px-4 py-3" title={when(u.lastSeenAt)}>{ago(u.lastSeenAt)}</td>
                      <td className="px-4 py-3" title={when(u.lastLoginAt)}>{ago(u.lastLoginAt)}</td>
                      <td className="px-4 py-3">{u.loginCount || "–"}</td>
                      <td className="px-4 py-3" title={when(u.createdAt)}>{u.createdAt ? new Date(u.createdAt).toLocaleDateString() : ""}</td>
                    </tr>
                  ))}
                  {!rows.length && (
                    <tr><td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">No one matches that search.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
          {tab === "users" && <p className="mt-4 text-xs text-muted-foreground">Sign-in times are kept from this update on. People who joined earlier show their time once they next open Krish.</p>}
        </div>
      </main>
    </div>
  );
}
