/**
 * Sample still frames from a video file in the browser, so any vision model can
 * "watch" it. Returns { duration, frames: [{ blob, time }] }.
 */
export async function sampleVideoFrames(file, count = 8, maxSide = 768) {
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = url;
  try {
    await new Promise((resolve, reject) => {
      video.onloadedmetadata = resolve;
      video.onerror = () => reject(new Error("This browser can't read that video format"));
    });
    // Some recordings report Infinity until seeked to the end.
    if (!Number.isFinite(video.duration)) {
      video.currentTime = 1e7;
      await new Promise((r) => { video.onseeked = r; });
    }
    const duration = video.duration || 0;
    const scale = Math.min(1, maxSide / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const ctx = canvas.getContext("2d");
    const n = Math.max(1, Math.min(count, Math.ceil(duration)));
    const frames = [];
    for (let i = 0; i < n; i++) {
      const time = n === 1 ? 0 : (duration * (i + 0.5)) / n;
      video.currentTime = time;
      await new Promise((r) => { video.onseeked = r; });
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.82));
      if (blob) frames.push({ blob, time });
    }
    return { duration, frames };
  } finally {
    URL.revokeObjectURL(url);
  }
}
