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

import httpx

from agent import web

logger = logging.getLogger(__name__)

RATES_URL = "https://open.er-api.com/v6/latest/USD"  # free, no key
LOOKUP_TIMEOUT = 10.0

_CURRENT = re.compile(
    r"\b(today|todays|tonight|right now|current(ly)?|latest|recent(ly)?|this (week|month|year)|yesterday|"
    r"news|headlines?|price|prices|rate|rates|weather|forecast|temperature|score|scores|"
    r"stock|share price|sensex|nifty|bitcoin|btc|crypto|gold|silver|petrol|diesel|election|"
    r"search|google|look ?up|browse|internet|who won|who is the|20[2-9]\d)\b",
    re.I,
)
_CURRENCY = re.compile(
    r"\b(dollar|dollars|usd|rupee|rupees|inr|euro|euros|eur|pound|pounds|gbp|yen|jpy|dirham|aed|riyal|sar|"
    r"yuan|cny|currency|exchange rate|forex|fx)\b",
    re.I,
)
_CODES = re.compile(r"\b[A-Z]{3}\b")
_DEFAULT_CODES = ["INR", "EUR", "GBP", "AED", "JPY", "CNY", "CAD", "AUD", "SGD", "SAR"]
_NAMES = {"rupee": "INR", "euro": "EUR", "pound": "GBP", "yen": "JPY", "dirham": "AED", "riyal": "SAR",
          "yuan": "CNY"}


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
    async with httpx.AsyncClient(timeout=LOOKUP_TIMEOUT, headers={"User-Agent": web.USER_AGENT}) as client:
        resp = await client.get(RATES_URL)
        resp.raise_for_status()
        data = resp.json()
    rates = data.get("rates") or {}
    wanted = [c for c in _CODES.findall(text.upper()) if c in rates and c != "USD"]
    wanted += [code for name, code in _NAMES.items() if name in text.lower()]
    codes = list(dict.fromkeys(wanted + _DEFAULT_CODES))
    lines = [f"1 USD = {rates[c]:,.4f} {c}" for c in codes if c in rates]
    if not lines:
        return None
    updated = data.get("time_last_update_utc", "recently")
    return f"Live exchange rates (source: open.er-api.com, updated {updated}):\n" + "\n".join(lines)


async def _search(text: str) -> Optional[str]:
    results = await web.search(text[:200], 5)
    if not results:
        return None
    lines = [f"{i + 1}. {r['title']} ({r['url']})\n   {r['snippet']}" for i, r in enumerate(results)]
    return "Web search results:\n" + "\n".join(lines)


async def lookup(user_messages: List[str]) -> Optional[str]:
    """Live context for the latest question, or None when it doesn't need any (or the lookup fails)."""
    text = _recent_user_text(user_messages)
    if not needs_lookup(text):
        return None
    jobs = [_search(text)]
    if _CURRENCY.search(text):
        jobs.insert(0, _rates(text))
    try:
        found = await asyncio.wait_for(asyncio.gather(*jobs, return_exceptions=True), LOOKUP_TIMEOUT + 2)
    except asyncio.TimeoutError:
        logger.warning("Live lookup timed out")
        return None
    parts = []
    for item in found:
        if isinstance(item, Exception):
            logger.warning("Live lookup part failed: %s", item)
        elif item:
            parts.append(item)
    return "\n\n".join(parts) or None
