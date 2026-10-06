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
  pro: "For creators who build and make every day.",
  max: "For businesses and power users.",
};

function features(plan) {
  return [
    { ok: true, text: "Unlimited chat, search and Counsellor" },
    ...DAILY.map((d) => ({ ok: true, text: `${plan.daily[d.key]} ${plan.daily[d.key] === 1 ? d.one : d.many} a day` })),
    { ok: true, text: `${plan.total.automation} automation${plan.total.automation === 1 ? "" : "s"}` },
    { ok: plan.publish, text: "Publish apps to the web" },
    { ok: plan.premium, text: "Premium AI models" },
  ];
}

function Usage({ usage }) {
  return (
    <div className="mt-6 rounded-2xl border border-border bg-card p-5 shadow-sm" data-testid="plans-usage">
      <h2 className="text-sm font-semibold">Used today</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">Refills every night at 12 (India time). Chat is never counted.</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {[...DAILY, { key: "automation", label: "Automations (total)" }].map((d) => {
          const u = usage[d.key];
          const pct = Math.min(100, Math.round((u.used / Math.max(1, u.limit)) * 100));
          return (
            <div key={d.key}>
              <div className="flex justify-between text-xs"><span>{d.label}</span><span className="text-muted-foreground">{u.used} / {u.limit}</span></div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface">
                <div className={`h-full rounded-full ${pct >= 100 ? "bg-destructive" : "bg-primary"}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
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
        <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
          <h1 className="flex items-center gap-2 text-2xl font-bold"><Crown className="h-6 w-6 text-primary" /> Plans</h1>
          <p className="mt-1 text-sm text-muted-foreground">Chat is unlimited on every plan. Plans set how much you can build and make each day.</p>

          {!data ? (
            <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : (
            <>
              <div className="mt-6 grid gap-4 md:grid-cols-3" data-testid="plans-grid">
                {data.plans.map((p) => {
                  const current = p.id === data.plan;
                  const popular = p.id === "pro";
                  return (
                    <div key={p.id} data-testid={`plan-${p.id}`}
                      className={`relative flex flex-col rounded-2xl border bg-card p-5 shadow-sm ${popular ? "border-primary ring-1 ring-primary/40" : "border-border"}`}>
                      {popular && <span className="absolute -top-2.5 left-5 rounded-full bg-primary px-2.5 py-0.5 text-[11px] font-semibold text-primary-foreground">Most popular</span>}
                      <div className="flex items-center justify-between">
                        <h2 className="text-lg font-bold">{p.name}</h2>
                        {current && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">Your plan</span>}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{TAGLINE[p.id]}</p>
                      <p className="mt-4"><span className="text-3xl font-bold">₹{p.price}</span><span className="text-sm text-muted-foreground">{p.price ? " / month" : " forever"}</span></p>
                      <ul className="mt-4 flex-1 space-y-2 text-sm">
                        {features(p).map((f) => (
                          <li key={f.text} className={`flex items-start gap-2 ${f.ok ? "" : "text-muted-foreground line-through"}`}>
                            {f.ok ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" /> : <X className="mt-0.5 h-4 w-4 shrink-0" />}
                            {f.text}
                          </li>
                        ))}
                      </ul>
                      <Button className="mt-5 w-full" variant={popular ? "default" : "outline"} disabled data-testid={`plan-button-${p.id}`}>
                        {current ? "Current plan" : p.price ? "Coming soon" : "Free"}
                      </Button>
                    </div>
                  );
                })}
              </div>
              <p className="mt-3 text-center text-xs text-muted-foreground">Payments are coming soon. Pro and Max will open here when they're ready.</p>
              {data.limitsOn && <Usage usage={data.usage} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
