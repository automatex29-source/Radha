"""Editing pictures the user uploaded or Krish made.

Two kinds of edits:
- quick edits (free, on the server with Pillow): rotate, flip, crop, black-and-white, brighter, sharper...
- AI edits from an instruction ("change the shirt to red", "put a beach behind her"): OpenAI's image edit with
  OPENAI_API_KEY, else Pollinations' Kontext model with the free POLLINATIONS_API_KEY.
"""
import io
import logging
import os
from typing import List, Optional

import media

logger = logging.getLogger("radha.image_edit")

POLLINATIONS_EDIT_MODEL = os.environ.get("POLLINATIONS_EDIT_MODEL", "kontext")
MAX_SIDE = 4096

QUICK_EDITS = {
    "rotate_left": "turn 90° anticlockwise", "rotate_right": "turn 90° clockwise", "flip": "upside down",
    "mirror": "mirror left-right", "black_and_white": "black and white", "sepia": "old-photo brown tone",
    "brighter": "brighter", "darker": "darker", "more_contrast": "more contrast", "more_color": "more colourful",
    "sharpen": "sharper", "blur": "soft blur", "square": "crop to a square (centre)",
    "portrait": "crop to 4:5 portrait (centre)", "landscape": "crop to 16:9 (centre)", "smaller": "half the size",
}


def ai_edit_available() -> bool:
    return media.openai_configured() or bool(os.environ.get("POLLINATIONS_API_KEY"))


def _center_crop(img, ratio: float):
    w, h = img.size
    if w / h > ratio:
        nw = int(h * ratio)
        return img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    nh = int(w / ratio)
    return img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))


def quick_edit(data: bytes, edits: List[str]) -> bytes:
    """Apply simple edits in order and return PNG (JPEG for photos without transparency) bytes."""
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    unknown = [e for e in edits if e not in QUICK_EDITS]
    if unknown:
        raise ValueError(f"Unknown quick edit {unknown[0]!r}. Use: {', '.join(QUICK_EDITS)}")
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    for e in edits:
        if e == "rotate_left":
            img = img.transpose(Image.Transpose.ROTATE_90)
        elif e == "rotate_right":
            img = img.transpose(Image.Transpose.ROTATE_270)
        elif e == "flip":
            img = ImageOps.flip(img)
        elif e == "mirror":
            img = ImageOps.mirror(img)
        elif e == "black_and_white":
            img = ImageOps.grayscale(img).convert("RGB")
        elif e == "sepia":
            img = ImageOps.colorize(ImageOps.grayscale(img), "#2e1f0f", "#f3e3c3")
        elif e == "brighter":
            img = ImageEnhance.Brightness(img).enhance(1.25)
        elif e == "darker":
            img = ImageEnhance.Brightness(img).enhance(0.78)
        elif e == "more_contrast":
            img = ImageEnhance.Contrast(img).enhance(1.3)
        elif e == "more_color":
            img = ImageEnhance.Color(img).enhance(1.35)
        elif e == "sharpen":
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
        elif e == "blur":
            img = img.filter(ImageFilter.GaussianBlur(3))
        elif e == "square":
            img = _center_crop(img, 1.0)
        elif e == "portrait":
            img = _center_crop(img, 4 / 5)
        elif e == "landscape":
            img = _center_crop(img, 16 / 9)
        elif e == "smaller":
            img = img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    if img.mode == "RGBA":
        img.save(out, "PNG", optimize=True)
    else:
        img.save(out, "JPEG", quality=92)
    return out.getvalue()


def _as_png(data: bytes) -> bytes:
    """Edit APIs want a PNG under a size limit."""
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.thumbnail((1536, 1536))
    out = io.BytesIO()
    img.convert("RGBA").save(out, "PNG")
    return out.getvalue()


async def ai_edit(data: bytes, instruction: str) -> bytes:
    if not ai_edit_available():
        raise media.MediaUnavailable(
            "AI photo edits need the free POLLINATIONS_API_KEY (from enter.pollinations.ai) or OPENAI_API_KEY on the "
            "server. Quick edits (rotate, crop, black and white, brighter...) work without a key.")
    png = _as_png(data)
    errors = []
    if media.openai_configured():
        try:
            resp = await media._client().images.edit(model=media.IMAGE_MODEL, image=("image.png", png, "image/png"),
                                                      prompt=instruction[:3000])
            return await _result_bytes(resp)
        except Exception as exc:
            logger.warning("OpenAI image edit failed: %s", exc)
            errors.append(f"openai: {str(exc)[:160]}")
    if os.environ.get("POLLINATIONS_API_KEY"):
        try:
            import httpx

            async with httpx.AsyncClient(timeout=media.IMAGE_TIMEOUT, follow_redirects=True) as client:
                resp = await client.post(
                    f"{media.POLLINATIONS_BASE}/v1/images/edits",
                    headers={"Authorization": f"Bearer {os.environ['POLLINATIONS_API_KEY']}", "User-Agent": "KrishAI/1.0"},
                    data={"prompt": instruction[:3000], "model": POLLINATIONS_EDIT_MODEL},
                    files={"image": ("image.png", png, "image/png")})
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            if media.image_type(resp.content):
                return resp.content
            from types import SimpleNamespace
            body = resp.json()
            items = [SimpleNamespace(**i) for i in body.get("data") or []]
            return await _result_bytes(SimpleNamespace(data=items))
        except Exception as exc:
            logger.warning("Pollinations image edit failed: %s", exc)
            errors.append(f"pollinations: {str(exc)[:160]}")
    raise RuntimeError("The photo edit failed. " + "; ".join(errors))


async def _result_bytes(resp) -> bytes:
    import base64

    if not resp.data:
        raise RuntimeError("no image returned")
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        return base64.b64decode(item.b64_json)
    import httpx
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(item.url)
        r.raise_for_status()
        return r.content


async def latest_image(db, user_id: str, conversation_id: Optional[str], name: Optional[str] = None) -> Optional[dict]:
    """The picture to edit: one with this file name, else the newest picture in the chat."""
    query = {"userId": user_id, "conversationId": conversation_id, "contentType": {"$regex": "^image/(png|jpeg|webp)"}}
    if name:
        named = await db.media.find(dict(query, name=name), {"data": 0}).sort("createdAt", -1).to_list(1)
        if named:
            return named[0]
    docs = await db.media.find(query, {"data": 0}).sort("createdAt", -1).to_list(1)
    return docs[0] if docs else None
