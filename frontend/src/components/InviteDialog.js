import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, formatApiError } from "@/lib/api";
import { inviteLink } from "@/lib/referral";
import { toast } from "sonner";
import { Check, Copy, Gift, Loader2, MessageCircle, Share2 } from "lucide-react";

/** Invite friends: a personal link that gives the friend and the inviter free days of Pro. */
export default function InviteDialog({ open, onOpenChange }) {
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/referrals").then(({ data }) => setData(data)).catch((e) => toast.error(formatApiError(e)));
  }, [open]);

  const link = data ? inviteLink(data.code) : "";
  const message = data ? `I'm using Krish AI, a smart AI helper for chat, study, apps and more. Join with my link and we both get ${data.rewardDays} days of Pro free: ${link}` : "";

  const copy = async () => {
    try { await navigator.clipboard.writeText(link); } catch { /* the link is on screen */ }
    setCopied(true);
    toast.success("Invite link copied");
    setTimeout(() => setCopied(false), 1500);
  };
  const share = async () => {
    try { await navigator.share({ title: "Krish AI", text: message }); } catch { /* closed */ }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="invite-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Gift className="h-4 w-4 text-primary" /> Invite friends</DialogTitle>
        </DialogHeader>
        {!data ? (
          <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
        ) : (
          <div>
            <p className="text-sm text-muted-foreground">
              When a friend signs up with your link, you <b className="text-foreground">both get {data.rewardDays} days of Pro</b> free.
              You can earn this for up to {data.maxRewards} friends.
            </p>
            <div className="mt-4 flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2">
              <span className="min-w-0 flex-1 truncate font-mono text-sm" data-testid="invite-link">{link}</span>
              <Button size="sm" variant="outline" onClick={copy} data-testid="invite-copy">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer" data-testid="invite-whatsapp"
                className="flex h-10 items-center justify-center gap-2 rounded-xl bg-[#25D366] text-sm font-semibold text-white">
                <MessageCircle className="h-4 w-4" /> WhatsApp
              </a>
              {typeof navigator !== "undefined" && navigator.share ? (
                <Button variant="outline" onClick={share} className="h-10 rounded-xl"><Share2 className="mr-2 h-4 w-4" /> Share</Button>
              ) : (
                <Button variant="outline" onClick={copy} className="h-10 rounded-xl"><Copy className="mr-2 h-4 w-4" /> Copy link</Button>
              )}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3 border-t border-border pt-4 text-center">
              <div><p className="text-2xl font-extrabold tabular-nums">{data.joined}</p><p className="text-xs text-muted-foreground">friends joined</p></div>
              <div><p className="text-2xl font-extrabold tabular-nums">{data.daysEarned}</p><p className="text-xs text-muted-foreground">free Pro days earned</p></div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
