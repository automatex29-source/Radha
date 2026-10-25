import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Check, Clock, Copy, Loader2, Smartphone } from "lucide-react";

// The standard UPI payment link: every UPI app (GPay, PhonePe, Paytm, BHIM) opens it with the amount filled in.
function upiLink(upi, amount, note) {
  const q = new URLSearchParams({ pa: upi.id, pn: upi.name, am: String(amount), cu: "INR", tn: note });
  return `upi://pay?${q.toString().replace(/\+/g, "%20")}`;
}

/** Pay by UPI: scan the QR (or open a UPI app on a phone), pay, then send the 12-digit UPI reference for approval. */
export default function UpiPayDialog({ plan, price, upi, code, onClose, onSent }) {
  const [qr, setQr] = useState("");
  const [utr, setUtr] = useState("");
  const [sending, setSending] = useState(false);
  const note = `Krish AI ${plan.name}`;
  const link = upiLink(upi, price, note);

  useEffect(() => {
    QRCode.toDataURL(link, { margin: 1, width: 360 }).then(setQr).catch(() => setQr(""));
  }, [link]);

  const copyId = async () => {
    try { await navigator.clipboard.writeText(upi.id); toast.success("UPI ID copied"); } catch { /* it's on screen */ }
  };

  const send = async (e) => {
    e.preventDefault();
    setSending(true);
    try {
      const { data } = await api.post("/billing/upi", { plan: plan.id, utr, code: code || "" });
      onSent(data);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally { setSending(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && !sending && onClose()}>
      <DialogContent className="max-w-sm" data-testid="upi-dialog">
        <DialogTitle className="text-lg font-bold">Pay ₹{price} for {plan.name}</DialogTitle>
        <p className="-mt-1 text-[0.8rem] text-muted-foreground">30 days of {plan.name}. No auto-renewal.</p>

        <div className="mt-1 flex flex-col items-center gap-2">
          {qr ? <img src={qr} alt={`UPI QR code to pay ₹${price}`} className="h-48 w-48 rounded-xl border border-border bg-white p-1.5" data-testid="upi-qr" />
            : <div className="flex h-48 w-48 items-center justify-center rounded-xl border border-border"><Loader2 className="h-5 w-5 animate-spin" /></div>}
          <p className="text-center text-[0.75rem] text-muted-foreground">Scan with GPay, PhonePe, Paytm or any UPI app</p>
          <a href={link} className="md:hidden" data-testid="upi-open-app">
            <Button type="button" className="h-9 rounded-lg"><Smartphone className="mr-1.5 h-4 w-4" /> Open UPI app</Button>
          </a>
          <button type="button" onClick={copyId} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-[0.8rem]" data-testid="upi-id">
            {upi.id} <Copy className="h-3 w-3" />
          </button>
        </div>

        <form onSubmit={send} className="mt-2 space-y-2">
          <label className="text-[0.8rem] font-medium" htmlFor="upi-utr">After paying, enter the 12-digit UPI reference</label>
          <Input id="upi-utr" value={utr} onChange={(e) => setUtr(e.target.value.replace(/[^\d ]/g, ""))} inputMode="numeric"
            placeholder="e.g. 4321 1234 5678" maxLength={16} data-testid="upi-utr" />
          <p className="text-[0.72rem] leading-snug text-muted-foreground">
            Find it in your UPI app under the payment's details, called UTR, UPI Ref No. or Transaction ID.
          </p>
          <Button type="submit" disabled={sending || utr.replace(/\s/g, "").length !== 12} className="h-10 w-full rounded-lg" data-testid="upi-send">
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Check className="mr-1.5 h-4 w-4" /> I've paid</>}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Shown on the Plans page while a UPI payment waits for the owner to check it. */
export function UpiPending({ pending }) {
  if (!pending) return null;
  return (
    <div className="plans-panel mt-3 flex items-center gap-2.5 rounded-2xl px-4 py-2.5 text-[0.8rem]" data-testid="upi-pending">
      <Clock className="h-4 w-4 shrink-0 text-amber-500" />
      <p>Your UPI payment of <b>₹{pending.amount}</b> for {pending.planName} (ref {pending.utr}) is being checked.
        {" "}{pending.planName} switches on as soon as it's approved, usually within a few hours.</p>
    </div>
  );
}
