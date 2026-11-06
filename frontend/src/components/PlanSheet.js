import { useState } from "react";
import { platformFee } from "@/lib/checkout";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import BrandMark from "@/components/BrandMark";
import { ArrowRight, Brain, Check, Gauge, ImageIcon, Layers, Loader2, Lock, Rocket, Sparkles, Upload, Zap } from "lucide-react";

const firstName = (name) => (name || "").trim().split(" ")[0];

// A rupee amount as Razorpay charges it: whole rupees as they are, otherwise with paise (₹470.82).
const rupees = (n) => n.toLocaleString("en-IN", { minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 });

// What a plan adds, as a few rows: an icon, a short title and one line. No AI company or model names here.
// Premium answers and HD pictures are only promised once their keys are set up (plan.premium, plan.quality.media).
function benefits(plan, video) {
  const m = plan.monthly;
  const { uploadMb, videoSeconds } = plan.quality || {};
  const hd = plan.quality?.media === "premium";
  if (plan.id === "max") {
    const extras = [plan.premium ? "our smartest AI" : "unlimited chat", "publishing", hd && "HD pictures", "Counsellor Pro"].filter(Boolean);
    return [
      { icon: Gauge, title: "More than double Pro", text: m ? `About ${m.answers} premium answers or ${m.builds} app builds a month.` : "More than twice Pro's usage, every week." },
      { icon: ImageIcon, title: "Create every day", text: video ? `More pictures, decks and videos up to ${videoSeconds} seconds.` : "More pictures, decks and builds than Pro." },
      { icon: Zap, title: `${plan.total.automation} automations`, text: "Krish runs your repeat jobs on a schedule." },
      { icon: Upload, title: "Bigger uploads", text: `Files up to ${uploadMb}MB.` },
      { icon: Layers, title: "Everything in Pro", text: `${extras.slice(0, -1).join(", ").replace(/^./, (c) => c.toUpperCase())} and ${extras.at(-1)}.` },
    ];
  }
  return [
    plan.premium
      ? { icon: Sparkles, title: "Smarter answers", text: "Our smartest AI steps in for code and hard questions." }
      : { icon: Sparkles, title: "Unlimited chat", text: "No message limit. Chat as much as you like, any time." },
    { icon: Gauge, title: "Much more usage", text: m ? `About ${m.answers} premium answers or ${m.builds} app builds a month, plus unlimited chat.` : "Many times Basic's builds, pictures and decks." },
    { icon: Rocket, title: "Build and publish apps", text: "Make a website or app and put it live with one tap." },
    hd
      ? { icon: ImageIcon, title: video ? "HD pictures and video" : "HD pictures", text: "Sharper posters, invites and slides." }
      : { icon: Zap, title: `${plan.total.automation} automations`, text: "Krish runs your repeat jobs on a schedule." },
    { icon: Brain, title: "Counsellor Pro", text: "A counsellor who remembers your last talk." },
  ];
}

/** Opens when someone taps a paid plan: a Pro/Max switch, the price, what it adds, then one Pay button.
 *  Phones scroll the middle and keep Pay stuck to the bottom. */
export function PlanSheet({ plan, plans, user, priceOf, offer, video, gstRate = 0, platformFeePct = 0, autopayOn = true, busy, onPay, onClose }) {
  const choices = plans?.length ? plans : plan ? [plan] : [];
  const [id, setId] = useState(plan?.id);
  if (!plan) return null;
  const shown = choices.find((p) => p.id === id) || plan;
  const price = priceOf ? priceOf(shown) : shown.price;
  const first = firstName(user?.name);
  // An offer code makes it a one-time 30-day payment; otherwise it's autopay, renewing every month.
  const withCode = !!(offer && price !== shown.price);
  const oneTime = withCode || !autopayOn; // no autopay: each payment is 30 days
  const was = shown.listPrice || shown.price;
  const off = was > price ? Math.round((1 - price / was) * 100) : 0;
  const gst = Math.round(price * gstRate) / 100; // 18% GST on top once the business has a GSTIN
  const fee = platformFee(price + gst, platformFeePct); // covers the payment gateway's fee
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent overlayClassName="bg-black/85 backdrop-blur-sm"
        className="flex max-h-[94dvh] max-w-[calc(100%-1.5rem)] flex-col gap-0 overflow-hidden rounded-3xl border-border/60 p-0 sm:max-w-[500px]"
        data-testid="plan-sheet">
        <div className="min-h-0 flex-1 overflow-y-auto">
          {/* Hero: the mark on a soft orange glow */}
          <div className="relative overflow-hidden px-6 pb-4 pt-7 text-center sm:px-8">
            <div className="pointer-events-none absolute left-1/2 top-[-5.5rem] h-56 w-[26rem] -translate-x-1/2 rounded-full bg-orange-500/25 blur-3xl dark:bg-orange-500/20" />
            <div className="pointer-events-none absolute left-1/2 top-[-2rem] h-28 w-48 -translate-x-1/2 rounded-full bg-amber-300/30 blur-2xl dark:bg-amber-400/10" />
            <div className="relative mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-orange-500/20 bg-background shadow-[0_8px_30px_-6px_rgba(249,115,22,0.45)]">
              <BrandMark className="h-10 w-10" />
            </div>
            <DialogTitle className="relative mt-3.5 text-[1.55rem] font-semibold leading-tight tracking-tight sm:text-[1.75rem]">
              {first ? `Unlock Krish ${shown.name}, ${first}` : `Unlock Krish ${shown.name}`}
            </DialogTitle>
            <p className="relative mt-1.5 text-[0.88rem] text-muted-foreground">{shown.id === "max"
              ? "For people and businesses who create every day."
              : `${shown.premium ? "Smarter answers" : "Unlimited chat"}, more of everything, and your apps on the web.`}</p>

            {choices.length > 1 && (
              <div className="relative mx-auto mt-4 inline-flex rounded-full border border-border bg-muted/60 p-1" role="tablist">
                {choices.map((p) => (
                  <button key={p.id} type="button" role="tab" aria-selected={p.id === shown.id} onClick={() => setId(p.id)}
                    data-testid={`plan-sheet-toggle-${p.id}`}
                    className={`rounded-full px-6 py-1.5 text-sm font-semibold transition-colors ${p.id === shown.id
                      ? "bg-background text-foreground shadow-sm dark:bg-white/10" : "text-muted-foreground hover:text-foreground"}`}>
                    {p.name}
                  </button>
                ))}
              </div>
            )}

            <div className="relative mt-4">
              <div className="flex items-baseline justify-center gap-2.5">
                <span className="text-[3rem] font-semibold leading-none tracking-tight tabular-nums" data-testid="plan-sheet-price">₹{price.toLocaleString("en-IN")}</span>
                {price !== was && <span className="text-lg tabular-nums text-muted-foreground line-through">₹{was.toLocaleString("en-IN")}</span>}
                {(withCode || off > 0) && (
                  <span className="self-center rounded-full bg-orange-500/12 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-orange-600 dark:bg-orange-500/15 dark:text-orange-300">
                    {withCode ? `${offer.percentOff}% off` : `${off}% off`}
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-[0.84rem] text-muted-foreground">
                {withCode ? `30 days of ${shown.name}, with ${offer.code}` : oneTime ? "for 30 days" : "per month"} · <span data-testid="plan-sheet-per-day">just ₹{Math.round(price / 30)}/day</span>
                {gst > 0 && <span data-testid="plan-sheet-gst"> · + ₹{rupees(gst)} GST</span>}
                {fee > 0 && <span className="text-[0.75rem]" data-testid="plan-sheet-fee"> · + charges</span>}
              </p>
            </div>
          </div>

          <ul className="space-y-1 px-4 pb-3 sm:px-6" data-testid="plan-sheet-perks">
            {benefits(shown, video).map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex items-start gap-3.5 rounded-2xl px-2.5 py-2">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-orange-500/10 text-orange-600 dark:bg-orange-500/15 dark:text-orange-300">
                  <Icon className="h-5 w-5" strokeWidth={1.9} />
                </span>
                <span className="min-w-0">
                  <span className="block text-[0.93rem] font-semibold leading-snug">{title}</span>
                  <span className="block text-[0.83rem] leading-snug text-muted-foreground">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="shrink-0 border-t border-border/70 bg-background px-6 pb-5 pt-4 sm:px-8">
          <Button onClick={() => onPay(shown.id)} disabled={busy} data-testid="plan-sheet-pay"
            className="h-12 w-full rounded-2xl bg-gradient-to-r from-orange-500 to-amber-500 text-base font-semibold text-white shadow-[0_10px_30px_-10px_rgba(249,115,22,0.8)] hover:from-orange-500/90 hover:to-amber-500/90">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <>{fee > 0 ? "Continue to pay" : `Pay ₹${rupees(price + gst)}`}<ArrowRight className="ml-1.5 h-4 w-4" /></>}
          </Button>
          <p className="mt-2.5 flex items-center justify-center gap-1.5 text-[11.5px] text-muted-foreground">
            <Lock className="h-3 w-3" /> Secure payment by Razorpay · {oneTime ? "No auto-renewal" : "Cancel anytime"}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** After a payment goes through: a short, happy thank-you and where to start. */
export function PlanWelcome({ plan, user, until, onClose, onStart }) {
  if (!plan) return null;
  const first = firstName(user?.name);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm text-center" data-testid="plan-welcome">
        <div className="mx-auto mt-2 flex h-14 w-14 items-center justify-center rounded-2xl bg-foreground text-background">
          <Check className="h-7 w-7" strokeWidth={1.75} />
        </div>
        <DialogTitle className="krish-display mt-3 text-[1.7rem] font-normal leading-tight">
          {first ? `You're on ${plan.name}, ${first}!` : `You're on ${plan.name}!`}
        </DialogTitle>
        <p className="text-sm text-muted-foreground">
          Thank you for supporting Krish AI. {plan.name} is active{until ? ` until ${until}` : ""}. Make something new today.
        </p>
        <Button onClick={onStart} className="mt-2 h-11 w-full rounded-lg bg-foreground font-medium text-background shadow-none hover:bg-foreground/90" data-testid="plan-welcome-start">
          Start creating <ArrowRight className="ml-1 h-4 w-4" />
        </Button>
      </DialogContent>
    </Dialog>
  );
}
