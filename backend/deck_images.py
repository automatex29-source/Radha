"""Pictures for Decks: AI-made images that match each slide, or stock photos ranked by relevance.

AI images go through media.generate_image (OpenAI, Pollinations or Hugging Face,
whichever the server has; the keyless Pollinations endpoint otherwise) and are
stored in the media collection, so slides point at /api/media/<id>.
Stock photos come from Pexels or Unsplash when a key is set, otherwise from
Openverse (free, no key), filtered to large landscape photos and ranked by how
well their title and tags match the search words.
"""
import io
import logging
import os
import re
from typing import List, Optional
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger("radha.decks")
UA = {"User-Agent": "KrishAI/1.0 (presentation builder)"}
MEDIA_URL = re.compile(r"^/api/media/([\w-]{8,64})$")
AI_STYLE = ("professional editorial photograph, natural light, sharp focus, rich color, high detail, "
            "clean composition with space around the subject, 16:9")
_cache: dict = {}
_STOP = {"a", "an", "the", "of", "and", "or", "for", "to", "in", "on", "with", "at", "by", "from", "is", "are",
         "how", "why", "what", "your", "our", "vs", "into"}


def enabled() -> bool:
    return os.environ.get("DECK_IMAGES", "1") != "0"


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in _STOP}


def score(query: str, item: dict) -> float:
    """Relevance first (query words found in the title/tags), then size."""
    want = _words(query)
    have = _words(item.get("_text", ""))
    overlap = len(want & have) / max(1, len(want))
    width = item.get("_width") or 1200
    bonus = {"stocksnap": 0.25, "rawpixel": 0.2, "wikimedia": 0.05}.get(item.get("_source", ""), 0)
    return overlap * 2 + min(width, 4000) / 4000 + bonus


async def _openverse(client: httpx.AsyncClient, query: str, large: bool) -> List[dict]:
    url = (f"https://api.openverse.org/v1/images/?q={quote_plus(query)}&page_size=30&aspect_ratio=wide"
           f"&mature=false&category=photograph{'&size=large' if large else ''}")
    r = await client.get(url)
    r.raise_for_status()
    out = []
    for p in r.json().get("results", []):
        link = p.get("url") or ""
        width = p.get("width") or 0
        if not link.startswith("https://") or not re.search(r"\.(jpe?g|png|webp)(\?|$)", link, re.I):
            continue
        if width and width < 1000:
            continue
        who = p.get("creator") or "unknown"
        lic = (p.get("license") or "").upper()
        tags = " ".join(t.get("name", "") for t in (p.get("tags") or []) if isinstance(t, dict))
        out.append({"url": link, "thumb": p.get("thumbnail") or link,
                    "credit": f"Photo by {who} ({'CC ' + lic if lic and lic != 'CC0' else lic or 'CC'})",
                    "link": p.get("foreign_landing_url") or "",
                    "_text": f"{p.get('title', '')} {tags}", "_width": width, "_source": p.get("source", "")})
    return out


async def search(query: str) -> List[dict]:
    """Up to ~12 landscape photos for the words, best match first."""
    query = (query or "").strip()[:100]
    if not query or not enabled():
        return []
    if query in _cache:
        return _cache[query]
    results: List[dict] = []
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=UA) as client:
            if os.environ.get("PEXELS_API_KEY"):
                r = await client.get(f"https://api.pexels.com/v1/search?query={quote_plus(query)}"
                                     "&orientation=landscape&size=large&per_page=15",
                                     headers={"Authorization": os.environ["PEXELS_API_KEY"]})
                r.raise_for_status()
                results = [{"url": p["src"]["large2x"], "thumb": p["src"]["medium"],
                            "credit": f"Photo by {p.get('photographer', '')} on Pexels", "link": p.get("url", "")}
                           for p in r.json().get("photos", [])]
            elif os.environ.get("UNSPLASH_ACCESS_KEY"):
                r = await client.get(f"https://api.unsplash.com/search/photos?query={quote_plus(query)}"
                                     "&orientation=landscape&per_page=15&content_filter=high",
                                     headers={"Authorization": f"Client-ID {os.environ['UNSPLASH_ACCESS_KEY']}"})
                r.raise_for_status()
                results = [{"url": p["urls"]["regular"], "thumb": p["urls"]["small"],
                            "credit": f"Photo by {p['user']['name']} on Unsplash", "link": p["links"]["html"]}
                           for p in r.json().get("results", [])]
            else:
                results = await _openverse(client, query, large=True)
                if len(results) < 4:
                    seen = {x["url"] for x in results}
                    results += [x for x in await _openverse(client, query, large=False) if x["url"] not in seen]
                results.sort(key=lambda x: score(query, x), reverse=True)
    except Exception as exc:  # pictures are a nice-to-have: never fail the deck over them
        logger.info("image search failed for %r: %s", query, exc)
    results = [{k: v for k, v in x.items() if not k.startswith("_")} for x in results[:12]]
    if results:
        _cache[query] = results
        if len(_cache) > 300:
            _cache.pop(next(iter(_cache)))
    return results


def queries_for(slide: dict, topic: str = "") -> List[str]:
    """The slide's own search words first, then shorter and broader fallbacks."""
    out = []
    q = (slide.get("image_query") or "").strip()
    if q:
        out.append(q)
        words = q.split()
        if len(words) > 2:
            out.append(" ".join(words[:2]))
    title_words = [w for w in re.findall(r"[A-Za-z]+", slide.get("title") or "") if w.lower() not in _STOP and len(w) > 3]
    if title_words:
        out.append(" ".join(title_words[:3]))
    topic_words = [w for w in re.findall(r"[A-Za-z]+", topic or "") if w.lower() not in _STOP and len(w) > 3]
    if topic_words:
        out.append(" ".join(topic_words[:2]))
    return list(dict.fromkeys(out))


async def find_stock(slide: dict, used: set, topic: str = "") -> Optional[dict]:
    for q in queries_for(slide, topic):
        for img in await search(q):
            if img["url"] not in used:
                used.add(img["url"])
                return img
    return None


def ai_prompt(slide: dict, topic: str = "") -> str:
    base = (slide.get("image_prompt") or slide.get("image_query") or slide.get("title") or topic or "").strip()
    context = f" Presentation about {topic}." if topic and topic.lower() not in base.lower() else ""
    return f"{base}.{context} {AI_STYLE}"


async def make_ai(db, user_id: str, slide: dict, topic: str = "", prompt: Optional[str] = None) -> dict:
    """Generate a 16:9 picture for the slide and store it. Raises on failure."""
    import media

    data = await media.generate_image(f"{prompt.strip()}. {AI_STYLE}" if prompt else ai_prompt(slide, topic),
                                      "1536x1024")
    data = shrink(data) or data
    saved = await media.save_media(db, user_id, data, media.image_type(data) or "image/jpeg", "generated",
                                   name="slide-picture.jpg")
    return {"url": saved["url"], "thumb": "", "credit": "AI-made picture", "link": ""}


def shrink(data: bytes, box: int = 1600) -> Optional[bytes]:
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((box, box))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def download(url: str) -> Optional[bytes]:
    """Fetch a photo for the .pptx, shrunk so the file stays small."""
    try:
        with httpx.stream("GET", url, timeout=15, follow_redirects=True, headers=UA) as r:
            r.raise_for_status()
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > 10 * 1024 * 1024:
                    return None
        return shrink(bytes(buf))
    except Exception as exc:
        logger.info("image download failed for %s: %s", url, exc)
        return None


async def stored_bytes(db, user_id: str, url: str) -> Optional[bytes]:
    """Bytes of a picture saved in the media collection (AI-made or uploaded)."""
    import media

    m = MEDIA_URL.match(url or "")
    if not m:
        return None
    doc = await media.load_media(db, user_id, m.group(1))
    if not doc:
        return None
    return shrink(await media.read_bytes(db, doc))
