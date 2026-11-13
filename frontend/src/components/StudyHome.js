import { useRef } from "react";
import { GraduationCap, Camera, ListChecks, Layers, FileText, CalendarDays, Lightbulb, ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

// The start screen while Study mode is on: who the student is (saved on the account by PUT /auth/study, so
// Krish stops asking "which class?") and the six things students do most.
const LEVELS = [
  { id: "class-6-8", label: "Class 6–8" },
  { id: "class-9-10", label: "Class 9–10" },
  { id: "class-11-12", label: "Class 11–12" },
  { id: "jee", label: "JEE" },
  { id: "neet", label: "NEET" },
  { id: "cuet", label: "CUET" },
  { id: "govt", label: "Govt exams" },
  { id: "college", label: "College" },
];
const SCHOOL = new Set(["class-6-8", "class-9-10", "class-11-12"]);
const BOARDS = [{ id: "cbse", label: "CBSE" }, { id: "icse", label: "ICSE" }, { id: "state", label: "State board" }];
const LANGS = [{ id: "en", label: "English" }, { id: "hinglish", label: "Hinglish" }, { id: "hi", label: "हिंदी" }];

// `file`: opens a picker first ("image" for a photo of a question, "doc" for a chapter or notes);
// `text` goes in the message box so the student can finish the sentence (or just tap Send).
const ACTIONS = [
  { id: "photo", icon: Camera, title: "Solve from a photo", hint: "Snap a question, get every step.", file: "image", text: "Solve this question step by step." },
  { id: "quiz", icon: ListChecks, title: "Quiz me", hint: "MCQs with instant answers and a score.", text: "Quiz me with 10 MCQs on " },
  { id: "cards", icon: Layers, title: "Flashcards", hint: "Flip cards to revise fast.", text: "Make flashcards for " },
  { id: "notes", icon: FileText, title: "Notes from a PDF", hint: "Short notes and likely exam questions.", file: "doc", text: "Make short revision notes and the 10 most likely exam questions from this file." },
  { id: "plan", icon: CalendarDays, title: "Exam plan", hint: "A day-by-day plan to your exam.", text: "Make a day-by-day study plan. My exam is on " },
  { id: "explain", icon: Lightbulb, title: "Explain a topic", hint: "Simple words, one idea at a time.", text: "Explain simply: " },
];

function Chip({ on, onClick, children, testId }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on} data-testid={testId}
      className={`shrink-0 rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors ${
        on ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:border-foreground/25 hover:text-foreground"}`}>
      {children}
    </button>
  );
}

export default function StudyHome({ onAttach, onPrefill }) {
  const { user, setUser } = useAuth();
  const imageRef = useRef(null);
  const docRef = useRef(null);
  const pending = useRef("");
  const profile = user?.study || {};

  const save = async (change) => {
    const next = { level: profile.level || null, board: profile.board || null, lang: profile.lang || null, ...change };
    if (!SCHOOL.has(next.level)) next.board = null;
    setUser((u) => (u ? { ...u, study: next } : u));
    try {
      const { data } = await api.put("/auth/study", next);
      setUser(data);
    } catch {
      toast.error("Couldn't save that. Try again.");
    }
  };

  const run = (a) => {
    if (a.file && onAttach) {
      pending.current = a.text;
      (a.file === "image" ? imageRef : docRef).current?.click();
      return;
    }
    onPrefill(a.text);
  };

  const picked = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    for (const f of files) await onAttach(f);
    onPrefill(pending.current);
  };

  return (
    <div data-testid="study-home" className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-3 py-4 sm:px-4">
      <div className="radha-fade-up rounded-3xl border border-border bg-card/70 p-4 sm:p-6">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300">
            <GraduationCap className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg font-semibold tracking-tight text-foreground sm:text-xl">Study with Krish</h2>
            <p className="text-[13px] text-muted-foreground sm:text-sm">Step by step, at your level. Krish teaches, checks you understood, and quizzes you.</p>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">I'm studying for</p>
            <div className="krish-no-scrollbar -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-0.5 sm:flex-wrap">
              {LEVELS.map((l) => (
                <Chip key={l.id} on={profile.level === l.id} testId={`study-level-${l.id}`}
                  onClick={() => save({ level: profile.level === l.id ? null : l.id })}>{l.label}</Chip>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            {SCHOOL.has(profile.level) && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">Board</p>
                <div className="flex gap-1.5">
                  {BOARDS.map((b) => (
                    <Chip key={b.id} on={profile.board === b.id} testId={`study-board-${b.id}`}
                      onClick={() => save({ board: profile.board === b.id ? null : b.id })}>{b.label}</Chip>
                  ))}
                </div>
              </div>
            )}
            <div>
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">Explain in</p>
              <div className="flex gap-1.5">
                {LANGS.map((l) => (
                  <Chip key={l.id} on={profile.lang === l.id} testId={`study-lang-${l.id}`}
                    onClick={() => save({ lang: profile.lang === l.id ? null : l.id })}>{l.label}</Chip>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {ACTIONS.filter((a) => !a.file || onAttach).map((a, i) => (
          <button key={a.id} type="button" onClick={() => run(a)} data-testid={`study-action-${a.id}`}
            style={{ animationDelay: `${0.04 * i}s` }}
            className="krish-topic-card group flex items-start gap-3 rounded-xl border border-border bg-card px-3 py-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-md active:translate-y-0">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-600 transition-transform group-hover:scale-105 dark:bg-amber-500/15 dark:text-amber-300">
              <a.icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium leading-snug text-foreground">{a.title}</p>
              <p className="mt-0.5 text-xs leading-snug text-muted-foreground max-sm:hidden">{a.hint}</p>
            </div>
            <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground/60 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 max-sm:hidden" />
          </button>
        ))}
      </div>
      <input ref={imageRef} type="file" accept="image/*" className="hidden" onChange={picked} data-testid="study-photo-input" />
      <input ref={docRef} type="file" accept=".pdf,.doc,.docx,.txt,.md,.ppt,.pptx,image/*" className="hidden" onChange={picked} data-testid="study-doc-input" />
    </div>
  );
}
