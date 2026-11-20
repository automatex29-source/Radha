import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChevronRight, Loader2, LockKeyhole } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { Bar, DayTip, FeatureIcon, PLAN_DOT, Panel, RangePicker, Tile, ago, compact, dayTick, num } from "@/components/ActivityParts";

/** Across everyone: most used features, how many people use each, active people per day, the most active people. */
export default function ActivityTab() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.get("/admin/activity", { params: { days } }).then(({ data }) => setData(data)).catch((e) => setError(formatApiError(e)));
  }, [days]);

  if (error && !data) return <p className="mt-10 text-center text-sm text-destructive">{error}</p>;
  if (!data) return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;
  const s = data.summary;
  const fMax = Math.max(1, ...data.features.map((f) => f.count));
  const rangeLabel = days === 365 ? "year" : `${days} days`;

  return (
    <div className="owner-viz mt-6" data-testid="owner-activity">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">Tap anyone to see what they did.</p>
        <RangePicker days={days} onChange={setDays} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="owner-activity-tiles">
        <Tile label="Active people" value={num(s.activePeople)} foot={`Of ${num(s.totalPeople)} · ${num(s.newPeople)} new`} />
        <Tile label="Per day" value={num(s.avgDaily)} foot="Average active people" />
        <Tile label="Actions" value={num(s.actions)} foot={`Feature uses in ${rangeLabel}`} />
        <Tile label="AI tokens" value={compact(s.tokens)} foot={`${num(s.quiet)} people were quiet`} />
      </div>

      <Panel className="mt-3" title="Active people per day" subtitle="India time" testId="owner-activity-daily">
        <div className="h-44 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.daily} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient id="act-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--viz-1)" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="var(--viz-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
              <XAxis dataKey="day" tickFormatter={dayTick} tick={{ fontSize: 10, fill: "var(--viz-axis)" }} axisLine={false} tickLine={false} minTickGap={18} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "var(--viz-axis)" }} axisLine={false} tickLine={false} />
              <Tooltip content={<DayTip rows={[["active", "Active people"]]} />} />
              <Area type="monotone" dataKey="active" stroke="var(--viz-1)" strokeWidth={2} fill="url(#act-fill)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Panel title="Most used features" subtitle="Uses, and how many of the active people tried each" testId="owner-activity-features" flush>
          <ul className="divide-y divide-border/50">
            {data.features.map((f) => (
              <li key={f.kind} className={`flex items-center gap-3 px-4 py-2.5 ${f.count ? "" : "opacity-55"}`}>
                <FeatureIcon kind={f.kind} className="h-7 w-7" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2 text-[13px]">
                    <span className="truncate font-semibold">{f.label}</span>
                    <span className="shrink-0 font-bold tabular-nums">{num(f.count)}</span>
                  </div>
                  <div className="mt-1"><Bar value={f.count} max={fMax} /></div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{num(f.people)} {f.people === 1 ? "person" : "people"} · {f.share}% of active</p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Most active people" subtitle={`By feature uses in the last ${rangeLabel}`} testId="owner-activity-people" flush>
          {!data.topPeople.length ? <p className="px-4 py-10 text-center text-sm text-muted-foreground">No one used a feature in this period yet.</p> : (
            <ul className="divide-y divide-border/50">
              {data.topPeople.map((p, i) => (
                <li key={p.userId}>
                  <Link to={`/admin/users/${p.userId}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50" data-testid="owner-activity-person">
                    <span className="w-4 shrink-0 text-right text-[11px] font-semibold tabular-nums text-muted-foreground">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-1.5 truncate text-[13px] font-semibold">{p.name || p.email}<span className={`h-1.5 w-1.5 shrink-0 rounded-full ${PLAN_DOT[p.plan] || PLAN_DOT.basic}`} title={p.plan} /></p>
                      <p className="truncate text-[11px] text-muted-foreground">Mostly {p.favourite?.toLowerCase() || "–"} · {p.featuresUsed} feature{p.featuresUsed === 1 ? "" : "s"} · {ago(p.lastSeenAt).toLowerCase()}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-[13px] font-bold tabular-nums">{num(p.actions)}</p>
                      <p className="text-[10.5px] text-muted-foreground">{compact(p.tokens)} tokens</p>
                    </div>
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <p className="mt-4 flex items-start gap-2 text-[11.5px] text-muted-foreground"><LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0" />Counts only. No one's chats or prompts are read for these numbers.</p>
    </div>
  );
}
