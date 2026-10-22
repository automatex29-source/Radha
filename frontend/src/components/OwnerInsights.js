import { useCallback, useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Loader2, ThumbsDown, ThumbsUp } from "lucide-react";

const FEATURES = [
  ["chat", "Chat"], ["counsellor", "Counsellor"], ["web", "Web search"], ["voice", "Voice"], ["think", "Think"],
  ["build", "App builds"], ["picture", "Pictures"], ["deck", "Decks"], ["video", "Videos"],
];

function dayLabel(day) {
  return new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

function Card({ children, testId }) {
  return <div className="mt-6 overflow-x-auto rounded-2xl border border-border/70 bg-card/80 shadow-sm" data-testid={testId}>{children}</div>;
}

function useStats() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.get("/admin/stats").then(({ data }) => setStats(data)).catch((e) => setError(formatApiError(e)));
  }, []);
  return { stats, error };
}

function Loading({ error }) {
  return error ? <p className="mt-10 text-center text-sm text-destructive">{error}</p>
    : <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;
}

/** People and features used each day (India time), with sign-ups and 👍 / 👎. */
export function UsageTab() {
  const { stats, error } = useStats();
  if (!stats) return <Loading error={error} />;
  const today = stats.days[0];
  const week = stats.days.slice(0, 7);
  const sum = (f) => week.reduce((n, d) => n + f(d), 0);
  return (
    <>
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="owner-usage-tiles">
        {[["People today", today.activeUsers], ["Sign-ups this week", sum((d) => d.signups)],
          ["Messages this week", sum((d) => d.features.chat + d.features.counsellor)], ["Total accounts", stats.totalUsers]].map(([label, n]) => (
          <div key={label} className="rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-1 text-2xl font-extrabold tabular-nums">{n}</p>
          </div>
        ))}
      </div>
      <Card testId="owner-usage-table">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead className="border-b border-border/70 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-3 font-medium">Day</th>
              <th className="px-3 py-3 font-medium">People</th>
              <th className="px-3 py-3 font-medium">Sign-ups</th>
              {FEATURES.map(([k, label]) => <th key={k} className="px-3 py-3 font-medium">{label}</th>)}
              <th className="px-3 py-3 font-medium">👍 / 👎</th>
              <th className="px-3 py-3 font-medium">Problems</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {stats.days.map((d) => (
              <tr key={d.day} className="border-b border-border/50 last:border-0">
                <td className="whitespace-nowrap px-3 py-2.5 font-medium">{dayLabel(d.day)}</td>
                <td className="px-3 py-2.5">{d.activeUsers}</td>
                <td className="px-3 py-2.5">{d.signups}</td>
                {FEATURES.map(([k]) => <td key={k} className="px-3 py-2.5">{d.features[k] || 0}</td>)}
                <td className="px-3 py-2.5">{d.thumbsUp} / {d.thumbsDown}</td>
                <td className={`px-3 py-2.5 ${d.problems ? "font-semibold text-rose-600 dark:text-rose-400" : ""}`}>{d.problems}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="mt-4 text-xs text-muted-foreground">Counting starts with this update, so earlier days show 0. Days follow India time.</p>
    </>
  );
}

/** The latest crashes in the app and errors on the server (kept 30 days). */
export function ProblemsTab() {
  const { stats, error } = useStats();
  if (!stats) return <Loading error={error} />;
  if (!stats.problems.length) return <p className="mt-10 text-center text-sm text-muted-foreground">No problems in the last 30 days. 🎉</p>;
  return (
    <Card testId="owner-problems">
      <ul className="divide-y divide-border/50">
        {stats.problems.map((p, i) => (
          <li key={i} className="px-4 py-3 text-sm">
            <p className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${p.source === "app" ? "bg-amber-500/15 text-amber-700 dark:text-amber-300" : "bg-rose-500/15 text-rose-700 dark:text-rose-300"}`}>
                {p.source === "app" ? "In the app" : "On the server"}
              </span>
              <span className="text-xs text-muted-foreground">{new Date(p.createdAt).toLocaleString()}{p.path ? ` · ${p.path}` : ""}</span>
            </p>
            <p className="mt-1 break-words font-mono text-xs">{p.message}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Answers people marked 👎, with the question asked, so weak spots are easy to see. */
export function AnswersTab() {
  const { stats, error } = useStats();
  if (!stats) return <Loading error={error} />;
  const week = stats.days.slice(0, 7);
  const up = week.reduce((n, d) => n + d.thumbsUp, 0);
  const down = week.reduce((n, d) => n + d.thumbsDown, 0);
  return (
    <>
      <p className="mt-6 flex items-center gap-4 text-sm" data-testid="owner-ratings-week">
        <span className="text-muted-foreground">Last 7 days:</span>
        <span className="flex items-center gap-1.5"><ThumbsUp className="h-4 w-4 text-emerald-600" /> {up}</span>
        <span className="flex items-center gap-1.5"><ThumbsDown className="h-4 w-4 text-rose-600" /> {down}</span>
      </p>
      {!stats.disliked.length ? (
        <p className="mt-10 text-center text-sm text-muted-foreground">No answers marked 👎 yet.</p>
      ) : (
        <Card testId="owner-disliked">
          <ul className="divide-y divide-border/50">
            {stats.disliked.map((d) => (
              <li key={d.messageId} className="px-4 py-3 text-sm">
                <p className="text-xs text-muted-foreground">{new Date(d.createdAt).toLocaleString()}{d.model ? ` · ${d.model}` : ""}</p>
                <p className="mt-1 font-semibold">{d.question || "(question not found)"}</p>
                <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-muted-foreground">{d.answer}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

/** Offer codes such as LAUNCH50 for the Plans page: make them, see how often they were used, switch them off. */
export function OfferCodesTab() {
  const [codes, setCodes] = useState(null);
  const [form, setForm] = useState({ code: "", percentOff: "50", maxUses: "", expiresOn: "" });
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.get("/admin/promos").then(({ data }) => setCodes(data.codes)).catch((e) => toast.error(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);
  const upd = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/admin/promos", {
        code: form.code, percentOff: Number(form.percentOff), maxUses: Number(form.maxUses || 0),
        expiresOn: form.expiresOn || null,
      });
      toast.success(`${form.code.toUpperCase()} is ready to share`);
      setForm({ code: "", percentOff: "50", maxUses: "", expiresOn: "" });
      load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const toggle = async (c) => {
    try {
      await api.put(`/admin/promos/${encodeURIComponent(c.code)}`, { active: !c.active });
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <>
      <form onSubmit={create} className="mt-6 grid gap-3 rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm sm:grid-cols-5" data-testid="promo-form">
        <label className="text-xs font-medium sm:col-span-2">Code
          <Input value={form.code} onChange={upd("code")} placeholder="LAUNCH50" required minLength={3} maxLength={24}
            className="mt-1 uppercase" data-testid="promo-code-input" />
        </label>
        <label className="text-xs font-medium">% off
          <Input type="number" min={1} max={90} value={form.percentOff} onChange={upd("percentOff")} required className="mt-1" data-testid="promo-percent-input" />
        </label>
        <label className="text-xs font-medium">How many uses
          <Input type="number" min={0} value={form.maxUses} onChange={upd("maxUses")} placeholder="No limit" className="mt-1" />
        </label>
        <label className="text-xs font-medium">Last day
          <Input type="date" value={form.expiresOn} onChange={upd("expiresOn")} className="mt-1" />
        </label>
        <div className="flex items-center justify-between gap-3 sm:col-span-5">
          <p className="text-xs text-muted-foreground">Works on one Pro or Max payment. Each person can use a code once.</p>
          <Button type="submit" disabled={busy} data-testid="promo-create">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Make code"}</Button>
        </div>
      </form>
      {!codes ? <Loading /> : !codes.length ? (
        <p className="mt-8 text-center text-sm text-muted-foreground">No offer codes yet.</p>
      ) : (
        <Card testId="promo-list">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="border-b border-border/70 text-xs text-muted-foreground">
              <tr><th className="px-4 py-3 font-medium">Code</th><th className="px-4 py-3 font-medium">Off</th>
                <th className="px-4 py-3 font-medium">Used</th><th className="px-4 py-3 font-medium">Ends</th><th className="px-4 py-3" /></tr>
            </thead>
            <tbody>
              {codes.map((c) => (
                <tr key={c.code} className={`border-b border-border/50 last:border-0 ${c.active ? "" : "text-muted-foreground"}`}>
                  <td className="px-4 py-3 font-mono font-semibold">{c.code}</td>
                  <td className="px-4 py-3">{c.percentOff}%</td>
                  <td className="px-4 py-3 tabular-nums">{c.uses}{c.maxUses ? ` of ${c.maxUses}` : ""}</td>
                  <td className="px-4 py-3">{c.expiresAt ? new Date(new Date(c.expiresAt).getTime() - 1).toLocaleDateString() : "Never"}</td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="outline" onClick={() => toggle(c)}>{c.active ? "Switch off" : "Switch on"}</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
