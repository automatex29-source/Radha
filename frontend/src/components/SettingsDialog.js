import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { LANGUAGES, translate, useT } from "@/lib/i18n";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Check, Languages, Loader2, Settings, Trash2 } from "lucide-react";

/** Settings: the app language, which Krish replies in and the app's text follows, and deleting the account. */
export default function SettingsDialog({ open, onOpenChange }) {
  const { setLanguage } = useAuth();
  const t = useT();
  const [saving, setSaving] = useState(null);

  const choose = async (code) => {
    if (code === t.lang || saving) return;
    setSaving(code);
    try {
      await setLanguage(code);
      toast.success(translate(code, "languageSaved"));
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(null); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="settings-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Settings className="h-4 w-4 text-primary" /> {t("settings")}</DialogTitle>
        </DialogHeader>
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold"><Languages className="h-4 w-4 text-primary" /> {t("language")}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{t("languageHint")}</p>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3" role="radiogroup" aria-label={t("language")}>
            {LANGUAGES.map((l) => {
              const on = l.code === t.lang;
              return (
                <button key={l.code} role="radio" aria-checked={on} onClick={() => choose(l.code)}
                  data-testid={`language-option-${l.code}`}
                  className={`flex items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left transition-colors ${
                    on ? "border-primary bg-primary/10 ring-1 ring-primary/40" : "border-border bg-card hover:bg-surface"
                  }`}>
                  <span className="min-w-0 leading-tight">
                    <span className="block truncate text-sm font-medium" dir={l.rtl ? "rtl" : undefined}>{l.native}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{l.name}</span>
                  </span>
                  {saving === l.code ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                    : on ? <Check className="h-4 w-4 shrink-0 text-primary" /> : null}
                </button>
              );
            })}
          </div>
        </div>
        <DeleteAccount />
      </DialogContent>
    </Dialog>
  );
}

/** Deletes the account and everything in it, after the password is typed again. */
function DeleteAccount() {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/delete-account", { password });
      toast.success("Your account and everything in it was deleted.");
      await logout();
    } catch (err) {
      toast.error(formatApiError(err));
      setBusy(false);
    }
  };

  return (
    <div className="border-t border-border pt-4" data-testid="delete-account-section">
      <p className="flex items-center gap-2 text-sm font-semibold"><Trash2 className="h-4 w-4 text-destructive" /> Delete account</p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Permanently removes your account, chats, files, projects, apps, decks, docs, automations and memory. This can't be undone.
      </p>
      {!open ? (
        <Button type="button" variant="outline" onClick={() => setOpen(true)} data-testid="delete-account-start"
          className="mt-3 h-9 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive">
          Delete my account
        </Button>
      ) : (
        <form onSubmit={submit} className="mt-3 flex flex-col gap-2 sm:flex-row">
          <Input type="password" autoComplete="current-password" autoFocus required value={password}
            onChange={(e) => setPassword(e.target.value)} placeholder="Type your password to confirm"
            data-testid="delete-account-password" className="h-9 flex-1" />
          <Button type="submit" variant="destructive" disabled={busy || !password} data-testid="delete-account-confirm" className="h-9">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Delete forever"}
          </Button>
        </form>
      )}
    </div>
  );
}
