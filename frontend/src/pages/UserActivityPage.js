import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { Bar as RBar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowLeft, CalendarDays, Loader2, LockKeyhole, Mail, MessageCircleQuestion } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import AdminLayout from "@/components/AdminLayout";
import {
  Bar, DayTip, FeatureIcon, PLAN_DOT, Panel, RangePicker, Tile, ago, compact, dayTick, num,
} from "@/components/ActivityParts";

const METHOD = { password: "with email", google: "with Google", signup: "new account", reset: "after a password reset" };
const SIZE = (b) => (!b ? "" : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);
const hourLabel = (h) => (h === 0 ? "12a" : h < 12 ? `${h}a` : h === 12 ? "12p" : `${h - 12}p`);

function when(iso) {
  return iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "";
}

function Meter({ label, used, limit, foot }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-[12.5px]">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground"><b className="font-semibold text-foreground">{num(used)}</b> / {num(limit)} · {pct}%</span>
      </div>
      <div className="mt-1.5"><Bar value={used} max={limit} className={pct >= 90 ? "bg-rose-500" : "bg-[var(--viz-1)]"} /></div>
      {foot && <p className="mt-1 text-[11px] text-muted-foreground">{foot}</p>}
    </div>
  );
}

export default function UserActivityPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user?.isOwner) return;
    setError("");
    api.get(`/admin/users/${id}/activity`, { params: { days } }).then(({ data }) => setData(data))
      .catch((e) => setError(formatApiError(e)));
  }, [user, id, days]);

  if (!user?.isOwner) return <Navigate to="/" replace />;
  const u = data?.user;
  const s = data?.summary;
  const used = data ? data.features.filter((f) => f.count) : [];
  const unused = data ? data.features.filter((f) => !f.count) : [];
  const fMax = used.length ? Math.max(...used.map((f) => f.count)) : 0;
  const hMax = data ? Math.max(...data.hours) : 0;
  const busiest = data && hMax ? data.hours.indexOf(hMax) : null;
  const rangeLabel = days === 365 ? "year" : `${days} days`;

  return (
    <AdminLayout>
      <div data-testid="user-activity-page">
          <Link to="/admin/users" className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground" data-testid="user-activity-back">
            <ArrowLeft className="h-3.5 w-3.5" /> Users
          </Link>

          {error && !data ? <p className="mt-10 text-center text-sm text-destructive">{error}</p> : !data ? (
            <div className="flex justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : (
            <>
              <header className="mt-3 flex flex-wrap items-center justify-between gap-4">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-foreground text-lg font-bold text-background">
                    {(u.name || u.email || "?").trim()[0].toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <h1 className="truncate text-xl font-bold tracking-tight sm:text-2xl" data-testid="user-activity-name">{u.name || "No name"}</h1>
                    <p className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-muted-foreground">
                      <span className="inline-flex min-w-0 items-center gap-1"><Mail className="h-3 w-3 shrink-0" /><span className="truncate">{u.email}</span></span>
                      <span className="inline-flex items-center gap-1 font-medium text-foreground"><span className={`h-1.5 w-1.5 rounded-full ${PLAN_DOT[u.plan] || PLAN_DOT.basic}`} />{u.planName}
                        {u.planExpiresAt && u.plan !== "basic" ? <span className="font-normal text-muted-foreground">until {new Date(u.planExpiresAt).toLocaleDateString()}</span> : null}</span>
                    </p>
                  </div>
                </div>
                <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
                  <Link to={`/admin/questions?user=${u.id}`} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-semibold hover:bg-muted" data-testid="user-activity-questions">
                    <MessageCircleQuestion className="h-3.5 w-3.5" /> Their questions
                  </Link>
                  <RangePicker days={days} onChange={setDays} />
                </div>
              </header>

              <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 rounded-xl border border-border/80 bg-card px-4 py-3 text-[12.5px] sm:grid-cols-4" data-testid="user-activity-account">
                {[["Last active", ago(u.lastSeenAt)], ["Last sign-in", ago(u.lastLoginAt)], ["Sign-ins", `${num(u.loginCount)} · ${u.signIn}`],
                  ["Joined", u.createdAt ? new Date(u.createdAt).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "–"]].map(([k, v]) => (
                  <div key={k} className="min-w-0 py-1"><p className="text-[11px] text-muted-foreground">{k}</p><p className="truncate font-semibold">{v}</p></div>
                ))}
              </div>

              <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-5" data-testid="user-activity-tiles">
                <Tile label="Actions" value={num(s.actions)} foot={`In the last ${rangeLabel}`} />
                <Tile label="Active days" value={num(s.activeDays)} foot={`Out of ${num(days)}`} />
                <Tile label="Features used" value={`${s.featuresUsed}`} foot={`Of ${data.features.length}`} />
                <Tile label="AI tokens" value={compact(s.tokens)} foot="Read and written by Krish" />
                <Tile label="Things made" value={num(s.made)} foot={`${num(s.madeEver)} ever · ${num(s.chats)} chats`} />
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-5">
                <Panel className="lg:col-span-3" title="Features used" subtitle="How many times, and when last" testId="user-activity-features" flush>
                  {!used.length ? <p className="px-4 py-10 text-center text-sm text-muted-foreground">No feature use in the last {rangeLabel}.</p> : (
                    <ul className="divide-y divide-border/50">
                      {used.sort((a, b) => b.count - a.count).map((f) => (
                        <li key={f.kind} className="flex items-center gap-3 px-4 py-2.5" data-testid={`user-feature-${f.kind}`}>
                          <FeatureIcon kind={f.kind} />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-baseline justify-between gap-2">
                              <p className="truncate text-[13px] font-semibold">{f.label}</p>
                              <p className="shrink-0 text-[13px] font-bold tabular-nums">{num(f.count)}<span className="ml-1 text-[11px] font-normal text-muted-foreground">{f.count === 1 ? "time" : "times"}</span></p>
                            </div>
                            <div className="mt-1"><Bar value={f.count} max={fMax} /></div>
                            <p className="mt-1 text-[11px] text-muted-foreground">Last {ago(f.last).toLowerCase()}{f.first && f.first !== f.last ? ` · first ${ago(f.first).toLowerCase()}` : ""}</p>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  {unused.length > 0 && (
                    <p className="border-t border-border/50 px-4 py-2.5 text-[11.5px] text-muted-foreground">Not used yet: {unused.map((f) => f.label).join(", ")}</p>
                  )}
                </Panel>

                <div className="flex flex-col gap-3 lg:col-span-2">
                  <Panel title="Usage and plan" subtitle={`${u.planName} plan limits`} testId="user-activity-usage">
                    <div className="space-y-3.5">
                      <Meter label="This session" used={data.usage.sessionUsed} limit={data.usage.sessionLimit} foot="Credits, refills every few hours" />
                      <Meter label="This week" used={data.usage.weekUsed} limit={data.usage.weekLimit} foot="Credits" />
                      <Meter label="Tokens today" used={data.usage.tokensToday} limit={data.usage.fairUseLimit} foot="Daily fair-use allowance" />
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-2 border-t border-border/60 pt-3 text-[12px]">
                      <div><p className="text-muted-foreground">Chat tokens</p><p className="font-semibold tabular-nums">{num(data.usage.tokensByKind.chat || 0)}</p></div>
                      <div><p className="text-muted-foreground">App Builder tokens</p><p className="font-semibold tabular-nums">{num(data.usage.tokensByKind.build || 0)}</p></div>
                    </div>
                  </Panel>
                  <Panel title="When they use Krish" subtitle={busiest !== null ? `Busiest around ${hourLabel(busiest)}m, India time` : "India time"} testId="user-activity-hours">
                    <div className="flex h-16 items-end gap-[3px]">
                      {data.hours.map((n, h) => (
                        <div key={h} title={`${hourLabel(h)}m: ${n}`} className="flex-1 rounded-sm bg-[var(--viz-1)]" style={{ height: `${hMax ? Math.max(n ? 8 : 3, (n / hMax) * 100) : 3}%`, opacity: n ? 1 : 0.15 }} />
                      ))}
                    </div>
                    <div className="mt-1 flex justify-between text-[10px] text-muted-foreground"><span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>11pm</span></div>
                  </Panel>
                </div>
              </div>

              <Panel className="mt-3" title="Activity per day" subtitle="Actions and visits, India time" testId="user-activity-daily">
                <div className="h-48 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.daily} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
                      <XAxis dataKey="day" tickFormatter={dayTick} tick={{ fontSize: 10, fill: "var(--viz-axis)" }} axisLine={false} tickLine={false} minTickGap={18} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "var(--viz-axis)" }} axisLine={false} tickLine={false} />
                      <Tooltip cursor={{ fill: "var(--viz-grid)" }} content={<DayTip rows={[["actions", "Actions"], ["visits", "Visits"]]} />} />
                      <RBar dataKey="actions" stackId="a" fill="var(--viz-1)" radius={[0, 0, 0, 0]} isAnimationActive={false} />
                      <RBar dataKey="visits" stackId="a" fill="var(--viz-2)" fillOpacity={0.55} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-2 flex gap-4 text-[11px] text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[var(--viz-1)]" />Actions</span>
                  <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[var(--viz-2)] opacity-60" />Just opened Krish</span>
                </div>
              </Panel>

              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <Panel title="Things they made" subtitle="Names and dates only, newest first" testId="user-activity-made" flush>
                  {!data.made.length ? <p className="px-4 py-10 text-center text-sm text-muted-foreground">Nothing made yet.</p> : (
                    <ul className="max-h-[420px] divide-y divide-border/50 overflow-y-auto">
                      {data.made.map((m, i) => (
                        <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                          <FeatureIcon kind={m.type} className="h-7 w-7" />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-[13px] font-medium">{m.name}</p>
                            <p className="truncate text-[11px] text-muted-foreground">{[m.label, m.note, SIZE(m.size)].filter(Boolean).join(" · ")}</p>
                          </div>
                          <span className="shrink-0 text-[11px] text-muted-foreground" title={when(m.at)}>{ago(m.at)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>

                <Panel title="Recent activity" subtitle="What happened, newest first" testId="user-activity-timeline" flush>
                  {!data.timeline.length ? <p className="px-4 py-10 text-center text-sm text-muted-foreground">No activity in the last {rangeLabel}.</p> : (
                    <ol className="max-h-[420px] overflow-y-auto px-4 py-2">
                      {data.timeline.map((t, i) => (
                        <li key={i} className="relative flex gap-3 py-2 pl-1">
                          {i < data.timeline.length - 1 && <span className="absolute left-[17px] top-9 h-[calc(100%-20px)] w-px bg-border" />}
                          <FeatureIcon kind={t.kinds[0]} className="h-7 w-7" />
                          <div className="min-w-0 flex-1">
                            <p className="text-[13px] font-medium">{t.labels.join(" + ")}{t.method && METHOD[t.method] ? <span className="font-normal text-muted-foreground"> {METHOD[t.method]}</span> : null}</p>
                            {t.name && <p className="truncate text-[11.5px] text-muted-foreground">{t.name}</p>}
                          </div>
                          <span className="shrink-0 pt-0.5 text-[11px] text-muted-foreground">{when(t.at)}</span>
                        </li>
                      ))}
                    </ol>
                  )}
                </Panel>
              </div>

              <Panel className="mt-3" title="Payments" subtitle="Plans they bought" testId="user-activity-payments" flush>
                {!data.payments.length ? <p className="px-4 py-6 text-center text-sm text-muted-foreground">No payments yet.</p> : (
                  <ul className="divide-y divide-border/50">
                    {data.payments.map((p, i) => (
                      <li key={i} className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13px]">
                        <span className="inline-flex items-center gap-2"><CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />{new Date(p.paidAt).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</span>
                        <span className="capitalize text-muted-foreground">{p.plan}{p.promoCode ? ` · ${p.promoCode}` : ""}</span>
                        <span className="font-semibold tabular-nums">₹{num(p.amount)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <p className="mt-5 flex items-start gap-2 text-[11.5px] leading-relaxed text-muted-foreground" data-testid="user-activity-privacy">
                <LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Krish's answers aren't shown here, and Counsellor use isn't shown per person. Their questions are on the Questions page. Tokens are counted from the update that added them.
              </p>
            </>
          )}
      </div>
    </AdminLayout>
  );
}
