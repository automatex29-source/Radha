import { useEffect, useRef, useState, useCallback } from "react";
import { useRecorder } from "@/hooks/useRecorder";
import { useAuth } from "@/context/AuthContext";
import { transcribeDetect, createSpeaker, stopSpeaking, speechText, watchForSpeech, VOICE_LANGS, getVoiceLang, setVoiceLang } from "@/lib/voice";
import AgentPortrait, { portraitColors } from "@/components/AgentPortrait";
import { X, Mic, MicOff, Loader2, Volume2, Square, Pause, Camera, CameraOff, MonitorUp, SwitchCamera, PhoneOff } from "lucide-react";

const LABELS = {
  idle: "Paused. Tap to talk",
  listening: "Listening… just speak",
  transcribing: "Got it…",
  thinking: "Thinking…",
  speaking: "Speaking… talk or tap to interrupt",
};

const BARGE_KEY = "radha.voiceBargeIn";
const canShareScreen = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getDisplayMedia;

/** One still from the live camera or screen, as a JPEG no wider than 1280px (null if not ready). */
function grabFrame(video) {
  if (!video || !video.videoWidth) return Promise.resolve(null);
  const scale = Math.min(1, 1280 / video.videoWidth);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.8));
}

function getBargeIn() {
  try { return localStorage.getItem(BARGE_KEY) !== "0"; } catch { return true; }
}

/**
 * Hands-free voice conversation: listen -> transcribe -> ask -> speak the reply as it
 * is written -> listen again. Talking (or tapping) while it speaks interrupts it.
 * `onUtterance(text, { onText })` sends the message, calls onText with the reply so far,
 * and resolves with the full reply. `onCancelReply()` stops a reply that is being written.
 * `agent` (a Pro Counsellor agent) turns it into a call with that companion.
 */
export default function VoiceMode({ onClose, onUtterance, onCancelReply, voice, agent = null }) {
  const rec = useRecorder();
  const { user } = useAuth();
  const settingsLangRef = useRef("en");
  settingsLangRef.current = user?.language || "en";
  const [spoken, setSpoken] = useState(null); // language heard last, in Auto
  const [phase, setPhase] = useState("idle");
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [lang, setLang] = useState(getVoiceLang);
  const [bargeIn, setBargeIn] = useState(getBargeIn);
  const [seconds, setSeconds] = useState(0); // call length, shown on an agent call
  const activeRef = useRef(true);
  const speakerRef = useRef(null);
  const unwatchRef = useRef(null);
  const nextRef = useRef("listen"); // what to do after an interruption: "listen" or "pause"
  const bargeRef = useRef(bargeIn);
  bargeRef.current = bargeIn;
  const runningRef = useRef(false);
  const lastLangRef = useRef(null); // language and words heard last, to help hear the next turn right
  const lastHeardRef = useRef("");
  // Live view: "camera" or "screen"; each question sends Krish one picture of what it shows.
  const [view, setView] = useState(null);
  const [facing, setFacing] = useState("environment");
  const streamRef = useRef(null);
  const videoRef = useRef(null);
  const viewRef = useRef(null);
  viewRef.current = view;

  const stopView = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setView(null);
  }, []);

  const startView = useCallback(async (kind, face = facing) => {
    setError("");
    try {
      const stream = kind === "screen"
        ? await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false })
        : await navigator.mediaDevices.getUserMedia({ video: { facingMode: face, width: { ideal: 1280 } }, audio: false });
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = stream;
      stream.getVideoTracks()[0]?.addEventListener("ended", () => { if (streamRef.current === stream) stopView(); });
      setView(kind);
    } catch (e) {
      if (e?.name !== "NotAllowedError" && e?.name !== "AbortError") setError(kind === "screen" ? "Couldn't share your screen" : "Couldn't open the camera");
      else if (kind === "camera") setError("Camera permission was blocked. Allow it in your browser to show Krish things.");
    }
  }, [facing, stopView]);

  useEffect(() => {
    if (videoRef.current && streamRef.current && videoRef.current.srcObject !== streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play?.().catch(() => {});
    }
  }, [view, facing]);

  const flipCamera = () => {
    const next = facing === "environment" ? "user" : "environment";
    setFacing(next);
    startView("camera", next);
  };

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
        const result = await transcribeDetect(blob, { hint: lastLangRef.current, context: lastHeardRef.current });
        const text = result.text.trim();
        if (!activeRef.current || nextRef.current === "pause") break;
        if (!text) continue;
        // Auto: answer in the language they just spoke; if unknown, their Settings language.
        const picked = getVoiceLang();
        const replyLang = picked !== "auto" ? picked
          : VOICE_LANGS.some((l) => l.id === result.language) ? result.language
          : settingsLangRef.current;
        if (picked === "auto") setSpoken(replyLang);
        lastLangRef.current = replyLang;
        lastHeardRef.current = text;
        setHeard(text);
        setReply("");
        setPhase("thinking");

        const speaker = createSpeaker({
          voice,
          lang: replyLang,
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
        const frame = viewRef.current ? await grabFrame(videoRef.current) : null;
        const answer = await onUtterance(text, {
          voiceLang: replyLang,
          frame: frame ? { blob: frame, source: viewRef.current } : null,
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
      streamRef.current?.getTracks().forEach((t) => t.stop());
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

  useEffect(() => {
    if (!agent) return undefined;
    const started = Date.now();
    const id = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [agent]);

  if (agent) {
    // A call with a Counsellor agent: their portrait, name, live captions and call buttons.
    const [c0, c1] = portraitColors(agent.id);
    const status = { idle: "On hold. Tap the mic to talk", listening: "Listening…", transcribing: "Listening…",
      thinking: `${agent.name} is thinking…`, speaking: `${agent.name} is speaking…` }[phase];
    const ring = phase === "listening" ? 1 + rec.level * 0.35 : 1;
    const callButton = "flex h-14 w-14 items-center justify-center rounded-full transition-colors";
    return (
      <div data-testid="voice-mode" className="fixed inset-0 z-[60] flex flex-col overflow-hidden text-white"
        style={{ backgroundColor: "#0a0a14", backgroundImage: `radial-gradient(120% 70% at 50% 28%, ${c1} 0%, ${c0} 38%, #0a0a14 88%)` }}>
        <div className="flex items-center justify-between gap-2 px-4 pt-4">
          <select value={lang} data-testid="voice-mode-language" aria-label="Spoken language"
            onChange={(e) => { setVoiceLang(e.target.value); setLang(e.target.value); }}
            className="h-9 max-w-[60%] rounded-full border border-white/20 bg-white/10 px-3 text-xs text-white backdrop-blur [&>option]:text-black">
            {VOICE_LANGS.map((l) => (
              <option key={l.id} value={l.id}>{l.id === "auto" ? l.name : `${l.label} (${l.name})`}</option>
            ))}
          </select>
          <span className="text-xs font-medium tabular-nums text-white/70" data-testid="voice-mode-timer">
            {String(Math.floor(seconds / 60)).padStart(2, "0")}:{String(seconds % 60).padStart(2, "0")}
          </span>
        </div>

        <div className="flex flex-1 flex-col items-center justify-center px-6" data-testid="voice-mode-agent">
          <button onClick={onOrb} disabled={phase === "transcribing"} data-testid="voice-mode-orb"
            title={replying ? "Interrupt" : phase === "listening" ? "Send now" : "Talk"}
            className="relative flex items-center justify-center rounded-full">
            {[0, 1, 2].map((i) => (
              <span key={i} aria-hidden="true"
                className={`absolute rounded-full border border-white/25 ${phase === "speaking" ? "krish-call-ring" : ""}`}
                style={{ inset: `${-18 - i * 22}px`, animationDelay: `${i * 0.45}s`, opacity: phase === "speaking" ? undefined : 0.5 - i * 0.14,
                  transform: phase === "listening" ? `scale(${ring + i * 0.02})` : undefined, transition: "transform 120ms" }} />
            ))}
            <AgentPortrait id={agent.id} className={`${view ? "h-28 w-28" : "h-40 w-40 sm:h-48 sm:w-48"} shadow-2xl ring-4 ring-white/30`} />
            {busy && <span className="absolute -bottom-2 rounded-full bg-black/50 p-1.5"><Loader2 className="h-4 w-4 animate-spin" /></span>}
          </button>
          <h2 className="mt-12 text-3xl font-bold tracking-tight">{agent.name}</h2>
          <p className="mt-1 text-sm text-white/75" data-testid="voice-mode-status">{status}</p>
          {error && <p className="mt-2 max-w-md text-center text-xs text-red-200">{error}</p>}

          {view && (
            <div className="relative mt-5 w-full max-w-xs overflow-hidden rounded-2xl border border-white/20 bg-black" data-testid="voice-mode-view">
              <video ref={videoRef} autoPlay playsInline muted
                className={`aspect-[4/3] w-full object-cover ${view === "camera" && facing === "user" ? "-scale-x-100" : ""} ${view === "screen" ? "object-contain" : ""}`} />
              {view === "camera" && (
                <button onClick={flipCamera} data-testid="voice-mode-flip" title="Switch camera"
                  className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 hover:bg-black/80">
                  <SwitchCamera className="h-4 w-4" />
                </button>
              )}
            </div>
          )}

          <div className="mt-6 w-full max-w-md space-y-2 text-center" data-testid="voice-mode-captions">
            {heard && <p className="text-sm text-white/60">You: “{heard}”</p>}
            <p className="radha-scroll max-h-36 overflow-y-auto rounded-2xl bg-white/10 px-4 py-3 text-[15px] leading-relaxed backdrop-blur">
              {reply ? speechText(reply) : agent.hello}
            </p>
          </div>
        </div>

        <div className="flex flex-col items-center gap-3 pb-8">
          <div className="flex items-start gap-6">
            <div className="flex flex-col items-center gap-1.5">
              <button onClick={() => (view === "camera" ? stopView() : startView("camera"))} data-testid="voice-mode-camera"
                title={view === "camera" ? "Turn camera off" : `Show ${agent.name} with your camera`}
                className={`${callButton} ${view === "camera" ? "bg-white text-black" : "bg-white/15 hover:bg-white/25"}`}>
                {view === "camera" ? <CameraOff className="h-6 w-6" /> : <Camera className="h-6 w-6" />}
              </button>
              <span className="text-[11px] text-white/70">Camera</span>
            </div>
            <div className="flex flex-col items-center gap-1.5">
              <button onClick={() => (phase === "idle" ? cycle() : interrupt("pause"))}
                data-testid={phase === "idle" ? "voice-mode-resume" : replying ? "voice-mode-stop" : "voice-mode-pause"}
                title={phase === "idle" ? "Talk" : "Hold"}
                className={`${callButton} ${phase === "idle" ? "bg-white text-black" : "bg-white/15 hover:bg-white/25"}`}>
                {phase === "idle" ? <MicOff className="h-6 w-6" /> : <Mic className="h-6 w-6" />}
              </button>
              <span className="text-[11px] text-white/70">{phase === "idle" ? "On hold" : "Mic on"}</span>
            </div>
            <div className="flex flex-col items-center gap-1.5">
              <button onClick={onClose} data-testid="voice-mode-close" title="End call"
                className={`${callButton} bg-red-500 shadow-lg shadow-red-500/30 hover:bg-red-600`}>
                <PhoneOff className="h-6 w-6" />
              </button>
              <span className="text-[11px] text-white/70">End</span>
            </div>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-[11px] text-white/60">
            <input type="checkbox" checked={bargeIn} onChange={toggleBargeIn} data-testid="voice-mode-barge-in" />
            Interrupt by talking (best with headphones)
          </label>
        </div>
      </div>
    );
  }

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

      {view && (
        <div className="relative mb-6 w-full max-w-sm overflow-hidden rounded-2xl border border-border bg-black shadow-xl" data-testid="voice-mode-view">
          <video ref={videoRef} autoPlay playsInline muted
            className={`aspect-[4/3] w-full object-cover ${view === "camera" && facing === "user" ? "-scale-x-100" : ""} ${view === "screen" ? "object-contain" : ""}`} />
          <span className="absolute left-2 top-2 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-medium text-white">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" /> Krish can see your {view}
          </span>
          {view === "camera" && (
            <button onClick={flipCamera} data-testid="voice-mode-flip" title="Switch camera"
              className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/80">
              <SwitchCamera className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      <button onClick={onOrb} disabled={phase === "transcribing"} data-testid="voice-mode-orb"
        title={phase === "speaking" || phase === "thinking" ? "Interrupt" : phase === "listening" ? "Send now" : "Talk"}
        className={`relative flex ${view ? "h-24 w-24" : "h-40 w-40"} items-center justify-center rounded-full bg-primary shadow-[0_0_80px_rgba(99,102,241,0.6)] transition-transform duration-100 disabled:opacity-80`}
        style={{ transform: `scale(${scale})` }}>
        {phase === "speaking" ? <Volume2 className={`${view ? "h-8 w-8" : "h-12 w-12"} animate-pulse text-white`} />
          : busy ? <Loader2 className={`${view ? "h-8 w-8" : "h-12 w-12"} animate-spin text-white`} />
          : <Mic className={`${view ? "h-8 w-8" : "h-12 w-12"} ${phase === "idle" ? "text-white/80" : "text-white"}`} />}
        {phase === "listening" && <span className="absolute inset-0 animate-ping rounded-full bg-primary/30" />}
      </button>

      <p className="mt-8 text-sm font-medium text-foreground" data-testid="voice-mode-status">{LABELS[phase]}</p>
      {lang === "auto" && spoken && (
        <p className="mt-2 text-xs text-muted-foreground" data-testid="voice-mode-heard-language">
          Answering in {VOICE_LANGS.find((l) => l.id === spoken)?.name || spoken}
        </p>
      )}
      {error && <p className="mt-2 max-w-md text-center text-xs text-destructive">{error}</p>}
      <div className="mt-6 w-full max-w-lg space-y-3 text-center">
        {heard && <p className="text-sm text-muted-foreground">“{heard}”</p>}
        {reply && <p className="radha-scroll max-h-40 overflow-y-auto text-sm text-foreground">{speechText(reply)}</p>}
      </div>

      <div className="absolute bottom-8 flex flex-col items-center gap-4">
        <div className="flex items-center gap-3">
          <button onClick={() => (view === "camera" ? stopView() : startView("camera"))} data-testid="voice-mode-camera"
            title={view === "camera" ? "Turn camera off" : "Show Krish with your camera"}
            className={`flex h-12 w-12 items-center justify-center rounded-full border transition-colors ${view === "camera" ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-foreground hover:bg-surface"}`}>
            {view === "camera" ? <CameraOff className="h-5 w-5" /> : <Camera className="h-5 w-5" />}
          </button>
          {canShareScreen && (
            <button onClick={() => (view === "screen" ? stopView() : startView("screen"))} data-testid="voice-mode-screen"
              title={view === "screen" ? "Stop sharing your screen" : "Share your screen with Krish"}
              className={`flex h-12 w-12 items-center justify-center rounded-full border transition-colors ${view === "screen" ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-foreground hover:bg-surface"}`}>
              <MonitorUp className="h-5 w-5" />
            </button>
          )}
        </div>
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
