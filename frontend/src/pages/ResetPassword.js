import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2, Sparkles, KeyRound } from "lucide-react";
import KrishWordmark from "@/components/KrishWordmark";

/** Opened from the emailed link: /reset-password?token=… */
export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const { startSession } = useAuth();
  const [valid, setValid] = useState(null); // null = checking
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) { setValid(false); return; }
    api.get("/auth/reset-password/check", { params: { token } })
      .then(({ data }) => setValid(data.valid))
      .catch(() => setValid(false));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (password !== confirm) { toast.error("The two passwords don't match."); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/auth/reset-password", { token, password });
      startSession(data);
      toast.success("Password changed. You're signed in.");
      navigate("/", { replace: true });
    } catch (err) {
      toast.error(formatApiError(err));
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-background px-5 py-10" data-testid="reset-password-page">
      <div className="radha-orb -top-20 left-1/2 h-64 w-64 -translate-x-1/2 bg-indigo-600/25" />
      <div className="relative w-full max-w-sm radha-fade-up">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary shadow-[0_0_30px_rgba(99,102,241,0.5)]">
            <Sparkles className="h-6 w-6 text-white" />
          </div>
          <p className="text-3xl leading-none"><KrishWordmark /></p>
        </div>

        {valid === null ? (
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        ) : !valid ? (
          <div data-testid="reset-link-invalid">
            <h1 className="text-2xl font-bold tracking-tight">This link has expired</h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Reset links work once and only for 30 minutes. Ask for a new one from the sign-in page.
            </p>
            <Button onClick={() => navigate("/login")} className="mt-6 h-11 w-full font-semibold">Back to sign in</Button>
          </div>
        ) : (
          <>
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/15 text-primary">
              <KeyRound className="h-6 w-6" />
            </div>
            <h1 className="mt-5 text-2xl font-bold tracking-tight">Choose a new password</h1>
            <p className="mt-1.5 text-sm text-muted-foreground">At least 6 characters. You'll be signed in right after.</p>
            <form onSubmit={submit} className="mt-6 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="new-password">New password</Label>
                <div className="relative">
                  <Input id="new-password" type={showPw ? "text" : "password"} autoComplete="new-password" autoFocus required minLength={6}
                    value={password} onChange={(e) => setPassword(e.target.value)} data-testid="new-password-input" className="h-11 bg-card pr-11" />
                  <button type="button" onClick={() => setShowPw((s) => !s)} aria-label={showPw ? "Hide password" : "Show password"}
                    className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center text-muted-foreground hover:text-foreground">
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="confirm-password">Type it again</Label>
                <Input id="confirm-password" type={showPw ? "text" : "password"} autoComplete="new-password" required minLength={6}
                  value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="confirm-password-input" className="h-11 bg-card" />
              </div>
              <Button type="submit" disabled={busy} data-testid="save-new-password-button" className="h-11 w-full font-semibold">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save new password"}
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
