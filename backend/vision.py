"""Turn pictures into text for models that can't see (e.g. Groq's free gpt-oss).

1. A free vision model on Groq (GROQ_VISION_MODEL, needs only GROQ_API_KEY) describes the
   picture and copies out its text.
2. If that isn't available, Tesseract OCR (installed in the Docker image) reads the text.

Results are cached on the media document, so each picture is read once.
"""
import asyncio
import base64
import io
import logging
import os
from typing import Optional

logger = logging.getLogger("radha.vision")

VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
_MAX_SIDE = 1600
_PROMPT = (
    "Describe this image for someone who cannot see it. First copy out ALL visible text exactly "
    "(keep numbers, tables and line breaks), then describe what the image shows in a few sentences. "
    "For charts, receipts, invoices, forms or screenshots, list every value. Be factual; do not guess."
)


def _shrink(data: bytes) -> bytes:
    """JPEG no larger than _MAX_SIDE px, to stay under the vision API's size limit."""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    img.thumbnail((_MAX_SIDE, _MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def ocr(data: bytes) -> str:
    """Text in an image via Tesseract; empty string when Tesseract isn't installed."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        return pytesseract.image_to_string(img).strip()
    except Exception as exc:  # missing binary, unreadable image
        logger.info("OCR unavailable: %s", str(exc)[:200])
        return ""


async def _describe_with_groq(data: bytes) -> Optional[str]:
    if not os.environ.get("GROQ_API_KEY") or not VISION_MODEL:
        return None
    import litellm
    url = "data:image/jpeg;base64," + base64.b64encode(await asyncio.to_thread(_shrink, data)).decode()
    resp = await litellm.acompletion(
        model=f"groq/{VISION_MODEL}",
        messages=[{"role": "user", "content": [
            {"type": "text", "text": _PROMPT},
            {"type": "image_url", "image_url": {"url": url}},
        ]}],
        max_tokens=900,
        timeout=60,
    )
    text = (resp.choices[0].message.content or "").strip()
    return text or None


async def image_to_text(data: bytes) -> str:
    """Best available text for an image: a vision model's description, else OCR text."""
    try:
        text = await _describe_with_groq(data)
        if text:
            return text
    except Exception as exc:
        logger.warning("Vision model failed, falling back to OCR: %s", str(exc)[:300])
    text = await asyncio.to_thread(ocr, data)
    return f"Text found in the image:\n{text}" if text else ""


async def describe_media(db, doc: dict) -> str:
    """Cached image_to_text for a stored media item."""
    if doc.get("description") is not None:
        return doc["description"]
    import media
    try:
        text = await image_to_text(await media.read_bytes(db, doc))
    except Exception:
        logger.exception("Could not read image %s", doc.get("id"))
        text = ""
    if text:  # don't cache failures: a later turn may succeed
        await db.media.update_one({"id": doc["id"]}, {"$set": {"description": text[:8000]}})
    return text
