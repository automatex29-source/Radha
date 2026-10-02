"""AI pictures for the sites Krish AI builds.

The AI writes image links like https://krish-image.invalid/chocolate-truffle-cake-studio-photo.jpg?w=800&h=600
(the .invalid host never resolves). They are rewritten (see rewrite()) to this server's /api/site-image, which
makes the picture once with the free image providers (Pollinations), crops it to the size asked for, and keeps
it, so every later visitor gets it instantly. If no picture can be made, the visitor is sent to a keyword photo.

Public on purpose (site visitors and sandboxed previews have no login), so it is limited: only free providers,
new pictures per visitor per hour and per day are capped, and the cache keeps the newest MAX_CACHED pictures.
"""
import asyncio
import io
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse, Response

import media

logger = logging.getLogger("radha.site_images")
router = APIRouter(prefix="/api")
db = None

HOST = "krish-image.invalid"
_LINK_RE = re.compile(r"https?://krish-image\.invalid/([^\s\"'()<>?#]+?)(?:\.(?:jpe?g|png|webp))?(?:\?([^\s\"'()<>#]*))?(?=[\s\"'()<>#]|$)")
MAX_CACHED = int(os.environ.get("SITE_IMAGE_CACHE", "800"))
PER_IP_HOUR = int(os.environ.get("SITE_IMAGE_PER_IP_HOUR", "40"))
PER_DAY = int(os.environ.get("SITE_IMAGE_PER_DAY", "600"))
_recent: Dict[str, list] = {}
_day = {"date": "", "count": 0}
_inflight: Dict[str, asyncio.Future] = {}


def init(database):
    global db
    db = database


async def ensure_indexes():
    await db.site_images.create_index("key", unique=True)
    await db.site_images.create_index("createdAt")


def _size(w: Optional[int], h: Optional[int]) -> tuple:
    def snap(v, default):
        return max(64, min(1600, int((v or default) / 8 + 0.5) * 8))  # same rounding as the frontend
    return snap(w, 800), snap(h, 600)


def clean_prompt(text: str) -> str:
    words = re.sub(r"[-_+]+|%20", " ", text or "")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s,.'&]", " ", words)).strip()[:200]


def rewrite(text: str, origin: str = "") -> str:
    """Point the AI's krish-image.invalid links at this server's /api/site-image."""
    def sub(m):
        params = dict(p.split("=", 1) for p in (m.group(2) or "").split("&") if "=" in p)
        w, h = _size(_int(params.get("w")), _int(params.get("h")))
        return f"{origin}/api/site-image?prompt={quote(clean_prompt(m.group(1)))}&w={w}&h={h}"
    return _LINK_RE.sub(sub, text) if HOST in (text or "") else text


def _int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _fallback(prompt: str, w: int, h: int) -> RedirectResponse:
    words = [x for x in re.findall(r"[a-zA-Z]{3,}", prompt) if x.lower() not in _STOP][:2] or ["abstract"]
    lock = sum(map(ord, prompt)) % 1000
    return RedirectResponse(f"https://loremflickr.com/{w}/{h}/{','.join(words).lower()}?lock={lock}", status_code=302,
                            headers={"Cache-Control": "public, max-age=300"})


_STOP = {"photo", "photograph", "image", "picture", "studio", "the", "and", "with", "for", "high", "quality", "close",
         "shot", "view", "style", "realistic", "professional", "beautiful", "modern", "top", "lighting", "background"}


def _allowed(ip: str) -> bool:
    now = time.time()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _day["date"] != today:
        _day.update(date=today, count=0)
    hits = [t for t in _recent.get(ip, []) if now - t < 3600]
    if len(hits) >= PER_IP_HOUR or _day["count"] >= PER_DAY:
        _recent[ip] = hits
        return False
    _recent[ip] = hits + [now]
    _day["count"] += 1
    if len(_recent) > 5000:
        _recent.clear()
    return True


def _crop(data: bytes, w: int, h: int) -> bytes:
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data)).convert("RGB")
    img = ImageOps.fit(img, (w, h), method=Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=78, method=4)
    return out.getvalue()


async def _make(prompt: str, w: int, h: int) -> bytes:
    """A picture from the free providers only (never a paid key: this endpoint is public)."""
    size = "1536x1024" if w > h * 1.2 else "1024x1536" if h > w * 1.2 else "1024x1024"
    full = f"{prompt}, high quality professional photograph, natural light, sharp focus"
    keyed = bool(os.environ.get("POLLINATIONS_API_KEY"))
    errors = []
    for legacy in ((False, True) if keyed else (True,)):
        try:
            return _crop(await media._pollinations(full, size, legacy=legacy), w, h)
        except Exception as exc:
            errors.append(str(exc)[:160])
    raise RuntimeError("; ".join(errors))


@router.get("/site-image")
async def site_image(request: Request, prompt: str = Query("", max_length=400), w: Optional[int] = None,
                     h: Optional[int] = None):
    prompt = clean_prompt(prompt) or "abstract colorful background"
    w, h = _size(w, h)
    key = f"{prompt.lower()}|{w}x{h}"
    headers = {"Cache-Control": "public, max-age=2592000, immutable", "Access-Control-Allow-Origin": "*",
               "Cross-Origin-Resource-Policy": "cross-origin"}
    doc = await db.site_images.find_one({"key": key}, {"data": 1})
    if doc:
        return Response(bytes(doc["data"]), media_type="image/webp", headers=headers)
    pending = _inflight.get(key)
    if pending is None:
        if not _allowed(request.client.host if request.client else "?"):
            return _fallback(prompt, w, h)
        fut = asyncio.get_running_loop().create_future()
        _inflight[key] = fut
        try:
            data = await _make(prompt, w, h)
            await db.site_images.update_one({"key": key}, {"$set": {"data": data, "createdAt": datetime.now(timezone.utc)}},
                                            upsert=True)
            await _trim()
            fut.set_result(data)
        except Exception as exc:
            logger.warning("site image failed for %r: %s", prompt, exc)
            fut.set_result(None)
        finally:
            _inflight.pop(key, None)
        data = fut.result()
    else:
        data = await pending
    if not data:
        return _fallback(prompt, w, h)
    return Response(data, media_type="image/webp", headers=headers)


async def _trim():
    extra = await db.site_images.count_documents({}) - MAX_CACHED
    if extra > 0:
        old = await db.site_images.find({}, {"_id": 1}).sort("createdAt", 1).limit(extra).to_list(extra)
        await db.site_images.delete_many({"_id": {"$in": [d["_id"] for d in old]}})
