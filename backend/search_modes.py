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


_YT_SUFFIX = re.compile(r"\s*[-|–]\s*YouTube\s*$", re.I)
OEMBED_TIMEOUT = 3.0


async def _oembed(client: httpx.AsyncClient, vid: str) -> Optional[dict]:
    """{"title", "channel"} for a video; {} when YouTube couldn't be asked; None when the video is gone or private."""
    try:
        resp = await asyncio.wait_for(client.get("https://www.youtube.com/oembed", params={
            "url": f"https://www.youtube.com/watch?v={vid}", "format": "json"}), OEMBED_TIMEOUT)
    except Exception:
        return {}
    if resp.status_code in (400, 401, 403, 404):
        return None
    try:
        data = resp.json() if resp.status_code == 200 else {}
    except ValueError:
        return {}
    return {"title": data.get("title") or "", "channel": data.get("author_name") or ""}


def rank_videos(found: List[dict], query: str) -> List[dict]:
    """Videos about the question first (their titles share its words), full videos before Shorts, and otherwise
    in the search engine's order."""
    terms = set(research.keywords(query)) - {"hindi", "video", "videos", "youtube"}

    def score(item):
        i, v = item
        hits = len(terms & set(research.keywords(v.get("title", "")))) if terms else 0
        return (-min(hits, 3), v.get("short", False), i)
    return [v for _, v in sorted(enumerate(found), key=score)]


async def video(query: str, limit: int = 6) -> List[dict]:
    """YouTube videos for the question: one card per video, dead and private videos left out, real titles and
    channel names from YouTube, and the most relevant first."""
    results = await web.search(f"{query} site:youtube.com", min(10, limit + 6))
    found, seen = [], set()
    for r in results:
        vid = youtube_id(r.get("url", ""))
        if not vid or vid in seen:
            continue
        seen.add(vid)
        found.append({**r, "id": vid, "title": _YT_SUFFIX.sub("", r.get("title") or "").strip(),
                      "short": "/shorts/" in r.get("url", ""),
                      "url": f"https://www.youtube.com/watch?v={vid}",
                      "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
    found = rank_videos(found, query)[:limit + 2]
    async with _client() as client:
        checked = await asyncio.gather(*(_oembed(client, v["id"]) for v in found))
    out = []
    for v, meta in zip(found, checked):
        if meta is None:
            continue
        if meta.get("title"):
            v["title"] = meta["title"]
        if meta.get("channel"):
            v["channel"] = meta["channel"]
        out.append({k: val for k, val in v.items() if k not in ("id", "short")})
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
    # The question itself is searched while the planner thinks of the other queries (searches are shared, see
    # web.search), so planning no longer adds its time before the first results.
    early = asyncio.ensure_future(safe(web.search(question.strip()[:200], research.RESULTS_PER_QUERY), 8, []))
    try:
        queries = await research.plan(question, "", model, research.default_ask)
    finally:
        early.cancel()  # the shared search keeps going for gather_sources below; only this waiter stops
    # The planner's queries are cleaned up (typos fixed, clearer words), so they lead; the raw question goes last.
    queries = queries[1:] + queries[:1] if len(queries) > 1 else queries
    # Short limits so a slow engine or page can't use up the whole Pro budget; a page that won't load keeps its snippet.
    terms = research.keywords(question)
    sources = await research.gather_sources(queries, terms, max_sources + 2, max_chars,
                                            search_timeout=8, fetch_timeout=5, fetch=web.read_page)
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


_VIDEO_ASK = re.compile(r"\b(videos?|youtube|yt|tutorials?|trailer|song|songs|gaana|gaane|lecture|lectures)\b", re.I)
_VIDEO_TOPIC = re.compile(
    r"\b(how to|how do i|how can i|recipe|recipes|tutorial|step by step|workout|exercises?|yoga|stretch(es|ing)?|"
    r"diy|install|fix|repair|learn|learning|guide|course|lesson|lessons|explained|kaise|banaye|banate|sikhe|sikho|"
    r"sikhna|cook|cooking|bake|baking|draw|drawing|sketch|paint|painting|guitar|piano|dance|makeup|hairstyle|"
    r"origami|craft|crafts|knit|stitch|tie a)\b", re.I)
# Questions where a video is no help: words, prices, code.
_NO_VIDEO = re.compile(
    r"\b(how to (say|spell|pronounce|write|reply|respond)|price|cost|rate|stock|share|news|"
    r"code|error|exception|python|javascript|java|react|sql|api|regex|bug|excel formula)\b", re.I)


def wants_videos(text: str) -> bool:
    """How-tos, recipes, workouts, lessons and tutorials are easier to follow on video, and anyone asking for a
    video or a song gets one. Not for code, prices or questions about words."""
    t = text or ""
    if _VIDEO_ASK.search(t):
        return True
    return bool(_VIDEO_TOPIC.search(t)) and not _NO_VIDEO.search(t)


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
