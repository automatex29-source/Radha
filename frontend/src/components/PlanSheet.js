import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import BrandMark from "@/components/BrandMark";
import { ArrowRight, Check, Loader2, Lock, RefreshCcw } from "lucide-react";

// One idea of what to make, shown under the list on laptops.
const IDEA = {
  pro: "Try it: a 15-slide class deck, ready in a minute.",
  max: "Try it: posters for your whole catalogue, every day.",
};

const firstName = (name) => (name || "").trim().split(" ")[0];

// A rupee amount as Razorpay charges it: whole rupees as they are, otherwise with paise (₹470.82).
const rupees = (n) => n.toLocaleString("en-IN", { minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 });

// What a plan adds to the one below it, as one plain list.
function perks(plan, video) {
  const m = plan.monthly;
  const usage = m ? `About ${m.answers} premium answers or ${m.builds} app builds a month` : null;
  const { uploadMb, videoSeconds } = plan.quality || {};
  if (plan.id === "max") {
    return [usage, "More pictures, decks and builds than Pro", `${plan.total.automation} automations`,
      ...(video ? [`Videos up to ${videoSeconds} seconds`] : []), `Uploads up to ${uploadMb}MB`].filter(Boolean);
  }
  return ["Claude Sonnet for code and hard questions", usage, "Unlimited chat on Krish Basic",
    video ? "HD pictures and real AI video" : "HD pictures", "Publish your apps", "Memory across chats",
    "Counsellor Pro"].filter(Boolean);
}

/** Opens when someone taps a paid plan: what it adds, the price, then pay. Laptops: the list on the left and the
 *  price on a dark side panel. Phones: one column, with the price and Pay stuck to the bottom. */
export function PlanSheet({ plan, user, price, offer, video, gstRate = 0, busy, onPay, onClose }) {
  if (!plan) return null;
  const first = firstName(user?.name);
  // An offer code makes it a one-time 30-day payment; otherwise it's autopay, renewing every month.
  const oneTime = !!(offer && price !== plan.price);
  const was = plan.listPrice || plan.price;
  const off = was > price ? Math.round((1 - price / was) * 100) : 0;
  const gst = Math.round(price * gstRate) / 100; // 18% GST on top once the business has a GSTIN
  const below = plan.id === "max" ? "Pro" : "Basic";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent overlayClassName="bg-black/85 backdrop-blur-sm"
        className="max-h-[92dvh] max-w-[calc(100%-1.5rem)] gap-0 overflow-hidden rounded-2xl p-0 sm:max-w-[720px] md:grid md:grid-cols-[1fr_270px] md:[&>button:last-child]:!bg-transparent md:[&>button:last-child]:!text-background"
        data-testid="plan-sheet">
        <div className="max-h-[calc(92dvh-11.5rem)] overflow-y-auto px-6 pb-5 pt-6 md:max-h-none md:px-8 md:py-8">
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground md:hidden">Krish AI {plan.name}</span>
          <DialogTitle className="mt-2 md:mt-0 text-[1.45rem] font-semibold leading-tight tracking-tight md:text-[1.6rem]">
            {first ? `Unlock Krish ${plan.name}, ${first}` : `Unlock Krish ${plan.name}`}
          </DialogTitle>
          <p className="mt-1.5 text-[0.86rem] text-muted-foreground">{plan.id === "max"
            ? "For people and businesses who create every day."
            : "Smarter answers, more of everything, and your apps on the web."}</p>

          <p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Everything in {below}, plus</p>
          <ul className="mt-2.5 space-y-2.5 text-[0.9rem]" data-testid="plan-sheet-perks">
            {perks(plan, video).map((perk) => (
              <li key={perk} className="flex items-start gap-2.5 leading-snug">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-foreground text-background">
                  <Check className="h-2.5 w-2.5" strokeWidth={3} />
                </span>
                {perk}
              </li>
            ))}
          </ul>
          <p className="mt-5 truncate text-[0.8rem] text-muted-foreground max-md:hidden">{IDEA[plan.id] || IDEA.pro}</p>
        </div>

        <div className="border-t border-border bg-background px-6 pb-5 pt-4 md:flex md:flex-col md:border-0 md:bg-foreground md:px-6 md:py-7 md:text-background">
          <div className="flex items-center gap-2.5 max-md:hidden">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-background"><BrandMark className="h-6 w-6" /></span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-background/70">Krish AI {plan.name}</span>
          </div>
          <div className="flex items-end justify-between gap-3 md:mt-7 md:block">
            <div>
              <span className="text-[12px] text-muted-foreground md:text-background/60">{oneTime ? `30 days of ${plan.name}` : `${plan.name}, per month`}</span>
              <div className="mt-0.5 flex items-baseline gap-2">
                <span className="text-[2rem] font-semibold leading-none tracking-tight tabular-nums md:text-[2.4rem]" data-testid="plan-sheet-price">₹{price.toLocaleString("en-IN")}</span>
                {price !== was && <span className="text-sm tabular-nums text-muted-foreground line-through md:text-background/50">₹{was.toLocaleString("en-IN")}</span>}
              </div>
            </div>
            <div className="text-right text-[12px] text-muted-foreground md:mt-1.5 md:text-left md:text-background/65">
              <p data-testid="plan-sheet-per-day">just ₹{Math.round(price / 30)}/day</p>
              {oneTime ? <p>{offer.code}: {offer.percentOff}% off, one time</p> : off > 0 && <p>Launch price · {off}% off</p>}
              {gst > 0 && <p data-testid="plan-sheet-gst">+ ₹{rupees(gst)} GST ({gstRate}%)</p>}
            </div>
          </div>
          <div className="md:mt-auto md:pt-6">
          <Button onClick={onPay} disabled={busy} data-testid="plan-sheet-pay"
            className="mt-3.5 h-11 w-full rounded-xl bg-foreground text-[0.95rem] font-semibold text-background shadow-none hover:bg-foreground/90 md:mt-0 md:bg-background md:text-foreground md:hover:bg-background/90">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : `Pay ₹${rupees(price + gst)}`}
          </Button>
          <div className="mt-2.5 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground md:flex-col md:items-center md:text-background/55">
            <span className="flex items-center gap-1"><Lock className="h-3 w-3" /> Secure payment by Razorpay</span>
            <span className="flex items-center gap-1"><RefreshCcw className="h-3 w-3" /> {oneTime ? "No auto-renewal" : "Renews monthly, cancel anytime"}</span>
          </div>
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
