"""Automatic live web lookups for plain chat.

Plain chat has no tools, so without this the model answers questions about
today's rates, news or prices from stale training data. When a question looks
like it needs current information, RADHA searches the web (DuckDuckGo, no key
needed) and, for currency questions, pulls live exchange rates from a free API,
then hands the results to the model as context.
"""
import asyncio
import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from agent import web

logger = logging.getLogger(__name__)

LOOKUP_TIMEOUT = 6.0

_CURRENT = re.compile(
    r"\b(today|todays|tonight|right now|current(ly)?|latest|recent(ly)?|this (week|month|year)|yesterday|"
    r"news|headlines?|price|prices|rate|rates|weather|forecast|temperature|score|scores|"
    r"stock|share price|sensex|nifty|bitcoin|btc|crypto|gold|silver|petrol|diesel|election|"
    r"search|google|look ?up|browse|internet|who won|who is the|20[2-9]\d)\b",
    re.I,
)
# Fact questions ("who is", "how much", "best phones under 20000", "X vs Y") also get a search, like Perplexity.
_QUESTION = re.compile(
    r"^\s*(who|what|when|where|which|whose|how (much|many|old|far|long|big|tall)|is there|are there|did|does|"
    r"kaun|kya|kab|kahan|kitna|kitne)\b|\b(best|top \d+|vs\.?|versus|compare|comparison|review|reviews|"
    r"near me|cheapest|release date|launch(ed)?|founder|ceo|population|capital of|net worth|salary|"
    r"how to (buy|apply|get|book|register|download))\b",
    re.I,
)
_CURRENCY = web.CURRENCY
MAX_QUESTION_CHARS = 300
CITE_NOTE = (
    "Cite: after each sentence that uses a numbered web result, add its number in square brackets, like [1] or "
    "[2][3]. Use only the numbers listed here. Don't add a separate list of sources or links; the app shows them."
)


def _recent_user_text(user_messages: List[str]) -> str:
    """The latest question, joined with the one before it when it is a short follow-up like "USD"."""
    if not user_messages:
        return ""
    last = user_messages[-1].strip()
    if len(last.split()) <= 3 and len(user_messages) > 1:
        return f"{user_messages[-2].strip()} {last}"
    return last


def needs_lookup(text: str) -> bool:
    if not text:
        return False
    if _CURRENT.search(text) or _CURRENCY.search(text):
        return True
    # A short fact question, not a request to write, code or translate something.
    return len(text) <= MAX_QUESTION_CHARS and "```" not in text and bool(_QUESTION.search(text))


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


async def _rates(text: str) -> Optional[str]:
    return await web.exchange_rates(text) or None


async def _search(text: str, limit: int = 5) -> Optional[Tuple[str, List[dict]]]:
    results = [r for r in await web.search(text[:200], limit) if r.get("url", "").startswith("http")]
    if not results:
        return None
    lines = [f"[{i + 1}] {r['title']} ({r['url']})\n   {r['snippet']}" for i, r in enumerate(results)]
    cards = [{"type": "web", "title": r["title"] or domain_of(r["url"]), "url": r["url"],
              "domain": domain_of(r["url"]), "snippet": (r.get("snippet") or "")[:240]} for r in results]
    return "Web search results:\n" + "\n".join(lines) + "\n" + CITE_NOTE, cards


async def gather(user_messages: List[str], search: bool = True, force: bool = False) -> Tuple[Optional[str], List[dict]]:
    """(live context, web source cards) for the latest question; (None, []) when it needs none or lookups fail.

    force=True (the Search button) always searches, with more results. With search=False only exchange rates
    are fetched.
    """
    text = _recent_user_text(user_messages)
    if not text or not (force or needs_lookup(text)):
        return None, []
    jobs = [_rates(text)] if _CURRENCY.search(text) else []
    if search:
        jobs.append(_search(text, 8 if force else 5))
    if not jobs:
        return None, []
    # Each part has its own time limit, so slow search engines never cost us the exchange rates.
    found = await asyncio.gather(*(asyncio.wait_for(j, LOOKUP_TIMEOUT) for j in jobs), return_exceptions=True)
    parts, cards = [], []
    for item in found:
        if isinstance(item, Exception):
            logger.warning("Live lookup part failed: %r", item)
        elif isinstance(item, tuple):
            parts.append(item[0])
            cards = item[1]
        elif item:
            parts.append(item)
    return "\n\n".join(parts) or None, cards


async def lookup(user_messages: List[str], search: bool = True) -> Optional[str]:
    """Live context for the latest question, or None when it doesn't need any (or the lookup fails)."""
    return (await gather(user_messages, search))[0]
