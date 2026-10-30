import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, BookOpen, Briefcase, Check, ChevronRight, Code2, Compass, FileText, Globe, GraduationCap,
  Heart, Home, Image, LayoutGrid, Leaf, Loader2, MapPin, MessageCircle, Palette, PenLine, Presentation, Rocket, Search,
  Sparkles, TrendingUp, Zap } from "lucide-react";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import BrandMark from "@/components/BrandMark";

// Asked once after signing in (backend: PUT /auth/about). The answers shape every Krish reply, and the end
// screen points them to the parts of Krish AI that fit what they want to do.
const WORK = [
  { id: "student", label: "Student", icon: GraduationCap, tone: "from-amber-400 to-orange-500" },
  { id: "working", label: "Working", icon: Briefcase, tone: "from-sky-500 to-indigo-600" },
  { id: "business", label: "Running a business", icon: Rocket, tone: "from-violet-500 to-fuchsia-500" },
  { id: "homemaker", label: "Homemaker", icon: Home, tone: "from-rose-400 to-pink-500" },
  { id: "job_seeker", label: "Looking for work", icon: Search, tone: "from-cyan-500 to-blue-600" },
  { id: "retired", label: "Retired", icon: Leaf, tone: "from-emerald-500 to-teal-600" },
  { id: "other", label: "Something else", icon: Sparkles, tone: "from-slate-500 to-slate-700" },
];
const USES = [
  { id: "study", label: "Study & homework", icon: BookOpen, tone: "from-amber-400 to-orange-500" },
  { id: "coding", label: "Coding & apps", icon: Code2, tone: "from-sky-500 to-indigo-600" },
  { id: "work", label: "Writing & emails", icon: PenLine, tone: "from-emerald-500 to-teal-600" },
  { id: "business", label: "Business & marketing", icon: TrendingUp, tone: "from-violet-500 to-fuchsia-500" },
  { id: "slides", label: "Slides & documents", icon: Presentation, tone: "from-rose-500 to-pink-500" },
  { id: "create", label: "Pictures & videos", icon: Palette, tone: "from-fuchsia-500 to-purple-600" },
  { id: "talk", label: "Life advice & a friend", icon: Heart, tone: "from-pink-500 to-rose-500" },
  { id: "everyday", label: "Everyday answers & news", icon: Globe, tone: "from-cyan-500 to-blue-600" },
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

const PICKED = "border-violet-500 bg-violet-500/10 ring-2 ring-violet-500/30";
const UNPICKED = "border-border bg-card hover:border-violet-300 active:scale-[0.98]";

function Tile({ icon: Icon, tone }) {
  return (
    <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${tone} text-white shadow-sm`}>
      <Icon className="h-5 w-5" />
    </span>
  );
}

/** One answer in a list (what they do). */
function Chip({ on, onClick, icon, tone, label, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={`flex items-center gap-3 rounded-2xl border p-2.5 pr-4 text-left text-[15px] font-semibold text-foreground transition ${on ? PICKED : UNPICKED}`}>
      <Tile icon={icon} tone={tone} />
      <span className="flex-1">{label}</span>
      {on ? <Check className="h-4 w-4 text-violet-600 dark:text-violet-300" /> : <ChevronRight className="h-4 w-4 text-muted-foreground/60" />}
    </button>
  );
}

/** One answer in a two-column grid (what they'll use Krish AI for); several can be picked. */
function Card({ on, onClick, icon, tone, label, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid} aria-pressed={on}
      className={`relative flex min-h-[104px] flex-col justify-between gap-3 rounded-2xl border p-3.5 text-left text-sm font-semibold leading-snug text-foreground transition ${on ? PICKED : UNPICKED}`}>
      <Tile icon={icon} tone={tone} />
      <span>{label}</span>
      <span className={`absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full border ${on ? "border-violet-600 bg-violet-600 text-white" : "border-border"}`}>
        {on && <Check className="h-3 w-3" strokeWidth={3} />}
      </span>
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
    { title: "What will you use Krish AI for?", hint: "Pick up to 3. We'll set things up for you." },
    { title: "Where do you live?", hint: "So prices, exams, news and examples fit your country." },
  ];

  if (saved) {
    const picks = (saved.about?.uses || []).map((u) => [u, FEATURES[u]]).filter(([, f]) => f);
    return (
      <div className="fixed inset-0 z-[70] flex flex-col bg-background" data-testid="welcome-results">
        <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-3xl flex-col px-5 pb-6 pt-10 sm:justify-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-pink-500 text-white shadow-lg shadow-violet-500/30">
            <Check className="h-7 w-7" strokeWidth={3} />
          </span>
          <p className="mt-5 text-sm font-semibold text-violet-600 dark:text-violet-300">All set, {saved.about?.callMe || callMe}</p>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Krish AI, made for you</h1>
          {saved.about?.country && (
            <p className="mt-3 inline-flex w-fit items-center gap-1.5 rounded-full bg-surface px-3 py-1 text-xs font-medium text-muted-foreground">
              <MapPin className="h-3.5 w-3.5" /> Answers set for {saved.about.country}
            </p>
          )}
          <p className="mt-6 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Picked for you</p>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-3 sm:gap-3">
            {picks.map(([id, f]) => {
              const Icon = f.icon;
              return (
                <button key={id} onClick={() => finish(f.path, f.flag)} data-testid={`welcome-feature-${id}`}
                  className="group flex items-center gap-3.5 rounded-2xl border border-border bg-card p-3.5 text-left shadow-sm transition active:scale-[0.98] sm:flex-col sm:items-start sm:rounded-3xl sm:p-5 sm:hover:-translate-y-1 sm:hover:shadow-lg">
                  <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${f.tone} text-white shadow-md`}>
                    <Icon className="h-6 w-6" />
                  </span>
                  <span className="min-w-0 flex-1 sm:mt-1">
                    <span className="block text-[15px] font-bold text-foreground sm:text-base">{f.title}</span>
                    <span className="mt-0.5 block text-[13px] leading-snug text-muted-foreground sm:text-sm">{f.text}</span>
                  </span>
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-300 sm:hidden">
                    <ArrowRight className="h-4 w-4" />
                  </span>
                  <span className="hidden items-center gap-1 text-sm font-semibold text-violet-600 dark:text-violet-300 sm:inline-flex">
                    Try it <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        </div>
        <div className="border-t border-border/60 bg-background/90 backdrop-blur sm:border-0">
          <div className="mx-auto flex max-w-3xl flex-col gap-2 px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:flex-row sm:items-center sm:gap-4 sm:pb-10">
            <button onClick={() => finish("/")} data-testid="welcome-start-chat"
              className="flex h-12 items-center justify-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-pink-500 px-6 text-[15px] font-semibold text-white shadow-lg shadow-violet-500/25 hover:opacity-90">
              <MessageCircle className="h-4 w-4" /> Start chatting with Krish
            </button>
            {!pro && (
              <button onClick={() => finish("/plans")} data-testid="welcome-see-pro"
                className="inline-flex h-10 items-center justify-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground">
                <Sparkles className="h-4 w-4" /> See what Pro adds
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const q = questions[step];
  return (
    <div className="fixed inset-0 z-[70] flex flex-col bg-background" data-testid="welcome-questions">
      <div className="mx-auto w-full max-w-xl px-5 pt-[max(1rem,env(safe-area-inset-top))]">
        <div className="flex h-12 items-center justify-between">
          <BrandMark className="h-8 w-8" />
          <span className="text-xs font-semibold text-muted-foreground">{step + 1} of {questions.length}</span>
          <button onClick={() => save(true)} disabled={saving} data-testid="welcome-skip"
            className="rounded-full px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-surface hover:text-foreground">Skip</button>
        </div>
        <div className="mt-2 flex gap-1.5" aria-hidden="true">
          {questions.map((_, i) => (
            <span key={i} className={`h-1 flex-1 rounded-full transition-colors ${i <= step ? "bg-gradient-to-r from-violet-500 to-pink-500" : "bg-border"}`} />
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-xl flex-col px-5 pb-6 pt-8 sm:justify-center sm:pt-6">
          <h1 className="text-[1.75rem] font-extrabold leading-[1.15] tracking-tight text-foreground sm:text-4xl">{q.title}</h1>
          <p className="mt-2 text-[15px] text-muted-foreground">{q.hint}</p>
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
              <div className="grid grid-cols-2 gap-2.5">
                {USES.map((u) => <Card key={u.id} {...u} on={uses.includes(u.id)} testid={`welcome-use-${u.id}`}
                  onClick={() => toggleUse(u.id)} />)}
              </div>
            )}
            {step === 3 && (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {[...new Set([initialCountry, "India", "United States", "United Kingdom", "Canada", "United Arab Emirates", "Australia"].filter(Boolean))].slice(0, 6).map((c) => (
                    <button key={c} type="button" onClick={() => setCountry(c)} data-testid={`welcome-country-${c}`}
                      className={`rounded-full border px-3.5 py-2 text-sm font-medium text-foreground transition ${country === c ? PICKED : UNPICKED}`}>{c}</button>
                  ))}
                </div>
                <select value={country} onChange={(e) => setCountry(e.target.value)} data-testid="welcome-country"
                  className="w-full rounded-2xl border border-border bg-card px-4 py-3.5 text-base text-foreground outline-none focus:border-violet-500">
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
      </div>
      <div className="border-t border-border/60 bg-background/90 backdrop-blur sm:border-0">
        <div className="mx-auto flex max-w-xl items-center gap-3 px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:pb-8">
          {step > 0 && (
            <button onClick={() => setStep(step - 1)} data-testid="welcome-back" aria-label="Back"
              className="flex h-12 w-12 items-center justify-center rounded-full border border-border text-foreground hover:bg-surface">
              <ArrowLeft className="h-5 w-5" />
            </button>
          )}
          <button disabled={!ready || saving} data-testid="welcome-next"
            onClick={() => (step < 3 ? setStep(step + 1) : save())}
            className="flex h-12 flex-1 items-center justify-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-pink-500 text-sm font-semibold text-white shadow-md transition hover:opacity-90 disabled:opacity-40">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : step < 3 ? <>Next <ArrowRight className="h-4 w-4" /></> : <>Finish <Check className="h-4 w-4" /></>}
          </button>
        </div>
      </div>
    </div>
  );
}
