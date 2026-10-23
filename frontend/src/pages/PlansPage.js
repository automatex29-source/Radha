import { useCallback, useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Check, Crown, Gauge, Gift, Loader2, Tag, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import InviteDialog from "@/components/InviteDialog";
import { PlanSheet, PlanWelcome } from "@/components/PlanSheet";
import { useNavigate } from "react-router-dom";

const TAGLINE = {
  basic: "Everything you need to get started.",
  pro: "For creators who build every day.",
  max: "For businesses and power users.",
};

// How much more a plan can make than Basic, by the size of their usage meters.
function times(plan, basic) {
  return basic ? Math.round(plan.meter.session / basic.meter.session) : 1;
}

// How Krish works on each plan (limits.work_of), in plain words.
function workFeatures(plan) {
  const w = plan.work;
  const every = w.automationMinutes >= 1440 ? "once a day" : w.automationMinutes >= 60 ? "every hour" : `every ${w.automationMinutes} minutes`;
  return [
    { ok: true, text: { free: "Krish Basic answers every question", hard: "Premium AI on hard questions, automatically", all: "Our strongest AI on every answer" }[w.model] },
    { ok: true, text: `Web search: up to ${w.searches} searches and ${w.results} results each` },
    { ok: true, text: w.model === "free" ? "App Builder on the free model" : `App Builder on premium AI, ${w.builderSteps} steps and ${w.repairRounds} rounds of self-checks` },
    { ok: w.research > 1, text: "Deep Research twice as deep" },
    { ok: true, text: `Automations can repeat ${every}` },
    { ok: w.priority, text: "Automations get their own lane, never wait in line" },
  ];
}

function features(plan, basic) {
  const x = times(plan, basic);
  return [
    { ok: true, text: "Unlimited chat and search" },
    { ok: true, text: x > 1 ? `${x}x the usage of Basic for builds, pictures, decks and videos` : "Builds, pictures, decks and videos" },
    { ok: true, text: "Usage refills every 5 hours" },
    { ok: true, text: `${plan.total.automation} automation${plan.total.automation === 1 ? "" : "s"}` },
    { ok: plan.publish, text: "Publish apps to the web" },
    ...workFeatures(plan),
    { ok: plan.quality.media === "premium", text: plan.work.pictureSize === "4K" ? "4K pictures and real AI video" : "HD pictures and real AI video" },
    { ok: plan.premium, text: "Think mode on our smartest model" },
    { ok: true, text: `Videos up to ${plan.quality.videoSeconds} seconds` },
    { ok: true, text: `Uploads up to ${plan.quality.uploadMb}MB` },
    { ok: true, text: "Remembers what you tell it, in every chat" },
  ];
}

const ORDER = ["basic", "pro", "max"];

// Razorpay's checkout window (UPI, cards, net banking, wallets), loaded only when someone pays.
let checkoutScript;
function loadCheckout() {
  if (window.Razorpay) return Promise.resolve();
  checkoutScript = checkoutScript || new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = resolve;
    s.onerror = () => { checkoutScript = null; reject(new Error("The payment window couldn't load. Check your internet and try again.")); };
    document.body.appendChild(s);
  });
  return checkoutScript;
}

function untilText(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function resetText(ts) {
  if (!ts) return null;
  const mins = Math.max(1, Math.round((ts * 1000 - Date.now()) / 60000));
  if (mins < 20 * 60) {
    const at = new Date(ts * 1000).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    return `Refills at ${at} (in ${mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`})`;
  }
  return `Refills on ${new Date(ts * 1000).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}`;
}

function MeterBar({ label, part, idle, testid }) {
  const pct = Math.min(100, Math.round((part.used / Math.max(1, part.limit)) * 100));
  return (
    <div data-testid={testid}>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-semibold">{label}</span>
        <span className="tabular-nums text-muted-foreground"><b className="text-foreground">{pct}%</b> used</span>
      </div>
      <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-surface-strong">
        <div className={`h-full rounded-full transition-all ${pct >= 100 ? "bg-rose-500" : pct >= 80 ? "bg-amber-500" : "bg-gradient-to-r from-indigo-500 to-violet-500"}`}
          style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{resetText(part.resetsAt) || idle}</p>
    </div>
  );
}

/** The usage meter, like Claude's: every build, picture, deck and video runs it down by how big it is. */
function Usage({ meter, costs, automation }) {
  const range = (r) => (r[0] === r[1] ? `${r[0]}` : `${r[0]}-${r[1]}`);
  return (
    <section className="mt-10 rounded-3xl border border-border/70 bg-card/80 p-6 shadow-sm backdrop-blur" data-testid="plans-usage">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-extrabold tracking-tight"><Gauge className="h-5 w-5 text-indigo-500" /> Your usage</h2>
        <p className="text-xs text-muted-foreground">Chat on Krish Basic is never counted.</p>
      </div>
      <div className="mt-5 grid gap-x-8 gap-y-5 sm:grid-cols-2">
        <MeterBar label="This session" part={meter.session} testid="meter-session"
          idle={`Starts when you make something, then refills ${meter.session.hours} hours later`} />
        <MeterBar label="This week" part={meter.week} testid="meter-week" idle="Starts when you make something" />
      </div>
      <div className="mt-6 rounded-2xl bg-surface p-4" data-testid="meter-costs">
        <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">What things use</p>
        <p className="mt-1 text-xs text-muted-foreground">Bigger requests use more: a longer build ask, a longer video, a longer chat.</p>
        <ul className="mt-2 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>App build</span><span className="tabular-nums text-muted-foreground">{range(costs.build)} credits</span></li>
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>AI picture</span><span className="tabular-nums text-muted-foreground">{costs.picture} credits</span></li>
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>Slide deck</span><span className="tabular-nums text-muted-foreground">{costs.deck} + pictures</span></li>
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>Video</span><span className="tabular-nums text-muted-foreground">{costs.videoSecond} a second</span></li>
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>Premium message</span><span className="tabular-nums text-muted-foreground">{range(costs.chat)} credits</span></li>
        </ul>
      </div>
      <p className="mt-4 text-xs text-muted-foreground" data-testid="meter-automations">
        Automations: {automation.used} of {automation.limit}
      </p>
    </section>
  );
}

function PlanCard({ plan, basic, current, currentPlan, paymentsOn, expires, busy, onBuy, offer }) {
  const popular = plan.id === "pro";
  const lower = ORDER.indexOf(plan.id) < ORDER.indexOf(currentPlan);
  const canBuy = paymentsOn && plan.price > 0 && !lower;
  const price = offer && plan.price ? offer.prices[plan.id] ?? plan.price : plan.price;
  return (
    <div data-testid={`plan-${plan.id}`}
      className={`relative flex flex-col rounded-3xl p-6 transition-shadow sm:p-7 ${popular
        ? "bg-gradient-to-b from-indigo-500/[0.07] to-violet-500/[0.03] shadow-[0_18px_50px_-20px_rgba(99,102,241,0.45)] ring-1 ring-indigo-400/50 dark:from-indigo-500/15"
        : "border border-border/70 bg-card/80 shadow-sm backdrop-blur"}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl font-extrabold tracking-tight">{plan.name}</h2>
        {current ? <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">Your plan</span>
          : popular ? <span className="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-2.5 py-1 text-[11px] font-semibold text-white">Most popular</span> : null}
      </div>
      <p className="mt-1.5 text-sm text-muted-foreground">{TAGLINE[plan.id]}</p>
      <div className="mt-6 flex items-baseline gap-1.5">
        {price !== plan.price && <span className="text-lg font-semibold text-muted-foreground line-through tabular-nums">₹{plan.price}</span>}
        <span className="text-[2.6rem] font-extrabold leading-none tracking-tight tabular-nums">₹{price}</span>
        <span className="text-sm text-muted-foreground">{plan.price ? "/ month" : "forever"}</span>
      </div>
      <div className="my-6 h-px bg-border/70" />
      <ul className="flex-1 space-y-3 text-[0.9rem]">
        {features(plan, basic).map((f) => (
          <li key={f.text} className={`flex items-start gap-2.5 ${f.ok ? "text-foreground/90" : "text-muted-foreground/70"}`}>
            <span className={`mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full ${f.ok ? "bg-indigo-500/10 text-indigo-600 dark:text-indigo-300" : "bg-muted text-muted-foreground"}`}>
              {f.ok ? <Check className="h-3 w-3" strokeWidth={3} /> : <X className="h-3 w-3" strokeWidth={3} />}
            </span>
            {f.text}
          </li>
        ))}
      </ul>
      <Button disabled={!canBuy || busy} onClick={() => onBuy(plan.id)} data-testid={`plan-button-${plan.id}`}
        className={`mt-7 h-11 w-full rounded-xl font-semibold disabled:opacity-100 ${canBuy && (popular || current)
          ? "bg-gradient-to-r from-indigo-500 to-violet-500 text-white" : canBuy ? "bg-foreground text-background"
          : "border border-border bg-transparent text-muted-foreground"}`}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" />
          : !plan.price ? (current ? "Current plan" : "Free")
          : !paymentsOn ? (current ? "Current plan" : "Coming soon")
          : current ? `Add a month · ₹${price}` : lower ? "Included in your plan" : `Get ${plan.name} · ₹${price}`}
      </Button>
      {current && expires && <p className="mt-2.5 text-center text-xs text-muted-foreground">Active until {untilText(expires)}</p>}
    </div>
  );
}

/** The three plans (Basic, Pro, Max), the user's current one and what they've used today. */
export default function PlansPage() {
  const [data, setData] = useState(null);
  const [buying, setBuying] = useState(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [codeText, setCodeText] = useState("");
  const [offer, setOffer] = useState(null); // {code, percentOff, prices: {pro, max}} once a code checks out
  const [checking, setChecking] = useState(false);

  const applyCode = async (e) => {
    e.preventDefault();
    const code = codeText.trim();
    if (!code) return;
    setChecking(true);
    try {
      const results = await Promise.allSettled(["pro", "max"].map((plan) => api.post("/billing/check-code", { plan, code })));
      const ok = results.filter((r) => r.status === "fulfilled").map((r) => r.value.data);
      if (!ok.length) throw results[0].reason;
      const prices = {};
      results.forEach((r, i) => { if (r.status === "fulfilled") prices[["pro", "max"][i]] = r.value.data.price; });
      setOffer({ code: ok[0].code, percentOff: ok[0].percentOff, prices });
      toast.success(`${ok[0].code} applied: ${ok[0].percentOff}% off`);
    } catch (err) {
      setOffer(null);
      toast.error(formatApiError(err));
    } finally { setChecking(false); }
  };
  const { user, setUser } = useAuth() || {};
  const navigate = useNavigate();
  const [picked, setPicked] = useState(null); // the plan whose "what you get" window is open
  const [welcome, setWelcome] = useState(null); // {plan, until} after a payment went through
  const priceOf = (plan) => (offer && offer.prices[plan.id]) ?? plan.price;

  const load = useCallback(() => {
    api.get("/usage").then(({ data }) => setData(data)).catch((e) => toast.error(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const buy = async (planId) => {
    setBuying(planId);
    try {
      const [{ data: order }] = await Promise.all([api.post("/billing/order", { plan: planId, code: offer && offer.prices[planId] ? offer.code : "" }), loadCheckout()]);
      await new Promise((resolve) => {
        const rzp = new window.Razorpay({
          key: order.keyId, order_id: order.orderId, amount: order.amount, currency: order.currency,
          name: "Krish AI", description: `${order.planName} plan · 1 month`,
          prefill: { name: order.name, email: order.email },
          theme: { color: "#6366f1" },
          handler: async (res) => {
            try {
              const { data: account } = await api.post("/billing/verify", {
                orderId: res.razorpay_order_id, paymentId: res.razorpay_payment_id, signature: res.razorpay_signature,
              });
              setUser?.(account);
              setWelcome({ plan: data.plans.find((p) => p.id === planId),
                until: account.planExpiresAt ? untilText(account.planExpiresAt) : "" });
              setOffer(null);
              setCodeText("");
              load();
            } catch (e) {
              toast.error(formatApiError(e));
            }
            resolve();
          },
          modal: { ondismiss: resolve },
        });
        rzp.on("payment.failed", (r) => toast.error(r?.error?.description || "The payment didn't go through. No money was taken."));
        rzp.open();
      });
    } catch (e) {
      toast.error(e?.response ? formatApiError(e) : e.message);
    } finally {
      setBuying(null);
    }
  };

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
                {data.plans.map((p) => (
                  <PlanCard key={p.id} plan={p} basic={data.plans.find((x) => x.id === "basic")} current={p.id === data.plan} currentPlan={data.plan}
                    paymentsOn={data.paymentsOn} expires={data.planExpiresAt} busy={buying === p.id} onBuy={(id) => setPicked(data.plans.find((x) => x.id === id))} offer={offer} />
                ))}
              </div>
              <p className="mt-5 text-center text-xs text-muted-foreground">
                {data.paymentsOn
                  ? "Pay once for 30 days with UPI, card, net banking or a wallet. No auto-renewal: pay again whenever you like to add another month."
                  : "Payments are coming soon. Pro and Max will open here when they're ready."}
              </p>
              {data.paymentsOn && (
                <form onSubmit={applyCode} className="mx-auto mt-6 flex max-w-sm items-center gap-2" data-testid="offer-code-form">
                  <div className="relative flex-1">
                    <Tag className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input value={codeText} onChange={(e) => setCodeText(e.target.value)} placeholder="Have an offer code?" maxLength={24}
                      className="h-10 rounded-xl pl-9 uppercase placeholder:normal-case" data-testid="offer-code-input" />
                  </div>
                  <Button type="submit" variant="outline" disabled={checking || !codeText.trim()} className="h-10 rounded-xl" data-testid="offer-code-apply">
                    {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : offer ? "Applied" : "Apply"}
                  </Button>
                </form>
              )}
              <button type="button" onClick={() => setInviteOpen(true)} data-testid="plans-invite"
                className="mx-auto mt-8 flex w-full max-w-xl items-center gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3 text-left transition-colors hover:bg-emerald-500/10">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"><Gift className="h-4 w-4" /></span>
                <span className="text-sm"><b>Get Pro free:</b> invite a friend and you both get 7 days of Pro.</span>
              </button>
              {data.limitsOn && <Usage meter={data.meter} costs={data.costs} automation={data.usage.automation} />}
            </>
          )}
        </div>
      </main>
      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} />
      {picked && data && (
        <PlanSheet plan={picked} current={data.plans.find((p) => p.id === data.plan)} basic={data.plans.find((p) => p.id === "basic")} user={user} price={priceOf(picked)}
          offer={offer} busy={buying === picked.id} onPay={() => { const id = picked.id; setPicked(null); buy(id); }} onClose={() => !buying && setPicked(null)} />
      )}
      <PlanWelcome plan={welcome?.plan} user={user} until={welcome?.until} onClose={() => setWelcome(null)}
        onStart={() => { setWelcome(null); navigate("/"); }} />
    </div>
  );
}
