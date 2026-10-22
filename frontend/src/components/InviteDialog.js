import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, formatApiError } from "@/lib/api";
import { inviteLink, inviteMessage } from "@/lib/referral";
import { toast } from "sonner";
import { Check, ChevronDown, Copy, Loader2, Share2 } from "lucide-react";

function WhatsAppIcon({ className }) {
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
      <DialogContent className="max-h-[92dvh] w-[calc(100vw-2rem)] max-w-[26rem] overflow-y-auto rounded-2xl p-0 sm:rounded-2xl" data-testid="invite-dialog">
        <div className="min-w-0 px-5 pb-5 pt-6 sm:px-6">
          <DialogTitle className="pr-8 text-xl font-bold tracking-tight">Invite friends, get Pro free</DialogTitle>
          <DialogDescription className="mt-1 text-sm text-muted-foreground">
            Share your link. When a friend joins, you both get {data?.rewardDays || 7} days of Pro.
          </DialogDescription>

          {!data ? (
            <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
          ) : (
            <div className="min-w-0">
              <img src={picture} alt="The picture your friends see with your link" data-testid="invite-picture"
                className="mt-5 aspect-[1200/630] w-full rounded-xl border border-border/70 bg-white object-cover" />

              <div className="mt-4 grid grid-cols-2 gap-2 text-center" data-testid="invite-rewards">
                <div className="rounded-xl bg-surface px-3 py-2.5">
                  <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">You get</p>
                  <p className="mt-0.5 text-sm font-semibold">{data.rewardDays} days of Pro</p>
                </div>
                <div className="rounded-xl bg-surface px-3 py-2.5">
                  <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Your friend gets</p>
                  <p className="mt-0.5 text-sm font-semibold">{data.rewardDays} days of Pro</p>
                </div>
              </div>

              <label className="mt-5 block text-xs font-medium text-muted-foreground" htmlFor="invite-link-box">Your invite link</label>
              <div className="mt-1.5 flex min-w-0 items-center gap-1 rounded-xl border border-border bg-background p-1 pl-3">
                <input id="invite-link-box" readOnly value={shortLink} onFocus={(e) => e.target.select()} data-testid="invite-link"
                  className="min-w-0 flex-1 truncate bg-transparent text-sm outline-none" />
                <Button size="sm" variant="ghost" onClick={() => copy()} data-testid="invite-copy" className="h-8 shrink-0 rounded-lg px-3">
                  {copied ? <><Check className="mr-1.5 h-3.5 w-3.5 text-emerald-600" /> Copied</> : <><Copy className="mr-1.5 h-3.5 w-3.5" /> Copy</>}
                </Button>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2">
                <a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer" data-testid="invite-whatsapp"
                  className="flex h-11 min-w-0 items-center justify-center gap-2 rounded-xl border border-border bg-background text-sm font-semibold transition-colors hover:bg-surface">
                  <WhatsAppIcon className="h-[18px] w-[18px] shrink-0 text-[#25D366]" /> WhatsApp
                </a>
                {canShare ? (
                  <Button variant="outline" onClick={share} className="h-11 min-w-0 rounded-xl font-semibold" data-testid="invite-share">
                    <Share2 className="mr-2 h-4 w-4 shrink-0" /> More ways
                  </Button>
                ) : (
                  <Button variant="outline" onClick={() => copy(message)} className="h-11 min-w-0 rounded-xl font-semibold" data-testid="invite-copy-message">
                    <Copy className="mr-2 h-4 w-4 shrink-0" /> Copy message
                  </Button>
                )}
              </div>

              <button type="button" onClick={() => setShowMessage((s) => !s)} aria-expanded={showMessage} data-testid="invite-message-toggle"
                className="mt-3 flex w-full items-center justify-between rounded-lg px-1 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
                What your friends receive
                <ChevronDown className={`h-4 w-4 transition-transform ${showMessage ? "rotate-180" : ""}`} />
              </button>
              {showMessage && (
                <p className="mt-1 whitespace-pre-line break-words rounded-xl bg-surface px-3.5 py-3 text-[13px] leading-relaxed" data-testid="invite-message">
                  {message}
                </p>
              )}

              <div className="mt-4 border-t border-border pt-4" data-testid="invite-progress">
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="text-muted-foreground">
                    <b className="font-semibold text-foreground tabular-nums">{data.joined}</b> {data.joined === 1 ? "friend" : "friends"} joined
                  </span>
                  <span className="text-muted-foreground">
                    <b className="font-semibold text-foreground tabular-nums">{data.daysEarned}</b> Pro days earned
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-strong">
                  <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.min(100, (rewarded / data.maxRewards) * 100)}%` }} />
                </div>
                <p className="mt-1.5 text-[11px] text-muted-foreground">{rewarded} of {data.maxRewards} friends rewarded</p>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
