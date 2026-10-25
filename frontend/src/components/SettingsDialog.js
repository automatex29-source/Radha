import { lazy, Suspense, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTheme } from "next-themes";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { LANGUAGES, translate, useT } from "@/lib/i18n";
import { api, formatApiError } from "@/lib/api";
import { OPEN_SETTINGS_EVENT } from "@/lib/settingsNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import MemoryDialog from "@/components/MemoryDialog";
import { toast } from "sonner";
import {
  Bell, Blocks, Brain, Check, ChevronLeft, ChevronRight, CreditCard, Crown, Download, ExternalLink, Gauge, Languages,
  Loader2, LogOut, Monitor, Moon, Pencil, Plug, Settings, Shield, Smartphone, Sun, Trash2, User,
} from "lucide-react";
import { canInstall, install, isIos, isStandalone, onInstallChange, pushSupported, turnVerseOff, turnVerseOn, verseOn } from "@/lib/pwa";

const ConnectorsPanel = lazy(() => import("@/components/settings/ConnectorsPanel"));
const PluginsPanel = lazy(() => import("@/components/settings/PluginsPanel"));

const SECTIONS = [
  { group: "Settings", items: [
    { id: "general", label: "General", icon: Settings },
    { id: "account", label: "Account", icon: User },
    { id: "privacy", label: "Privacy", icon: Shield },
    { id: "billing", label: "Billing", icon: CreditCard },
    { id: "usage", label: "Usage", icon: Gauge },
    { id: "notifications", label: "Notifications", icon: Bell },
  ] },
  { group: "Customize", items: [
    { id: "connectors", label: "Connectors", icon: Blocks },
    { id: "plugins", label: "Plugins", icon: Plug },
  ] },
];
const ALL = SECTIONS.flatMap((g) => g.items);

/** Mounted once for signed-in users: opens Settings from openSettings(), and after an app sign-in returns
 *  (?settings=connectors&connected=gmail). */
export function SettingsHost() {
  const [section, setSection] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onOpen = (e) => { setSection(e.detail || null); setOpen(true); };
    window.addEventListener(OPEN_SETTINGS_EVENT, onOpen);
    const params = new URLSearchParams(window.location.search);
    const wanted = params.get("settings");
    if (wanted) {
      setSection(ALL.some((s) => s.id === wanted) ? wanted : null);
      setOpen(true);
      if (params.get("connectError")) toast.error(params.get("connectError"));
      for (const key of ["settings", "connected", "connectError"]) params.delete(key);
      const rest = params.toString();
      window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : "") + window.location.hash);
    }
    return () => window.removeEventListener(OPEN_SETTINGS_EVENT, onOpen);
  }, []);

  return <SettingsDialog open={open} onOpenChange={setOpen} section={section} />;
}

/** Settings, laid out like Claude's: a side list of sections; on a phone, the list first, then one section. */
export default function SettingsDialog({ open, onOpenChange, section = null }) {
  const t = useT();
  const [active, setActive] = useState(section || "general");
  const [mobileList, setMobileList] = useState(!section);
  useEffect(() => {
    if (open) { setActive(section || "general"); setMobileList(!section); }
  }, [open, section]);

  const go = (id) => { setActive(id); setMobileList(false); };
  const current = ALL.find((s) => s.id === active) || ALL[0];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="settings-dialog" onOpenAutoFocus={(e) => e.preventDefault()}
        className="flex h-[100dvh] max-h-[100dvh] w-full max-w-full flex-col gap-0 overflow-hidden rounded-none p-0 outline-none focus:outline-none focus-visible:ring-0 sm:h-[min(760px,90dvh)] sm:max-w-[960px] sm:flex-row sm:rounded-2xl">
        <DialogTitle className="sr-only">{t("settings")}</DialogTitle>
        <DialogDescription className="sr-only">Your Krish AI settings</DialogDescription>
        <nav className={`${mobileList ? "flex" : "hidden"} min-h-0 w-full flex-1 flex-col overflow-y-auto border-border bg-sunken px-3 pb-6 pt-5 sm:flex sm:w-60 sm:flex-none sm:shrink-0 sm:border-r`}
          aria-label="Settings sections">
          <p className="px-3 pb-3 font-heading text-lg font-semibold sm:hidden">{t("settings")}</p>
          {SECTIONS.map((g) => (
            <div key={g.group} className="mb-3">
              <p className="px-3 pb-1.5 pt-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{g.group}</p>
              {g.items.map(({ id, label, icon: Icon }) => {
                const on = id === active;
                return (
                  <button key={id} type="button" onClick={() => go(id)} data-testid={`settings-nav-${id}`}
                    aria-current={on ? "page" : undefined}
                    className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[14px] transition-colors sm:py-2 ${
                      on ? "sm:bg-surface-strong sm:font-semibold sm:text-brand" : "hover:bg-surface"}`}>
                    <Icon className={`h-[18px] w-[18px] shrink-0 ${on ? "sm:text-brand" : "text-muted-foreground"}`} strokeWidth={1.8} />
                    <span className="flex-1">{label}</span>
                    <ChevronRight className="h-4 w-4 text-muted-foreground sm:hidden" />
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <section className={`${mobileList ? "hidden" : "flex"} min-w-0 flex-1 flex-col sm:flex`}>
          <header className="flex items-center gap-2 border-b border-border px-4 py-3 sm:hidden">
            <button type="button" onClick={() => setMobileList(true)} className="-ml-1 flex h-9 w-9 items-center justify-center rounded-lg hover:bg-surface"
              aria-label="All settings" data-testid="settings-back"><ChevronLeft className="h-5 w-5" /></button>
            <p className="font-heading text-base font-semibold">{current.label}</p>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-10 pt-5 sm:px-9 sm:pt-8" data-testid={`settings-section-${active}`}>
            <Suspense fallback={<div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>}>
              {active === "general" && <General />}
              {active === "account" && <Account onClose={() => onOpenChange(false)} />}
              {active === "privacy" && <Privacy go={go} />}
              {active === "billing" && <Billing onClose={() => onOpenChange(false)} />}
              {active === "usage" && <Usage onClose={() => onOpenChange(false)} />}
              {active === "notifications" && <Notifications go={go} />}
              {active === "connectors" && <ConnectorsPanel onClose={() => onOpenChange(false)} />}
              {active === "plugins" && <PluginsPanel onClose={() => onOpenChange(false)} />}
            </Suspense>
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ pieces
export function PageTitle({ title, hint }) {
  return (
    <div className="mb-6 hidden sm:block">
      <h2 className="font-heading text-[22px] font-semibold tracking-tight">{title}</h2>
      {hint && <p className="mt-1 text-[13.5px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function Block({ title, hint, icon: Icon, children, right, testid }) {
  return (
    <div className="border-b border-border py-5 first:pt-0 last:border-0" data-testid={testid}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[14px] font-semibold">{Icon && <Icon className="h-4 w-4 text-muted-foreground" />}{title}</p>
          {hint && <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted-foreground">{hint}</p>}
        </div>
        {right}
      </div>
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "");

// ----------------------------------------------------------------- General
function General() {
  const { setLanguage } = useAuth();
  const t = useT();
  const [saving, setSaving] = useState(null);
  const { theme, setTheme } = useTheme();

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
    <>
      <PageTitle title="General" hint="How Krish looks and which language it speaks." />
      <Block title={t("language")} hint={t("languageHint")} icon={Languages} testid="settings-language">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-3" role="radiogroup" aria-label={t("language")}>
          {LANGUAGES.map((l) => {
            const on = l.code === t.lang;
            return (
              <button key={l.code} role="radio" aria-checked={on} onClick={() => choose(l.code)} data-testid={`language-option-${l.code}`}
                className={`flex items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left transition-colors ${
                  on ? "border-primary bg-primary/10 ring-1 ring-primary/40" : "border-border bg-card hover:bg-surface"}`}>
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
      </Block>
      <Block title="Appearance" hint="Light, dark, or follow your device." icon={Sun} testid="settings-appearance">
        <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Appearance">
          {[["light", "Light", Sun], ["dark", "Dark", Moon], ["system", "Device", Monitor]].map(([id, label, Icon]) => {
            const on = (theme || "light") === id;
            return (
              <button key={id} role="radio" aria-checked={on} onClick={() => setTheme(id)} data-testid={`theme-${id}`}
                className={`flex flex-col items-center gap-2 rounded-xl border p-3 text-sm transition-colors ${
                  on ? "border-primary bg-primary/10 font-medium ring-1 ring-primary/40" : "border-border hover:bg-surface"}`}>
                <span className={`flex h-12 w-full items-center justify-center rounded-lg border border-border ${
                  id === "dark" ? "bg-[#0b0d14] text-white" : id === "light" ? "bg-white text-[#151a28]" : "bg-gradient-to-r from-white to-[#0b0d14] text-[#6366f1]"}`}>
                  <Icon className="h-4 w-4" />
                </span>
                {label}
              </button>
            );
          })}
        </div>
      </Block>
      <InstallApp />
    </>
  );
}

function InstallApp() {
  const [ready, setReady] = useState(canInstall());
  useEffect(() => onInstallChange(setReady), []);
  if (isStandalone() || (!ready && !isIos())) return null;
  return (
    <Block title="Krish on your home screen" icon={Smartphone} testid="install-app-section"
      hint={ready ? "Open Krish like an app, full screen, straight from your home screen."
        : <>In Safari, tap the Share button, then <b>Add to Home Screen</b>.</>}
      right={ready ? <Button type="button" variant="outline" onClick={install} className="h-9 shrink-0" data-testid="install-app-button">Install app</Button> : null} />
  );
}

// ----------------------------------------------------------------- Account
function Account({ onClose }) {
  const { user, setUser, logout } = useAuth();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user?.name || "");
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.put("/auth/profile", { name });
      setUser(data);
      setEditing(false);
      toast.success("Name saved.");
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title="Account" hint="Who you are on Krish, and how you sign in." />
      <div className="mb-6 flex items-center gap-4 rounded-2xl border border-border bg-card p-4">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-sky-400 text-xl font-bold text-white">
          {user?.name?.[0]?.toUpperCase() || "U"}
        </div>
        <div className="min-w-0 flex-1">
          {editing ? (
            <form onSubmit={save} className="flex gap-2">
              <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={80} className="h-9" data-testid="account-name-input" />
              <Button type="submit" disabled={busy || !name.trim()} className="h-9" data-testid="account-name-save">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}</Button>
            </form>
          ) : (
            <p className="flex items-center gap-2 truncate text-base font-semibold">{user?.name}
              <button type="button" onClick={() => { setName(user?.name || ""); setEditing(true); }} aria-label="Change name"
                className="rounded-md p-1 text-muted-foreground hover:bg-surface hover:text-foreground" data-testid="account-name-edit"><Pencil className="h-3.5 w-3.5" /></button>
            </p>
          )}
          <p className="truncate text-sm text-muted-foreground">{user?.email}</p>
        </div>
      </div>
      <Block title="Sign-in" hint={user?.google ? (user?.hasPassword ? "Google, or your email and password" : "With Google") : "Email and password"}
        right={<Button variant="outline" className="h-9 shrink-0" onClick={async () => { onClose(); await logout(); }} data-testid="account-logout">
          <LogOut className="mr-1.5 h-4 w-4" /> Sign out</Button>} />
      <Block title="Member since" hint={fmtDate(user?.createdAt)} />
      <Block title="Plan" hint={`Krish ${({ basic: "Basic", pro: "Pro", max: "Max" })[user?.plan] || "Basic"}${user?.planExpiresAt ? `, until ${fmtDate(user.planExpiresAt)}` : ""}`} />
      <DeleteAccount />
    </>
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
    <div className="mt-6 rounded-2xl border border-destructive/30 bg-destructive/[0.04] p-4" data-testid="delete-account-section">
      <p className="flex items-center gap-2 text-sm font-semibold text-destructive"><Trash2 className="h-4 w-4" /> Delete account</p>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
        Permanently removes your account, chats, files, projects, apps, decks, docs, automations, connected apps and memory. This can't be undone.
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

// ----------------------------------------------------------------- Privacy
function Privacy({ go }) {
  const [auto, setAuto] = useState(null);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [apps, setApps] = useState(null);

  useEffect(() => {
    api.get("/memory/settings").then(({ data }) => setAuto(data.auto)).catch(() => setAuto(true));
    api.get("/connectors").then(({ data }) => setApps(data.connectors.filter((c) => c.connected))).catch(() => setApps([]));
  }, []);

  const toggleMemory = async (next) => {
    setAuto(next);
    try { await api.put("/memory/settings", { auto: next }); }
    catch (e) { setAuto(!next); toast.error(formatApiError(e)); }
  };

  const download = async () => {
    setDownloading(true);
    try {
      const { data } = await api.get("/account/export", { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url; a.download = "krish-ai-my-data.json"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setDownloading(false); }
  };

  return (
    <>
      <PageTitle title="Privacy" hint="What Krish keeps, and how to take it with you." />
      <div className="mb-5 flex gap-3 rounded-2xl bg-surface-strong/70 p-4 text-[13px] leading-relaxed">
        <Shield className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
        <p>Your chats are private to you. Krish doesn't sell your data and doesn't show ads.
          Read the <a href="/privacy" target="_blank" rel="noreferrer" className="font-medium text-brand underline-offset-2 hover:underline">privacy policy</a>.</p>
      </div>
      <Block title="Memory" icon={Brain} testid="privacy-memory"
        hint="Krish remembers useful things you tell it (like your name, city or goals) so answers fit you."
        right={auto === null ? <Loader2 className="h-4 w-4 animate-spin text-primary" />
          : <Switch checked={auto} onCheckedChange={toggleMemory} aria-label="Learn from chats" data-testid="privacy-memory-toggle" />}>
        <Button variant="outline" className="h-9" onClick={() => setMemoryOpen(true)} data-testid="privacy-memory-manage">See and edit what Krish remembers</Button>
      </Block>
      <Block title="Connected apps" icon={Blocks}
        hint={apps === null ? "Checking…" : apps.length ? `Krish can use ${apps.map((a) => a.name).join(", ")}. Disconnect any time.` : "No apps connected."}
        right={<Button variant="outline" className="h-9 shrink-0" onClick={() => go("connectors")}>Manage</Button>} />
      <Block title="Download your data" icon={Download} testid="privacy-export"
        hint="A copy of your chats, memory, projects and settings, in one file."
        right={<Button variant="outline" className="h-9 shrink-0" onClick={download} disabled={downloading} data-testid="privacy-export-button">
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Download"}</Button>} />
      <Block title="Delete your account" icon={Trash2} hint="Removes everything, for good."
        right={<Button variant="outline" className="h-9 shrink-0" onClick={() => go("account")}>Go to Account</Button>} />
      <MemoryDialog open={memoryOpen} onOpenChange={setMemoryOpen} />
    </>
  );
}

// ----------------------------------------------------------------- Billing
const PLAN_COPY = {
  basic: { tag: "Free forever", line: "Chat, pictures, decks and apps, with a usage limit that refills." },
  pro: { tag: "₹299 a month", line: "10x the usage, premium models, HD pictures and publishing." },
  max: { tag: "₹699 a month", line: "30x the usage, the strongest models and the most automations." },
};

function Billing({ onClose }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [payments, setPayments] = useState(null);
  useEffect(() => { api.get("/billing/payments").then(({ data }) => setPayments(data.payments)).catch(() => setPayments([])); }, []);
  const plan = user?.plan || "basic";
  const plans = () => { onClose(); navigate("/plans"); };

  return (
    <>
      <PageTitle title="Billing" hint="Your plan and payments." />
      <div className={`relative overflow-hidden rounded-2xl p-5 ${plan === "basic" ? "border border-border bg-card" : "bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-white"}`}
        data-testid="billing-plan">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className={`text-[11px] font-semibold uppercase tracking-[0.12em] ${plan === "basic" ? "text-muted-foreground" : "text-white/80"}`}>Your plan</p>
            <p className="mt-1 flex items-center gap-2 font-heading text-2xl font-semibold">
              {plan !== "basic" && <Crown className="h-5 w-5" />} Krish {({ basic: "Basic", pro: "Pro", max: "Max" })[plan]}
            </p>
            <p className={`mt-1 text-[13px] ${plan === "basic" ? "text-muted-foreground" : "text-white/85"}`}>{PLAN_COPY[plan].line}</p>
          </div>
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${plan === "basic" ? "bg-surface" : "bg-white/20"}`}>{PLAN_COPY[plan].tag}</span>
        </div>
        {user?.planExpiresAt && <p className="mt-3 text-[13px] text-white/90">Active until <b>{fmtDate(user.planExpiresAt)}</b>. Plans don't renew on their own, so you're never charged by surprise.</p>}
        <Button onClick={plans} data-testid="billing-plans"
          className={`mt-4 h-10 rounded-xl ${plan === "basic" ? "bg-gradient-to-r from-indigo-500 to-violet-500 text-white" : "bg-white text-indigo-700 hover:bg-white/90"}`}>
          {plan === "max" ? "See plans" : plan === "pro" ? "Renew or move to Max" : "Upgrade to Pro"}
        </Button>
      </div>
      <Block title="Payment method" icon={CreditCard} hint="Pay each time with UPI, cards, net banking or wallets, through Razorpay. Krish never stores your card." />
      <Block title="Payment history" testid="billing-history">
        {payments === null ? <Loader2 className="h-4 w-4 animate-spin text-primary" />
          : payments.length === 0 ? <p className="text-[13px] text-muted-foreground">No payments yet.</p>
            : (
              <div className="overflow-hidden rounded-xl border border-border">
                {payments.map((p) => (
                  <div key={p.orderId} className="flex items-center justify-between gap-3 border-b border-border px-4 py-3 text-sm last:border-0">
                    <div className="min-w-0">
                      <p className="font-medium">Krish {p.planName}, 30 days</p>
                      <p className="text-xs text-muted-foreground">{fmtDate(p.paidAt || p.createdAt)}{p.promoCode ? ` · ${p.promoCode}` : ""}</p>
                    </div>
                    <span className="shrink-0 tabular-nums">₹{p.amount}</span>
                  </div>
                ))}
              </div>
            )}
      </Block>
      <p className="text-xs text-muted-foreground">Questions about a payment? See the <a href="/refunds" target="_blank" rel="noreferrer" className="underline">refund policy</a>.</p>
    </>
  );
}

// ------------------------------------------------------------------- Usage
function Meter({ label, part, idle, testid }) {
  const pct = part.limit ? Math.min(100, Math.round((part.used / part.limit) * 100)) : 0;
  const resets = part.resetsAt ? new Date(part.resetsAt * 1000) : null;
  return (
    <div data-testid={testid}>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">{pct}% used</span>
      </div>
      <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-surface">
        <div className={`h-full rounded-full transition-all ${pct > 85 ? "bg-amber-500" : "bg-gradient-to-r from-indigo-500 to-violet-500"}`} style={{ width: `${Math.max(pct, 2)}%` }} />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">
        {resets ? `Refills ${resets.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}` : idle}
      </p>
    </div>
  );
}

function Usage({ onClose }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/usage").then(({ data: d }) => setData(d)).catch((e) => { toast.error(formatApiError(e)); setData(false); }); }, []);
  if (data === null) return <Loader2 className="h-5 w-5 animate-spin text-primary" />;
  if (!data) return null;
  const range = (r) => (r[0] === r[1] ? `${r[0]}` : `${r[0]}–${r[1]}`);
  return (
    <>
      <PageTitle title="Usage" hint="Chat on Krish Basic is never counted. Making things uses your allowance." />
      {!data.limitsOn ? <p className="text-sm text-muted-foreground">There are no usage limits right now. Make as much as you like.</p> : (
        <>
          <div className="grid gap-6 rounded-2xl border border-border bg-card p-5 sm:grid-cols-2">
            <Meter label="This session" part={data.meter.session} testid="usage-session"
              idle={`Starts when you make something, then refills ${data.meter.session.hours} hours later`} />
            <Meter label="This week" part={data.meter.week} testid="usage-week" idle="Starts when you make something" />
          </div>
          <Block title="Automations" hint={`${data.usage.automation.used} of ${data.usage.automation.limit} on your plan`} />
          <Block title="What things use">
            <ul className="grid gap-x-8 gap-y-1.5 text-sm sm:grid-cols-2">
              {[["App build", `${range(data.costs.build)} credits`], ["AI picture", `${data.costs.picture} credits`],
                ["Slide deck", `${data.costs.deck} + pictures`], ...(data.video ? [["Video", `${data.costs.videoSecond} a second`]] : []),
                ["Premium message", `${range(data.costs.chat)} credits`]].map(([k, v]) => (
                <li key={k} className="flex justify-between gap-3"><span>{k}</span><span className="tabular-nums text-muted-foreground">{v}</span></li>
              ))}
            </ul>
          </Block>
        </>
      )}
      {data.plan !== "max" && (
        <Button variant="outline" className="mt-2 h-10" onClick={() => { onClose(); navigate("/plans"); }} data-testid="usage-more">
          Get more usage <ExternalLink className="ml-1.5 h-3.5 w-3.5" /></Button>
      )}
    </>
  );
}

// ----------------------------------------------------------- Notifications
function Notifications({ go }) {
  return (
    <>
      <PageTitle title="Notifications" hint="What Krish may send you, and where." />
      <DailyVerse />
      <Block title="Automation results" hint="Get each result by email, or on Telegram, WhatsApp, Slack or Discord once you connect them. Choose for each automation on the Automations page."
        right={<Button variant="outline" className="h-9 shrink-0" onClick={() => go("connectors")}>Connect apps</Button>} />
    </>
  );
}

/** The daily Gita verse: a notification on this device each morning at 7 (India time). */
export function DailyVerse({ compact = false }) {
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
  const control = busy ? <Loader2 className="h-4 w-4 animate-spin text-primary" />
    : <Switch checked={on} onCheckedChange={toggle} aria-label="Daily Gita verse" data-testid="daily-verse-toggle" />;
  if (compact) return control;
  return (
    <Block title="Daily Gita verse" icon={Bell} testid="daily-verse-section" right={control}
      hint={pushSupported() || !isIos() ? "A short verse and its meaning on this device every morning at 7."
        : "On iPhone, add Krish to your home screen first, then turn this on from there."} />
  );
}
