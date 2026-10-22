import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { LANGUAGES, translate, useT } from "@/lib/i18n";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Bell, Check, Languages, Loader2, Settings, Smartphone, Trash2 } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { canInstall, install, isIos, isStandalone, onInstallChange, pushSupported, turnVerseOff, turnVerseOn, verseOn } from "@/lib/pwa";

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
        <DailyVerse />
        <InstallApp />
        <DeleteAccount />
      </DialogContent>
    </Dialog>
  );
}

/** The daily Gita verse: a notification on this device each morning at 7 (India time). */
function DailyVerse() {
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { verseOn().then(setOn).catch(() => {}); }, []);

  const toggle = async (next) => {
    setBusy(true);
    try {
      if (next) {
        await turnVerseOn();
        await api.post("/push/test").catch(() => {});
        toast.success("Done. Here's today's verse; the next one comes tomorrow morning.");
      } else {
        await turnVerseOff();
      }
      setOn(next);
    } catch (e) {
      toast.error(e?.response ? formatApiError(e) : e.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="border-t border-border pt-4" data-testid="daily-verse-section">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold"><Bell className="h-4 w-4 text-primary" /> Daily Gita verse</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {pushSupported() || !isIos() ? "A short verse and its meaning on this device every morning at 7."
              : "On iPhone, add Krish to your home screen first, then turn this on from there."}
          </p>
        </div>
        {busy ? <Loader2 className="h-4 w-4 animate-spin text-primary" />
          : <Switch checked={on} onCheckedChange={toggle} aria-label="Daily Gita verse" data-testid="daily-verse-toggle" />}
      </div>
    </div>
  );
}

/** Install Krish as an app on the home screen (Android and desktop open the browser's own window). */
function InstallApp() {
  const [ready, setReady] = useState(canInstall());
  useEffect(() => onInstallChange(setReady), []);
  if (isStandalone() || (!ready && !isIos())) return null;
  return (
    <div className="border-t border-border pt-4" data-testid="install-app-section">
      <p className="flex items-center gap-2 text-sm font-semibold"><Smartphone className="h-4 w-4 text-primary" /> Krish on your home screen</p>
      {ready ? (
        <>
          <p className="mt-0.5 text-xs text-muted-foreground">Open Krish like an app, full screen, straight from your home screen.</p>
          <Button type="button" variant="outline" onClick={install} className="mt-3 h-9" data-testid="install-app-button">Install app</Button>
        </>
      ) : (
        <p className="mt-0.5 text-xs text-muted-foreground">In Safari, tap the Share button, then <b>Add to Home Screen</b>.</p>
      )}
    </div>
  );
}

/** Deletes the account and everything in it, after the password (or, for Google accounts, the email) is typed again. */
function DeleteAccount() {
  const { logout, user } = useAuth();
  const byEmail = user && user.hasPassword === false;
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/delete-account", byEmail ? { confirmEmail: password } : { password });
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
          <Input type={byEmail ? "email" : "password"} autoComplete={byEmail ? "off" : "current-password"} autoFocus required value={password}
            onChange={(e) => setPassword(e.target.value)} placeholder={byEmail ? `Type ${user.email} to confirm` : "Type your password to confirm"}
            data-testid="delete-account-password" className="h-9 flex-1" />
          <Button type="submit" variant="destructive" disabled={busy || !password} data-testid="delete-account-confirm" className="h-9">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Delete forever"}
          </Button>
        </form>
      )}
    </div>
  );
}
