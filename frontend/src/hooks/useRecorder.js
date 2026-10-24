import { useRef, useState, useCallback, useEffect } from "react";

// How long a pause ends a turn: short after a quick question, a little longer once they've talked a while
// (people pause to think mid-sentence).
const SILENCE_MS = 900;
const SILENCE_LONG_MS = 1300;
const NO_SPEECH_MS = 8000;
const MAX_MS = 60000;
const SPEECH_RMS = 0.035;

/**
 * Microphone recorder. `record()` resolves with the recorded Blob (or null if
 * cancelled) when `stop()` is called or, with { autoStop: true }, once the
 * speaker goes quiet after talking.
 */
export function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState(0);
  const stateRef = useRef(null);

  const cleanup = useCallback(() => {
    const st = stateRef.current;
    if (!st) return;
    cancelAnimationFrame(st.raf);
    st.stream.getTracks().forEach((t) => t.stop());
    st.ctx?.close().catch(() => {});
    stateRef.current = null;
    setRecording(false);
    setLevel(0);
  }, []);

  const stop = useCallback(() => {
    const st = stateRef.current;
    if (st && st.recorder.state !== "inactive") st.recorder.stop();
  }, []);

  const cancel = useCallback(() => {
    const st = stateRef.current;
    if (!st) return;
    st.cancelled = true;
    stop();
  }, [stop]);

  const record = useCallback(async ({ autoStop = false } = {}) => {
    if (stateRef.current) throw new Error("Already recording");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      throw new Error("This browser can't record audio");
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    const st = { stream, recorder, cancelled: false, raf: 0, ctx: null };
    stateRef.current = st;
    setRecording(true);

    // Level meter + silence detection.
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analyser);
      st.ctx = ctx;
      const buf = new Float32Array(analyser.fftSize);
      const started = performance.now();
      let heard = false;
      let firstLoud = 0;
      let lastLoud = started;
      let floor = 0; // background noise level, so a fan or traffic doesn't count as talking
      const tick = () => {
        analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        const rms = Math.sqrt(sum / buf.length);
        setLevel(Math.min(1, rms * 8));
        const now = performance.now();
        // Falls to quiet moments at once, rises only slowly, so it follows the room and not the voice.
        floor = !floor || rms < floor ? rms : floor + (rms - floor) * 0.001;
        if (rms > Math.max(SPEECH_RMS, floor * 3)) { if (!heard) firstLoud = now; heard = true; lastLoud = now; }
        const pause = heard && lastLoud - firstLoud > 4000 ? SILENCE_LONG_MS : SILENCE_MS;
        if (autoStop && ((heard && now - lastLoud > pause) || (!heard && now - started > NO_SPEECH_MS))) {
          if (!heard) st.cancelled = true;
          stop();
          return;
        }
        if (now - started > MAX_MS) { stop(); return; }
        st.raf = requestAnimationFrame(tick);
      };
      st.raf = requestAnimationFrame(tick);
    } catch { /* level meter is optional */ }

    return new Promise((resolve) => {
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = () => {
        const cancelled = st.cancelled;
        cleanup();
        resolve(cancelled || !chunks.length ? null : new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      };
      recorder.start(250);
    });
  }, [cleanup, stop]);

  useEffect(() => () => { if (stateRef.current) { stateRef.current.cancelled = true; stop(); } }, [stop]);

  return { record, stop, cancel, recording, level };
}
