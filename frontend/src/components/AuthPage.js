import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import ThemeToggle from "@/components/ThemeToggle";
import { Eye, EyeOff, Loader2, ArrowRight, ArrowLeft, ShieldCheck, Database, Cpu, MailCheck, Gift } from "lucide-react";
import { api } from "@/lib/api";
import KrishWordmark from "@/components/KrishWordmark";
import BrandMark from "@/components/BrandMark";
import Mascot from "@/components/Mascot";
import GoogleButton from "@/components/GoogleButton";
import { getRef } from "@/lib/referral";

export default function AuthPage() {
  const { login, register, googleLogin, formatApiError } = useAuth();
  const invited = Boolean(getRef());
  // Someone arriving from a friend's invite link most likely has no account yet.
  const [tab, setTab] = useState(invited ? "register" : "login");
  const [config, setConfig] = useState({});
  useEffect(() => {
    api.get("/auth/config").then(({ data }) => setConfig(data)).catch(() => {});
  }, []);

  const welcome = (data, fresh) => {
    if (data?.invited) toast.success(`Welcome to Krish AI! You and your friend got ${config.inviteDays || 7} days of Pro.`);
    else toast.success(fresh ? "Account created — welcome to Krish AI" : "Welcome back to Krish AI");
  };

  const onGoogle = async (credential) => {
    setBusy(true);
    try {
      welcome(await googleLogin(credential), false);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [resetSent, setResetSent] = useState(null); // {email, emailConfigured} after asking for a reset link

  const upd = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (tab === "forgot") {
        const { data } = await api.post("/auth/forgot-password", { email: form.email });
        setResetSent({ email: form.email, emailConfigured: data.emailConfigured });
      } else if (tab === "login") {
        await login(form.email, form.password);
        toast.success("Welcome back to Krish AI");
      } else {
        welcome(await register(form.name, form.email, form.password), true);
      }
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="krish-canvas grid min-h-dvh w-full lg:grid-cols-2">
      {/* Showcase panel */}
      <div className="relative hidden overflow-hidden lg:block">
        <div className="relative z-10 flex h-full flex-col justify-between p-12">
          <div className="flex items-center gap-2.5">
            <BrandMark className="h-9 w-9" />
            <div className="leading-none">
              <p className="text-2xl leading-none"><KrishWordmark /></p>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">by EmpireX</p>
            </div>
          </div>

          <div className="max-w-md">
            <Mascot className="krish-float -ml-2 mb-6 h-32 w-auto" />
            <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-foreground xl:text-5xl">
              Meet <span className="krish-gradient-text">Krish AI</span>, your saarthi for every task.
            </h1>
            <p className="mt-4 text-base text-muted-foreground">
              Ask anything, write, code, study and plan. All your chats are saved for you.
            </p>
            <div className="mt-8 space-y-3 text-sm text-foreground/80">
              <Feature icon={Cpu} tone="bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300" text="Chat, apps, decks and docs in one place" />
              <Feature icon={Database} tone="bg-sky-100 text-sky-600 dark:bg-sky-500/20 dark:text-sky-300" text="Every conversation saved" />
              <Feature icon={ShieldCheck} tone="bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300" text="Private: your chats are yours alone" />
            </div>
          </div>

          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} EmpireX · Krish AI</p>
        </div>
      </div>

      {/* Form panel */}
      <div className="relative flex items-center justify-center overflow-hidden px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(1.5rem,env(safe-area-inset-top))] sm:p-10">
        <ThemeToggle className="absolute right-4 top-[max(1rem,env(safe-area-inset-top))] z-10" />
        <div className="krish-glass relative w-full max-w-md rounded-3xl border border-white/70 p-6 shadow-[0_20px_60px_rgba(99,102,241,0.12)] radha-fade-up dark:border-white/5 sm:p-8">
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <BrandMark className="h-11 w-11" />
            <div className="leading-none">
              <p className="text-3xl leading-none"><KrishWordmark /></p>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">by EmpireX</p>
              <p className="mt-1.5 text-xs text-muted-foreground">Your saarthi for every task.</p>
            </div>
          </div>

          {tab === "forgot" ? (
            <ForgotPassword email={form.email} onEmail={upd("email")} busy={busy} sent={resetSent} onSubmit={submit}
              onBack={() => { setTab("login"); setResetSent(null); }} onRetry={() => setResetSent(null)} />
          ) : (<>

          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
            {tab === "login" ? "Welcome back" : "Create your account"}
          </h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {tab === "login" ? "Sign in to continue to Krish AI." : "It takes less than a minute."}
          </p>

          {invited && (
            <p className="mt-4 flex items-start gap-2 rounded-xl bg-emerald-500/10 px-3 py-2.5 text-sm text-emerald-700 dark:text-emerald-300" data-testid="invite-note">
              <Gift className="mt-0.5 h-4 w-4 shrink-0" />
              A friend invited you. Sign up and get {config.inviteDays || 7} days of Pro free.
            </p>
          )}

          {config.googleClientId && (
            <div className="mt-6">
              <GoogleButton clientId={config.googleClientId} onCredential={onGoogle} text={tab === "login" ? "signin_with" : "signup_with"} />
              <div className="mt-5 flex items-center gap-3 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" /> or use your email <span className="h-px flex-1 bg-border" />
              </div>
            </div>
          )}

          <div className={`${config.googleClientId ? "mt-5" : "mt-6"} flex rounded-xl border border-border bg-card p-1`}>
            <TabBtn active={tab === "login"} onClick={() => setTab("login")} testId="auth-tab-login">Login</TabBtn>
            <TabBtn active={tab === "register"} onClick={() => setTab("register")} testId="auth-tab-register">Register</TabBtn>
          </div>

          <form onSubmit={submit} className="mt-6 space-y-4">
            {tab === "register" && (
              <div className="space-y-1.5">
                <Label htmlFor="name">Name</Label>
                <Input id="name" data-testid="register-name-input" placeholder="Ada Lovelace" value={form.name} onChange={upd("name")} required autoComplete="name" className="h-11 rounded-xl bg-card" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" data-testid={tab === "login" ? "login-email-input" : "register-email-input"} placeholder="you@company.com" value={form.email} onChange={upd("email")} required autoComplete="email" inputMode="email" className="h-11 rounded-xl bg-card" />
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                {tab === "login" && (
                  <button type="button" onClick={() => { setTab("forgot"); setResetSent(null); }} data-testid="forgot-password-link"
                    className="-my-2 py-2 text-xs font-medium text-brand hover:underline">
                    Forgot password?
                  </button>
                )}
              </div>
              <div className="relative">
                <Input id="password" type={showPw ? "text" : "password"} data-testid={tab === "login" ? "login-password-input" : "register-password-input"} placeholder="At least 6 characters" value={form.password} onChange={upd("password")} required minLength={6} autoComplete={tab === "login" ? "current-password" : "new-password"} className="h-11 rounded-xl bg-card pr-11" />
                <button type="button" onClick={() => setShowPw((s) => !s)} aria-label={showPw ? "Hide password" : "Show password"} className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center text-muted-foreground hover:text-foreground" data-testid="toggle-password-visibility">
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button type="submit" disabled={busy} data-testid={tab === "login" ? "login-submit-button" : "register-submit-button"} className="group h-11 w-full rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 font-semibold shadow-[0_8px_24px_rgba(99,102,241,0.35)] hover:from-indigo-500 hover:to-violet-600">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : (
                <>{tab === "login" ? "Sign in" : "Create account"}<ArrowRight className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-0.5" /></>
              )}
            </Button>
          </form>
          <p className="mt-5 text-center text-xs leading-relaxed text-muted-foreground" data-testid="legal-links">
            {tab === "register" ? "By creating an account you agree to the " : "By continuing you agree to the "}
            <a href="/terms" className="font-medium text-foreground hover:underline">Terms</a> and{" "}
            <a href="/privacy" className="font-medium text-foreground hover:underline">Privacy Policy</a>.
          </p>
          </>)}
        </div>
      </div>
    </div>
  );
}

function ForgotPassword({ email, onEmail, busy, sent, onSubmit, onBack, onRetry }) {
  return (
    <div data-testid="forgot-password-panel">
      <button type="button" onClick={onBack} data-testid="forgot-back"
        className="-ml-1 mb-5 flex items-center gap-1.5 py-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to sign in
      </button>
      {sent ? (
        sent.emailConfigured ? (
          <div data-testid="reset-link-sent">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/15 text-primary">
              <MailCheck className="h-6 w-6" />
            </div>
            <h2 className="mt-5 text-2xl font-bold tracking-tight">Check your email</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              If <span className="font-medium text-foreground">{sent.email}</span> has a Krish AI account, we've sent it a link to
              choose a new password. The link works once and expires in 30 minutes. Look in spam if you don't see it.
            </p>
            <Button type="button" variant="outline" onClick={onRetry} className="mt-6 h-11 w-full">Use a different email</Button>
          </div>
        ) : (
          <div data-testid="reset-email-not-setup">
            <h2 className="text-2xl font-bold tracking-tight">Password reset isn't switched on yet</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Emails can't be sent from Krish AI yet, so we couldn't send a reset link. Please contact EmpireX support to get back into your account.
            </p>
          </div>
        )
      ) : (
        <>
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">Forgot your password?</h2>
          <p className="mt-1.5 text-sm text-muted-foreground">Enter your account email and we'll send you a link to choose a new one.</p>
          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="reset-email">Email</Label>
              <Input id="reset-email" type="email" autoComplete="email" inputMode="email" autoFocus data-testid="forgot-email-input"
                placeholder="you@company.com" value={email} onChange={onEmail} required className="h-11 rounded-xl bg-card" />
            </div>
            <Button type="submit" disabled={busy} data-testid="send-reset-link-button" className="h-11 w-full font-semibold">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Send reset link"}
            </Button>
          </form>
        </>
      )}
    </div>
  );
}

const Feature = ({ icon: Icon, text, tone }) => (
  <div className="flex items-center gap-3">
    <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${tone}`}><Icon className="h-4 w-4" /></span>
    <span>{text}</span>
  </div>
);

const TabBtn = ({ active, onClick, children, testId }) => (
  <button type="button" onClick={onClick} data-testid={testId}
    className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors ${active ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
    {children}
  </button>
);
