"""Media: image generation, speech-to-text, text-to-speech, and the media store.

Generation/transcription/speech use the OpenAI API (OPENAI_API_KEY, optional
OPENAI_BASE_URL for an OpenAI-compatible gateway). Media bytes live in the
`media` collection, owned per user, and are served by GET /api/media/{id}.
"""
import base64
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")
STT_MODEL = os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = os.environ.get("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"]
IMAGE_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
MAX_MEDIA_BYTES = 250 * 1024 * 1024  # high-quality video can be large
INLINE_LIMIT = 8 * 1024 * 1024  # larger files are split into chunks (MongoDB caps documents at 16MB)
CHUNK_BYTES = 4 * 1024 * 1024
IMAGE_QUALITY = os.environ.get("IMAGE_QUALITY", "high")  # low | medium | high
MAX_TTS_CHARS = 4000


class MediaUnavailable(Exception):
    """Raised when the provider key for a media feature isn't configured."""


def openai_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _client():
    if not openai_configured():
        raise MediaUnavailable("Set OPENAI_API_KEY on the backend to enable images and voice.")
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ.get("OPENAI_BASE_URL") or None)


async def generate_image(prompt: str, size: str = "1024x1024", quality: Optional[str] = None) -> bytes:
    if size not in IMAGE_SIZES:
        size = "1024x1024"
    kwargs = {"model": IMAGE_MODEL, "prompt": prompt, "size": size, "n": 1}
    if IMAGE_MODEL.startswith("gpt-image"):
        kwargs["quality"] = quality if quality in ("low", "medium", "high") else IMAGE_QUALITY
    resp = await _client().images.generate(**kwargs)
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        return base64.b64decode(item.b64_json)
    # Some models return a URL instead of inline bytes.
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(item.url)
        r.raise_for_status()
        return r.content


async def transcribe(data: bytes, filename: str) -> str:
    resp = await _client().audio.transcriptions.create(model=STT_MODEL, file=(filename, data))
    return resp.text


async def speak(text: str, voice: str = "nova") -> bytes:
    if voice not in TTS_VOICES:
        voice = "nova"
    resp = await _client().audio.speech.create(model=TTS_MODEL, voice=voice, input=text[:MAX_TTS_CHARS], response_format="mp3")
    return resp.content


# ------------------------------------------------------------------ store
async def save_media(db, user_id: str, data: bytes, content_type: str, kind: str,
                     name: Optional[str] = None, conversation_id: Optional[str] = None) -> dict:
    if len(data) > MAX_MEDIA_BYTES:
        raise ValueError(f"Media too large (max {MAX_MEDIA_BYTES // (1024 * 1024)}MB)")
    media_id = str(uuid.uuid4())
    chunks = 0
    if len(data) > INLINE_LIMIT:
        pieces = [data[i:i + CHUNK_BYTES] for i in range(0, len(data), CHUNK_BYTES)]
        await db.media_chunks.insert_many([{"mediaId": media_id, "n": n, "data": piece} for n, piece in enumerate(pieces)])
        chunks = len(pieces)
    doc = {
        "id": media_id,
        "userId": user_id,
        "conversationId": conversation_id,
        "kind": kind,  # upload | generated | code_output
        "name": name,
        "contentType": content_type,
        "size": len(data),
        "data": None if chunks else data,
        "chunks": chunks,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.media.insert_one(doc)
    return public_media(doc)


def public_media(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "kind": doc.get("kind"),
        "name": doc.get("name"),
        "contentType": doc.get("contentType"),
        "size": doc.get("size"),
        "url": f"/api/media/{doc['id']}",
    }


async def load_media(db, user_id: str, media_id: str) -> Optional[dict]:
    """Metadata only; read the bytes with read_bytes()."""
    return await db.media.find_one({"id": media_id, "userId": user_id}, {"data": 0})


async def read_bytes(db, doc: dict, start: int = 0, end: Optional[int] = None) -> bytes:
    """Bytes [start, end] (inclusive) of a media item, reading only the chunks needed."""
    size = doc.get("size") or 0
    end = size - 1 if end is None else min(end, size - 1)
    if end < start:
        return b""
    if not doc.get("chunks"):
        full = await db.media.find_one({"id": doc["id"]}, {"data": 1})
        return bytes(full["data"])[start:end + 1]
    first, last = start // CHUNK_BYTES, end // CHUNK_BYTES
    cursor = db.media_chunks.find({"mediaId": doc["id"], "n": {"$gte": first, "$lte": last}}).sort("n", 1)
    blob = b"".join([bytes(c["data"]) async for c in cursor])
    offset = start - first * CHUNK_BYTES
    return blob[offset:offset + (end - start + 1)]


async def delete_media(db, query: dict):
    ids = [d["id"] async for d in db.media.find(query, {"id": 1})]
    if ids:
        await db.media_chunks.delete_many({"mediaId": {"$in": ids}})
        await db.media.delete_many({"id": {"$in": ids}})


async def data_url(db, doc: dict) -> str:
    data = await read_bytes(db, doc)
    return f"data:{doc['contentType']};base64,{base64.b64encode(data).decode()}"
