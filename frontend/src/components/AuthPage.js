import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2, Sparkles, ArrowRight, ShieldCheck, Database, Cpu } from "lucide-react";

const HERO = "https://images.unsplash.com/photo-1637946175559-22c4fe13fc54?crop=entropy&cs=srgb&fm=jpg&q=85&w=1400";

export default function AuthPage() {
  const { login, register, formatApiError } = useAuth();
  const [tab, setTab] = useState("login");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "" });

  const upd = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (tab === "login") {
        await login(form.email, form.password);
        toast.success("Welcome back to RADHA");
      } else {
        await register(form.name, form.email, form.password);
        toast.success("Account created — welcome to RADHA");
      }
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen w-full lg:grid-cols-2">
      {/* Showcase panel */}
      <div className="relative hidden overflow-hidden border-r border-border lg:block">
        <img src={HERO} alt="" className="absolute inset-0 h-full w-full object-cover opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-tr from-[#07080B] via-[#07080B]/80 to-transparent" />
        <div className="relative z-10 flex h-full flex-col justify-between p-12">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary shadow-[0_0_30px_rgba(99,102,241,0.5)]">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div className="leading-none">
              <p className="text-lg font-extrabold tracking-tight">RADHA</p>
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">by A.utomateX</p>
            </div>
          </div>

          <div className="max-w-md">
            <h1 className="text-4xl font-extrabold leading-tight tracking-tighter text-foreground sm:text-5xl">
              The intelligent workspace for serious work.
            </h1>
            <p className="mt-4 text-base text-muted-foreground">
              Real conversations. Real reasoning. Persistent memory of everything you build. RADHA is the foundation of A.utomateX's AI platform.
            </p>
            <div className="mt-8 space-y-3 text-sm text-muted-foreground">
              <Feature icon={Cpu} text="Powered by a real frontier reasoning model" />
              <Feature icon={Database} text="Every conversation saved and reloadable" />
              <Feature icon={ShieldCheck} text="Private — your workspace is yours alone" />
            </div>
          </div>

          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} A.utomateX — RADHA V1</p>
        </div>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm radha-fade-up">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <p className="text-lg font-extrabold tracking-tight">RADHA</p>
          </div>

          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
            {tab === "login" ? "Sign in to RADHA" : "Create your workspace"}
          </h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {tab === "login" ? "Enter your credentials to continue." : "Start building with RADHA in seconds."}
          </p>

          <div className="mt-6 flex rounded-lg border border-border bg-card p-1">
            <TabBtn active={tab === "login"} onClick={() => setTab("login")} testId="auth-tab-login">Login</TabBtn>
            <TabBtn active={tab === "register"} onClick={() => setTab("register")} testId="auth-tab-register">Register</TabBtn>
          </div>

          <form onSubmit={submit} className="mt-6 space-y-4">
            {tab === "register" && (
              <div className="space-y-1.5">
                <Label htmlFor="name">Name</Label>
                <Input id="name" data-testid="register-name-input" placeholder="Ada Lovelace" value={form.name} onChange={upd("name")} required className="bg-card" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" data-testid={tab === "login" ? "login-email-input" : "register-email-input"} placeholder="you@company.com" value={form.email} onChange={upd("email")} required className="bg-card" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input id="password" type={showPw ? "text" : "password"} data-testid={tab === "login" ? "login-password-input" : "register-password-input"} placeholder="••••••••" value={form.password} onChange={upd("password")} required minLength={6} className="bg-card pr-10" />
                <button type="button" onClick={() => setShowPw((s) => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" data-testid="toggle-password-visibility">
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button type="submit" disabled={busy} data-testid={tab === "login" ? "login-submit-button" : "register-submit-button"} className="group w-full font-semibold">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : (
                <>{tab === "login" ? "Sign in" : "Create account"}<ArrowRight className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-0.5" /></>
              )}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}

const Feature = ({ icon: Icon, text }) => (
  <div className="flex items-center gap-3">
    <Icon className="h-4 w-4 text-primary" />
    <span>{text}</span>
  </div>
);

const TabBtn = ({ active, onClick, children, testId }) => (
  <button type="button" onClick={onClick} data-testid={testId}
    className={`flex-1 rounded-md px-4 py-2 text-sm font-semibold transition-colors ${active ? "bg-primary text-white" : "text-muted-foreground hover:text-foreground"}`}>
    {children}
  </button>
);
