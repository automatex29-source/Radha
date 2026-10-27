import { useCallback, useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Check, Copy, Loader2, Lock, RefreshCcw, Share2, Tag } from "lucide-react";
import { Input } from "@/components/ui/input";
import InviteDialog, { WhatsAppIcon } from "@/components/InviteDialog";
import { inviteLink, inviteMessage } from "@/lib/referral";
import { PlanSheet, PlanWelcome } from "@/components/PlanSheet";
import { useNavigate } from "react-router-dom";
import { openSettings } from "@/lib/settingsNav";

const TAGLINE = {
  basic: "Everything you need to get started.",
  pro: "For creators who build every day.",
  max: "For businesses and power users.",
};

// How much more a plan can make than Basic, by the size of their usage meters.
function times(plan, basic) {
  return basic ? Math.round(plan.meter.session / basic.meter.session) : 1;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// What each card lists: Basic in full, then what each bigger plan adds to the one before it. Video lines show only
// while making videos is switched on (VIDEO_GENERATION on the server).
function highlights(plan, basic, video) {
  const x = times(plan, basic);
  const { automation } = plan.total;
  const { videoSeconds, uploadMb } = plan.quality;
  if (plan.id === "basic") {
    return { label: "Includes", items: ["Unlimited chat and search", "Krish AI, our free model for every question",
      video ? "Builds, pictures, decks and videos" : "Builds, pictures and decks", plural(automation, "automation"), "Remembers what you tell it, in every chat"] };
  }
  if (plan.id === "max") {
    return { label: "Everything in Pro, plus", items: [`${x}x the usage of Basic`, ...(video ? [`Videos up to ${videoSeconds} seconds`] : []),
      plural(automation, "automation"), `Uploads up to ${uploadMb}MB`] };
  }
  return { label: "Everything in Basic, plus", items: [`${x}x the usage of Basic`,
    ...(plan.premium ? ["Premium AI models and Think mode"] : []),
    ...(plan.quality.media === "premium" ? [video ? "HD pictures and real AI video" : "HD AI pictures"] : []),
    ...(plan.publish ? ["Publish apps to the web"] : []),
    `${plural(automation, "automation")}, ${uploadMb}MB uploads`,
    ...(plan.premium ? ["Counsellor Pro"] : [])] };
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

function PlanCard({ plan, basic, current, currentPlan, paymentsOn, expires, busy, onBuy, offer, video, shown, autopay }) {
  const popular = plan.id === "pro";
  const lower = ORDER.indexOf(plan.id) < ORDER.indexOf(currentPlan);
  // Autopay on for this plan (or a bigger one) already renews it, so there's nothing to buy here.
  const renews = autopay && ORDER.indexOf(autopay.plan) >= ORDER.indexOf(plan.id);
  const canBuy = paymentsOn && plan.price > 0 && !lower && !renews;
  const was = plan.listPrice || plan.price; // the launch price is struck through from the regular price
  const price = offer && plan.price ? offer.prices[plan.id] ?? plan.price : plan.price;
  const { label, items } = highlights(plan, basic, video);
  const off = plan.listPrice > plan.price ? Math.round((1 - plan.price / plan.listPrice) * 100) : 0;
  return (
    <div data-testid={`plan-${plan.id}`}
      className={`plans-card relative flex-col rounded-2xl p-5 transition-transform duration-200 md:hover:-translate-y-1 ${shown ? "flex" : "hidden md:flex"} ${popular
        ? "plans-card-pop md:-translate-y-2 md:hover:-translate-y-3" : ""}`}>
      {popular && !current && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-foreground px-3 py-1 text-[11px] font-semibold text-background">Most popular</span>
      )}
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold">{plan.name}</h2>
        {current && <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">Your plan</span>}
      </div>
      <p className="mt-0.5 text-[12.5px] text-muted-foreground">{TAGLINE[plan.id]}</p>
      <div className="mt-3.5 flex items-end gap-2">
        <span className="text-[2.3rem] font-semibold leading-none tracking-tight tabular-nums">₹{price}</span>
        <span className="pb-1 text-[13px] text-muted-foreground">{plan.price ? "/ month" : "forever"}</span>
      </div>
      <div className="mt-2 flex h-5 items-center gap-2 text-[12px]">
        {price !== was && <span className="tabular-nums text-muted-foreground line-through">₹{was}</span>}
        {off > 0 && <span className="rounded-md bg-muted px-1.5 py-0.5 font-medium" data-testid={`plan-launch-${plan.id}`}>Launch price · {off}% off</span>}
      </div>
      <Button disabled={!canBuy || busy} onClick={() => onBuy(plan.id)} data-testid={`plan-button-${plan.id}`}
        className={`mt-3.5 h-10 w-full rounded-lg text-[0.88rem] font-medium shadow-none disabled:opacity-100 ${canBuy && popular
          ? "bg-foreground text-background hover:bg-foreground/90"
          : canBuy ? "border border-border bg-background text-foreground hover:bg-muted"
          : "border border-border bg-muted/50 text-muted-foreground"}`}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" />
          : !plan.price ? (current ? "Current plan" : "Free")
          : !paymentsOn ? (current ? "Current plan" : "Coming soon")
          : renews ? (current ? "Renews automatically" : "Included in your plan")
          : current ? `Add a month · ₹${price}` : lower ? "Included in your plan" : `Get ${plan.name}`}
      </Button>
      <p className="mt-1.5 h-4 text-center text-[11px] text-muted-foreground">
        {current && expires ? (renews ? `Next renewal ${untilText(expires)}` : `Active until ${untilText(expires)}`)
          : plan.price ? "Cancel anytime" : ""}
      </p>
      <div className="my-3.5 h-px bg-border" />
      <p className="mb-2 text-[12px] font-medium text-muted-foreground">{label}</p>
      <ul className="flex-1 space-y-1.5 text-[13px]">
        {items.map((text) => (
          <li key={text} className="flex items-start gap-2.5 leading-snug">
            <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={2.25} />
            {text}
          </li>
        ))}
      </ul>
    </div>
  );
}


/** Give Pro, get Pro: the person's own invite link, ready to copy or send, and the Pro days it has earned. */
function InviteFriends({ onMore }) {
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    api.get("/referrals").then(({ data }) => setData(data)).catch(() => {});
  }, []);
  const days = data?.rewardDays || 7;
  const link = data ? inviteLink(data.code) : "";
  const rewarded = data ? Math.round(data.daysEarned / Math.max(1, data.rewardDays)) : 0;
  const copy = async () => {
    if (!link) return;
    try { await navigator.clipboard.writeText(link); } catch { /* the link is on screen */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
    toast.success("Invite link copied");
  };
  return (
    <section className="plans-card grid items-center gap-3 rounded-2xl px-5 py-3.5 md:grid-cols-[1fr_1.15fr] md:gap-6" data-testid="plans-invite">
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold">Give Pro, get Pro</h2>
        <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">
          A friend joins with your link and gets {days} days of Pro, free. You get {days} days too, once.
          {data && (data.daysEarned
            ? <> <b className="font-semibold text-foreground">Your {data.daysEarned} Pro days are claimed.</b> Friends still get theirs.</>
            : null)}
        </p>
        {data && data.maxRewards > 1 && (
          <div className="mt-1.5 flex max-w-[12rem] gap-1 max-md:hidden" aria-hidden="true" data-testid="plans-invite-progress">
            {Array.from({ length: data.maxRewards }, (_, i) => (
              <span key={i} className={`h-1 flex-1 rounded-full ${i < rewarded ? "bg-foreground" : "bg-border"}`} />
            ))}
          </div>
        )}
      </div>
      <div className="flex min-w-0 items-center gap-1.5">
        <div className="flex min-w-0 flex-1 items-center gap-1.5 rounded-lg border border-border bg-background p-1 pl-2.5">
          <span className="min-w-0 flex-1 truncate text-[0.78rem] font-medium" data-testid="plans-invite-link">
            {link ? link.replace(/^https?:\/\//, "") : "Loading your link…"}
          </span>
          <Button onClick={copy} disabled={!link} data-testid="plans-invite-copy"
            className="h-7 shrink-0 rounded-md bg-foreground px-2.5 text-[0.75rem] font-medium text-background shadow-none hover:bg-foreground/90">
            {copied ? <><Check className="mr-1 h-3 w-3" /> Copied</> : <><Copy className="mr-1 h-3 w-3" /> Copy</>}
          </Button>
        </div>
        <a href={link ? `https://wa.me/?text=${encodeURIComponent(inviteMessage(link, days))}` : undefined} target="_blank" rel="noreferrer"
          data-testid="plans-invite-whatsapp" aria-disabled={!link} aria-label="Share on WhatsApp" title="WhatsApp"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-background transition-colors hover:bg-surface">
          <WhatsAppIcon className="h-4 w-4 text-[#25D366]" />
        </a>
        <button type="button" onClick={onMore} data-testid="plans-invite-more" aria-label="More ways to share" title="More ways to share"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-background transition-colors hover:bg-surface">
          <Share2 className="h-4 w-4" />
        </button>
      </div>
    </section>
  );
}

/** The three plans (Basic, Pro, Max), Counsellor Pro, inviting friends, and what the user has used. */
export default function PlansPage() {
  const [data, setData] = useState(null);
  const [buying, setBuying] = useState(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [codeText, setCodeText] = useState("");
  const [offer, setOffer] = useState(null); // {code, percentOff, prices: {pro, max}} once a code checks out
  const [checking, setChecking] = useState(false);
  const [codeOpen, setCodeOpen] = useState(false);

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
  // The plan open on phones: the next one up from the user's plan (Pro for Basic users).
  const [shown, setShown] = useState(null);
  const shownId = shown || (data && ORDER[Math.min(ORDER.indexOf(data.plan) + 1, ORDER.length - 1)]) || "pro";

  const load = useCallback(() => {
    api.get("/usage").then(({ data }) => setData(data)).catch((e) => toast.error(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const buy = async (planId) => {
    setBuying(planId);
    // Autopay (a monthly Razorpay subscription) unless an offer code is on: that's a one-time 30-day payment.
    let oneTime = !!(offer && offer.prices[planId]);
    try {
      const start = async () => {
        if (oneTime) return api.post("/billing/order", { plan: planId, code: offer.code });
        try {
          return await api.post("/billing/subscribe", { plan: planId });
        } catch (e) {
          if (e?.response?.status !== 503) throw e;
          oneTime = true; // autopay isn't available yet: pay once for 30 days instead
          return api.post("/billing/order", { plan: planId, code: "" });
        }
      };
      const [{ data: order }] = await Promise.all([start(), loadCheckout()]);
      await new Promise((resolve) => {
        const rzp = new window.Razorpay({
          key: order.keyId, ...(oneTime ? { order_id: order.orderId, amount: order.amount, currency: order.currency }
            : { subscription_id: order.subscriptionId }),
          name: "Krish AI", description: oneTime ? `${order.planName} plan · 1 month` : `${order.planName} plan · renews monthly`,
          prefill: { name: order.name, email: order.email },
          theme: { color: "#111111" },
          handler: async (res) => {
            try {
              const { data: account } = oneTime
                ? await api.post("/billing/verify", {
                  orderId: res.razorpay_order_id, paymentId: res.razorpay_payment_id, signature: res.razorpay_signature })
                : await api.post("/billing/subscribe/verify", {
                  subscriptionId: res.razorpay_subscription_id, paymentId: res.razorpay_payment_id, signature: res.razorpay_signature });
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
    <div className="flex h-dvh w-full overflow-hidden plans-canvas max-md:flex-col">
      <IconRail />
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1040px] px-4 pb-8 pt-5 sm:px-6 sm:pt-7">
          <header className="text-center">
            <h1 className="krish-display text-[1.9rem] leading-[1.05] sm:text-[2.5rem]">
              Choose the plan that <em className="text-[#4F46E5] dark:text-[#A5B4FC]">fits you</em>
            </h1>
            <p className="mx-auto mt-1.5 max-w-lg text-[0.8rem] leading-snug text-muted-foreground max-sm:hidden">Chat is unlimited on every plan. Upgrade for more app builds, {data?.video ? "pictures, decks and videos" : "pictures and decks"}.</p>
          </header>

          {!data ? (
            <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : (
            <>
              {/* Phones show one plan at a time, so all of it fits on the screen. */}
              <div role="tablist" aria-label="Plans" className="mx-auto mt-5 grid max-w-xs grid-cols-3 gap-1 rounded-xl bg-muted p-1 md:hidden" data-testid="plans-tabs">
                {data.plans.map((p) => (
                  <button key={p.id} role="tab" aria-selected={p.id === shownId} onClick={() => setShown(p.id)} data-testid={`plans-tab-${p.id}`}
                    className={`rounded-lg py-1.5 text-[0.8rem] font-medium transition-colors ${p.id === shownId ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"}`}>
                    {p.name}
                  </button>
                ))}
              </div>
              <div className="mt-6 grid gap-4 md:mt-8 md:grid-cols-3 md:items-stretch md:gap-5" data-testid="plans-grid">
                {data.plans.map((p) => (
                  <PlanCard key={p.id} plan={p} basic={data.plans.find((x) => x.id === "basic")} current={p.id === data.plan} currentPlan={data.plan}
                    paymentsOn={data.paymentsOn} expires={data.planExpiresAt} busy={buying === p.id} onBuy={(id) => setPicked(data.plans.find((x) => x.id === id))} offer={offer} video={data.video}
                    shown={p.id === shownId} autopay={data.autopay} />
                ))}
              </div>

              <div className="mt-5 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[12px] text-muted-foreground" data-testid="plans-trust">
                <span className="flex items-center gap-1.5"><Lock className="h-3.5 w-3.5" /> Secure payments by Razorpay</span>
                <span>UPI · Cards · Net banking</span>
                <span className="flex items-center gap-1.5"><RefreshCcw className="h-3.5 w-3.5" /> {data.paymentsOn ? "Renews monthly, cancel anytime" : "Payments open soon"}</span>
                {data.paymentsOn && !codeOpen && !offer && (
                  <button type="button" onClick={() => setCodeOpen(true)} className="underline underline-offset-2 hover:text-foreground" data-testid="offer-code-open">Have an offer code?</button>
                )}
              </div>
              {data.paymentsOn && (codeOpen || offer) && (
                <form onSubmit={applyCode} className="mx-auto mt-3 flex w-full max-w-[18rem] items-center gap-1.5" data-testid="offer-code-form">
                  <div className="relative flex-1">
                    <Tag className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input value={codeText} onChange={(e) => setCodeText(e.target.value)} placeholder="Offer code" maxLength={24} autoFocus
                      className="h-9 rounded-lg bg-background pl-8 text-[0.82rem] uppercase placeholder:normal-case" data-testid="offer-code-input" />
                  </div>
                  <Button type="submit" variant="outline" disabled={checking || !codeText.trim()} className="h-9 rounded-lg px-3 text-[0.82rem]" data-testid="offer-code-apply">
                    {checking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : offer ? "Applied" : "Apply"}
                  </Button>
                </form>
              )}
              {offer && <p className="mt-1.5 text-center text-[11px] text-muted-foreground">{offer.code} applied: a one-time payment for 30 days, no autopay.</p>}

              <div className="mt-5"><InviteFriends onMore={() => setInviteOpen(true)} /></div>
              <p className="mt-4 text-center text-[12px] text-muted-foreground">
                See how much you've used in <button type="button" onClick={() => openSettings("usage")} className="underline underline-offset-2 hover:text-foreground" data-testid="plans-usage-link">Settings &gt; Usage</button>
                {" "}· Questions? <a href="/refunds" className="underline underline-offset-2 hover:text-foreground">Refunds and cancelling</a>
              </p>
            </>
          )}
        </div>
      </main>
      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} />
      {picked && data && (
        <PlanSheet plan={picked} current={data.plans.find((p) => p.id === data.plan)} basic={data.plans.find((p) => p.id === "basic")} user={user} price={priceOf(picked)}
          offer={offer} video={data.video} busy={buying === picked.id} onPay={() => { const id = picked.id; setPicked(null); buy(id); }} onClose={() => !buying && setPicked(null)} />
      )}
      <PlanWelcome plan={welcome?.plan} user={user} until={welcome?.until} onClose={() => setWelcome(null)}
        onStart={() => { setWelcome(null); navigate("/"); }} />
    </div>
  );
}
