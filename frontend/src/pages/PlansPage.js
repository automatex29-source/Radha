import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Check, Crown, Loader2, X } from "lucide-react";

const DAILY = [
  { key: "build", label: "App builds", one: "app build", many: "app builds" },
  { key: "picture", label: "AI pictures", one: "AI picture", many: "AI pictures" },
  { key: "deck", label: "New decks", one: "new deck", many: "new decks" },
  { key: "video", label: "Videos", one: "video", many: "videos" },
];

const TAGLINE = {
  basic: "Everything you need to get started.",
  pro: "For creators who build every day.",
  max: "For businesses and power users.",
};

function features(plan) {
  return [
    { ok: true, text: "Unlimited chat and search" },
    ...DAILY.map((d) => ({ ok: true, text: `${plan.daily[d.key]} ${plan.daily[d.key] === 1 ? d.one : d.many} a day` })),
    { ok: true, text: `${plan.total.automation} automation${plan.total.automation === 1 ? "" : "s"}` },
    { ok: plan.publish, text: "Publish apps to the web" },
    { ok: plan.premium, text: "Premium AI models" },
  ];
}

function Usage({ usage }) {
  return (
    <section className="mt-10 rounded-3xl border border-border/70 bg-card/80 p-6 shadow-sm backdrop-blur" data-testid="plans-usage">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-extrabold tracking-tight">Used today</h2>
        <p className="text-xs text-muted-foreground">Refills at midnight (India time). Chat is never counted.</p>
      </div>
      <div className="mt-5 grid gap-x-8 gap-y-5 sm:grid-cols-2">
        {[...DAILY, { key: "automation", label: "Automations (total)" }].map((d) => {
          const u = usage[d.key];
          const pct = Math.min(100, Math.round((u.used / Math.max(1, u.limit)) * 100));
          return (
            <div key={d.key}>
              <div className="flex justify-between text-sm"><span className="font-medium">{d.label}</span>
                <span className="tabular-nums text-muted-foreground">{u.used} of {u.limit}</span></div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-strong">
                <div className={`h-full rounded-full ${pct >= 100 ? "bg-rose-500" : "bg-gradient-to-r from-slate-700 to-slate-900"}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function PlanCard({ plan, current }) {
  const popular = plan.id === "pro";
  return (
    <div data-testid={`plan-${plan.id}`}
      className={`relative flex flex-col rounded-3xl p-6 transition-shadow sm:p-7 ${popular
        ? "bg-card shadow-[0_18px_50px_-20px_rgba(15,23,42,0.30)] ring-2 ring-foreground/80"
        : "border border-border/70 bg-card/80 shadow-sm backdrop-blur"}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl font-extrabold tracking-tight">{plan.name}</h2>
        {current ? <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">Your plan</span>
          : popular ? <span className="rounded-full bg-primary px-2.5 py-1 text-[11px] font-semibold text-primary-foreground">Most popular</span> : null}
      </div>
      <p className="mt-1.5 text-sm text-muted-foreground">{TAGLINE[plan.id]}</p>
      <div className="mt-6 flex items-baseline gap-1.5">
        <span className="text-[2.6rem] font-extrabold leading-none tracking-tight tabular-nums">₹{plan.price}</span>
        <span className="text-sm text-muted-foreground">{plan.price ? "/ month" : "forever"}</span>
      </div>
      <div className="my-6 h-px bg-border/70" />
      <ul className="flex-1 space-y-3 text-[0.9rem]">
        {features(plan).map((f) => (
          <li key={f.text} className={`flex items-start gap-2.5 ${f.ok ? "text-foreground/90" : "text-muted-foreground/70"}`}>
            <span className={`mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full ${f.ok ? "bg-secondary text-foreground" : "bg-muted text-muted-foreground"}`}>
              {f.ok ? <Check className="h-3 w-3" strokeWidth={3} /> : <X className="h-3 w-3" strokeWidth={3} />}
            </span>
            {f.text}
          </li>
        ))}
      </ul>
      <Button disabled data-testid={`plan-button-${plan.id}`}
        className={`mt-7 h-11 w-full rounded-xl font-semibold disabled:opacity-100 ${popular && !current
          ? "bg-primary text-primary-foreground" : "border border-border bg-transparent text-muted-foreground"}`}>
        {current ? "Current plan" : plan.price ? "Coming soon" : "Free"}
      </Button>
    </div>
  );
}

/** The three plans (Basic, Pro, Max), the user's current one and what they've used today. */
export default function PlansPage() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/usage").then(({ data }) => setData(data)).catch((e) => toast.error(formatApiError(e)));
  }, []);

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl px-4 pb-12 pt-10 sm:px-6 sm:pt-14">
          <header className="text-center">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-card/70 px-3 py-1 text-xs font-medium text-muted-foreground">
              <Crown className="h-3.5 w-3.5 text-primary" /> Plans
            </span>
            <h1 className="mt-4 text-[1.9rem] font-extrabold leading-[1.1] tracking-tight sm:text-[2.6rem]">
              Choose the plan that <span className="krish-gradient-text">fits you</span>
            </h1>
            <p className="mx-auto mt-3 max-w-md text-[0.95rem] text-muted-foreground">Chat is unlimited on every plan. Upgrade for more app builds, pictures, decks and videos.</p>
          </header>

          {!data ? (
            <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : (
            <>
              <div className="mt-10 grid gap-5 md:grid-cols-3" data-testid="plans-grid">
                {data.plans.map((p) => <PlanCard key={p.id} plan={p} current={p.id === data.plan} />)}
              </div>
              <p className="mt-5 text-center text-xs text-muted-foreground">Payments are coming soon. Pro and Max will open here when they're ready.</p>
              {data.limitsOn && <Usage usage={data.usage} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
