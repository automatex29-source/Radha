import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, Loader2, Lock, MessageCircle } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { counselAgent } from "@/lib/counselAgents";
import { AgentArt } from "@/components/AgentPortrait";
import BrandMark from "@/components/BrandMark";

// Asked once after signing in (backend: PUT /auth/about). The answers shape Krish's replies and pick the
// Counsellor agents suggested at the end.
const WORK = [
  { id: "student", label: "Student", emoji: "📚" },
  { id: "working", label: "Working", emoji: "💼" },
  { id: "business", label: "Running a business", emoji: "🚀" },
  { id: "homemaker", label: "Homemaker", emoji: "🏡" },
  { id: "job_seeker", label: "Looking for work", emoji: "🔎" },
  { id: "retired", label: "Retired", emoji: "🌿" },
  { id: "other", label: "Something else", emoji: "✨" },
];
const WANTS = [
  { id: "peace", label: "Peace of mind", emoji: "🕊️" },
  { id: "career", label: "Career & money", emoji: "📈" },
  { id: "study", label: "Focus in studies", emoji: "🎯" },
  { id: "love", label: "Love & relationships", emoji: "💞" },
  { id: "confidence", label: "Confidence", emoji: "💪" },
  { id: "spiritual", label: "Spiritual growth", emoji: "🪷" },
  { id: "joy", label: "More happiness", emoji: "😊" },
];
const COUNTRIES = ["India", "Nepal", "Bangladesh", "Sri Lanka", "Pakistan", "United Arab Emirates", "Saudi Arabia",
  "Qatar", "Singapore", "Malaysia", "Mauritius", "Fiji", "United States", "Canada", "United Kingdom", "Ireland",
  "Germany", "France", "Netherlands", "Australia", "New Zealand", "South Africa", "Kenya", "Nigeria", "Other"];
// A first guess at the country from the device's time zone; they can change it.
const ZONES = { "Asia/Kolkata": "India", "Asia/Calcutta": "India", "Asia/Kathmandu": "Nepal", "Asia/Dhaka": "Bangladesh",
  "Asia/Colombo": "Sri Lanka", "Asia/Karachi": "Pakistan", "Asia/Dubai": "United Arab Emirates", "Asia/Riyadh": "Saudi Arabia",
  "Asia/Qatar": "Qatar", "Asia/Singapore": "Singapore", "Asia/Kuala_Lumpur": "Malaysia", "Indian/Mauritius": "Mauritius",
  "Pacific/Fiji": "Fiji", "Europe/London": "United Kingdom", "Europe/Dublin": "Ireland", "Europe/Berlin": "Germany",
  "Europe/Paris": "France", "Europe/Amsterdam": "Netherlands", "Africa/Johannesburg": "South Africa",
  "Africa/Nairobi": "Kenya", "Africa/Lagos": "Nigeria", "Pacific/Auckland": "New Zealand" };

function guessCountry() {
  let zone = "";
  try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { /* optional */ }
  if (ZONES[zone]) return ZONES[zone];
  if (zone.startsWith("Australia/")) return "Australia";
  if (/^America\/(Toronto|Vancouver|Edmonton|Winnipeg|Halifax|Regina|St_Johns)/.test(zone)) return "Canada";
  if (/^America\/(New_York|Chicago|Denver|Los_Angeles|Phoenix|Anchorage|Detroit)/.test(zone)) return "United States";
  return "";
}

function Chip({ on, onClick, emoji, label, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={`flex items-center gap-2 rounded-2xl border px-4 py-3 text-left text-sm font-medium transition ${on ? "border-violet-500 bg-violet-500/10 text-foreground ring-2 ring-violet-500/30" : "border-border bg-card text-foreground hover:-translate-y-0.5 hover:shadow-sm"}`}>
      <span className="text-lg" aria-hidden="true">{emoji}</span>
      <span className="flex-1">{label}</span>
      {on && <Check className="h-4 w-4 text-violet-600 dark:text-violet-300" />}
    </button>
  );
}

export default function WelcomeQuestions() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const pro = user?.plan === "pro" || user?.plan === "max";
  const [step, setStep] = useState(0);
  const [callMe, setCallMe] = useState((user?.name || "").trim().split(/\s+/)[0] || "");
  const [does, setDoes] = useState(null);
  const [wants, setWants] = useState([]);
  const initialCountry = useMemo(guessCountry, []);
  const [country, setCountry] = useState(initialCountry);
  const [otherCountry, setOtherCountry] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(null); // the user after saving: shows the suggestions

  const toggleWant = (id) => setWants((w) => (w.includes(id) ? w.filter((x) => x !== id) : w.length >= 3 ? w : [...w, id]));
  const place = country === "Other" ? otherCountry.trim() : country;
  const ready = [callMe.trim().length > 0, !!does, wants.length > 0, !!place][step];

  const save = async (skipped = false) => {
    setSaving(true);
    setError("");
    try {
      const { data } = await api.put("/auth/about", skipped ? { skipped: true }
        : { callMe: callMe.trim(), does, wants, country: place });
      if (skipped) setUser(data);
      else setSaved(data);
    } catch (e) {
      setError(formatApiError(e?.response?.data?.detail) || "Couldn't save. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const finish = (path) => {
    setUser(saved);
    navigate(path);
  };

  const questions = [
    { title: "What should we call you?", hint: "Your name, a nickname, anything you like." },
    { title: `What do you do, ${callMe.trim() || "friend"}?`, hint: "So the advice fits your days." },
    { title: "What do you want most right now?", hint: "Pick up to 3." },
    { title: "Where do you live?", hint: "We'll suggest counsellors who fit you best." },
  ];

  if (saved) {
    const picks = (saved.suggestedAgents || []).map(counselAgent).filter(Boolean);
    return (
      <div className="fixed inset-0 z-[70] overflow-y-auto bg-background" data-testid="welcome-results">
        <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-5 py-10">
          <p className="text-sm font-semibold text-violet-600 dark:text-violet-300">All set, {saved.about?.callMe || callMe} ✨</p>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Your counsellors</h1>
          <p className="mt-2 text-sm text-muted-foreground">Picked for what you want most{saved.about?.country ? ` and life in ${saved.about.country}` : ""}.</p>
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {picks.map((a, i) => (
              <button key={a.id} onClick={() => finish(pro ? `/counsellor?agent=${a.id}` : "/plans")}
                data-testid={`welcome-agent-${a.id}`}
                className="group relative aspect-[4/5] overflow-hidden rounded-[1.75rem] text-left shadow-md transition hover:-translate-y-1 hover:shadow-xl max-sm:aspect-[16/10]">
                <AgentArt id={a.id} className="transition duration-500 group-hover:scale-105" />
                <span className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent" />
                {i === 0 && <span className="absolute left-3 top-3 rounded-full bg-white px-2.5 py-1 text-[11px] font-bold text-slate-900">Best match</span>}
                <span className="absolute inset-x-0 bottom-0 p-4 text-white">
                  <span className="block text-lg font-bold">{a.name}</span>
                  <span className="block text-xs text-white/80">{a.tagline}</span>
                  <span className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-bold text-slate-900">
                    {pro ? <><MessageCircle className="h-3.5 w-3.5" /> Talk to {a.name}</> : <><Lock className="h-3.5 w-3.5" /> Unlock with Pro</>}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button onClick={() => finish("/counsellor")} data-testid="welcome-start-counsellor"
              className="rounded-full bg-gradient-to-r from-violet-600 to-pink-500 px-5 py-2.5 text-sm font-semibold text-white shadow-md hover:opacity-90">
              {pro ? "Open the Counsellor" : "Talk to Krish for free"}
            </button>
            <button onClick={() => finish("/")} data-testid="welcome-go-chat" className="text-sm font-medium text-muted-foreground hover:text-foreground">
              Go to chat
            </button>
          </div>
        </div>
      </div>
    );
  }

  const q = questions[step];
  return (
    <div className="fixed inset-0 z-[70] overflow-y-auto bg-background" data-testid="welcome-questions">
      <div className="mx-auto flex min-h-full max-w-xl flex-col px-5 py-6">
        <div className="flex items-center justify-between">
          <BrandMark className="h-9 w-9" />
          <button onClick={() => save(true)} disabled={saving} data-testid="welcome-skip"
            className="text-sm font-medium text-muted-foreground hover:text-foreground">Skip for now</button>
        </div>
        <div className="mt-6 flex gap-1.5" aria-hidden="true">
          {questions.map((_, i) => (
            <span key={i} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-gradient-to-r from-violet-500 to-pink-500" : "bg-border"}`} />
          ))}
        </div>
        <div className="flex flex-1 flex-col justify-center py-8">
          {step === 0 && <p className="mb-2 text-sm font-semibold text-violet-600 dark:text-violet-300">Welcome to Krish AI 👋 4 quick questions</p>}
          <h1 className="text-[1.9rem] font-extrabold leading-tight tracking-tight text-foreground sm:text-4xl">{q.title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{q.hint}</p>
          <div className="mt-6">
            {step === 0 && (
              <input autoFocus value={callMe} onChange={(e) => setCallMe(e.target.value.slice(0, 40))} data-testid="welcome-name"
                onKeyDown={(e) => { if (e.key === "Enter" && ready) setStep(1); }} placeholder="e.g. Sneha"
                className="h-14 w-full rounded-2xl border border-border bg-card px-4 text-lg text-foreground outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-500/30" />
            )}
            {step === 1 && (
              <div className="grid gap-2.5 sm:grid-cols-2">
                {WORK.map((w) => <Chip key={w.id} {...w} on={does === w.id} testid={`welcome-does-${w.id}`}
                  onClick={() => { setDoes(w.id); setStep(2); }} />)}
              </div>
            )}
            {step === 2 && (
              <div className="grid gap-2.5 sm:grid-cols-2">
                {WANTS.map((w) => <Chip key={w.id} {...w} on={wants.includes(w.id)} testid={`welcome-want-${w.id}`}
                  onClick={() => toggleWant(w.id)} />)}
              </div>
            )}
            {step === 3 && (
              <div className="space-y-3">
                <select value={country} onChange={(e) => setCountry(e.target.value)} data-testid="welcome-country"
                  className="h-14 w-full rounded-2xl border border-border bg-card px-4 text-lg text-foreground outline-none focus:border-violet-500">
                  <option value="">Choose your country</option>
                  {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                {country === "Other" && (
                  <input value={otherCountry} onChange={(e) => setOtherCountry(e.target.value.slice(0, 60))} placeholder="Type your country"
                    data-testid="welcome-country-other"
                    className="h-12 w-full rounded-2xl border border-border bg-card px-4 text-foreground outline-none focus:border-violet-500" />
                )}
                {initialCountry && country === initialCountry && <p className="text-xs text-muted-foreground">Guessed from your device. Change it if it's wrong.</p>}
              </div>
            )}
          </div>
          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </div>
        <div className="flex items-center gap-3 pb-2">
          {step > 0 && (
            <button onClick={() => setStep(step - 1)} data-testid="welcome-back" aria-label="Back"
              className="flex h-12 w-12 items-center justify-center rounded-full border border-border text-foreground hover:bg-surface">
              <ArrowLeft className="h-5 w-5" />
            </button>
          )}
          <button disabled={!ready || saving} data-testid="welcome-next"
            onClick={() => (step < 3 ? setStep(step + 1) : save())}
            className="flex h-12 flex-1 items-center justify-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-pink-500 text-sm font-semibold text-white shadow-md transition hover:opacity-90 disabled:opacity-40">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : step < 3 ? <>Next <ArrowRight className="h-4 w-4" /></> : "Show my counsellors"}
          </button>
        </div>
      </div>
    </div>
  );
}
