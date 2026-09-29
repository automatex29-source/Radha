import { useState } from "react";
import { toast } from "sonner";
import { Github, Loader2, ExternalLink } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";

const TOKEN_KEY = "radha_github_token";
const NEW_TOKEN_URL = "https://github.com/settings/tokens/new?scopes=repo&description=RADHA%20App%20Builder";

const readToken = () => { try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; } };

/** Sends the app's current files to a GitHub repository (created if needed). */
export default function GitHubPushButton({ app, onPushed }) {
  const slug = app.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "my-app";
  const [open, setOpen] = useState(false);
  const [repo, setRepo] = useState(app.github?.repo || slug);
  const [token, setToken] = useState(readToken);
  const [remember, setRemember] = useState(true);
  const [isPrivate, setIsPrivate] = useState(true);
  const [busy, setBusy] = useState(false);

  const push = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/apps/${app.id}/github`, { repo: repo.trim(), token: token.trim(), private: isPrivate });
      try { remember ? localStorage.setItem(TOKEN_KEY, token.trim()) : localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
      toast.success(data.created ? `Created ${data.repo} on GitHub` : `Pushed to ${data.repo}`, {
        action: { label: "Open", onClick: () => window.open(data.url, "_blank", "noopener") },
      });
      setOpen(false);
      onPushed?.();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button data-testid="github-push-button" title="Send the code to GitHub"
          className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-xs font-medium hover:border-primary/50">
          <Github className="h-3.5 w-3.5" /> GitHub
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Push to GitHub</DialogTitle>
          <DialogDescription>
            RADHA sends this app's files to a GitHub repository, and creates it if it doesn't exist yet.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="gh-repo">Repository</Label>
            <Input id="gh-repo" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="my-app" className="bg-card" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gh-token">GitHub token</Label>
            <Input id="gh-token" type="password" value={token} onChange={(e) => setToken(e.target.value)}
              placeholder="ghp_…" className="bg-card font-mono" autoComplete="off" />
            <a href={NEW_TOKEN_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
              Create a token (tick “repo”, then Generate) <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} /> Make a new repository private
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Remember the token on this device
          </label>
          {app.github?.url && (
            <a href={app.github.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              Last pushed to {app.github.repo} <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
        <DialogFooter>
          <Button onClick={push} disabled={busy || !repo.trim() || token.trim().length < 10} data-testid="github-push-submit">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Push"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
