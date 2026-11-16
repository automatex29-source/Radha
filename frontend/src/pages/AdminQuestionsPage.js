import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar as RBar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChevronLeft, ChevronRight, Hammer, Loader2, LockKeyhole, MessageSquare, Search, X } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import AdminLayout from "@/components/AdminLayout";
import { Input } from "@/components/ui/input";
import { Bar, DayTip, Panel, Tile, ago, dayTick, num } from "@/components/ActivityParts";

const RANGES = [[1, "24 hours"], [7, "7 days"], [30, "30 days"], [90, "90 days"]];

function when(iso) {
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

/** What people ask Krish: topics, trending words and the questions, never who asked them. */
export default function AdminQuestionsPage() {
  const [params, setParams] = useSearchParams();
  const user = params.get("user") || "";
  const [days, setDays] = useState(7);
  const [topic, setTopic] = useState("");
  const [typed, setTyped] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => { const t = setTimeout(() => { setQ(typed); setPage(0); }, 300); return () => clearTimeout(t); }, [typed]);
  useEffect(() => {
    setLoading(true);
    api.get("/admin/questions", { params: { days, topic, q, page, user } })
      .then(({ data }) => { setData(data); setError(""); }).catch((e) => setError(formatApiError(e))).finally(() => setLoading(false));
  }, [days, topic, q, page, user]);

  const pick = (t) => { setTopic((cur) => (cur === t ? "" : t)); setPage(0); };
  const topMax = data?.topics[0]?.count || 0;
  const avg = data ? Math.round((data.total / data.days) * 10) / 10 : 0;
  const top = data?.topics.find((t) => t.name !== "Other");

  return (
    <AdminLayout title="Questions" subtitle={data?.user ? <>Questions from <b className="font-semibold text-foreground">{data.user.name || data.user.email}</b> · <button type="button" className="font-semibold text-primary hover:underline" onClick={() => { setParams({}); setPage(0); }}>Show everyone</button></> : "What people ask Krish, and who asked"}
      actions={
        <div className="flex flex-1 rounded-lg border border-border bg-card p-0.5 sm:flex-none" role="tablist" data-testid="questions-range">
          {RANGES.map(([d, label]) => (
            <button key={d} type="button" role="tab" aria-selected={days === d} onClick={() => { setDays(d); setPage(0); }}
              className={`flex-1 whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-semibold transition-colors sm:flex-none ${days === d ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}>{label}</button>
          ))}
        </div>
      }>
      {error && !data ? <p className="mt-10 text-center text-sm text-destructive">{error}</p> : !data ? (
        <div className="flex justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      ) : (
        <div data-testid="admin-questions">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Tile label="Questions" value={num(data.total)} foot={data.capped ? "Latest 5,000 read" : `In the last ${RANGES.find(([d]) => d === days)[1]}`} />
            <Tile label="Per day" value={num(avg)} foot="On average" />
            <Tile label="Top topic" value={top ? `${top.share}%` : "–"} foot={top ? top.name : "No topic yet"} />
            <Tile label="In App Builder" value={num(data.where.find((w) => w.name === "App Builder")?.count || 0)} foot={`${num(data.where.find((w) => w.name === "Chat")?.count || 0)} in chat`} />
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-5">
            <Panel className="lg:col-span-3" title="Questions per day" subtitle="India time" testId="questions-daily">
              <div className="h-44 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.daily} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
                    <XAxis dataKey="day" tickFormatter={dayTick} tick={{ fontSize: 10, fill: "var(--viz-axis)" }} axisLine={false} tickLine={false} minTickGap={18} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "var(--viz-axis)" }} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{ fill: "var(--viz-grid)" }} content={<DayTip rows={[["count", "Questions"]]} />} />
                    <RBar dataKey="count" fill="var(--viz-1)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel className="lg:col-span-2" title="Trending words" subtitle="Most used words in questions" testId="questions-words">
              {!data.words.length ? <p className="py-8 text-center text-sm text-muted-foreground">Not enough questions yet.</p> : (
                <div className="flex flex-wrap gap-1.5">
                  {data.words.map((w) => (
                    <button key={w.word} type="button" onClick={() => { setTyped(w.word); }}
                      className="rounded-md border border-border/80 bg-background px-2 py-1 text-[12px] hover:border-foreground/40">
                      {w.word} <span className="tabular-nums text-muted-foreground">{w.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            <Panel title="Topics" subtitle="Tap one to see its questions" testId="questions-topics" flush>
              <ul className="divide-y divide-border/50">
                {data.topics.map((t) => (
                  <li key={t.name}>
                    <button type="button" onClick={() => pick(t.name)} data-testid="questions-topic"
                      className={`w-full px-4 py-2.5 text-left transition-colors ${topic === t.name ? "bg-muted" : "hover:bg-muted/50"}`}>
                      <div className="flex items-baseline justify-between gap-2 text-[13px]">
                        <span className="truncate font-semibold">{t.name}</span>
                        <span className="shrink-0 tabular-nums"><b>{num(t.count)}</b> <span className="text-[11px] text-muted-foreground">{t.share}%</span></span>
                      </div>
                      <div className="mt-1.5"><Bar value={t.count} max={topMax} /></div>
                    </button>
                  </li>
                ))}
                {!data.topics.length && <li className="px-4 py-8 text-center text-sm text-muted-foreground">No questions yet.</li>}
              </ul>
            </Panel>

            <Panel className="lg:col-span-2" testId="questions-list" flush
              title={topic ? `${topic}` : "All questions"}
              subtitle={`${num(data.matching)} question${data.matching === 1 ? "" : "s"}${q ? ` with "${q}"` : ""}, newest first`}
              action={
                <div className="flex w-full items-center gap-2 sm:w-auto">
                  <div className="relative flex-1 sm:w-56 sm:flex-none">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Search questions or people" className="h-8 pl-8 pr-7 text-xs" data-testid="questions-search" />
                    {typed && <button type="button" onClick={() => setTyped("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label="Clear"><X className="h-3.5 w-3.5" /></button>}
                  </div>
                  {topic && <button type="button" onClick={() => pick(topic)} className="shrink-0 rounded-md border border-border px-2 py-1 text-[11px] font-medium hover:bg-muted">Clear topic</button>}
                </div>
              }>
              <ul className={`divide-y divide-border/50 ${loading ? "opacity-60" : ""}`}>
                {data.questions.map((x, i) => (
                  <li key={`${x.at}-${i}`} className="px-4 py-3">
                    <p className="whitespace-pre-wrap break-words text-[13.5px] leading-relaxed">{x.text}</p>
                    <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
                      <Link to={`/admin/users/${x.userId}`} className="inline-flex min-w-0 items-center gap-1.5 font-semibold text-foreground hover:underline" title={x.email} data-testid="question-person">
                        <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-foreground text-[9px] font-bold text-background">{(x.name || "?")[0].toUpperCase()}</span>
                        <span className="truncate">{x.name}</span>
                      </Link>
                      <span className="max-sm:hidden">{x.email}</span>
                      <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 font-medium text-foreground/80">{x.topic}</span>
                      <span className="inline-flex items-center gap-1">{x.where === "App Builder" ? <Hammer className="h-3 w-3" /> : <MessageSquare className="h-3 w-3" />}{x.where}</span>
                      <span title={when(x.at)}>{ago(x.at)}</span>
                    </p>
                  </li>
                ))}
                {!data.questions.length && <li className="px-4 py-10 text-center text-sm text-muted-foreground">No questions match.</li>}
              </ul>
              {data.pages > 1 && (
                <div className="flex items-center justify-between border-t border-border/60 px-4 py-2.5 text-[12px]">
                  <button type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="inline-flex items-center gap-1 rounded-md px-2 py-1 font-medium hover:bg-muted disabled:opacity-40"><ChevronLeft className="h-3.5 w-3.5" />Newer</button>
                  <span className="text-muted-foreground">Page {page + 1} of {data.pages}</span>
                  <button type="button" disabled={page + 1 >= data.pages} onClick={() => setPage((p) => p + 1)} className="inline-flex items-center gap-1 rounded-md px-2 py-1 font-medium hover:bg-muted disabled:opacity-40">Older<ChevronRight className="h-3.5 w-3.5" /></button>
                </div>
              )}
            </Panel>
          </div>

          <p className="mt-5 flex items-start gap-2 text-[11.5px] leading-relaxed text-muted-foreground">
            <LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            Questions show who asked them, as the privacy policy says. Emails and phone numbers inside questions are hidden, and Counsellor chats and automation tasks are never included.
          </p>
        </div>
      )}
    </AdminLayout>
  );
}
