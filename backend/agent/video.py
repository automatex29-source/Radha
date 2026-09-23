"""Video generation: OpenAI Sora (REST) or Google Veo (google-genai).

Provider: VIDEO_PROVIDER=openai|gemini, otherwise whichever key is set
(OPENAI_API_KEY first). Generation is asynchronous on both sides, so we submit
a job and poll until it finishes (VIDEO_TIMEOUT_SECONDS, default 10 minutes).
"""
import asyncio
import os
import time
from typing import Optional, Tuple

import httpx

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


class VideoError(Exception):
    pass


def provider() -> Optional[str]:
    explicit = os.environ.get("VIDEO_PROVIDER")
    if explicit in ("openai", "gemini"):
        return explicit
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
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


async def generate_video(prompt: str, seconds: int = 8, orientation: str = "landscape",
                         quality: Optional[str] = None) -> Tuple[bytes, str]:
    which = provider()
    portrait = orientation == "portrait"
    quality = quality if quality in ("high", "standard") else (DEFAULT_QUALITY if DEFAULT_QUALITY in ("high", "standard") else "high")
    if which == "openai":
        return await _sora(prompt, seconds, portrait, quality), "video/mp4"
    if which == "gemini":
        return await _veo(prompt, portrait, quality), "video/mp4"
    raise VideoError("Set OPENAI_API_KEY or GEMINI_API_KEY to enable video generation")
