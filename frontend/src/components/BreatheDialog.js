import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// A one-minute calming breath for the Counsellor: in for 4, hold for 4, out for 6, three times.
// Afterwards the person can tell the Counsellor how they feel with one tap.
const PHASES = [
  { label: "Breathe in", hint: "slowly, through your nose", secs: 4, scale: 1 },
  { label: "Hold", hint: "soft shoulders", secs: 4, scale: 1 },
  { label: "Breathe out", hint: "let it all go", secs: 6, scale: 0.55 },
];
const ROUNDS = 3;
const FEELINGS = [
  { label: "Calmer 😌", text: "I just did the breathing exercise and I feel calmer now 😌" },
  { label: "A bit better 🙂", text: "I did the breathing exercise. I feel a little better 🙂" },
  { label: "Still tense 😣", text: "I did the breathing exercise but I still feel tense 😣" },
];

export default function BreatheDialog({ open, onOpenChange, onDone }) {
  const [step, setStep] = useState(-1); // -1 before starting, ROUNDS * 3 when finished
  const [left, setLeft] = useState(0);

  useEffect(() => {
    if (!open) setStep(-1);
  }, [open]);

  useEffect(() => {
    if (step < 0 || step >= ROUNDS * PHASES.length) return undefined;
    setLeft(PHASES[step % PHASES.length].secs);
    const tick = setInterval(() => setLeft((s) => s - 1), 1000);
    const next = setTimeout(() => setStep((s) => s + 1), PHASES[step % PHASES.length].secs * 1000);
    return () => { clearInterval(tick); clearTimeout(next); };
  }, [step]);

  const done = step >= ROUNDS * PHASES.length;
  const phase = step >= 0 && !done ? PHASES[step % PHASES.length] : null;
  const round = Math.min(Math.floor(Math.max(step, 0) / PHASES.length), ROUNDS - 1);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm overflow-hidden text-center" data-testid="breathe-dialog">
        <DialogHeader className="items-center text-center">
          <DialogTitle>{done ? "Well done 💛" : "Breathe with me"}</DialogTitle>
          <DialogDescription>
            {done ? "That was a minute just for you. How do you feel now?" : "One calm minute. Follow the circle."}
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
              <p className="text-3xl">{done ? "🌸" : "🌬️"}</p>
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
