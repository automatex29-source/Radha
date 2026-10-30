import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, BookOpen, Briefcase, Check, Compass, Image, LayoutGrid, Loader2, MessageCircle,
  Presentation, FileText, Heart, Zap } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import BrandMark from "@/components/BrandMark";

// Asked once after signing in (backend: PUT /auth/about). The answers shape every Krish reply, and the end
// screen points them to the parts of Krish AI that fit what they want to do.
const WORK = [
  { id: "student", label: "Student", emoji: "📚" },
  { id: "working", label: "Working", emoji: "💼" },
  { id: "business", label: "Running a business", emoji: "🚀" },
  { id: "homemaker", label: "Homemaker", emoji: "🏡" },
  { id: "job_seeker", label: "Looking for work", emoji: "🔎" },
  { id: "retired", label: "Retired", emoji: "🌿" },
  { id: "other", label: "Something else", emoji: "✨" },
];
const USES = [
  { id: "study", label: "Study & homework", emoji: "📚" },
  { id: "coding", label: "Coding & building apps", emoji: "💻" },
  { id: "work", label: "Work, writing & emails", emoji: "✍️" },
  { id: "business", label: "Business & marketing", emoji: "📈" },
  { id: "slides", label: "Presentations & documents", emoji: "📊" },
  { id: "create", label: "Pictures & videos", emoji: "🎨" },
  { id: "talk", label: "Life advice & someone to talk to", emoji: "💛" },
  { id: "everyday", label: "Everyday questions & news", emoji: "🌍" },
];
// The part of Krish AI each use leads to on the end screen. `study` turns Study mode on (see Workspace).
const FEATURES = {
  study: { icon: BookOpen, title: "Study mode", text: "Step-by-step teaching, quizzes and exam prep.", path: "/", flag: "krish.study", tone: "from-amber-400 to-orange-500" },
  coding: { icon: LayoutGrid, title: "App builder", text: "Describe an app or website and watch it get built.", path: "/apps", tone: "from-sky-500 to-indigo-600" },
  work: { icon: FileText, title: "Docs", text: "Write and polish emails, letters and reports.", path: "/docs", tone: "from-emerald-500 to-teal-600" },
  business: { icon: Zap, title: "Automations", text: "Agents that do your repeat tasks on a schedule.", path: "/automations", tone: "from-violet-500 to-fuchsia-500" },
  slides: { icon: Presentation, title: "Decks", text: "Beautiful slides from a single line.", path: "/decks", tone: "from-rose-500 to-pink-500" },
  create: { icon: Image, title: "Pictures & videos", text: "Ask in chat: \"make a poster for my shop\".", path: "/", tone: "from-fuchsia-500 to-purple-600" },
  talk: { icon: Heart, title: "Counsellor", text: "A caring friend to talk to, by text or call.", path: "/counsellor", tone: "from-pink-500 to-rose-500" },
  everyday: { icon: Compass, title: "Discover", text: "Today's news and answers with live web search.", path: "/discover", tone: "from-cyan-500 to-blue-600" },
};
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
  const [uses, setUses] = useState([]);
  const initialCountry = useMemo(guessCountry, []);
  const [country, setCountry] = useState(initialCountry);
  const [otherCountry, setOtherCountry] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(null); // the user after saving: shows the suggestions

  const toggleUse = (id) => setUses((u) => (u.includes(id) ? u.filter((x) => x !== id) : u.length >= 3 ? u : [...u, id]));
  const place = country === "Other" ? otherCountry.trim() : country;
  const ready = [callMe.trim().length > 0, !!does, uses.length > 0, !!place][step];

  const save = async (skipped = false) => {
    setSaving(true);
    setError("");
    try {
      const { data } = await api.put("/auth/about", skipped ? { skipped: true }
        : { callMe: callMe.trim(), does, uses, country: place });
      if (skipped) setUser(data);
      else setSaved(data);
    } catch (e) {
      setError(formatApiError(e?.response?.data?.detail) || "Couldn't save. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const finish = (path, flag) => {
    if (flag) {
      try { localStorage.setItem(flag, "1"); } catch { /* optional */ }
      // The chat page is already open under this screen, so tell it to switch the mode on now.
      window.dispatchEvent(new CustomEvent("krish-flag", { detail: flag }));
    }
    setUser(saved);
    navigate(path);
  };

  const questions = [
    { title: "What should we call you?", hint: "Your name, a nickname, anything you like." },
    { title: `What do you do, ${callMe.trim() || "friend"}?`, hint: "So the advice fits your days." },
    { title: "What will you use Krish AI for most?", hint: "Pick up to 3." },
    { title: "Where do you live?", hint: "So prices, exams, news and examples fit your country." },
  ];

  if (saved) {
    const picks = (saved.about?.uses || []).map((u) => [u, FEATURES[u]]).filter(([, f]) => f);
    return (
      <div className="fixed inset-0 z-[70] overflow-y-auto bg-background" data-testid="welcome-results">
        <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-5 py-10">
          <p className="text-sm font-semibold text-violet-600 dark:text-violet-300">All set, {saved.about?.callMe || callMe} ✨</p>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Krish AI, made for you</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Krish will now answer with your life{saved.about?.country ? ` in ${saved.about.country}` : ""} in mind. Start with these:
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            {picks.map(([id, f]) => {
              const Icon = f.icon;
              return (
                <button key={id} onClick={() => finish(f.path, f.flag)} data-testid={`welcome-feature-${id}`}
                  className="group flex flex-col rounded-3xl border border-border bg-card p-5 text-left shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
                  <span className={`flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br ${f.tone} text-white shadow-md`}>
                    <Icon className="h-6 w-6" />
                  </span>
                  <span className="mt-4 text-base font-bold text-foreground">{f.title}</span>
                  <span className="mt-1 flex-1 text-sm leading-snug text-muted-foreground">{f.text}</span>
                  <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-violet-600 dark:text-violet-300">
                    Try it <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                  </span>
                </button>
              );
            })}
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button onClick={() => finish("/")} data-testid="welcome-start-chat"
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-pink-500 px-5 py-2.5 text-sm font-semibold text-white shadow-md hover:opacity-90">
              <MessageCircle className="h-4 w-4" /> Start chatting with Krish
            </button>
            {!pro && (
              <button onClick={() => finish("/plans")} data-testid="welcome-see-pro" className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground">
                <Briefcase className="h-4 w-4" /> See what Pro adds
              </button>
            )}
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
                {USES.map((u) => <Chip key={u.id} {...u} on={uses.includes(u.id)} testid={`welcome-use-${u.id}`}
                  onClick={() => toggleUse(u.id)} />)}
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
