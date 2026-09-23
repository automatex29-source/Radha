import { useEffect, useRef, useState, useCallback } from "react";
import { useRecorder } from "@/hooks/useRecorder";
import { transcribe, speak, stopSpeaking, speechText } from "@/lib/voice";
import { X, Mic, Loader2, Volume2 } from "lucide-react";

const LABELS = {
  idle: "Tap to talk",
  listening: "Listening… (tap to send)",
  transcribing: "Transcribing…",
  thinking: "Thinking…",
  speaking: "Speaking… (tap to interrupt)",
};

/**
 * Hands-free voice conversation: listen -> transcribe -> ask -> speak reply -> listen again.
 * `onUtterance(text)` must send the message and resolve with the assistant's reply text.
 */
export default function VoiceMode({ onClose, onUtterance, voice }) {
  const rec = useRecorder();
  const [phase, setPhase] = useState("idle");
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const activeRef = useRef(true);

  const cycle = useCallback(async () => {
    setError("");
    try {
      setPhase("listening");
      const blob = await rec.record({ autoStop: true });
      if (!activeRef.current) return;
      if (!blob) { setPhase("idle"); return; }
      setPhase("transcribing");
      const text = (await transcribe(blob)).trim();
      if (!activeRef.current) return;
      if (!text) { setPhase("idle"); return; }
      setHeard(text);
      setReply("");
      setPhase("thinking");
      const answer = await onUtterance(text);
      if (!activeRef.current) return;
      setReply(answer || "");
      if (answer) {
        setPhase("speaking");
        await speak(speechText(answer), voice);
      }
      if (activeRef.current) cycle();
    } catch (e) {
      if (!activeRef.current) return;
      setError(e?.response?.data?.detail || e.message || "Voice error");
      setPhase("idle");
    }
  }, [rec, onUtterance, voice]);

  useEffect(() => {
    activeRef.current = true;
    cycle();
    return () => {
      activeRef.current = false;
      rec.cancel();
      stopSpeaking();
    };
    // Start once on open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onOrb = () => {
    if (phase === "listening") rec.stop();
    else if (phase === "speaking") stopSpeaking(); // cycle continues to listening
    else if (phase === "idle") cycle();
  };

  const scale = phase === "listening" ? 1 + rec.level * 0.5 : 1;
  const busy = phase === "transcribing" || phase === "thinking";

  return (
    <div className="fixed inset-0 z-[60] flex flex-col items-center justify-center bg-[#07080B]/95 px-6 backdrop-blur-xl" data-testid="voice-mode">
      <button onClick={onClose} data-testid="voice-mode-close" title="End voice mode"
        className="absolute right-5 top-5 flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-muted-foreground hover:text-foreground">
        <X className="h-5 w-5" />
      </button>

      <button onClick={onOrb} disabled={busy} data-testid="voice-mode-orb"
        className="relative flex h-40 w-40 items-center justify-center rounded-full bg-primary shadow-[0_0_80px_rgba(99,102,241,0.6)] transition-transform duration-100 disabled:opacity-80"
        style={{ transform: `scale(${scale})` }}>
        {phase === "speaking" ? <Volume2 className="h-12 w-12 text-white" />
          : busy ? <Loader2 className="h-12 w-12 animate-spin text-white" />
          : <Mic className="h-12 w-12 text-white" />}
        {phase === "listening" && <span className="absolute inset-0 animate-ping rounded-full bg-primary/30" />}
      </button>

      <p className="mt-8 text-sm font-medium text-foreground" data-testid="voice-mode-status">{LABELS[phase]}</p>
      {error && <p className="mt-2 max-w-md text-center text-xs text-destructive">{error}</p>}
      <div className="mt-6 w-full max-w-lg space-y-3 text-center">
        {heard && <p className="text-sm text-muted-foreground">“{heard}”</p>}
        {reply && <p className="radha-scroll max-h-40 overflow-y-auto text-sm text-foreground">{speechText(reply)}</p>}
      </div>
    </div>
  );
}
