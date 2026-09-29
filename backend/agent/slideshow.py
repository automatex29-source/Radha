"""Free video fallback: AI images for a few scenes, animated into an MP4.

Each scene gets a slow Ken Burns move (zoom in, zoom out or pan) and scenes
cross-fade into each other. It is not true motion video, but it needs no paid
key and runs on a small CPU. ffmpeg comes from the system or imageio-ffmpeg.
"""
import asyncio
import logging
import os
import shutil
import tempfile
from typing import List, Optional

import media

logger = logging.getLogger("radha.agent")

FPS = int(os.environ.get("SLIDESHOW_FPS", "24"))
LONG_SIDE = int(os.environ.get("SLIDESHOW_LONG_SIDE", "1280"))
FADE = 0.7
ZOOM = 0.14
TIMEOUT_SECONDS = int(os.environ.get("SLIDESHOW_TIMEOUT_SECONDS", "480"))
MAX_SCENES = 6

# Shot variety when the model gives one prompt and no scene list.
SHOTS = ["wide establishing shot", "medium shot of the main subject in action",
         "dramatic close-up detail", "sweeping cinematic wide shot, final moment",
         "low angle hero shot", "aerial view"]
STYLE = "cinematic film still, highly detailed, sharp focus, dramatic lighting, rich color, 35mm"


class SlideshowError(Exception):
    pass


def ffmpeg_path() -> Optional[str]:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def scene_prompts(prompt: str, scenes: Optional[List[str]], seconds: int) -> List[str]:
    scenes = [s.strip() for s in (scenes or []) if isinstance(s, str) and s.strip()][:MAX_SCENES]
    if scenes:
        return [f"{s}. {STYLE}" for s in scenes]
    count = max(3, min(MAX_SCENES, round(seconds / 3)))
    return [f"{prompt}, {SHOTS[i]}. {STYLE}" for i in range(count)]


def _frame_size(portrait: bool) -> tuple:
    short = (LONG_SIDE * 9 // 16) // 2 * 2
    return (short, LONG_SIDE) if portrait else (LONG_SIDE, short)


def _motion(i: int, frames: int) -> str:
    """zoompan expressions for scene i: alternate zoom in, pan, zoom out, pan back."""
    t = f"on/{frames}"
    center_x, center_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    kind = i % 4
    if kind == 0:
        return f"z='1+{ZOOM}*{t}':x='{center_x}':y='{center_y}'"
    if kind == 1:
        return f"z='{1 + ZOOM}':x='(iw-iw/zoom)*{t}':y='{center_y}'"
    if kind == 2:
        return f"z='{1 + ZOOM}-{ZOOM}*{t}':x='{center_x}':y='{center_y}'"
    return f"z='{1 + ZOOM}':x='(iw-iw/zoom)*(1-{t})':y='{center_y}'"


def build_command(ffmpeg: str, images: List[str], out: str, clip_seconds: float, portrait: bool) -> List[str]:
    w, h = _frame_size(portrait)
    frames = int(round(clip_seconds * FPS))
    # One thread keeps memory low (~170MB) on small hosts; it is only a few seconds of CPU.
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-filter_complex_threads", "1"]
    for path in images:
        cmd += ["-i", path]
    parts = []
    for i in range(len(images)):
        # Upscale 2x before zoompan so the slow move doesn't jitter.
        parts.append(f"[{i}:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                     f"zoompan={_motion(i, frames)}:d={frames}:s={w}x{h}:fps={FPS},setsar=1,format=yuv420p[v{i}]")
    last = "v0"
    for i in range(1, len(images)):
        offset = i * (clip_seconds - FADE)
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[x{i}]")
        last = f"x{i}"
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-threads", "1", out]
    return cmd


async def make_slideshow(prompt: str, seconds: int = 12, portrait: bool = False,
                         scenes: Optional[List[str]] = None) -> bytes:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise SlideshowError("ffmpeg is not installed")
    prompts = scene_prompts(prompt, scenes, seconds)
    size = "1024x1536" if portrait else "1536x1024"
    # Keyless image services allow about one request at a time per server, so only go parallel with a key.
    limit = asyncio.Semaphore(3 if media.image_key_configured() else 1)

    async def one(p: str) -> bytes:
        async with limit:
            return await media.generate_image(p, size)

    results = await asyncio.gather(*(one(p) for p in prompts), return_exceptions=True)
    shots = [r for r in results if isinstance(r, bytes)]
    for r in results:
        if not isinstance(r, bytes):
            logger.warning("slideshow scene failed: %s", r)
    if not shots:
        raise SlideshowError(f"Could not create any scene images ({results[0]})")
    if len(shots) == 1:
        shots = shots * 2  # one picture still gets two different camera moves
    total = max(6, min(30, seconds or 12))
    clip = (total + FADE * (len(shots) - 1)) / len(shots)
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, data in enumerate(shots):
            path = os.path.join(tmp, f"scene{i}.img")
            with open(path, "wb") as f:
                f.write(data)
            paths.append(path)
        out = os.path.join(tmp, "video.mp4")
        proc = await asyncio.create_subprocess_exec(*build_command(ffmpeg, paths, out, clip, portrait),
                                                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            raise SlideshowError("Making the video took too long")
        if proc.returncode != 0 or not os.path.exists(out):
            raise SlideshowError(f"ffmpeg failed: {err.decode(errors='replace')[-300:]}")
        with open(out, "rb") as f:
            return f.read()
