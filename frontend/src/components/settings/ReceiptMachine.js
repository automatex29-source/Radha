import { useCallback, useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Download, FileText, Loader2, RotateCcw } from "lucide-react";

const rupees = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })} ${d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`;
};

// Bars for the little barcode at the foot of the receipt, the same for the same payment every time.
function bars(seed) {
  let h = 0;
  for (const c of seed || "krish") h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return Array.from({ length: 34 }, (_, i) => 1 + ((h >> (i % 24)) & 3));
}

// A short beep like a card machine's, when the browser allows sound.
function beep() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "square"; o.frequency.value = 2400;
    g.gain.setValueAtTime(0.04, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.16);
    o.connect(g).connect(ctx.destination);
    o.start(); o.stop(ctx.currentTime + 0.17);
    setTimeout(() => ctx.close(), 400);
  } catch { /* no sound */ }
}

function Row({ label, value, strong }) {
  return (
    <div className={`flex justify-between gap-3 ${strong ? "text-[13px] font-bold" : ""}`}>
      <span className="truncate">{label}</span><span className="shrink-0 tabular-nums">{value}</span>
    </div>
  );
}

function Contactless({ className = "" }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <path d="M8.5 7.5a6 6 0 0 1 0 9" /><path d="M12 5a9.5 9.5 0 0 1 0 14" /><path d="M15.5 2.5a13 13 0 0 1 0 19" />
    </svg>
  );
}

/** Settings > Billing: tap a payment, then tap the Krish card on the machine. It reads, beeps, and the receipt
 *  prints out of the top. The invoice PDF opens from the receipt or the buttons below it. */
export default function ReceiptMachine({ payment, onClose, onInvoice, opening }) {
  const p = payment;
  const [phase, setPhase] = useState("idle"); // idle (tap the card) -> reading -> approved (printing)
  const [run, setRun] = useState(0);
  const timers = useRef([]);
  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  const later = (fn, ms) => timers.current.push(setTimeout(fn, ms));
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  const tap = useCallback(() => { setPhase((ph) => (ph === "idle" ? "reading" : ph)); }, []);

  // A new payment: wait for a tap, or tap by itself after a moment.
  useEffect(() => {
    clear();
    if (!p) return undefined;
    setPhase("idle");
    later(tap, 2600);
    return clear;
  }, [p, tap]);
  // Reading the card: a moment later it is approved, beeps and prints.
  useEffect(() => {
    if (phase !== "reading") return undefined;
    const t = setTimeout(() => { setPhase("approved"); setRun((n) => n + 1); beep(); }, reduced ? 0 : 1300);
    return () => clearTimeout(t);
  }, [phase, reduced]);

  const again = () => { clear(); setPhase("idle"); later(tap, 350); };
  const listed = p ? (p.baseAmount ?? (p.amount - (p.gst || 0) - (p.platformFee || 0))) : 0;
  const printed = phase === "approved";

  return (
    <Dialog open={!!p} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-[400px] gap-0 overflow-x-hidden border-0 outline-none focus:outline-none focus-visible:outline-none bg-transparent p-0 shadow-none [&>button]:text-white/80 [&>button]:hover:bg-white/10"
        overlayClassName="bg-[radial-gradient(ellipse_at_center,rgba(30,27,46,0.82),rgba(5,5,10,0.94))] backdrop-blur-sm" data-testid="receipt-machine">
        <DialogTitle className="sr-only">Payment receipt</DialogTitle>
        <DialogDescription className="sr-only">The receipt for this payment, with links to the invoice.</DialogDescription>
        {p && (
          <div className="flex flex-col items-center px-4 pb-3 pt-5">
            {/* The receipt rises out of the printer slot. Tap it to open the invoice. */}
            <div className="relative z-0 -mb-[18px] w-[260px] overflow-hidden pt-2">
              {printed && (
                <button key={run} type="button" onClick={() => onInvoice(p, false)} aria-label="Open the invoice"
                  className="kai-receipt block w-full cursor-pointer text-left" data-testid="receipt-paper">
                  <div className="kai-receipt-paper relative mx-auto w-[236px] px-4 pb-8 pt-3 font-mono text-[11px] leading-[1.45] text-[#2b2b2b] transition-transform hover:-translate-y-0.5">
                    <div className="flex flex-col items-center text-center">
                      <img src="/icon-192.png" alt="" className="h-8 w-8 mix-blend-multiply" />
                      <p className="mt-1 text-[14px] font-bold tracking-[0.08em]">KRISH AI</p>
                      <p className="text-[10px] text-[#6b6b6b]">by EmpireX · krishai.net</p>
                    </div>
                    <p className="my-1.5 overflow-hidden whitespace-nowrap text-[#9a9a9a]">{"- ".repeat(40)}</p>
                    <Row label="Date" value={when(p.paidAt || p.createdAt)} />
                    {p.invoiceNo && <Row label="Invoice" value={p.invoiceNo} />}
                    <Row label="Paid by" value={p.autopay ? "Autopay" : "Razorpay"} />
                    <p className="my-1.5 overflow-hidden whitespace-nowrap text-[#9a9a9a]">{"- ".repeat(40)}</p>
                    <Row label={`${p.planName} plan, 30 days`} value={rupees(listed)} />
                    {p.promoCode && <Row label={`Offer ${p.promoCode}`} value="applied" />}
                    {p.gst > 0 && <Row label="GST 18%" value={rupees(p.gst)} />}
                    {p.platformFee > 0 && <Row label="Platform fee" value={rupees(p.platformFee)} />}
                    <p className="my-1.5 overflow-hidden whitespace-nowrap text-[#9a9a9a]">{"= ".repeat(40)}</p>
                    <Row label="TOTAL" value={rupees(p.amount)} strong />
                    <p className="mt-2 text-center text-[12px] font-bold tracking-[0.25em] text-[#15803d]">✓ APPROVED</p>
                    <div className="mx-auto mt-2 flex h-6 w-fit items-stretch gap-[2px]" aria-hidden>
                      {bars(p.orderId).map((w, i) => <span key={i} className="bg-[#2b2b2b]" style={{ width: w }} />)}
                    </div>
                    <p className="mt-2 text-center text-[10px] text-[#6b6b6b]">Thank you for choosing Krish AI</p>
                    <p className="kai-receipt-hint mt-2 text-center text-[10px] font-sans font-semibold text-[#FF6A1E]">Tap the receipt to open the invoice</p>
                  </div>
                </button>
              )}
            </div>

            {/* The card machine. */}
            <div className="relative z-10 w-[240px]">
              {/* printer housing with the paper slot */}
              <div className="relative mx-auto h-[26px] w-[224px] rounded-t-[22px] bg-gradient-to-b from-[#3b3f4b] to-[#2a2d36]">
                <div className="absolute inset-x-5 top-[9px] h-[7px] rounded-full bg-black shadow-[inset_0_2px_3px_rgba(0,0,0,1)]" />
              </div>
              <div className={`kai-pos-body rounded-[26px] rounded-t-[16px] bg-gradient-to-b from-[#2f323c] via-[#23262e] to-[#17191f] p-4 pt-3 shadow-[0_30px_60px_-15px_rgba(0,0,0,0.8),inset_0_1px_0_rgba(255,255,255,0.08)] ${phase === "reading" ? "kai-pos-shake" : ""}`}>
                <div className="mb-2 flex items-center justify-between px-1 text-[8px] font-semibold uppercase tracking-[0.25em] text-white/35">
                  <span>Krish Pay</span>
                  <span className={`h-2 w-2 rounded-full ${printed ? "bg-[#22c55e] shadow-[0_0_8px_#22c55e]" : phase === "reading" ? "kai-pos-led bg-[#f59e0b] shadow-[0_0_8px_#f59e0b]" : "bg-[#3b82f6] shadow-[0_0_6px_#3b82f6]"}`} />
                </div>
                {/* screen */}
                <button type="button" onClick={tap} disabled={phase !== "idle"} aria-label="Tap the card to print the receipt"
                  className="block w-full rounded-xl bg-gradient-to-b from-[#0f2a1f] to-[#0a1d15] px-3 pb-3 pt-1.5 text-center font-mono shadow-[inset_0_2px_10px_rgba(0,0,0,0.8)] outline-none ring-[#6ee7a8]/40 focus-visible:ring-2"
                  data-testid="receipt-tap">
                  <div className="flex items-center justify-between text-[8px] text-[#6ee7a8]/60"><span>▮▮▮▯ 4G</span><span>{(p.paidAt || p.createdAt || "").slice(11, 16)}</span><span>▭ 92%</span></div>
                  {phase === "idle" && (
                    <div className="py-1.5 text-[#6ee7a8]">
                      <Contactless className="kai-pos-wave mx-auto h-7 w-7" />
                      <p className="mt-0.5 text-[11px] font-bold tracking-wider">TAP CARD</p>
                      <p className="text-[9px] text-[#6ee7a8]/70">to print your receipt</p>
                    </div>
                  )}
                  {phase === "reading" && (
                    <div className="py-2.5 text-[#fcd34d]">
                      <p className="text-[12px] font-bold tracking-wider">READING CARD</p>
                      <div className="mt-2 flex justify-center gap-1.5"><span className="kai-dot" /><span className="kai-dot [animation-delay:.15s]" /><span className="kai-dot [animation-delay:.3s]" /></div>
                    </div>
                  )}
                  {printed && (
                    <div className="py-1.5 text-[#6ee7a8]">
                      <p className="text-[10px] tracking-[0.3em] text-[#6ee7a8]/70">APPROVED</p>
                      <p className="kai-pos-status text-[17px] font-bold">{rupees(p.amount)}</p>
                      <p className="kai-printing text-[9px] text-[#6ee7a8]/70">Receipt printed</p>
                    </div>
                  )}
                </button>
                {/* function keys and keypad */}
                <div className="mt-3 grid grid-cols-3 gap-1.5" aria-hidden>
                  <span className="h-2 rounded-full bg-[#b4232b]" /><span className="h-2 rounded-full bg-[#d97706]" /><span className="h-2 rounded-full bg-[#15803d]" />
                </div>
                <div className="mt-2 grid grid-cols-3 gap-1" aria-hidden>
                  {["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"].map((k) => (
                    <span key={k} className="flex h-[19px] items-center justify-center rounded-md bg-gradient-to-b from-[#454a57] to-[#353944] text-[10px] font-semibold text-white/85 shadow-[inset_0_-2px_0_rgba(0,0,0,0.4),0_1px_0_rgba(255,255,255,0.05)]">{k}</span>
                  ))}
                </div>
                <div className="mt-3 flex items-center justify-center gap-1.5 text-[8.5px] uppercase tracking-[0.22em] text-white/40">
                  <Contactless className="h-3 w-3" /> Secured by Razorpay
                </div>
              </div>
              {/* the Krish card: tap it onto the machine */}
              <button type="button" onClick={tap} disabled={phase !== "idle"} aria-label="Tap the Krish card on the machine"
                className={`kai-card absolute -right-7 bottom-6 h-[76px] w-[120px] rounded-xl bg-gradient-to-br from-[#FFB347] via-[#FF8A1E] to-[#F2552C] p-2 text-left text-white shadow-[0_14px_28px_-8px_rgba(242,85,44,0.7)] ${
                  phase === "idle" ? "kai-card-float" : "kai-card-tapped"}`} data-testid="receipt-card">
                <div className="flex items-center justify-between">
                  <span className="h-[14px] w-[19px] rounded-[3px] bg-gradient-to-br from-[#fde68a] to-[#d4a017] shadow-inner" />
                  <Contactless className="h-3.5 w-3.5 rotate-0 opacity-90" />
                </div>
                <p className="mt-2 text-[8px] tracking-[0.2em] opacity-85">•••• KRISH</p>
                <p className="text-[10px] font-bold tracking-wide">KRISH AI</p>
              </button>
            </div>

            <div className="mt-5 flex w-full max-w-[320px] items-center gap-2">
              <button type="button" onClick={() => onInvoice(p, false)} disabled={!!opening}
                className="kai-invoice-btn group relative flex h-12 flex-1 items-center justify-center gap-2 overflow-hidden rounded-2xl bg-gradient-to-r from-[#FF9A3C] via-[#FF7A1E] to-[#F2552C] text-[15px] font-semibold text-white shadow-[0_12px_28px_-8px_rgba(255,122,30,0.75)] transition-transform hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-70"
                data-testid="receipt-view-invoice">
                <span className="kai-invoice-shine pointer-events-none absolute inset-y-0 -left-1/2 w-1/3 skew-x-[-20deg] bg-white/35" />
                {opening === p.orderId ? <Loader2 className="h-4 w-4 animate-spin" /> : <><FileText className="h-[18px] w-[18px]" />View invoice</>}
              </button>
              <button type="button" onClick={() => onInvoice(p, true)} disabled={!!opening} aria-label="Download invoice"
                className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/15 bg-white/10 text-white backdrop-blur transition hover:bg-white/20"
                data-testid="receipt-download">
                {opening === p.orderId + ":d" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-[18px] w-[18px]" />}
              </button>
              <button type="button" onClick={again} aria-label="Print the receipt again"
                className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/15 bg-white/10 text-white backdrop-blur transition hover:bg-white/20"
                data-testid="receipt-reprint">
                <RotateCcw className="h-[18px] w-[18px]" />
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
