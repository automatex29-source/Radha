"""Perplexity-style search extras: Focus (Academic, Social, Video), picture results and Pro search.

All free, no keys: OpenAlex for papers, Reddit and YouTube through the normal web search, Bing images with
Wikimedia Commons as the fallback for pictures. Pro search plans a few queries and reads the best pages.
"""
import asyncio
import html
import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import httpx
import lxml.html

from agent import research, web

logger = logging.getLogger(__name__)

FOCUSES = ("web", "academic", "social", "video")
_TIMEOUT = httpx.Timeout(8.0, connect=5.0)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True,
                             headers={"User-Agent": web.BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"})


# ------------------------------------------------------------------ academic
def _abstract(inverted: Optional[Dict[str, List[int]]]) -> str:
    if not inverted:
        return ""
    words = sorted((pos, w) for w, places in inverted.items() for pos in places)
    return " ".join(w for _, w in words)


def parse_openalex(data: dict, limit: int) -> List[dict]:
    out = []
    for w in data.get("results", []):
        loc = w.get("primary_location") or {}
        url = loc.get("landing_page_url") or w.get("doi") or w.get("id") or ""
        if not url.startswith("http") or not w.get("display_name"):
            continue
        authors = [a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])[:3]]
        venue = ((loc.get("source") or {}).get("display_name")) or ""
        meta = ", ".join(x for x in [", ".join(a for a in authors if a), str(w.get("publication_year") or ""),
                                     venue, f"cited {w.get('cited_by_count', 0)} times"] if x)
        out.append({"title": w["display_name"], "url": url,
                    "snippet": (meta + ". " + _abstract(w.get("abstract_inverted_index")))[:400]})
        if len(out) >= limit:
            break
    return out


async def academic(query: str, limit: int = 6) -> List[dict]:
    async with _client() as client:
        resp = await client.get("https://api.openalex.org/works", params={
            "search": query, "per-page": limit + 4, "filter": "has_abstract:true"})
        resp.raise_for_status()
        return parse_openalex(resp.json(), limit)


# ------------------------------------------------------------- social, video
async def social(query: str, limit: int = 6) -> List[dict]:
    results = await web.search(f"{query} site:reddit.com", limit + 2)
    return [r for r in results if "reddit.com" in r.get("url", "")][:limit] or results[:limit]


def youtube_id(url: str) -> str:
    p = urlparse(url)
    if p.netloc.endswith("youtu.be"):
        return p.path.strip("/")[:11]
    if "youtube.com" in p.netloc:
        if p.path == "/watch":
            return (parse_qs(p.query).get("v") or [""])[0][:11]
        m = re.match(r"/(shorts|embed|live)/([\w-]{11})", p.path)
        if m:
            return m.group(2)
    return ""


async def video(query: str, limit: int = 6) -> List[dict]:
    results = await web.search(f"{query} site:youtube.com", limit + 4)
    out = []
    for r in results:
        vid = youtube_id(r.get("url", ""))
        if vid:
            out.append({**r, "url": f"https://www.youtube.com/watch?v={vid}",
                        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
    return out[:limit]


# -------------------------------------------------------------------- images
def parse_bing_images(page: str, limit: int) -> List[dict]:
    doc = lxml.html.fromstring(page)
    out = []
    for a in doc.xpath("//a[contains(@class,'iusc')][@m]"):
        try:
            m = json.loads(html.unescape(a.get("m")))
        except ValueError:
            continue
        thumb, full, src = m.get("turl", ""), m.get("murl", ""), m.get("purl", "")
        if thumb.startswith("http") and src.startswith("http"):
            out.append({"type": "image", "thumbnail": thumb, "image": full or thumb, "url": src,
                        "title": (m.get("t") or "").strip()[:120]})
        if len(out) >= limit:
            break
    return out


def parse_commons(data: dict, limit: int) -> List[dict]:
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("thumburl") and re.search(r"\.(jpe?g|png|webp)$", p.get("title", ""), re.I):
            out.append({"type": "image", "thumbnail": info["thumburl"], "image": info.get("url") or info["thumburl"],
                        "url": info.get("descriptionurl") or info["thumburl"],
                        "title": re.sub(r"^File:|\.\w+$", "", p["title"])[:120]})
        if len(out) >= limit:
            break
    return out


async def images(query: str, limit: int = 6) -> List[dict]:
    async with _client() as client:
        try:
            resp = await client.get("https://www.bing.com/images/search", params={"q": query, "form": "HDRSC2"})
            found = parse_bing_images(resp.text, limit) if resp.status_code == 200 else []
            if found:
                return found
            logger.warning("Bing images gave no results (HTTP %s)", resp.status_code)
        except Exception as exc:
            logger.warning("Bing images failed: %s", exc)
        resp = await client.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrnamespace": 6,
            "gsrlimit": limit * 2, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 400})
        resp.raise_for_status()
        return parse_commons(resp.json(), limit)


# ---------------------------------------------------------------- pro search
def on_topic(sources: List[dict], terms: List[str]) -> List[dict]:
    """Drops pages that don't mention the question's words (a search for "current CEO" can bring back a bank
    called Current). Keeps the closest matches when too few pass, and everything when none match at all."""
    terms = set(terms)
    if not terms:
        return sources
    def hits(s):
        words = set(research.keywords(f"{s.get('title', '')} {s.get('url', '')} {s.get('text', '')}"))
        return len(terms & words)
    need = min(2, len(terms))
    for floor in (need, 1):
        kept = [s for s in sources if hits(s) >= floor]
        if len(kept) >= 2 or (kept and floor == 1):
            return kept
    return sources


async def pro(question: str, model: str, max_sources: int = 6, max_chars: int = 900) -> dict:
    """Plans a few searches, reads the best pages. Returns {"queries", "results"} (results carry page text)."""
    queries = await research.plan(question, "", model, research.default_ask)
    # The planner's queries are cleaned up (typos fixed, clearer words), so they lead; the raw question goes last.
    queries = queries[1:] + queries[:1] if len(queries) > 1 else queries
    # Short limits so a slow engine or page can't use up the whole Pro budget; a page that won't load keeps its snippet.
    terms = research.keywords(question)
    sources = await research.gather_sources(queries, terms, max_sources + 2, max_chars,
                                            search_timeout=12, fetch_timeout=8)
    sources = on_topic(sources, terms)[:max_sources]
    return {"queries": queries,
            "results": [{"title": s["title"], "url": s["url"], "snippet": s["text"]} for s in sources]}


async def search(query: str, focus: str, limit: int) -> List[dict]:
    if focus == "academic":
        return await academic(query, limit)
    if focus == "social":
        return await social(query, limit)
    if focus == "video":
        return await video(query, limit)
    return await web.search(query, limit)


def wants_images(text: str) -> bool:
    """Pictures help for places, people, products, animals and "show me" questions, not for prices or how-tos."""
    t = text.lower()
    if re.search(r"\b(price|rate|score|how to|why|calculate|code|error|stock|share)\b", t):
        return False
    # "Who is the CEO of X" asks for a name; picture searches for it bring back random things.
    if re.search(r"\bwho (is|was|are|were) the\b", t):
        return False
    return bool(re.search(r"\b(show|photo|photos|picture|pictures|image|images|look like|looks like|design|"
                          r"who is|who was|where is|car|phone|laptop|place|places|temple|fort|beach|city|animal|"
                          r"bird|flower|dish|recipe|dress|logo|building|monument)\b", t))


async def safe(coro, timeout: float, default):
    try:
        return await asyncio.wait_for(coro, timeout)
    except Exception as exc:
        logger.warning("search extra failed: %r", exc)
        return default
