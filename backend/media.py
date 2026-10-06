"""Media: image generation, speech-to-text, text-to-speech, and the media store.

Transcription uses the OpenAI API (OPENAI_API_KEY, optional OPENAI_BASE_URL
for an OpenAI-compatible gateway) or, without it, Groq's free Whisper
(GROQ_API_KEY). Server speech uses OpenAI; without it the browser speaks
replies itself. Images use OpenAI when that
key is set and free providers (Pollinations, Hugging Face) otherwise. Media bytes live in the
`media` collection, owned per user, and are served by GET /api/media/{id}.
"""
import base64
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import fal_api

logger = logging.getLogger("radha.media")

IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")
STT_MODEL = os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = os.environ.get("TTS_MODEL", "gpt-4o-mini-tts")
GROQ_STT_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
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


# ------------------------------------------------------------------ images
# Free providers, used when there's no OpenAI key (or IMAGE_PROVIDER picks one):
#   pollinations: gen.pollinations.ai; POLLINATIONS_API_KEY (free sk_ key from enter.pollinations.ai)
#                 lifts the anonymous rate limit. Without a key we try the keyless endpoints.
#   huggingface:  FLUX.1-schnell on HF inference with a free HF_TOKEN (small monthly allowance).
POLLINATIONS_BASE = os.environ.get("POLLINATIONS_BASE_URL", "https://gen.pollinations.ai").rstrip("/")
# Best first: Seedream 4.0 draws far more detailed, photo-like pictures (and real words on signs) than the fast
# Z-Image Turbo. It spends the key's free daily Pollen; when that runs out or the model is busy, the next one answers.
POLLINATIONS_IMAGE_MODELS = [m.strip() for m in (os.environ.get("POLLINATIONS_IMAGE_MODELS")
                                                 or os.environ.get("POLLINATIONS_IMAGE_MODEL")
                                                 or "bytedance/seedream-4.0,tongyi-mai/z-image-turbo").split(",")
                             if m.strip()]
# A better model that is slow today shouldn't keep the person waiting: it gets this long before the next one tries.
BEST_IMAGE_TIMEOUT = float(os.environ.get("BEST_IMAGE_TIMEOUT_SECONDS", "60"))
LEGACY_POLLINATIONS = "https://image.pollinations.ai/prompt"
HF_IMAGE_MODEL = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
IMAGE_TIMEOUT = float(os.environ.get("IMAGE_TIMEOUT_SECONDS", "150"))


class ImageError(Exception):
    pass


def image_available() -> bool:
    return os.environ.get("IMAGE_PROVIDER", "").lower() not in ("off", "0", "none")


def image_key_configured() -> bool:
    return any(os.environ.get(k) for k in ("FAL_KEY", "OPENAI_API_KEY", "POLLINATIONS_API_KEY", "HF_TOKEN"))


def spells_well() -> bool:
    """True when a premium image model (fal Nano Banana Pro or OpenAI) is set up; those can write real words."""
    return fal_api.configured() or openai_configured()


_ASKS_TEXT = re.compile(r'["\u201c]|\b(text|texts|word|words|wording|title|titled|headline|caption|captions|saying|'
                        r'says|written|write|writing|letters?|lettering|typography|font|quote|slogan|tagline|'
                        r'label(?:ed|led)?|name on)\b', re.I)
_SCREENS = re.compile(r"\b(phones?|smartphones?|mobiles?|screens?|laptops?|monitors?|tablets?|computers?|"
                      r"dashboards?|apps?|websites?|tvs?|televisions?|displays?|devices?)\b", re.I)
_SURFACES = re.compile(r"\b(signs?|signboards?|billboards?|banners?|posters?|books?|newspapers?|documents?|"
                       r"papers?|whiteboards?|charts?|graphs?|labels?|menus?|packaging|packages?|boxes?|bottles?|"
                       r"cans?|storefronts?|shops?|t-shirts?|shirts?|cards?|notebooks?)\b", re.I)
_NEGATIVES = re.compile(r"[,.]?\s*\b(no|without)\s+(text|words|letters|logos?|watermarks?|writing|captions?|"
                        r"borders?)\b", re.I)


def asks_for_text(prompt: str) -> bool:
    """Did the person ask for words in the picture (a title, a slogan, something in quotes)?"""
    return bool(_ASKS_TEXT.search(prompt or ""))


def text_free(prompt: str) -> str:
    """Steer a free image model to a picture with no writing at all.

    Free models can't spell, so any text they draw comes out as gibberish (a phone showing "JON2Video").
    Diffusion models also tend to draw whatever words the prompt names, so instead of "no text" this
    drops quoted words and says what screens, signs and labels should show: abstract color and blank space.
    """
    p = re.sub(r'["\u201c][^"\u201d]{0,120}["\u201d]', "", prompt or "")
    p = _NEGATIVES.sub("", p)
    p = re.sub(r"\s{2,}", " ", p).strip(" .,;")
    extra = []
    if _SCREENS.search(p):
        extra.append("every screen glows with soft abstract color gradients and simple rounded shapes only")
    if _SURFACES.search(p):
        extra.append("signs, pages, packaging and labels are plain, smooth and blank")
    extra.append("pure visual storytelling with clean unmarked surfaces")
    return f"{p}. {', '.join(extra)}"


def image_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _image_providers() -> list:
    explicit = os.environ.get("IMAGE_PROVIDER", "").lower()
    if explicit in ("fal", "openai", "pollinations", "huggingface"):
        order = [explicit]
    else:
        order = []
        if fal_api.configured():  # premium: Nano Banana Pro via fal.ai
            order.append("fal")
        if openai_configured():
            order.append("openai")
        if os.environ.get("POLLINATIONS_API_KEY"):
            order.append("pollinations")
        if os.environ.get("HF_TOKEN"):
            order.append("huggingface")
    # gen.pollinations.ai needs a key now, so without one only the old keyless endpoint is worth trying.
    for free in (("pollinations",) if os.environ.get("POLLINATIONS_API_KEY") else ()) + ("pollinations_legacy",):
        if free not in order:
            order.append(free)
    return order


def _dims(size: str) -> tuple:
    w, _, h = (size if size in IMAGE_SIZES and size != "auto" else "1024x1024").partition("x")
    return int(w), int(h)


def _check_image(resp, size: Optional[str] = None) -> bytes:
    if resp.status_code >= 400:
        raise ImageError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    if not image_type(resp.content):
        raise ImageError(f"not an image ({resp.headers.get('content-type', '?')})")
    if size:
        # Rate-limited or keyless requests can come back as a small "pollinations.ai" banner instead of the
        # picture; a real result has the shape we asked for.
        from PIL import Image
        import io

        got_w, got_h = Image.open(io.BytesIO(resp.content)).size
        want_w, want_h = _dims(size)
        if min(got_w, got_h) < 256 or abs(got_w / got_h - want_w / want_h) > 0.15:
            raise ImageError(f"got a {got_w}x{got_h} placeholder instead of a {want_w}x{want_h} picture")
    return resp.content


async def _pollinations(prompt: str, size: str, legacy: bool = False, seed: Optional[int] = None) -> bytes:
    import random
    from urllib.parse import quote

    import httpx

    w, h = _dims(size)
    params = {"width": w, "height": h, "seed": seed or random.randint(1, 2_000_000_000), "nologo": "true"}
    headers = {"User-Agent": "KrishAI/1.0"}
    if legacy:
        url = f"{LEGACY_POLLINATIONS}/{quote(prompt[:1500], safe='')}"
        # No "enhance": it has a model rewrite the prompt first, which adds seconds; our prompts are already full.
        params.update({"model": "flux", "private": "true"})
        async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT, follow_redirects=True) as client:
            return _check_image(await client.get(url, params=params, headers=headers), size)
    url = f"{POLLINATIONS_BASE}/image/{quote(prompt[:1500], safe='')}"
    if os.environ.get("POLLINATIONS_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['POLLINATIONS_API_KEY']}"
    errors = []
    for i, model in enumerate(POLLINATIONS_IMAGE_MODELS):
        last = i == len(POLLINATIONS_IMAGE_MODELS) - 1
        try:
            async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT if last else BEST_IMAGE_TIMEOUT,
                                         follow_redirects=True) as client:
                return _check_image(await client.get(url, params={**params, "model": model}, headers=headers), size)
        except Exception as exc:
            if last:
                raise ImageError("; ".join(errors + [f"{model}: {str(exc)[:160] or type(exc).__name__}"]))
            logger.info("pollinations model %s failed, trying the next: %s", model, str(exc)[:200])
            errors.append(f"{model}: {str(exc)[:120] or type(exc).__name__}")


async def _huggingface(prompt: str, size: str) -> bytes:
    import httpx

    w, h = _dims(size)
    async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT) as client:
        resp = await client.post(
            f"https://router.huggingface.co/hf-inference/models/{HF_IMAGE_MODEL}",
            headers={"Authorization": f"Bearer {os.environ.get('HF_TOKEN', '')}", "Accept": "image/png"},
            json={"inputs": prompt, "parameters": {"width": w, "height": h}})
        return _check_image(resp)


async def generate_image(prompt: str, size: str = "1024x1024", quality: Optional[str] = None,
                         seed: Optional[int] = None) -> bytes:
    """Best configured provider first, then the free ones. Returns PNG/JPEG/WebP bytes (see image_type)."""
    errors = []
    for which in _image_providers():
        try:
            if which == "fal":
                return await _fal_image(prompt, size, seed)
            if which == "openai":
                return await _openai_image(prompt, size, quality)
            if which == "huggingface":
                return await _huggingface(prompt, size)
            return await _pollinations(prompt, size, legacy=which == "pollinations_legacy", seed=seed)
        except Exception as exc:  # fall through to the next provider
            logger.warning("image provider %s failed: %s", which, exc)
            errors.append(f"{which}: {str(exc)[:160]}")
    hint = "" if image_key_configured() else (" Add a free POLLINATIONS_API_KEY (from enter.pollinations.ai) "
                                              "on the server to turn on images.")
    raise ImageError("Image generation failed. " + "; ".join(errors) + hint)


FAL_IMAGE_MODEL = os.environ.get("FAL_IMAGE_MODEL", "fal-ai/nano-banana-pro")
FAL_IMAGE_RESOLUTION = os.environ.get("FAL_IMAGE_RESOLUTION", "1K")


async def _fal_image(prompt: str, size: str, seed: Optional[int] = None) -> bytes:
    w, h = _dims(size)
    ratio = "1:1" if w == h else ("3:2" if w > h else "2:3")
    payload = {"prompt": prompt, "num_images": 1, "aspect_ratio": ratio, "resolution": FAL_IMAGE_RESOLUTION}
    if seed:
        payload["seed"] = seed
    result = await fal_api.run(FAL_IMAGE_MODEL, payload, timeout=180)
    images = result.get("images") or []
    if not images or not images[0].get("url"):
        raise ImageError(f"fal returned no image: {str(result)[:200]}")
    data = await fal_api.download(images[0]["url"])
    if not image_type(data):
        raise ImageError("fal returned something that is not an image")
    return data


async def _openai_image(prompt: str, size: str = "1024x1024", quality: Optional[str] = None) -> bytes:
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


def transcription_available() -> bool:
    return openai_configured() or bool(os.environ.get("GROQ_API_KEY"))


async def transcribe(data: bytes, filename: str, language: Optional[str] = None) -> str:
    """Speech to text. `language` is an optional ISO-639-1 hint (e.g. "hi", "en")."""
    return (await transcribe_detect(data, filename, language))[0]


# Whisper reports the language it heard by English name.
WHISPER_NAMES = {"english": "en", "hindi": "hi", "bengali": "bn", "marathi": "mr", "gujarati": "gu",
                 "tamil": "ta", "telugu": "te", "kannada": "kn", "malayalam": "ml", "urdu": "ur",
                 "punjabi": "pa", "panjabi": "pa", "spanish": "es", "french": "fr", "german": "de", "arabic": "ar"}


async def transcribe_detect(data: bytes, filename: str, language: Optional[str] = None) -> tuple:
    """Speech to text plus the language that was spoken: (text, ISO-639-1 code or None)."""
    extra = {"language": language} if language else {}
    if openai_configured():
        resp = await _client().audio.transcriptions.create(model=STT_MODEL, file=(filename, data), **extra)
        text, heard = resp.text, None
    else:
        if not os.environ.get("GROQ_API_KEY"):
            raise MediaUnavailable("Set GROQ_API_KEY (free) or OPENAI_API_KEY on the backend to enable voice input.")
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.environ["GROQ_API_KEY"], base_url=GROQ_BASE_URL)
        resp = await client.audio.transcriptions.create(model=GROQ_STT_MODEL, file=(filename, data),
                                                        response_format="verbose_json", **extra)
        text, heard = resp.text, getattr(resp, "language", None)
    code = language or WHISPER_NAMES.get((heard or "").strip().lower()) or (heard if heard in WHISPER_NAMES.values() else None)
    # The script it was written in is the surest sign (Whisper can say "urdu" for Hindi and vice versa).
    return text, script_language(text) or code


# Free natural voices (Microsoft Edge's online neural voices, no key) when there's no OpenAI key.
# Voice languages: ISO-639-1 code -> Edge neural voice. Whisper understands all of them.
EDGE_VOICES = {
    "hi": os.environ.get("EDGE_VOICE_HI", "hi-IN-SwaraNeural"),
    "en": os.environ.get("EDGE_VOICE_EN", "en-IN-NeerjaNeural"),
    "bn": "bn-IN-TanishaaNeural",
    "mr": "mr-IN-AarohiNeural",
    "gu": "gu-IN-DhwaniNeural",
    "ta": "ta-IN-PallaviNeural",
    "te": "te-IN-ShrutiNeural",
    "kn": "kn-IN-SapnaNeural",
    "ml": "ml-IN-SobhanaNeural",
    "ur": "ur-IN-GulNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "ar": "ar-SA-ZariyahNeural",
    "pa": "pa-IN-OjasNeural",
}
VOICE_LANGUAGES = tuple(EDGE_VOICES)

# In auto mode, the script a reply is written in picks the voice.
_SCRIPTS = [("pa", r"[\u0A00-\u0A7F]"), ("bn", r"[\u0980-\u09FF]"), ("gu", r"[\u0A80-\u0AFF]"), ("ta", r"[\u0B80-\u0BFF]"),
            ("te", r"[\u0C00-\u0C7F]"), ("kn", r"[\u0C80-\u0CFF]"), ("ml", r"[\u0D00-\u0D7F]"),
            ("ur", r"[\u0600-\u06FF]"), ("hi", r"[\u0900-\u097F]")]

def script_language(text: str) -> Optional[str]:
    """The language an Indian or Arabic script points to; None for Latin text."""
    for code, pattern in _SCRIPTS:
        if re.search(pattern, text or ""):
            return code
    return None


# Whisper sometimes "hears" these stock phrases in silence or background noise.
_PHANTOM = {"thank you.", "thank you", "thanks for watching!", "thanks for watching.", "thank you for watching.",
            "you", ".", "bye.", "धन्यवाद।", "धन्यवाद", "शुक्रिया", "subscribe", "please subscribe."}


def clean_transcript(text: str) -> str:
    text = (text or "").strip()
    return "" if text.lower() in _PHANTOM else text


def edge_available() -> bool:
    if os.environ.get("EDGE_TTS", "1") == "0":
        return False
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def speech_available() -> bool:
    return openai_configured() or edge_available()


def edge_voice(text: str, lang: Optional[str] = None) -> str:
    """The chosen language's voice; in auto mode, the voice for the script the text is written in."""
    if lang in EDGE_VOICES:
        return EDGE_VOICES[lang]
    return EDGE_VOICES.get(script_language(text) or "en", EDGE_VOICES["en"])


async def _edge_speak(text: str, lang: Optional[str]) -> bytes:
    import edge_tts
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text[:MAX_TTS_CHARS], edge_voice(text, lang)).stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    if not audio:
        raise RuntimeError("The free voice service returned no audio")
    return bytes(audio)


async def speak(text: str, voice: str = "nova", lang: Optional[str] = None) -> bytes:
    if not openai_configured():
        if not edge_available():
            raise MediaUnavailable("Set OPENAI_API_KEY on the backend for server voices.")
        return await _edge_speak(text, lang)
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
