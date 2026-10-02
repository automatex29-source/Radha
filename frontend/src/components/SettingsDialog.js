import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { LANGUAGES, translate, useT } from "@/lib/i18n";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Check, Languages, Loader2, Settings } from "lucide-react";

/** Settings: for now the app language, which Krish replies in and the app's text follows. */
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
      </DialogContent>
    </Dialog>
  );
}
