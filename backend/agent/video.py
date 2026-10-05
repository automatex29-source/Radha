"""Video generation: OpenAI Sora, Google Veo, Pollinations, or a free slideshow.

Provider: VIDEO_PROVIDER=openai|gemini|pollinations|slideshow|off, otherwise the
first key that is set: OPENAI_API_KEY, POLLINATIONS_API_KEY (Veo only with VIDEO_PROVIDER=gemini).
With no key we make a "slideshow": AI images for a few scenes, animated with
slow camera moves and cross-fades (see slideshow.py). Pollinations falls back to
the slideshow when its free daily allowance runs out. Sora and Veo are
asynchronous, so we submit a job and poll (VIDEO_TIMEOUT_SECONDS, default 10 min).
"""
import asyncio
import logging
import os
import time
from typing import Optional, Tuple

import httpx

import fal_api
import media

from . import prompt_boost, slideshow, styles

# "high" (default): Sora 2 Pro at 1792x1024 / Veo 3 at 1080p. "standard": faster, cheaper, 720p.
DEFAULT_QUALITY = os.environ.get("VIDEO_QUALITY", "high")
SORA = {
    "high": {"model": os.environ.get("SORA_PRO_MODEL", "sora-2-pro"), "landscape": "1792x1024", "portrait": "1024x1792"},
    "standard": {"model": os.environ.get("SORA_MODEL", "sora-2"), "landscape": "1280x720", "portrait": "720x1280"},
}
VEO = {
    "high": {"model": os.environ.get("VEO_MODEL", "veo-3.0-generate-001"), "resolution": "1080p"},
    "standard": {"model": os.environ.get("VEO_FAST_MODEL", "veo-3.0-fast-generate-001"), "resolution": "720p"},
}
TIMEOUT_SECONDS = int(os.environ.get("VIDEO_TIMEOUT_SECONDS", "600"))
POLL_SECONDS = 8
SORA_SECONDS = {4, 8, 12}
logger = logging.getLogger("radha.agent")


POLLINATIONS_VIDEO_MODEL = os.environ.get("POLLINATIONS_VIDEO_MODEL", "alibaba/wan-2.2-fast")
POLLINATIONS_VIDEO_SECONDS = int(os.environ.get("POLLINATIONS_VIDEO_SECONDS", "5"))
PROVIDERS = ("fal", "openai", "gemini", "pollinations", "slideshow")
FAL_VIDEO_MODEL = os.environ.get("FAL_VIDEO_MODEL", "fal-ai/veo3.1/fast")
FAL_VIDEO_RESOLUTION = os.environ.get("FAL_VIDEO_RESOLUTION", "1080p")
FAL_SECONDS = (4, 6, 8)


class VideoError(Exception):
    pass


def provider() -> Optional[str]:
    explicit = os.environ.get("VIDEO_PROVIDER", "").lower()
    if explicit in PROVIDERS:
        return explicit
    if explicit in ("off", "0", "none"):
        return None
    if fal_api.configured():
        return "fal"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    # A Gemini key alone doesn't pick Veo: Veo has no free tier, and the key is usually there for chat.
    # Set VIDEO_PROVIDER=gemini on a paid Google plan.
    if os.environ.get("POLLINATIONS_API_KEY"):
        return "pollinations"
    if slideshow.ffmpeg_path() and media.image_available():
        return "slideshow"
    return None


def available() -> bool:
    return provider() is not None


def _http_client() -> httpx.AsyncClient:
    base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    return httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(120.0, connect=15.0),
                             headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"})


async def _sora(prompt: str, seconds: int, portrait: bool, quality: str) -> bytes:
    seconds = min(SORA_SECONDS, key=lambda s: abs(s - seconds))
    cfg = SORA[quality]
    size = cfg["portrait" if portrait else "landscape"]
    async with _http_client() as client:
        # Multipart form, as the Videos API expects.
        resp = await client.post("/videos", files={
            "model": (None, cfg["model"]), "prompt": (None, prompt),
            "seconds": (None, str(seconds)), "size": (None, size),
        })
        if resp.status_code >= 400:
            raise VideoError(f"Video request rejected: {resp.text[:300]}")
        job = resp.json()
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while job.get("status") not in ("completed", "failed"):
            if time.monotonic() > deadline:
                raise VideoError("Video generation timed out")
            await asyncio.sleep(POLL_SECONDS)
            job = (await client.get(f"/videos/{job['id']}")).raise_for_status().json()
        if job["status"] == "failed":
            raise VideoError((job.get("error") or {}).get("message") or "Video generation failed")
        content = await client.get(f"/videos/{job['id']}/content")
        content.raise_for_status()
        return content.content


def _genai_client():
    from google import genai

    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


async def _veo(prompt: str, portrait: bool, quality: str) -> bytes:
    from google.genai import types

    cfg = VEO[quality]
    client = _genai_client()
    config = types.GenerateVideosConfig(number_of_videos=1, aspect_ratio="9:16" if portrait else "16:9")
    if not portrait:
        config.resolution = cfg["resolution"]  # Veo 3 serves 1080p for 16:9
    op = await client.aio.models.generate_videos(model=cfg["model"], prompt=prompt, config=config)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while not op.done:
        if time.monotonic() > deadline:
            raise VideoError("Video generation timed out")
        await asyncio.sleep(POLL_SECONDS)
        op = await client.aio.operations.get(op)
    if op.error:
        raise VideoError(str(op.error.get("message") if isinstance(op.error, dict) else op.error))
    videos = (op.response.generated_videos if op.response else None) or []
    if not videos:
        raise VideoError("No video returned (the prompt may have been blocked by safety filters)")
    video = videos[0].video
    data = video.video_bytes or await client.aio.files.download(file=video)
    if not data:
        raise VideoError("Video download failed")
    return data


async def _pollinations(prompt: str, seconds: int, portrait: bool) -> bytes:
    from urllib.parse import quote

    params = {"model": POLLINATIONS_VIDEO_MODEL, "duration": max(2, min(seconds, POLLINATIONS_VIDEO_SECONDS)),
              "aspectRatio": "9:16" if portrait else "16:9"}
    headers = {"Authorization": f"Bearer {os.environ.get('POLLINATIONS_API_KEY', '')}", "User-Agent": "KrishAI/1.0"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=20.0), follow_redirects=True) as client:
        resp = await client.get(f"{media.POLLINATIONS_BASE}/video/{quote(prompt[:1500], safe='')}",
                                params=params, headers=headers)
    if resp.status_code >= 400 or not resp.headers.get("content-type", "").startswith("video/"):
        raise VideoError(f"Pollinations video HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.content


async def _fal(prompt: str, seconds: int, portrait: bool) -> bytes:
    duration = min(FAL_SECONDS, key=lambda s: abs(s - (seconds or 8)))
    result = await fal_api.run(FAL_VIDEO_MODEL, {
        "prompt": prompt, "aspect_ratio": "9:16" if portrait else "16:9", "duration": f"{duration}s",
        "resolution": FAL_VIDEO_RESOLUTION, "generate_audio": True})
    url = (result.get("video") or {}).get("url")
    if not url:
        raise VideoError(f"fal returned no video: {str(result)[:200]}")
    return await fal_api.download(url)


async def generate(prompt: str, seconds: int = 8, orientation: str = "", quality: Optional[str] = None,
                   scenes: Optional[list] = None, style: str = "", captions: Optional[list] = None) -> dict:
    """{"data", "contentType", "method": "ai_video" | "slideshow", "note"}."""
    which = provider()
    portrait = orientation == "portrait" or (not orientation and styles.video_style(style).get("portrait", False))
    ai_prompt = f"{prompt}. {styles.video_scene_words(style)}" if style else prompt
    quality = quality if quality in ("high", "standard") else (DEFAULT_QUALITY if DEFAULT_QUALITY in ("high", "standard") else "high")
    note = ""
    if which == "fal":
        try:
            cinematic = await prompt_boost.video_prompt(prompt, styles.video_scene_words(style) if style else "",
                                                        min(8, seconds or 8))
            return {"data": await _fal(cinematic, seconds, portrait), "contentType": "video/mp4",
                    "method": "ai_video"}
        except Exception as exc:
            logger.warning("fal video failed, falling back to the free method: %s", exc)
            note = "The premium video service failed (its credit may be used up), so a free method was used. "
            which = "pollinations" if os.environ.get("POLLINATIONS_API_KEY") else "slideshow"
    if which == "openai":
        return {"data": await _sora(ai_prompt, seconds, portrait, quality), "contentType": "video/mp4", "method": "ai_video"}
    if which == "gemini":
        try:
            return {"data": await _veo(ai_prompt, portrait, quality), "contentType": "video/mp4", "method": "ai_video"}
        except Exception as exc:
            logger.warning("veo video failed, falling back to the free method: %s", exc)
            note = "Google's video service failed (it needs a paid plan), so a free method was used. "
            which = "pollinations" if os.environ.get("POLLINATIONS_API_KEY") else "slideshow"
    if which == "pollinations":
        try:
            return {"data": await _pollinations(ai_prompt, seconds, portrait), "contentType": "video/mp4",
                    "method": "ai_video"}
        except Exception as exc:
            logger.warning("pollinations video failed, making a slideshow instead: %s", exc)
            note += "The AI video service was unavailable (its free daily allowance may be used up). "
    if which in ("pollinations", "slideshow"):
        try:
            data = await slideshow.make_slideshow(prompt, seconds or 12, portrait, scenes, style, captions)
        except slideshow.SlideshowError as exc:
            raise VideoError(str(exc))
        return {"data": data, "contentType": "video/mp4", "method": "slideshow", "note": note}
    raise VideoError("Video generation is turned off")


async def generate_video(prompt: str, seconds: int = 8, orientation: str = "landscape",
                         quality: Optional[str] = None) -> Tuple[bytes, str]:
    out = await generate(prompt, seconds, orientation, quality)
    return out["data"], out["contentType"]
