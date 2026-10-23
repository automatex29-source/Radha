import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import BrandMark from "@/components/BrandMark";
import { ArrowRight, BadgeCheck, Crown, Loader2, Lock, PartyPopper, RefreshCcw, Sparkles } from "lucide-react";

const DAILY = [
  { key: "picture", label: "AI pictures" },
  { key: "deck", label: "slide decks" },
  { key: "video", label: "video credits" },
  { key: "build", label: "app builds" },
];

const IDEAS = {
  pro: [
    "A full wedding or birthday invitation, with pictures, in a minute",
    "A 15-slide deck for your class or client, ready to present",
    "A small shop or portfolio website, published with one tap",
  ],
  max: [
    "Product photos and posters for your whole catalogue, every day",
    "Weekly reports written and emailed by automations, on their own",
    "Long research with the strongest AI models, for your business",
  ],
};

const firstName = (name) => (name || "").trim().split(" ")[0];

/** Opens when someone taps a paid plan: what it unlocks for them (compared with their plan now), then pay. */
export function PlanSheet({ plan, current, user, price, offer, busy, onPay, onClose }) {
  if (!plan) return null;
  const first = firstName(user?.name);
  const more = (k) => plan.daily[k];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md overflow-hidden p-0" data-testid="plan-sheet">
        <div className="relative bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 px-6 pb-6 pt-7 text-white">
          <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/15 blur-2xl" />
          <div className="flex items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/95 shadow-lg"><BrandMark className="h-9 w-9" /></span>
            <span className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2.5 py-1 text-xs font-bold uppercase tracking-wider">
              <Crown className="h-3.5 w-3.5" /> Krish AI {plan.name}
            </span>
          </div>
          <DialogTitle className="mt-4 text-2xl font-extrabold leading-tight tracking-tight">
            {first ? `${first}, here's what ${plan.name} unlocks for you` : `Here's what ${plan.name} unlocks for you`}
          </DialogTitle>
          <p className="mt-1.5 text-sm text-white/85">{plan.id === "max"
            ? "For people and businesses who create every single day."
            : "For students, creators and anyone who wants more from Krish."}</p>
        </div>

        <div className="max-h-[55dvh] overflow-y-auto px-6 pt-5">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Every day</p>
          <ul className="mt-2 space-y-2" data-testid="plan-sheet-compare">
            {DAILY.map((d) => (
              <li key={d.key} className="flex items-center justify-between gap-3 rounded-xl bg-surface px-3 py-2 text-sm">
                <span className="font-medium capitalize">{d.label}</span>
                <span className="tabular-nums">
                  <span className="text-muted-foreground line-through decoration-1">{current?.daily[d.key]}</span>
                  <ArrowRight className="mx-1.5 inline h-3 w-3 text-muted-foreground" />
                  <b className="text-primary">{more(d.key)}</b>
                </span>
              </li>
            ))}
            {[
              "Premium AI models for harder questions",
              "HD pictures and real AI video",
              "Think mode answers with our smartest model",
              ...(plan.quality ? [
                `Videos up to ${plan.quality.videoSeconds} seconds, uploads up to ${plan.quality.uploadMb}MB`,
              ] : []),
              "Krish remembers what you tell it, in every chat",
              "Publish your apps to the web",
            ].map((perk) => (
              <li key={perk} className="flex items-center gap-2 rounded-xl bg-surface px-3 py-2 text-sm"><BadgeCheck className="h-4 w-4 shrink-0 text-primary" /> {perk}</li>
            ))}
          </ul>

          <p className="mt-5 text-xs font-bold uppercase tracking-wider text-muted-foreground">Things you could make this week</p>
          <ul className="mt-2 space-y-1.5 text-sm">
            {(IDEAS[plan.id] || IDEAS.pro).map((idea) => (
              <li key={idea} className="flex gap-2"><Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" /> {idea}</li>
            ))}
          </ul>
        </div>

        <div className="border-t border-border px-6 pb-6 pt-4">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">30 days of {plan.name}</span>
            <span className="text-right">
              {price !== plan.price && <span className="mr-2 text-sm text-muted-foreground line-through">₹{plan.price}</span>}
              <span className="text-2xl font-extrabold tabular-nums">₹{price}</span>
            </span>
          </div>
          {offer && price !== plan.price && <p className="mt-1 text-right text-xs font-medium text-emerald-600 dark:text-emerald-400">{offer.code}: {offer.percentOff}% off applied</p>}
          <Button onClick={onPay} disabled={busy} data-testid="plan-sheet-pay"
            className="mt-4 h-12 w-full rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 text-base font-bold text-white">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : `Pay ₹${price} with UPI or card`}
          </Button>
          <div className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1"><RefreshCcw className="h-3 w-3" /> No auto-renewal</span>
            <span className="flex items-center gap-1"><Lock className="h-3 w-3" /> Secure payment by Razorpay</span>
          </div>
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
        <div className="mx-auto mt-2 flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-lg krish-float">
          <PartyPopper className="h-8 w-8" />
        </div>
        <DialogTitle className="mt-3 text-2xl font-extrabold tracking-tight">
          {first ? `You're on ${plan.name}, ${first}!` : `You're on ${plan.name}!`}
        </DialogTitle>
        <p className="text-sm text-muted-foreground">
          Thank you for supporting Krish AI. {plan.name} is active{until ? ` until ${until}` : ""}. Try a premium model or make something new today.
        </p>
        <Button onClick={onStart} className="mt-2 h-11 w-full rounded-xl font-semibold" data-testid="plan-welcome-start">
          Start creating <ArrowRight className="ml-1 h-4 w-4" />
        </Button>
      </DialogContent>
    </Dialog>
  );
}
