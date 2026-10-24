import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heart, Lock, Wind } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// Calming breaths for the Counsellor. Everyone gets the one-minute calm; Pro and Max also get a sleep breath and
// box breathing. Afterwards the person can tell the Counsellor how they feel with one tap.
const IN = (secs, hint = "slowly, through your nose") => ({ label: "Breathe in", hint, secs, scale: 1 });
const HOLD = (secs, scale = 1) => ({ label: "Hold", hint: "soft shoulders", secs, scale });
const OUT = (secs, hint = "let it all go") => ({ label: "Breathe out", hint, secs, scale: 0.55 });
const EXERCISES = [
  { id: "calm", name: "1-minute calm", note: "In 4, hold 4, out 6", phases: [IN(4), HOLD(4), OUT(6)], rounds: 3 },
  { id: "sleep", name: "4-7-8 for sleep", note: "Slows a racing mind", pro: true,
    phases: [IN(4), HOLD(7), OUT(8, "slowly, through your mouth")], rounds: 4 },
  { id: "box", name: "Box breathing", note: "Focus before exams", pro: true,
    phases: [IN(4), HOLD(4), OUT(4), HOLD(4, 0.55)], rounds: 4 },
];
const FEELINGS = [
  { label: "Calmer", text: "I just did the breathing exercise and I feel calmer now." },
  { label: "A bit better", text: "I did the breathing exercise. I feel a little better." },
  { label: "Still tense", text: "I did the breathing exercise but I still feel tense." },
];

export default function BreatheDialog({ open, onOpenChange, onDone, pro }) {
  const navigate = useNavigate();
  const [exercise, setExercise] = useState(EXERCISES[0]);
  const [step, setStep] = useState(-1); // -1 before starting, rounds * phases when finished
  const [left, setLeft] = useState(0);
  const { phases: PHASES, rounds: ROUNDS } = exercise;

  useEffect(() => {
    if (!open) setStep(-1);
  }, [open]);

  useEffect(() => {
    if (step < 0 || step >= ROUNDS * PHASES.length) return undefined;
    setLeft(PHASES[step % PHASES.length].secs);
    const tick = setInterval(() => setLeft((s) => s - 1), 1000);
    const next = setTimeout(() => setStep((s) => s + 1), PHASES[step % PHASES.length].secs * 1000);
    return () => { clearInterval(tick); clearTimeout(next); };
  }, [step, PHASES, ROUNDS]);

  const done = step >= ROUNDS * PHASES.length;
  const phase = step >= 0 && !done ? PHASES[step % PHASES.length] : null;
  const round = Math.min(Math.floor(Math.max(step, 0) / PHASES.length), ROUNDS - 1);
  const minutes = Math.round(PHASES.reduce((n, p) => n + p.secs, 0) * ROUNDS / 60);
  const choose = (x) => {
    if (x.pro && !pro) { onOpenChange(false); navigate("/plans"); return; }
    setExercise(x);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm overflow-hidden text-center" data-testid="breathe-dialog">
        <DialogHeader className="items-center text-center">
          <DialogTitle>{done ? "Well done" : "Breathe with me"}</DialogTitle>
          <DialogDescription>
            {done ? "That was time just for you. How do you feel now?"
              : step < 0 ? "Pick one, then follow the circle." : `${exercise.name}, about ${minutes} min.`}
          </DialogDescription>
        </DialogHeader>

        <div className="relative mx-auto my-3 flex h-52 w-52 items-center justify-center" aria-live="polite">
          <span className="absolute inset-0 rounded-full bg-gradient-to-br from-sky-200/50 via-violet-200/40 to-pink-200/50 blur-xl dark:from-sky-500/15 dark:via-violet-500/15 dark:to-pink-500/15" />
          <span data-testid="breathe-circle"
            className="krish-breathe absolute inset-3 rounded-full bg-gradient-to-br from-sky-400 via-violet-400 to-pink-400 opacity-90 shadow-[0_10px_40px_rgba(139,92,246,0.35)]"
            style={{ transform: `scale(${phase ? phase.scale : done ? 0.8 : 0.55})`, transitionDuration: `${phase ? phase.secs : 0.6}s` }} />
          <div className="relative text-white drop-shadow">
            {phase ? (
              <>
                <p className="text-lg font-semibold">{phase.label}</p>
                <p className="text-3xl font-bold tabular-nums">{Math.max(left, 1)}</p>
                <p className="text-xs opacity-90">{phase.hint}</p>
              </>
            ) : (
              done ? <Heart className="h-9 w-9" /> : <Wind className="h-9 w-9" />
            )}
          </div>
        </div>

        {!done && (
          <div className="flex justify-center gap-1.5" aria-label={`Round ${round + 1} of ${ROUNDS}`}>
            {Array.from({ length: ROUNDS }, (_, i) => (
              <span key={i} className={`h-1.5 w-6 rounded-full ${step >= 0 && i <= round ? "bg-violet-500" : "bg-muted"}`} />
            ))}
          </div>
        )}

        {step < 0 && (
          <div className="grid gap-1.5 text-left" role="radiogroup" aria-label="Breathing exercise">
            {EXERCISES.map((x) => {
              const on = x.id === exercise.id;
              const locked = x.pro && !pro;
              return (
                <button key={x.id} role="radio" aria-checked={on} onClick={() => choose(x)} data-testid={`breathe-pick-${x.id}`}
                  className={`flex items-center gap-3 rounded-xl border px-3 py-2 text-left transition ${on ? "border-violet-400 bg-violet-50 dark:bg-violet-500/10" : "border-border hover:border-violet-300"}`}>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold text-foreground">{x.name}</span>
                    <span className="block text-xs text-muted-foreground">{x.note}</span>
                  </span>
                  {x.pro && (
                    <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-bold ${locked ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300" : "bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-200"}`}>
                      {locked && <Lock className="h-2.5 w-2.5" />} Pro
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
        {step < 0 && (
          <button onClick={() => setStep(0)} data-testid="breathe-start"
            className="mx-auto mt-2 rounded-full bg-gradient-to-r from-sky-500 to-violet-500 px-6 py-2 text-sm font-semibold text-white shadow-sm transition hover:brightness-110">
            Start
          </button>
        )}
        {done && (
          <div className="flex flex-wrap justify-center gap-2">
            {FEELINGS.map((f, i) => (
              <button key={f.label} data-testid={`breathe-feeling-${i}`} onClick={() => { onOpenChange(false); onDone(f.text); }}
                className="rounded-full border border-border bg-card px-3.5 py-1.5 text-sm font-medium text-foreground transition hover:border-violet-400 hover:bg-violet-50 dark:hover:bg-violet-500/10">
                {f.label}
              </button>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
