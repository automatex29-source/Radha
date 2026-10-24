import { useCallback, useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Check, Copy, Gauge, Loader2, Share2, Tag } from "lucide-react";
import { Input } from "@/components/ui/input";
import InviteDialog, { WhatsAppIcon } from "@/components/InviteDialog";
import { inviteLink, inviteMessage } from "@/lib/referral";
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

const COUNSELLOR_PRO = [
  ["Deeper replies", "Every talk answered by our strongest model."],
  ["Remembers your last talk", "Picks up gently where you left off."],
  ["Sleep and focus breathing", "4-7-8 for sleep, box breathing before exams."],
  ["Mood week", "See how your last seven days felt."],
];

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
        <div className={`h-full rounded-full transition-all ${pct >= 100 ? "bg-rose-500" : pct >= 80 ? "bg-amber-500" : "bg-foreground"}`}
          style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{resetText(part.resetsAt) || idle}</p>
    </div>
  );
}

/** The usage meter, like Claude's: every build, picture, deck (and video, when on) runs it down by how big it is. */
function Usage({ meter, costs, automation, video }) {
  const range = (r) => (r[0] === r[1] ? `${r[0]}` : `${r[0]}-${r[1]}`);
  return (
    <section className="plans-panel mt-6 rounded-[20px] p-6 sm:p-9" data-testid="plans-usage">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="krish-display flex items-center gap-2 text-[1.7rem] leading-none"><Gauge className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} /> Your usage</h2>
        <p className="text-xs text-muted-foreground">Chat on Krish Basic is never counted.</p>
      </div>
      <div className="mt-5 grid gap-x-8 gap-y-5 sm:grid-cols-2">
        <MeterBar label="This session" part={meter.session} testid="meter-session"
          idle={`Starts when you make something, then refills ${meter.session.hours} hours later`} />
        <MeterBar label="This week" part={meter.week} testid="meter-week" idle="Starts when you make something" />
      </div>
      <div className="mt-6 rounded-xl bg-sunken p-4" data-testid="meter-costs">
        <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">What things use</p>
        <p className="mt-1 text-xs text-muted-foreground">Bigger requests use more: a longer build ask{video ? ", a longer video" : ""}, a longer chat.</p>
        <ul className="mt-2 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>App build</span><span className="tabular-nums text-muted-foreground">{range(costs.build)} credits</span></li>
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>AI picture</span><span className="tabular-nums text-muted-foreground">{costs.picture} credits</span></li>
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>Slide deck</span><span className="tabular-nums text-muted-foreground">{costs.deck} + pictures</span></li>
          {video && <li className="flex justify-between gap-3 whitespace-nowrap"><span>Video</span><span className="tabular-nums text-muted-foreground">{costs.videoSecond} a second</span></li>}
          <li className="flex justify-between gap-3 whitespace-nowrap"><span>Premium message</span><span className="tabular-nums text-muted-foreground">{range(costs.chat)} credits</span></li>
        </ul>
      </div>
      <p className="mt-4 text-xs text-muted-foreground" data-testid="meter-automations">
        Automations: {automation.used} of {automation.limit}
      </p>
    </section>
  );
}

function PlanCard({ plan, basic, current, currentPlan, paymentsOn, expires, busy, onBuy, offer, video }) {
  const popular = plan.id === "pro";
  const lower = ORDER.indexOf(plan.id) < ORDER.indexOf(currentPlan);
  const canBuy = paymentsOn && plan.price > 0 && !lower;
  const price = offer && plan.price ? offer.prices[plan.id] ?? plan.price : plan.price;
  const { label, items } = highlights(plan, basic, video);
  const soft = popular ? "text-background/60" : "text-muted-foreground";
  return (
    <div data-testid={`plan-${plan.id}`}
      className={`relative flex flex-col px-6 py-8 sm:px-8 sm:py-9 ${popular
        ? "z-[1] rounded-[20px] bg-foreground text-background shadow-[0_30px_60px_-30px_rgba(15,17,30,0.55)] max-md:order-first md:-my-px"
        : "plans-panel rounded-[20px] md:rounded-none md:border-0 md:bg-transparent dark:md:bg-transparent"}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-sans text-[13px] font-semibold uppercase tracking-[0.14em]">{plan.name}</h2>
        {current ? <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${popular ? "border-background/40 text-background/80" : "border-border text-muted-foreground"}`}>Your plan</span>
          : popular ? <span className="rounded-full border border-background/40 px-2.5 py-0.5 text-[11px] font-medium text-background/80">Most popular</span> : null}
      </div>
      <div className="mt-7 flex items-baseline gap-2">
        {price !== plan.price && <span className={`krish-display text-2xl line-through tabular-nums ${soft}`}>₹{plan.price}</span>}
        <span className="krish-display text-[3.6rem] leading-none tabular-nums sm:text-[4rem]">₹{price}</span>
        <span className={`text-sm ${soft}`}>{plan.price ? "per month" : "forever"}</span>
      </div>
      <p className={`mt-3 text-[0.92rem] ${soft}`}>{TAGLINE[plan.id]}</p>
      <div className={`my-6 h-px ${popular ? "bg-background/15" : "bg-border/80"}`} />
      <p className={`mb-3.5 text-xs font-medium ${soft}`}>{label}</p>
      <ul className="flex-1 space-y-3 text-[0.9rem]">
        {items.map((text) => (
          <li key={text} className="flex items-start gap-3 leading-snug">
            <Check className={`mt-0.5 h-4 w-4 shrink-0 ${popular ? "" : "text-foreground/80"}`} strokeWidth={1.75} />
            {text}
          </li>
        ))}
      </ul>
      <Button disabled={!canBuy || busy} onClick={() => onBuy(plan.id)} data-testid={`plan-button-${plan.id}`}
        className={`mt-8 h-11 w-full rounded-[10px] text-[0.92rem] font-medium shadow-none disabled:opacity-100 ${popular
          ? "bg-background text-foreground hover:bg-background/90"
          : canBuy ? "border border-foreground/80 bg-transparent text-foreground hover:bg-foreground hover:text-background"
          : "border border-border bg-transparent text-muted-foreground"}`}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" />
          : !plan.price ? (current ? "Current plan" : "Free")
          : !paymentsOn ? (current ? "Current plan" : "Coming soon")
          : current ? `Add a month · ₹${price}` : lower ? "Included in your plan" : `Get ${plan.name}`}
      </Button>
      {current && expires && <p className={`mt-2.5 text-center text-xs ${soft}`}>Active until {untilText(expires)}</p>}
    </div>
  );
}

/** Counsellor Pro, part of Pro and Max: what the Counsellor adds on a paid plan. */
function CounsellorPro() {
  return (
    <section className="plans-panel mt-6 grid gap-8 rounded-[20px] p-6 sm:p-9 md:grid-cols-[1fr_2fr] md:gap-10" data-testid="plans-counsellor-pro">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Included in Pro and Max</p>
        <h2 className="krish-display mt-2.5 text-[2.1rem] leading-tight">Counsellor <em>Pro</em></h2>
        <p className="mt-2.5 text-[0.92rem] leading-relaxed text-muted-foreground">Deeper, warmer conversations on our best model, for the days you need someone to listen.</p>
      </div>
      <dl className="grid content-center gap-x-9 gap-y-5 sm:grid-cols-2">
        {COUNSELLOR_PRO.map(([title, text]) => (
          <div key={title} className="plans-line border-t pt-3.5">
            <dt className="text-[0.92rem] font-semibold">{title}</dt>
            <dd className="mt-1 text-[0.85rem] leading-relaxed text-muted-foreground">{text}</dd>
          </div>
        ))}
      </dl>
    </section>
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
    <section className="plans-panel mt-6 grid overflow-hidden rounded-[20px] md:grid-cols-[1.05fr_1fr]" data-testid="plans-invite">
      <div className="p-6 sm:p-9">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Invite friends</p>
        <h2 className="krish-display mt-2.5 text-[2.1rem] leading-tight">Give Pro. <em className="text-[#4F46E5] dark:text-[#A5B4FC]">Get Pro.</em></h2>
        <p className="mt-2.5 max-w-sm text-[0.92rem] leading-relaxed text-muted-foreground">
          When a friend joins with your link, you each get {days} days of Pro, free.
        </p>
        <ol className="mt-6 grid gap-3 text-[0.88rem] sm:grid-cols-3 sm:gap-4">
          {["Share your link", "Your friend signs up", `You both get ${days} days of Pro`].map((step, i) => (
            <li key={step} className="flex items-baseline gap-2.5 sm:flex-col sm:gap-1">
              <span className="krish-display text-xl leading-none text-muted-foreground">{i + 1}.</span>
              <span className="leading-snug">{step}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="plans-line flex flex-col justify-center gap-3 border-t bg-sunken/60 p-6 sm:p-9 md:border-l md:border-t-0">
        <p className="text-xs font-medium text-muted-foreground">Your invite link</p>
        <div className="flex min-w-0 items-center gap-2 rounded-[10px] border border-border bg-background p-1.5 pl-3.5">
          <span className="min-w-0 flex-1 truncate text-[0.88rem] font-medium" data-testid="plans-invite-link">
            {link ? link.replace(/^https?:\/\//, "") : "Loading your link…"}
          </span>
          <Button onClick={copy} disabled={!link} data-testid="plans-invite-copy"
            className="h-8 shrink-0 rounded-[7px] bg-foreground px-3.5 text-[0.82rem] font-medium text-background shadow-none hover:bg-foreground/90">
            {copied ? <><Check className="mr-1.5 h-3.5 w-3.5" /> Copied</> : <><Copy className="mr-1.5 h-3.5 w-3.5" /> Copy</>}
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <a href={link ? `https://wa.me/?text=${encodeURIComponent(inviteMessage(link, days))}` : undefined} target="_blank" rel="noreferrer"
            data-testid="plans-invite-whatsapp" aria-disabled={!link}
            className="flex h-10 items-center justify-center gap-2 rounded-[10px] border border-border bg-background text-[0.85rem] font-medium transition-colors hover:bg-surface">
            <WhatsAppIcon className="h-4 w-4 shrink-0 text-[#25D366]" /> WhatsApp
          </a>
          <button type="button" onClick={onMore} data-testid="plans-invite-more"
            className="flex h-10 items-center justify-center gap-2 rounded-[10px] border border-border bg-background text-[0.85rem] font-medium transition-colors hover:bg-surface">
            <Share2 className="h-4 w-4 shrink-0" /> More ways
          </button>
        </div>
        {data && (
          <div className="mt-2" data-testid="plans-invite-progress">
            <div className="flex gap-1" aria-hidden="true">
              {Array.from({ length: data.maxRewards }, (_, i) => (
                <span key={i} className={`h-1 flex-1 rounded-full ${i < rewarded ? "bg-foreground" : "bg-border"}`} />
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {data.joined ? <><b className="font-semibold text-foreground">{data.daysEarned} Pro days</b> earned from {plural(data.joined, "friend")}, up to {data.maxRewards}.</>
                : `No friends yet. You can earn Pro from up to ${data.maxRewards} friends.`}
            </p>
          </div>
        )}
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
    <div className="flex h-dvh w-full overflow-hidden plans-canvas max-md:flex-col">
      <IconRail />
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1100px] px-4 pb-14 pt-10 sm:px-8 sm:pt-16">
          <header className="text-center">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Plans</p>
            <h1 className="krish-display mt-3 text-[2.75rem] leading-[1.02] sm:text-[4.25rem]">
              Choose the plan that <em className="text-[#4F46E5] dark:text-[#A5B4FC]">fits you</em>
            </h1>
            <p className="mx-auto mt-4 max-w-md text-[0.97rem] leading-relaxed text-muted-foreground">Chat is unlimited on every plan. Upgrade for more app builds, {data?.video ? "pictures, decks and videos" : "pictures and decks"}.</p>
          </header>

          {!data ? (
            <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : (
            <>
              <div className="mt-10 grid gap-3.5 sm:mt-14 plans-grid md:grid-cols-3 md:gap-0 md:rounded-[20px]" data-testid="plans-grid">
                {data.plans.map((p) => (
                  <PlanCard key={p.id} plan={p} basic={data.plans.find((x) => x.id === "basic")} current={p.id === data.plan} currentPlan={data.plan}
                    paymentsOn={data.paymentsOn} expires={data.planExpiresAt} busy={buying === p.id} onBuy={(id) => setPicked(data.plans.find((x) => x.id === id))} offer={offer} video={data.video} />
                ))}
              </div>
              <CounsellorPro />
              <InviteFriends onMore={() => setInviteOpen(true)} />
              <p className="mt-8 text-center text-xs text-muted-foreground">
                {data.paymentsOn
                  ? "Pay once for 30 days with UPI, card, net banking or a wallet. No auto-renewal: pay again whenever you like to add another month."
                  : "Payments are coming soon. Pro and Max will open here when they're ready."}
              </p>
              {data.paymentsOn && (
                <form onSubmit={applyCode} className="mx-auto mt-4 flex max-w-sm items-center gap-2" data-testid="offer-code-form">
                  <div className="relative flex-1">
                    <Tag className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input value={codeText} onChange={(e) => setCodeText(e.target.value)} placeholder="Have an offer code?" maxLength={24}
                      className="h-10 rounded-[10px] bg-background pl-9 uppercase placeholder:normal-case" data-testid="offer-code-input" />
                  </div>
                  <Button type="submit" variant="outline" disabled={checking || !codeText.trim()} className="h-10 rounded-[10px]" data-testid="offer-code-apply">
                    {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : offer ? "Applied" : "Apply"}
                  </Button>
                </form>
              )}
              {data.limitsOn && <Usage meter={data.meter} costs={data.costs} automation={data.usage.automation} video={data.video} />}
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
