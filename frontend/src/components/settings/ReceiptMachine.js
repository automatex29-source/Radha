import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Download, FileText, Loader2, RotateCcw } from "lucide-react";

const rupees = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}  ${d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`;
};

// Bars for the little barcode at the foot of the receipt, the same for the same payment every time.
function bars(seed) {
  let h = 0;
  for (const c of seed || "krish") h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return Array.from({ length: 34 }, (_, i) => 1 + ((h >> (i % 24)) & 3));
}

function Row({ label, value, strong }) {
  return (
    <div className={`flex justify-between gap-3 ${strong ? "text-[13px] font-bold" : ""}`}>
      <span className="truncate">{label}</span><span className="shrink-0 tabular-nums">{value}</span>
    </div>
  );
}

/** Settings > Billing: tap a payment and its receipt prints out of a card machine. View or download the invoice
 *  PDF from there. */
export default function ReceiptMachine({ payment, onClose, onInvoice, opening }) {
  const [run, setRun] = useState(0); // bumps to print the receipt again
  useEffect(() => { if (payment) setRun((n) => n + 1); }, [payment]);
  const p = payment;
  const listed = p ? (p.baseAmount ?? (p.amount - (p.gst || 0) - (p.platformFee || 0))) : 0;

  return (
    <Dialog open={!!p} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-[380px] gap-0 overflow-x-hidden border-0 bg-transparent p-0 shadow-none" overlayClassName="bg-black/70 backdrop-blur-sm"
        data-testid="receipt-machine">
        <DialogTitle className="sr-only">Payment receipt</DialogTitle>
        <DialogDescription className="sr-only">The receipt for this payment, with links to the invoice.</DialogDescription>
        {p && (
          <div className="flex flex-col items-center px-4 pb-3 pt-9">
            {/* The receipt rises out of the printer slot at the top of the machine. */}
            <div className="relative z-0 -mb-[14px] w-[264px] overflow-hidden pt-2">
              <div key={run} className="kai-receipt" data-testid="receipt-paper">
                <div className="kai-receipt-paper relative mx-auto w-[244px] px-4 pb-6 pt-4 font-mono text-[11px] leading-[1.45] text-[#2b2b2b]">
                  <div className="flex flex-col items-center text-center">
                    <img src="/icon-192.png" alt="" className="h-8 w-8" />
                    <p className="mt-1 text-[14px] font-bold tracking-[0.08em]">KRISH AI</p>
                    <p className="text-[10px] text-[#6b6b6b]">by EmpireX · krishai.net</p>
                  </div>
                  <p className="my-2 overflow-hidden whitespace-nowrap text-[#9a9a9a]">{"- ".repeat(40)}</p>
                  <Row label="Date" value={when(p.paidAt || p.createdAt)} />
                  {p.invoiceNo && <Row label="Invoice" value={p.invoiceNo} />}
                  <Row label="Paid by" value={p.autopay ? "Autopay" : "Razorpay"} />
                  <p className="my-2 overflow-hidden whitespace-nowrap text-[#9a9a9a]">{"- ".repeat(40)}</p>
                  <Row label={`${p.planName} plan, 30 days`} value={rupees(listed)} />
                  {p.promoCode && <Row label={`Offer ${p.promoCode}`} value="applied" />}
                  {p.gst > 0 && <Row label="GST 18%" value={rupees(p.gst)} />}
                  {p.platformFee > 0 && <Row label="Platform fee" value={rupees(p.platformFee)} />}
                  <p className="my-2 overflow-hidden whitespace-nowrap text-[#9a9a9a]">{"= ".repeat(40)}</p>
                  <Row label="TOTAL" value={rupees(p.amount)} strong />
                  <p className="mt-3 text-center text-[12px] font-bold tracking-[0.25em] text-[#15803d]">✓ APPROVED</p>
                  <div className="mx-auto mt-3 flex h-8 w-fit items-stretch gap-[2px]" aria-hidden>
                    {bars(p.orderId).map((w, i) => <span key={i} className="bg-[#2b2b2b]" style={{ width: w }} />)}
                  </div>
                  <p className="mt-2 text-center text-[10px] text-[#6b6b6b]">Thank you for choosing Krish AI</p>
                </div>
              </div>
            </div>

            {/* The card machine. */}
            <div className="relative z-10 w-[236px] rounded-[28px] bg-gradient-to-b from-[#2a2d36] to-[#16181d] p-4 pt-5 shadow-[0_24px_60px_-12px_rgba(0,0,0,0.6),inset_0_1px_0_rgba(255,255,255,0.08)]">
              <div className="absolute inset-x-6 top-[6px] h-[6px] rounded-full bg-black/70 shadow-[inset_0_2px_3px_rgba(0,0,0,0.9)]" aria-hidden />
              <div key={run} className="kai-pos-screen rounded-xl bg-[#0d1f17] px-3 py-3 text-center font-mono shadow-[inset_0_2px_8px_rgba(0,0,0,0.7)]">
                <p className="text-[10px] tracking-[0.3em] text-[#6ee7a8]/70">KRISH AI</p>
                <p className="kai-pos-status mt-1 text-[15px] font-bold text-[#6ee7a8]">PAID {rupees(p.amount)}</p>
                <p className="text-[10px] text-[#6ee7a8]/70">{(p.paidAt || p.createdAt || "").slice(0, 10)}</p>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2" aria-hidden>
                {["1", "2", "3", "4", "5", "6", "7", "8", "9", "✕", "0", "✓"].map((k) => (
                  <span key={k} className={`flex h-6 items-center justify-center rounded-lg text-[11px] font-semibold shadow-[inset_0_-2px_0_rgba(0,0,0,0.35)] ${
                    k === "✕" ? "bg-[#b4232b] text-white" : k === "✓" ? "bg-[#15803d] text-white" : "bg-[#3a3e49] text-white/85"}`}>{k}</span>
                ))}
              </div>
              <div className="mt-3 flex items-center justify-center gap-1.5 text-[9px] uppercase tracking-[0.2em] text-white/40">
                <span className="h-1.5 w-1.5 rounded-full bg-[#6ee7a8] kai-pos-led" /> Secured by Razorpay
              </div>
            </div>

            <div className="mt-5 flex w-full max-w-[300px] gap-2">
              <Button onClick={() => onInvoice(p, false)} disabled={!!opening} className="h-10 flex-1 rounded-xl" data-testid="receipt-view-invoice">
                {opening === p.orderId ? <Loader2 className="h-4 w-4 animate-spin" /> : <><FileText className="mr-1.5 h-4 w-4" />View invoice</>}
              </Button>
              <Button variant="secondary" onClick={() => onInvoice(p, true)} disabled={!!opening} className="h-10 w-10 rounded-xl p-0" aria-label="Download invoice"
                data-testid="receipt-download">
                {opening === p.orderId + ":d" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              </Button>
              <Button variant="secondary" onClick={() => setRun((n) => n + 1)} className="h-10 w-10 rounded-xl p-0" aria-label="Print the receipt again"
                data-testid="receipt-reprint">
                <RotateCcw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
