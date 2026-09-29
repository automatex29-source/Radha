"""Free video fallback: AI images for a few scenes, animated into an MP4.

Each scene gets a slow Ken Burns move (zoom in, zoom out or pan), scenes blend
with the style's transitions (see styles.py), and optional on-screen captions
fade in over each scene. It is not true motion video, but it needs no paid key
and runs on a small CPU. ffmpeg comes from the system or imageio-ffmpeg.
"""
import asyncio
import logging
import os
import random
import shutil
import tempfile
from typing import List, Optional

import media

from . import prompt_boost, styles

logger = logging.getLogger("radha.agent")

FPS = int(os.environ.get("SLIDESHOW_FPS", "24"))
LONG_SIDE = int(os.environ.get("SLIDESHOW_LONG_SIDE", "1280"))
FADE = 0.7
TIMEOUT_SECONDS = int(os.environ.get("SLIDESHOW_TIMEOUT_SECONDS", "480"))
MAX_SCENES = 6


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


def scene_prompts(prompt: str, scenes: Optional[List[str]], seconds: int, style: str = "") -> List[str]:
    cfg = styles.video_style(style)
    look = styles.video_scene_words(style)
    scenes = [s.strip() for s in (scenes or []) if isinstance(s, str) and s.strip()][:MAX_SCENES]
    if scenes:
        return [f"{s}. {look}" for s in scenes]
    count = max(3, min(MAX_SCENES, len(cfg["shots"]), round(seconds / cfg["pace"])))
    return [f"{prompt}, {cfg['shots'][i]}. {look}" for i in range(count)]


def _font(size: int):
    from PIL import ImageFont

    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def caption_png(text: str, w: int, h: int, path: str, bottom: int = 0) -> None:
    """Transparent overlay: a soft dark band at the bottom with bold white text."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    size = max(18, int(min(w, h) * 0.075))
    font = _font(size)
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) > w * 0.86 and line:
            lines.append(line)
            line = word
        else:
            line = trial
    lines = (lines + [line])[:3]
    line_h = int(size * 1.25)
    block = line_h * len(lines)
    top = h - bottom - block - int(h * 0.09)
    band = max(0, top - int(h * 0.08))
    for y in range(band, h - bottom):  # gradient so the text reads on any picture
        alpha = int(170 * min(1.0, (y - band) / max(1, top - band)))
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    for i, ln in enumerate(lines):
        tw = draw.textlength(ln, font=font)
        draw.text(((w - tw) / 2, top + i * line_h), ln, font=font, fill=(255, 255, 255, 255),
                  stroke_width=max(1, size // 18), stroke_fill=(0, 0, 0, 200))
    img.save(path)


def _frame_size(portrait: bool) -> tuple:
    short = (LONG_SIDE * 9 // 16) // 2 * 2
    return (short, LONG_SIDE) if portrait else (LONG_SIDE, short)


def _letterbox(style: str, portrait: bool, h: int) -> int:
    return int(h * 0.12) if styles.video_style(style).get("letterbox") and not portrait else 0


def _motion(i: int, frames: int, zoom: float) -> str:
    """zoompan expressions for scene i: alternate zoom in, pan, zoom out, pan back."""
    t = f"on/{frames}"
    center_x, center_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    kind = i % 4
    if kind == 0:
        return f"z='1+{zoom}*{t}':x='{center_x}':y='{center_y}'"
    if kind == 1:
        return f"z='{1 + zoom}':x='(iw-iw/zoom)*{t}':y='{center_y}'"
    if kind == 2:
        return f"z='{1 + zoom}-{zoom}*{t}':x='{center_x}':y='{center_y}'"
    return f"z='{1 + zoom}':x='(iw-iw/zoom)*(1-{t})':y='{center_y}'"


def build_command(ffmpeg: str, images: List[str], out: str, clip_seconds: float, portrait: bool,
                  style: str = "", captions: Optional[List[Optional[str]]] = None) -> List[str]:
    cfg = styles.video_style(style)
    w, h = _frame_size(portrait)
    frames = int(round(clip_seconds * FPS))
    captions = captions or []
    # One thread keeps memory low (~170MB) on small hosts; it is only a few seconds of CPU.
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-filter_complex_threads", "1"]
    for path in images:
        cmd += ["-i", path]
    overlay_input = {}
    for i, cap in enumerate(captions[:len(images)]):
        if cap:
            overlay_input[i] = len(images) + len(overlay_input)
            cmd += ["-loop", "1", "-t", f"{clip_seconds:.3f}", "-i", cap]
    bar = _letterbox(style, portrait, h)
    parts = []
    for i in range(len(images)):
        # Upscale 2x before zoompan so the slow move doesn't jitter.
        chain = (f"[{i}:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                 f"zoompan={_motion(i, frames, cfg['zoom'])}:d={frames}:s={w}x{h}:fps={FPS},setsar=1")
        if bar:
            chain += f",drawbox=y=0:w=iw:h={bar}:color=black:t=fill,drawbox=y=ih-{bar}:w=iw:h={bar}:color=black:t=fill"
        if i in overlay_input:
            parts.append(f"[{overlay_input[i]}:v]format=rgba,fade=in:st=0.35:d=0.5:alpha=1[c{i}]")
            parts.append(f"{chain}[b{i}]")
            chain = f"[b{i}][c{i}]overlay=0:0:shortest=1"
        parts.append(f"{chain},format=yuv420p[v{i}]")
    last = "v0"
    for i in range(1, len(images)):
        offset = i * (clip_seconds - FADE)
        transition = cfg["transitions"][(i - 1) % len(cfg["transitions"])]
        parts.append(f"[{last}][v{i}]xfade=transition={transition}:duration={FADE}:offset={offset:.3f}[x{i}]")
        last = f"x{i}"
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-threads", "1", out]
    return cmd


async def make_slideshow(prompt: str, seconds: int = 12, portrait: bool = False,
                         scenes: Optional[List[str]] = None, style: str = "",
                         captions: Optional[List[str]] = None) -> bytes:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise SlideshowError("ffmpeg is not installed")
    prompts = scene_prompts(prompt, scenes, seconds, style)
    boosted = await prompt_boost.video_scenes(prompt, scenes, style, len(prompts))
    if boosted:
        look = styles.video_scene_words(style)
        prompts = [f"{s}. {look}" for s in boosted]
    size = "1024x1536" if portrait else "1536x1024"
    seed = random.randint(1, 2_000_000_000)  # one seed for every scene keeps the look consistent
    # Keyless image services allow about one request at a time per server, so only go parallel with a key.
    limit = asyncio.Semaphore(3 if media.image_key_configured() else 1)

    async def one(p: str) -> bytes:
        async with limit:
            return await media.generate_image(p, size, seed=seed)

    results = await asyncio.gather(*(one(p) for p in prompts), return_exceptions=True)
    kept = [(i, r) for i, r in enumerate(results) if isinstance(r, bytes)]
    for r in results:
        if not isinstance(r, bytes):
            logger.warning("slideshow scene failed: %s", r)
    if not kept:
        raise SlideshowError(f"Could not create any scene images ({results[0]})")
    texts = [c.strip() if isinstance(c, str) else "" for c in (captions or [])]
    shots = [data for _, data in kept]
    shot_caps = [texts[i] if i < len(texts) else "" for i, _ in kept]
    if len(shots) == 1:
        shots, shot_caps = shots * 2, shot_caps + [""]  # one picture still gets two different camera moves
    total = max(6, min(30, seconds or 12))
    clip = (total + FADE * (len(shots) - 1)) / len(shots)
    w, h = _frame_size(portrait)
    with tempfile.TemporaryDirectory() as tmp:
        paths, cap_paths = [], []
        for i, data in enumerate(shots):
            path = os.path.join(tmp, f"scene{i}.img")
            with open(path, "wb") as f:
                f.write(data)
            paths.append(path)
            cap_path = None
            if shot_caps[i]:
                cap_path = os.path.join(tmp, f"caption{i}.png")
                caption_png(shot_caps[i][:120], w, h, cap_path, _letterbox(style, portrait, h))
            cap_paths.append(cap_path)
        out = os.path.join(tmp, "video.mp4")
        cmd = build_command(ffmpeg, paths, out, clip, portrait, style, cap_paths)
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            raise SlideshowError("Making the video took too long")
        if proc.returncode != 0 or not os.path.exists(out):
            raise SlideshowError(f"ffmpeg failed: {err.decode(errors='replace')[-300:]}")
        with open(out, "rb") as f:
            return f.read()
