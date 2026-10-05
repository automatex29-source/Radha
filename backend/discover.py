"""Discover: today's top news by topic, like Perplexity's Discover feed.

Free Google News RSS feeds, no key. Cached for 15 minutes per topic and language so a busy home page
doesn't hammer the feed.
"""
import email.utils
import logging
import re
import time
from typing import Dict, List, Tuple
from urllib.parse import urlparse

import httpx
import lxml.etree

logger = logging.getLogger(__name__)

TOPICS = {  # our name -> Google News section (None = top stories)
    "top": None, "india": "NATION", "world": "WORLD", "business": "BUSINESS", "tech": "TECHNOLOGY",
    "sports": "SPORTS", "science": "SCIENCE", "entertainment": "ENTERTAINMENT", "health": "HEALTH",
}
# Languages Google News serves for India; everything else falls back to English.
_LANGS = {"hi": "hi", "bn": "bn", "ta": "ta", "te": "te", "mr": "mr", "gu": "gu", "kn": "kn", "ml": "ml", "pa": "pa"}
CACHE_SECONDS = 15 * 60
_cache: Dict[Tuple[str, str], Tuple[float, List[dict]]] = {}


def feed_url(topic: str, lang: str) -> str:
    hl = _LANGS.get(lang or "", "en")
    params = f"hl={hl}-IN&gl=IN&ceid=IN:{hl}" if hl != "en" else "hl=en-IN&gl=IN&ceid=IN:en"
    section = TOPICS.get(topic)
    if section:
        return f"https://news.google.com/rss/headlines/section/topic/{section}?{params}"
    return f"https://news.google.com/rss?{params}"


def _when(pub: str) -> str:
    try:
        return email.utils.parsedate_to_datetime(pub).isoformat()
    except (TypeError, ValueError):
        return ""


def parse_feed(xml: bytes, limit: int) -> List[dict]:
    root = lxml.etree.fromstring(xml, parser=lxml.etree.XMLParser(recover=True, resolve_entities=False))
    out, seen = [], set()
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        src = item.find("source")
        source = (src.text or "").strip() if src is not None else ""
        site = src.get("url", "") if src is not None else ""
        # Google adds " - Source" to every title.
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].strip()
        key = re.sub(r"\W+", "", title.lower())[:60]
        if not title or not link.startswith("http") or key in seen:
            continue
        seen.add(key)
        host = urlparse(site).netloc.lower()
        out.append({"title": title, "url": link, "source": source, "domain": host[4:] if host.startswith("www.") else host,
                    "published": _when(item.findtext("pubDate") or "")})
        if len(out) >= limit:
            break
    return out


async def stories(topic: str = "top", lang: str = "en", limit: int = 24) -> List[dict]:
    topic = topic if topic in TOPICS else "top"
    key = (topic, _LANGS.get(lang or "", "en"))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1][:limit]
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0 (compatible; KrishAI/1.0)"}) as client:
        resp = await client.get(feed_url(topic, lang))
        resp.raise_for_status()
    found = parse_feed(resp.content, 40)
    if found:
        _cache[key] = (time.time(), found)
    elif hit:
        return hit[1][:limit]  # keep showing the last good list
    return found[:limit]
