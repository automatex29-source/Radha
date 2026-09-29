import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Check, Copy, Link2, Loader2 } from "lucide-react";

const shareLink = (shareId) => `${window.location.origin}/share/${shareId}`;

/** Create, copy or turn off the public read-only link for a conversation. */
export default function ShareDialog({ open, onOpenChange, conversation, onChange }) {
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const shareId = conversation?.shareId;

  useEffect(() => { if (open) setCopied(false); }, [open]);

  const create = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/conversations/${conversation.id}/share`);
      onChange?.(data.shareId);
      copy(data.shareId);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(false); }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await api.delete(`/conversations/${conversation.id}/share`);
      onChange?.(null);
      toast.success("Link turned off");
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(false); }
  };

  const copy = async (id = shareId) => {
    try {
      await navigator.clipboard.writeText(shareLink(id));
      setCopied(true);
      toast.success("Link copied");
    } catch { /* clipboard blocked: the link is shown to copy by hand */ }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="share-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Link2 className="h-4 w-4 text-primary" /> Share this chat</DialogTitle>
          <DialogDescription>
            Anyone with the link can read this chat, including new messages, but can't reply or see your other chats.
          </DialogDescription>
        </DialogHeader>
        {shareId ? (
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input readOnly value={shareLink(shareId)} onFocus={(e) => e.target.select()} className="bg-card font-mono text-xs" data-testid="share-link-input" />
              <Button onClick={() => copy()} className="gap-1.5" data-testid="share-copy-button">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <Button variant="ghost" size="sm" onClick={stop} disabled={busy} data-testid="share-stop-button"
              className="text-muted-foreground hover:text-destructive">
              {busy && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />} Stop sharing
            </Button>
          </div>
        ) : (
          <Button onClick={create} disabled={busy || !conversation} className="gap-1.5" data-testid="share-create-button">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />} Create link
          </Button>
        )}
      </DialogContent>
    </Dialog>
  );
}
