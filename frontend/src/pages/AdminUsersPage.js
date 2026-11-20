import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import AdminLayout from "@/components/AdminLayout";
import { Input } from "@/components/ui/input";
import { ChevronRight, Loader2, Search } from "lucide-react";
import ActivityTab from "@/components/ActivityTab";
import { AnswersTab, OfferCodesTab, ProblemsTab, UsageTab } from "@/components/OwnerInsights";

const SECTIONS = {
  users: ["Users", "Everyone with an account. Tap anyone to see what they did."],
  activity: ["Activity", "Most used features, active people per day and the most active people"],
  usage: ["Daily usage", "People and features used each day, India time"],
  answers: ["Answer ratings", "Answers people marked 👍 or 👎"],
  problems: ["Problems", "Crashes in the app and errors on the server, last 30 days"],
  codes: ["Offer codes", "Discount codes for Pro and Max"],
};
const PLAN_DOT = { basic: "bg-slate-400 dark:bg-slate-500", pro: "bg-[var(--viz-1)]", max: "bg-[var(--viz-2)]" };

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

function UsersList() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

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

  if (error) return <p className="mt-10 text-center text-sm text-destructive">{error}</p>;
  if (!data) return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[12.5px] text-muted-foreground" data-testid="admin-users-summary">
          <b className="font-semibold text-foreground">{data.total}</b> account{data.total === 1 ? "" : "s"} · <b className="font-semibold text-foreground">{today}</b> active in the last 24 hours
        </p>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or email" className="bg-card pl-9" data-testid="admin-users-search" />
        </div>
      </div>
      <div className="mt-3 overflow-x-auto rounded-xl border border-border/80 bg-card shadow-[0_1px_2px_rgba(15,23,42,0.04)]" data-testid="admin-users-table">
        <table className="w-full min-w-[680px] text-left text-[13px]">
          <thead className="border-b border-border/70 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 font-semibold">Name</th>
              <th className="px-4 py-2.5 font-semibold">Plan</th>
              <th className="px-4 py-2.5 font-semibold">Last active</th>
              <th className="px-4 py-2.5 font-semibold">Last sign-in</th>
              <th className="px-4 py-2.5 text-right font-semibold">Sign-ins</th>
              <th className="px-4 py-2.5 font-semibold">Joined</th>
              <th className="w-8 px-2 py-2.5" aria-label="Open" />
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} onClick={() => navigate(`/admin/users/${u.id}`)} data-testid="admin-users-row"
                className="cursor-pointer border-b border-border/50 transition-colors last:border-0 hover:bg-muted/50">
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">{(u.name || u.email || "?")[0].toUpperCase()}</span>
                    <div className="min-w-0"><p className="truncate font-semibold">{u.name || "No name"}</p><p className="truncate text-[11.5px] text-muted-foreground">{u.email}</p></div>
                  </div>
                </td>
                <td className="px-4 py-2.5"><span className="inline-flex items-center gap-1.5 text-[12px] font-medium capitalize"><span className={`h-1.5 w-1.5 rounded-full ${PLAN_DOT[u.plan] || PLAN_DOT.basic}`} />{u.plan}</span></td>
                <td className="px-4 py-2.5" title={when(u.lastSeenAt)}>{ago(u.lastSeenAt)}</td>
                <td className="px-4 py-2.5 text-muted-foreground" title={when(u.lastLoginAt)}>{ago(u.lastLoginAt)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{u.loginCount || "–"}</td>
                <td className="px-4 py-2.5 text-muted-foreground" title={when(u.createdAt)}>{u.createdAt ? new Date(u.createdAt).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : ""}</td>
                <td className="px-2 py-2.5 text-muted-foreground">
                  <Link to={`/admin/users/${u.id}`} onClick={(e) => e.stopPropagation()} aria-label={`See what ${u.name || u.email} did`}><ChevronRight className="h-4 w-4" /></Link>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">No one matches that search.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">Sign-in times are kept from the update that added them. People who joined earlier show their time once they next open Krish.</p>
    </>
  );
}

/** One section of the admin panel: the users list, activity, daily usage, answer ratings, problems or codes. */
export default function AdminUsersPage({ section = "users" }) {
  const [title, subtitle] = SECTIONS[section] || SECTIONS.users;
  const body = section === "activity" ? <ActivityTab /> : section === "usage" ? <UsageTab /> : section === "answers" ? <AnswersTab />
    : section === "problems" ? <ProblemsTab /> : section === "codes" ? <OfferCodesTab /> : <UsersList />;
  return (
    <AdminLayout title={title} subtitle={subtitle}>
      <div data-testid={`admin-section-${section}`}>{body}</div>
    </AdminLayout>
  );
}
