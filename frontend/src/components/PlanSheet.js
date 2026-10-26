import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import BrandMark from "@/components/BrandMark";
import { ArrowRight, Check, Loader2, Lock, RefreshCcw } from "lucide-react";

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
export function PlanSheet({ plan, current, basic, user, price, offer, video, busy, onPay, onClose }) {
  if (!plan) return null;
  const first = firstName(user?.name);
  const usage = (p) => Math.round(p.meter.session / Math.max(1, (basic || p).meter.session));
  const perks = [
    "Premium AI models for harder questions",
    video ? "HD pictures and real AI video" : "HD AI pictures",
    "Think mode, answered by our smartest model",
    "Counsellor Pro, which remembers your last talk",
    ...(plan.quality ? [video ? `Videos up to ${plan.quality.videoSeconds} seconds, uploads up to ${plan.quality.uploadMb}MB`
      : `Uploads up to ${plan.quality.uploadMb}MB`] : []),
    "Memory across every chat",
    "Publish your apps to the web",
  ];
  // Phones: header, features, then price and Pay. Laptops: a wide card, the black side (title, price, Pay) on the
  // left and the features in two columns on the right, so nothing needs scrolling.
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-[calc(100%-2rem)] gap-0 overflow-hidden p-0 sm:max-w-[780px] md:grid md:grid-cols-[290px_1fr] md:grid-rows-[1fr_auto] max-md:[&>button:last-child]:!bg-transparent max-md:[&>button:last-child]:!text-background" data-testid="plan-sheet">
        <div className="bg-foreground px-6 pb-5 pt-5 text-background md:col-start-1 md:row-start-1 md:pb-4 md:pt-7">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-background"><BrandMark className="h-6 w-6" /></span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-background/70">Krish AI {plan.name}</span>
          </div>
          <DialogTitle className="krish-display mt-4 text-[1.6rem] font-normal leading-[1.1] md:mt-6 md:text-[1.9rem]">
            {first ? <>{first}, here's what <em>{plan.name}</em> unlocks</> : <>What <em>{plan.name}</em> unlocks for you</>}
          </DialogTitle>
          <p className="mt-2 text-[0.82rem] text-background/60">{plan.id === "max"
            ? "For people and businesses who create every single day."
            : "For students, creators and anyone who wants more from Krish."}</p>
        </div>

        <div className="max-h-[45dvh] overflow-y-auto px-6 py-4 md:col-start-2 md:row-span-2 md:row-start-1 md:max-h-none md:px-7 md:py-7">
          <div className="flex items-center justify-between border-b border-border pb-2.5 text-sm" data-testid="plan-sheet-compare">
            <span>{video ? "Builds, pictures, decks and videos" : "Builds, pictures and decks"}</span>
            <span className="shrink-0 tabular-nums">
              {current && <><span className="text-muted-foreground line-through decoration-1">{usage(current)}x</span>
                <ArrowRight className="mx-1.5 inline h-3 w-3 text-muted-foreground" /></>}
              <b className="font-semibold">{usage(plan)}x</b>
            </span>
          </div>
          <p className="mt-1.5 text-[11px] text-muted-foreground">Usage refills every 5 hours.</p>

          <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Included</p>
          <ul className="mt-2 grid gap-x-5 gap-y-2 text-[0.85rem] md:grid-cols-2">
            {perks.map((perk) => (
              <li key={perk} className="flex items-start gap-2 leading-snug"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={2} /> {perk}</li>
            ))}
          </ul>

          <p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground max-md:hidden">Things you could make this week</p>
          <ul className="mt-2 space-y-1.5 text-[0.82rem] text-muted-foreground max-md:hidden">
            {(IDEAS[plan.id] || IDEAS.pro).map((idea) => (
              <li key={idea} className="flex gap-2.5"><span className="mt-[0.55rem] h-px w-3 shrink-0 bg-muted-foreground/60" /> {idea}</li>
            ))}
          </ul>
        </div>

        <div className="border-t border-border px-6 pb-5 pt-4 md:col-start-1 md:row-start-2 md:border-0 md:bg-foreground md:pb-6 md:pt-2 md:text-background">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground md:text-background/60">30 days of {plan.name}</span>
            <span className="text-right">
              {price !== plan.price && <span className="mr-2 text-sm text-muted-foreground line-through md:text-background/50">₹{plan.price}</span>}
              <span className="krish-display text-[1.8rem] leading-none tabular-nums">₹{price}</span>
            </span>
          </div>
          {offer && price !== plan.price && <p className="mt-1 text-right text-xs text-muted-foreground md:text-background/60">{offer.code}: {offer.percentOff}% off applied</p>}
          <Button onClick={onPay} disabled={busy} data-testid="plan-sheet-pay"
            className="mt-3.5 h-11 w-full rounded-lg bg-foreground text-[0.95rem] font-medium text-background shadow-none hover:bg-foreground/90 md:bg-background md:text-foreground md:hover:bg-background/90">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : `Pay ₹${price}`}
          </Button>
          <div className="mt-2.5 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground md:text-background/55">
            <span className="flex items-center gap-1"><Lock className="h-3 w-3" /> Secure payment by Razorpay</span>
            <span className="flex items-center gap-1"><RefreshCcw className="h-3 w-3" /> No auto-renewal</span>
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
        <div className="mx-auto mt-2 flex h-14 w-14 items-center justify-center rounded-2xl bg-foreground text-background">
          <Check className="h-7 w-7" strokeWidth={1.75} />
        </div>
        <DialogTitle className="krish-display mt-3 text-[1.7rem] font-normal leading-tight">
          {first ? `You're on ${plan.name}, ${first}!` : `You're on ${plan.name}!`}
        </DialogTitle>
        <p className="text-sm text-muted-foreground">
          Thank you for supporting Krish AI. {plan.name} is active{until ? ` until ${until}` : ""}. Try a premium model or make something new today.
        </p>
        <Button onClick={onStart} className="mt-2 h-11 w-full rounded-lg bg-foreground font-medium text-background shadow-none hover:bg-foreground/90" data-testid="plan-welcome-start">
          Start creating <ArrowRight className="ml-1 h-4 w-4" />
        </Button>
      </DialogContent>
    </Dialog>
  );
}
