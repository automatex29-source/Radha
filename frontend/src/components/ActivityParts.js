import {
  AppWindow, Bot, Brain, FileText, Globe, Hammer, Image as ImageIcon, LogIn, MessageSquare, Mic, Presentation,
  Upload, Video, Zap,
} from "lucide-react";

/** Pieces shared by the owner's Activity tab and a person's activity page. */
export const FEATURE_ICON = {
  chat: MessageSquare, web: Globe, think: Brain, voice: Mic, picture: ImageIcon, video: Video, deck: Presentation,
  doc: FileText, build: Hammer, app: AppWindow, automation: Zap, upload: Upload, file: FileText, login: LogIn,
};
export const FEATURE_TONE = {
  chat: "text-sky-600 bg-sky-500/10 dark:text-sky-300", web: "text-emerald-600 bg-emerald-500/10 dark:text-emerald-300",
  think: "text-violet-600 bg-violet-500/10 dark:text-violet-300", voice: "text-rose-600 bg-rose-500/10 dark:text-rose-300",
  picture: "text-amber-600 bg-amber-500/10 dark:text-amber-300", video: "text-orange-600 bg-orange-500/10 dark:text-orange-300",
  deck: "text-fuchsia-600 bg-fuchsia-500/10 dark:text-fuchsia-300", doc: "text-blue-600 bg-blue-500/10 dark:text-blue-300",
  build: "text-teal-600 bg-teal-500/10 dark:text-teal-300", app: "text-cyan-600 bg-cyan-500/10 dark:text-cyan-300",
  automation: "text-yellow-600 bg-yellow-500/10 dark:text-yellow-300", upload: "text-slate-600 bg-slate-500/10 dark:text-slate-300",
  file: "text-indigo-600 bg-indigo-500/10 dark:text-indigo-300", login: "text-slate-600 bg-slate-500/10 dark:text-slate-300",
};
export const RANGE_DAYS = [[7, "7 days"], [30, "30 days"], [90, "90 days"], [365, "1 year"]];
export const PLAN_DOT = { basic: "bg-slate-400 dark:bg-slate-500", pro: "bg-[var(--viz-1)]", max: "bg-[var(--viz-2)]" };

export const num = (n) => Number(n || 0).toLocaleString("en-IN");
export const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e4 ? `${Math.round(n / 1e3)}k` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : num(n));

export function ago(iso) {
  if (!iso) return "Never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export const dayTick = (d) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
export const dayLong = (d) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });

export function FeatureIcon({ kind, className = "h-8 w-8" }) {
  const Icon = FEATURE_ICON[kind] || Bot;
  return (
    <span className={`inline-flex shrink-0 items-center justify-center rounded-lg ${FEATURE_TONE[kind] || FEATURE_TONE.login} ${className}`}>
      <Icon className="h-[55%] w-[55%]" />
    </span>
  );
}

export function Panel({ title, subtitle, action, children, className = "", testId, flush }) {
  return (
    <section className={`min-w-0 rounded-xl border border-border/80 bg-card shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${className}`} data-testid={testId}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-border/60 px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[11.5px] text-muted-foreground">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

export function Tile({ label, value, foot, testId }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/80 bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]" data-testid={testId}>
      <p className="truncate text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1.5 text-[24px] font-bold leading-none tabular-nums tracking-tight">{value}</p>
      {foot && <p className="mt-1.5 truncate text-[11.5px] text-muted-foreground">{foot}</p>}
    </div>
  );
}

export function Bar({ value, max, className = "bg-[var(--viz-1)]" }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full ${className}`} style={{ width: `${max ? Math.max(value ? 3 : 0, Math.min(100, (value / max) * 100)) : 0}%` }} />
    </div>
  );
}

export function RangePicker({ days, onChange }) {
  return (
    <div className="flex rounded-lg border border-border bg-card p-0.5" role="tablist" data-testid="activity-range">
      {RANGE_DAYS.map(([d, label]) => (
        <button key={d} type="button" role="tab" aria-selected={days === d} onClick={() => onChange(d)}
          className={`flex-1 whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-semibold transition-colors sm:flex-none ${days === d ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function DayTip({ active, payload, label, rows }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-36 rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-muted-foreground">{dayLong(label)}</p>
      {rows.map(([key, name]) => {
        const p = payload.find((x) => x.dataKey === key);
        return p ? <p key={key} className="flex justify-between gap-4"><span>{name}</span><span className="font-semibold tabular-nums">{num(p.value)}</span></p> : null;
      })}
    </div>
  );
}
