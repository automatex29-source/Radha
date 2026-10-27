import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, formatApiError } from "@/lib/api";
import { inviteLink, inviteMessage } from "@/lib/referral";
import { toast } from "sonner";
import { Check, ChevronDown, Copy, Loader2, Share2 } from "lucide-react";

export function WhatsAppIcon({ className }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="currentColor">
      <path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.8 11.9 11.9 0 0 0 4.6 4c1.7.7 2.4.8 3.2.6a2.8 2.8 0 0 0 1.8-1.3 2.3 2.3 0 0 0 .2-1.3c-.1-.1-.2-.2-.5-.3Z" />
    </svg>
  );
}

/** Invite friends: a personal link that gives the friend and the inviter free days of Pro. */
export default function InviteDialog({ open, onOpenChange }) {
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [showMessage, setShowMessage] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/referrals").then(({ data }) => setData(data)).catch((e) => toast.error(formatApiError(e)));
  }, [open]);

  const link = data ? inviteLink(data.code) : "";
  const shortLink = link.replace(/^https?:\/\//, "");
  const message = data ? inviteMessage(link, data.rewardDays) : "";
  const picture = data ? `/api/cards/invite/${data.code}.png` : "";
  const canShare = typeof navigator !== "undefined" && Boolean(navigator.share);
  const rewarded = data ? Math.round(data.daysEarned / Math.max(1, data.rewardDays)) : 0;

  const copy = async (text = link) => {
    try { await navigator.clipboard.writeText(text); } catch { /* the link is on screen */ }
    if (text === link) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
    toast.success(text === link ? "Invite link copied" : "Invite message copied. Paste it anywhere");
  };
  // On phones the invite picture goes along with the message, so it stands out in the chat.
  const share = async () => {
    try {
      const blob = await fetch(picture).then((r) => r.blob());
      const file = new File([blob], "krish-ai-invite.png", { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: "Krish AI", text: message });
        return;
      }
    } catch (e) {
      if (e?.name === "AbortError") return;
    }
    try { await navigator.share({ title: "Krish AI", text: message }); } catch { /* closed */ }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] w-[calc(100vw-2rem)] max-w-[26rem] gap-0 overflow-y-auto rounded-3xl border-0 p-0 shadow-2xl sm:rounded-3xl [&>button]:text-white/70 [&>button]:hover:text-white"
        data-testid="invite-dialog">
        <div className="relative overflow-hidden bg-[#0b0c14] px-6 pb-6 pt-7 text-white">
          <div className="pointer-events-none absolute -left-16 top-6 h-56 w-56 rounded-full bg-orange-500/25 blur-3xl" />
          <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-indigo-500/30 blur-3xl" />
          <p className="relative text-[11px] font-medium uppercase tracking-[0.18em] text-white/55">Krish AI Rewards</p>
          <DialogTitle className="relative mt-2 text-[1.65rem] font-semibold leading-tight tracking-tight">
            Give Pro. <span className="text-[#ffb048]">Get Pro.</span>
          </DialogTitle>
          <DialogDescription className="relative mt-1.5 text-sm leading-relaxed text-white/70">
            When a friend joins with your link, they get {data?.rewardDays || 7} days of Krish AI Pro, on us. You get {data?.rewardDays || 7} days too, once.
          </DialogDescription>
          {data && (
            <img src={picture} alt="The picture your friends see with your link" data-testid="invite-picture"
              className="relative mt-5 aspect-[1200/630] w-full rounded-2xl object-cover shadow-[0_20px_50px_-15px_rgba(0,0,0,0.8)] ring-1 ring-white/10" />
          )}
        </div>

        <div className="min-w-0 px-6 pb-6 pt-5">
          {!data ? (
            <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
          ) : (
            <div className="min-w-0">
              <Button onClick={canShare ? share : () => copy(message)} data-testid="invite-share"
                className="h-12 w-full rounded-2xl bg-foreground text-[15px] font-semibold text-background hover:bg-foreground/90">
                {canShare ? <><Share2 className="mr-2 h-4 w-4" /> Share your invite</> : <><Copy className="mr-2 h-4 w-4" /> Copy invite message</>}
              </Button>

              <div className="mt-2.5 grid grid-cols-2 gap-2.5">
                <a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer" data-testid="invite-whatsapp"
                  className="flex h-11 min-w-0 items-center justify-center gap-2 rounded-2xl border border-border text-sm font-medium transition-colors hover:bg-surface">
                  <WhatsAppIcon className="h-[18px] w-[18px] shrink-0 text-[#25D366]" /> WhatsApp
                </a>
                <button type="button" onClick={() => copy()} data-testid="invite-copy"
                  className="flex h-11 min-w-0 items-center justify-center gap-2 rounded-2xl border border-border text-sm font-medium transition-colors hover:bg-surface">
                  {copied ? <><Check className="h-4 w-4 shrink-0 text-emerald-600" /> Copied</> : <><Copy className="h-4 w-4 shrink-0" /> Copy link</>}
                </button>
              </div>

              <div className="mt-4 flex min-w-0 items-center gap-2 rounded-xl bg-surface px-3.5 py-2.5">
                <span className="shrink-0 text-xs text-muted-foreground">Your link</span>
                <input readOnly value={shortLink} onFocus={(e) => e.target.select()} aria-label="Your invite link" data-testid="invite-link"
                  className="min-w-0 flex-1 truncate bg-transparent text-right text-[13px] font-medium outline-none" />
              </div>

              <button type="button" onClick={() => setShowMessage((s) => !s)} aria-expanded={showMessage} data-testid="invite-message-toggle"
                className="mt-3 flex w-full items-center justify-between py-1 text-xs font-medium text-muted-foreground hover:text-foreground">
                Preview the message
                <ChevronDown className={`h-4 w-4 transition-transform ${showMessage ? "rotate-180" : ""}`} />
              </button>
              {showMessage && (
                <p className="mt-1.5 whitespace-pre-line break-words rounded-xl border border-border/70 px-3.5 py-3 text-[13px] leading-relaxed text-foreground/90" data-testid="invite-message">
                  {message}
                </p>
              )}

              <div className="mt-5 border-t border-border/70 pt-4" data-testid="invite-progress">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium">Your rewards</span>
                  <span className="text-muted-foreground tabular-nums">{rewarded >= data.maxRewards ? "Claimed" : `${data.rewardDays} Pro days, once`}</span>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {data.daysEarned
                    ? <><b className="font-semibold text-foreground">{data.daysEarned} Pro days</b> earned. {data.joined} {data.joined === 1 ? "friend has" : "friends have"} joined, and every new friend still gets {data.rewardDays} days.</>
                    : `No friends yet. Your first friend to join earns you ${data.rewardDays} days of Pro.`}
                </p>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
