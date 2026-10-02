import { useEffect, useRef, useState, useCallback } from "react";
import { useRecorder } from "@/hooks/useRecorder";
import { transcribe, createSpeaker, stopSpeaking, speechText, watchForSpeech, VOICE_LANGS, getVoiceLang, setVoiceLang } from "@/lib/voice";
import { X, Mic, Loader2, Volume2, Square, Pause } from "lucide-react";

const LABELS = {
  idle: "Paused. Tap to talk",
  listening: "Listening… just speak",
  transcribing: "Got it…",
  thinking: "Thinking…",
  speaking: "Speaking… talk or tap to interrupt",
};

const BARGE_KEY = "radha.voiceBargeIn";
function getBargeIn() {
  try { return localStorage.getItem(BARGE_KEY) !== "0"; } catch { return true; }
}

/**
 * Hands-free voice conversation: listen -> transcribe -> ask -> speak the reply as it
 * is written -> listen again. Talking (or tapping) while it speaks interrupts it.
 * `onUtterance(text, { onText })` sends the message, calls onText with the reply so far,
 * and resolves with the full reply. `onCancelReply()` stops a reply that is being written.
 */
export default function VoiceMode({ onClose, onUtterance, onCancelReply, voice }) {
  const rec = useRecorder();
  const [phase, setPhase] = useState("idle");
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [lang, setLang] = useState(getVoiceLang);
  const [bargeIn, setBargeIn] = useState(getBargeIn);
  const activeRef = useRef(true);
  const speakerRef = useRef(null);
  const unwatchRef = useRef(null);
  const nextRef = useRef("listen"); // what to do after an interruption: "listen" or "pause"
  const bargeRef = useRef(bargeIn);
  bargeRef.current = bargeIn;
  const runningRef = useRef(false);

  const stopWatching = () => { unwatchRef.current?.(); unwatchRef.current = null; };

  // Stop the current reply (voice and text). Then listen again, or pause.
  const interrupt = useCallback((next) => {
    nextRef.current = next;
    stopWatching();
    speakerRef.current?.stop();
    onCancelReply?.();
    if (next === "listen" && rec.recording) rec.stop();
    if (next === "pause") rec.cancel();
  }, [onCancelReply, rec]);

  const cycle = useCallback(async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    setError("");
    try {
      while (activeRef.current) {
        nextRef.current = "listen";
        setPhase("listening");
        const blob = await rec.record({ autoStop: true });
        if (!activeRef.current || nextRef.current === "pause") break;
        if (!blob) { setPhase("idle"); break; } // nobody spoke for a while: pause
        setPhase("transcribing");
        const text = (await transcribe(blob)).trim();
        if (!activeRef.current || nextRef.current === "pause") break;
        if (!text) continue;
        setHeard(text);
        setReply("");
        setPhase("thinking");

        const speaker = createSpeaker({
          voice,
          onStart: () => {
            if (!activeRef.current) return;
            setPhase("speaking");
            if (bargeRef.current) {
              watchForSpeech(() => interrupt("listen")).then((unwatch) => {
                if (speakerRef.current === speaker && activeRef.current) unwatchRef.current = unwatch;
                else unwatch();
              });
            }
          },
        });
        speakerRef.current = speaker;
        const answer = await onUtterance(text, {
          onText: (t) => { setReply(t); speaker.push(t); },
        });
        if (!activeRef.current) break;
        setReply(answer || "");
        speaker.end(answer || "");
        await speaker.done;
        stopWatching();
        speakerRef.current = null;
        if (!activeRef.current || nextRef.current === "pause") break;
      }
    } catch (e) {
      if (activeRef.current) setError(e?.response?.data?.detail || e.message || "Voice error");
    } finally {
      stopWatching();
      speakerRef.current = null;
      runningRef.current = false;
      if (activeRef.current) setPhase((p) => (p === "listening" || p === "transcribing" || p === "thinking" || p === "speaking" ? "idle" : p));
    }
  }, [rec, onUtterance, voice, interrupt]);

  useEffect(() => {
    activeRef.current = true;
    cycle();
    return () => {
      activeRef.current = false;
      stopWatching();
      speakerRef.current?.stop();
      rec.cancel();
      stopSpeaking();
    };
    // Start once on open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onOrb = () => {
    if (phase === "listening") rec.stop(); // send now instead of waiting for the pause
    else if (phase === "speaking" || phase === "thinking") interrupt("listen");
    else if (phase === "idle") cycle();
  };

  const toggleBargeIn = () => {
    const v = !bargeIn;
    setBargeIn(v);
    try { localStorage.setItem(BARGE_KEY, v ? "1" : "0"); } catch { /* optional */ }
    if (!v) stopWatching();
  };

  const scale = phase === "listening" ? 1 + rec.level * 0.5 : 1;
  const busy = phase === "transcribing" || phase === "thinking";
  const replying = phase === "thinking" || phase === "speaking";

  return (
    <div className="fixed inset-0 z-[60] flex flex-col items-center justify-center bg-background/95 px-6 backdrop-blur-xl" data-testid="voice-mode">
      <div className="absolute left-4 right-4 top-4 flex items-center justify-between gap-2">
        <select value={lang} data-testid="voice-mode-language" aria-label="Spoken language"
          onChange={(e) => { setVoiceLang(e.target.value); setLang(e.target.value); }}
          className="h-10 rounded-full border border-border bg-card px-3 text-sm text-foreground">
          {VOICE_LANGS.map((l) => (
            <option key={l.id} value={l.id}>{l.id === "auto" ? l.name : `${l.label} (${l.name})`}</option>
          ))}
        </select>
        <button onClick={onClose} data-testid="voice-mode-close" title="End voice mode"
          className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-muted-foreground hover:text-foreground">
          <X className="h-5 w-5" />
        </button>
      </div>

      <button onClick={onOrb} disabled={phase === "transcribing"} data-testid="voice-mode-orb"
        title={phase === "speaking" || phase === "thinking" ? "Interrupt" : phase === "listening" ? "Send now" : "Talk"}
        className="relative flex h-40 w-40 items-center justify-center rounded-full bg-primary shadow-[0_0_80px_rgba(99,102,241,0.6)] transition-transform duration-100 disabled:opacity-80"
        style={{ transform: `scale(${scale})` }}>
        {phase === "speaking" ? <Volume2 className="h-12 w-12 animate-pulse text-white" />
          : busy ? <Loader2 className="h-12 w-12 animate-spin text-white" />
          : phase === "idle" ? <Mic className="h-12 w-12 text-white/80" />
          : <Mic className="h-12 w-12 text-white" />}
        {phase === "listening" && <span className="absolute inset-0 animate-ping rounded-full bg-primary/30" />}
      </button>

      <p className="mt-8 text-sm font-medium text-foreground" data-testid="voice-mode-status">{LABELS[phase]}</p>
      {error && <p className="mt-2 max-w-md text-center text-xs text-destructive">{error}</p>}
      <div className="mt-6 w-full max-w-lg space-y-3 text-center">
        {heard && <p className="text-sm text-muted-foreground">“{heard}”</p>}
        {reply && <p className="radha-scroll max-h-40 overflow-y-auto text-sm text-foreground">{speechText(reply)}</p>}
      </div>

      <div className="absolute bottom-8 flex flex-col items-center gap-4">
        {replying ? (
          <button onClick={() => interrupt("pause")} data-testid="voice-mode-stop"
            className="flex items-center gap-2 rounded-full border border-border bg-card px-5 py-2.5 text-sm font-medium text-foreground hover:bg-surface">
            <Square className="h-4 w-4 fill-current" /> Stop
          </button>
        ) : phase === "listening" ? (
          <button onClick={() => interrupt("pause")} data-testid="voice-mode-pause"
            className="flex items-center gap-2 rounded-full border border-border bg-card px-5 py-2.5 text-sm font-medium text-foreground hover:bg-surface">
            <Pause className="h-4 w-4" /> Pause
          </button>
        ) : null}
        <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={bargeIn} onChange={toggleBargeIn} data-testid="voice-mode-barge-in" />
          Interrupt by talking (best with headphones)
        </label>
      </div>
    </div>
  );
}
