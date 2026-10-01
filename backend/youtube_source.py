"""Read a YouTube video for the Decks page: title, description and captions.

YouTube often blocks or redirects requests from cloud servers (consent page, "sign in to confirm
you're not a bot"), so every step has a fallback and we keep whatever we managed to read:
  1. the watch page (with consent cookies) -> title, description, caption track links
  2. oEmbed -> title and channel, which is almost never blocked
  3. captions via youtube-transcript-api, then via the caption links from step 1
Only fixed youtube.com hosts are requested here, so no user-controlled URL is fetched.
"""
import asyncio
import json
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 15
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}
# Skips the EU/India consent interstitial that otherwise replaces the watch page.
COOKIES = {"CONSENT": "YES+cb", "SOCS": "CAI"}
PREFERRED_LANGS = ("en", "en-US", "en-GB", "hi")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, cookies=COOKIES, follow_redirects=True)


def parse_watch_page(html: str) -> dict:
    """Title, description and caption tracks from a watch page's HTML."""
    title = ""
    m = re.search(r'<meta name="title" content="([^"]*)"', html) or re.search(r"<title>([^<]*)</title>", html)
    if m:
        title = m.group(1).replace(" - YouTube", "").strip()
    description = ""
    m = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html)
    if m:
        try:
            description = json.loads(f'"{m.group(1)}"')
        except ValueError:
            pass
    tracks = []
    m = re.search(r'"captionTracks":(\[.*?\])', html)
    if m:
        try:
            tracks = json.loads(m.group(1))
        except ValueError:
            tracks = []
    return {"title": title, "description": description, "tracks": tracks}


def pick_track(tracks: list) -> Optional[str]:
    """Caption URL in the best language: English or Hindi first, human-made before auto-made."""
    def rank(t):
        code = t.get("languageCode", "")
        lang = PREFERRED_LANGS.index(code) if code in PREFERRED_LANGS else len(PREFERRED_LANGS)
        return (lang, t.get("kind") == "asr")
    good = [t for t in tracks if t.get("baseUrl", "").startswith("https://www.youtube.com/")]
    return sorted(good, key=rank)[0]["baseUrl"] if good else None


def parse_json3(data: dict) -> str:
    parts = []
    for event in data.get("events") or []:
        text = "".join(seg.get("utf8", "") for seg in event.get("segs") or [])
        if text.strip():
            parts.append(text.strip())
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def parse_xml_captions(xml: str) -> str:
    import html as html_lib

    texts = re.findall(r"<(?:text|p)[^>]*>(.*?)</(?:text|p)>", xml, flags=re.S)
    clean = (html_lib.unescape(re.sub(r"<[^>]+>", "", t)) for t in texts)
    return re.sub(r"\s+", " ", " ".join(clean)).strip()


def _library_transcript(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    try:
        codes = [t.language_code for t in api.list(video_id)]
        fetched = api.fetch(video_id, languages=list(PREFERRED_LANGS) + codes)
    except Exception:
        fetched = api.fetch(video_id)
    return " ".join(getattr(x, "text", "") or (x.get("text", "") if isinstance(x, dict) else "") for x in fetched)


async def _watch_page(client: httpx.AsyncClient, video_id: str) -> dict:
    try:
        resp = await client.get("https://www.youtube.com/watch", params={"v": video_id, "hl": "en"})
        return parse_watch_page(resp.text)
    except Exception as exc:
        logger.info("youtube watch page failed: %s", exc)
        return {"title": "", "description": "", "tracks": []}


async def _oembed(client: httpx.AsyncClient, video_id: str) -> dict:
    try:
        resp = await client.get("https://www.youtube.com/oembed",
                                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"})
        if resp.status_code == 200:
            data = resp.json()
            return {"title": data.get("title") or "", "channel": data.get("author_name") or ""}
    except Exception as exc:
        logger.info("youtube oembed failed: %s", exc)
    return {"title": "", "channel": ""}


async def _track_transcript(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url, params={"fmt": "json3"})
        if resp.status_code == 200 and resp.text.strip():
            try:
                return parse_json3(resp.json())
            except ValueError:
                return parse_xml_captions(resp.text)
    except Exception as exc:
        logger.info("youtube caption track failed: %s", exc)
    return ""


async def read(video_id: str) -> dict:
    """{"title", "channel", "description", "transcript"} with whatever could be read (may all be empty)."""
    async with _client() as client:
        page, meta = await asyncio.gather(_watch_page(client, video_id), _oembed(client, video_id))
        try:
            transcript = await asyncio.get_running_loop().run_in_executor(None, _library_transcript, video_id)
        except Exception as exc:
            logger.info("youtube transcript library failed: %s", exc)
            transcript = ""
        if not transcript.strip():
            url = pick_track(page["tracks"])
            transcript = await _track_transcript(client, url) if url else ""
    return {"title": meta["title"] or page["title"], "channel": meta["channel"],
            "description": page["description"], "transcript": transcript.strip()}
