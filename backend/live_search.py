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
from typing import List, Optional

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
_CURRENCY = web.CURRENCY


def _recent_user_text(user_messages: List[str]) -> str:
    """The latest question, joined with the one before it when it is a short follow-up like "USD"."""
    if not user_messages:
        return ""
    last = user_messages[-1].strip()
    if len(last.split()) <= 3 and len(user_messages) > 1:
        return f"{user_messages[-2].strip()} {last}"
    return last


def needs_lookup(text: str) -> bool:
    return bool(text) and bool(_CURRENT.search(text) or _CURRENCY.search(text))


async def _rates(text: str) -> Optional[str]:
    return await web.exchange_rates(text) or None


async def _search(text: str) -> Optional[str]:
    results = await web.search(text[:200], 5)
    if not results:
        return None
    lines = [f"{i + 1}. {r['title']} ({r['url']})\n   {r['snippet']}" for i, r in enumerate(results)]
    return "Web search results:\n" + "\n".join(lines)


async def lookup(user_messages: List[str], search: bool = True) -> Optional[str]:
    """Live context for the latest question, or None when it doesn't need any (or the lookup fails).

    With search=False only exchange rates are fetched (agent turns search with their own tool).
    """
    text = _recent_user_text(user_messages)
    if not needs_lookup(text):
        return None
    jobs = [_rates(text)] if _CURRENCY.search(text) else []
    if search:
        jobs.append(_search(text))
    if not jobs:
        return None
    # Each part has its own time limit, so slow search engines never cost us the exchange rates.
    found = await asyncio.gather(*(asyncio.wait_for(j, LOOKUP_TIMEOUT) for j in jobs), return_exceptions=True)
    parts = []
    for item in found:
        if isinstance(item, Exception):
            logger.warning("Live lookup part failed: %r", item)
        elif item:
            parts.append(item)
    return "\n\n".join(parts) or None
