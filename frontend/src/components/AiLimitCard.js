import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, BellRing, Check } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import BrandMark from "@/components/BrandMark";

const pad = (n) => String(n).padStart(2, "0");

/** In place of the reply when the free AI's usage limit is hit: a dark card with the Krish AI mark, a live
 *  hours / minutes / seconds clock to the reset, a bar that fills as it comes, Notify me and Upgrade. */
export default function AiLimitCard({ limit, id }) {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  const resets = limit?.resetsAt ? limit.resetsAt * 1000 : null;
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(Date.now());
  const [notify, setNotify] = useState(false);
  const notified = useRef(false);

  useEffect(() => {
    if (!resets || resets <= Date.now()) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [resets]);

  const ready = !!resets && resets <= now;
  useEffect(() => {
    if (!ready || !notify || notified.current) return;
    notified.current = true;
    try {
      if (typeof Notification !== "undefined" && Notification.permission === "granted") {
        new Notification("Krish AI is ready again", { body: "You can send your message now.", icon: "/icon-192.png" });
      }
    } catch { /* the in-page toast below still shows */ }
    toast.success("Krish AI is ready again. Send your message.");
  }, [ready, notify]);

  const askNotify = async () => {
    try {
      if (typeof Notification !== "undefined" && Notification.permission === "default") await Notification.requestPermission();
    } catch { /* not supported: the in-page toast still works */ }
    setNotify(true);
    toast("We'll let you know when Krish AI is ready.");
  };

  const left = resets ? Math.max(0, Math.ceil((resets - now) / 1000)) : 0;
  const parts = [["hours", Math.floor(left / 3600)], ["min", Math.floor((left % 3600) / 60)], ["sec", left % 60]];
  const progress = ready ? 100 : resets ? Math.min(100, Math.max(3, ((now - start) / Math.max(1, resets - start)) * 100)) : 0;
  const at = resets ? new Date(resets).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
  const next = user?.plan === "pro" ? "Max" : user?.plan === "max" ? null : "Pro";

  const title = ready ? "Krish AI is ready again" : limit?.daily ? "You've used today's free limit" : "You've used your free limit";
  const sub = ready ? "Send your message again to continue."
    : at ? `Krish will be back at ${at}` : limit?.daily ? "Krish will be back in a few hours" : "Krish will be back in about a minute";

  return (
    <div data-testid={`ai-limit-card-${id}`}
      className="krish-limit radha-fade-up relative mt-1 max-w-[30rem] overflow-hidden rounded-2xl border border-white/10 bg-[#0f0f17] p-5 text-white shadow-[0_18px_50px_-24px_rgba(0,0,0,0.6)]">
      <div aria-hidden className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-[radial-gradient(circle,rgba(249,115,22,0.35),transparent_65%)]" />
      <div className="relative flex items-center gap-3">
        <BrandMark className="h-10 w-10 shrink-0 text-white" thinking={!ready} />
        <div className="min-w-0">
          <p className="font-heading text-[16px] font-semibold tracking-tight">{title}</p>
          <p className="text-[13px] text-[#a1a1b5]" data-testid="ai-limit-when">{sub}</p>
        </div>
        {ready && <Check className="ml-auto h-5 w-5 shrink-0 text-emerald-400" />}
      </div>

      {resets && !ready && (
        <div className="relative mt-4 grid grid-cols-3 gap-2" data-testid="ai-limit-clock">
          {parts.map(([label, n]) => (
            <div key={label} className="rounded-xl border border-white/10 bg-white/[0.04] py-2.5 text-center">
              <span key={n} className="krish-limit-digit block font-mono text-[24px] font-semibold tabular-nums tracking-tight">{pad(n)}</span>
              <span className="text-[10px] uppercase tracking-[0.14em] text-[#8a8aa0]">{label}</span>
            </div>
          ))}
        </div>
      )}
      <div className="relative mt-4 h-1 overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full transition-[width] duration-1000 ease-linear ${ready ? "bg-emerald-400" : "bg-gradient-to-r from-orange-500 to-amber-400"}`}
          style={{ width: `${progress}%` }} />
      </div>

      {!ready && (
        <div className="relative mt-4 flex gap-2">
          {resets && (
            <button onClick={askNotify} disabled={notify} data-testid="ai-limit-notify"
              className="flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg border border-white/15 text-[13px] font-medium text-[#d4d4e0] transition-colors hover:bg-white/5 disabled:opacity-70">
              {notify ? <BellRing className="h-3.5 w-3.5 text-amber-400" /> : <Bell className="h-3.5 w-3.5" />}
              {notify ? "We'll notify you" : "Notify me"}
            </button>
          )}
          {next && (
            <button onClick={() => navigate("/plans")} data-testid="ai-limit-upgrade"
              className="h-9 flex-1 rounded-lg bg-white text-[13px] font-semibold text-[#0f0f17] transition-transform hover:opacity-90 active:scale-[0.97]">
              Upgrade to {next}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
