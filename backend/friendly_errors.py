"""Turn an AI provider's error into words a user understands, with the time it will work again.

The free models (Groq, Cerebras, Gemini, OpenRouter) answer "rate limit reached ... try again in 7m12s" or
"quota exceeded ... retry in 34s" when their free allowance is used up. Instead of that raw text (or an
internal one like "HarmonyError: render failed"), the user sees when Krish AI will answer again, in their time.
"""
import re
import time
from typing import Optional

import limits

_LIMIT_WORDS = re.compile(r"rate.?limit|quota|too many requests|\b429\b|resource.?exhausted|per day|tokens per|"
                          r"requests per|credits", re.IGNORECASE)
_WAIT = re.compile(r"(?:try again|retry|retry_after|retry-after|please wait)[^0-9]{0,20}"
                   r"(?:(\d+)h)?\s*(?:(\d+)m(?!s))?\s*(?:([\d.]+)\s*s)?", re.IGNORECASE)
_RETRY_DELAY = re.compile(r"retryDelay\W+(\d+)s", re.IGNORECASE)


def wait_seconds(text: str) -> Optional[float]:
    """Seconds the provider says to wait, or None when it doesn't say."""
    m = _RETRY_DELAY.search(text)
    if m:
        return float(m.group(1))
    for m in _WAIT.finditer(text):
        h, mins, secs = m.groups()
        if h or mins or secs:
            return int(h or 0) * 3600 + int(mins or 0) * 60 + float(secs or 0)
    return None


def is_limit(exc: Exception) -> bool:
    return type(exc).__name__ in ("RateLimitError",) or bool(_LIMIT_WORDS.search(str(exc)))


def limit_info(exc: Exception, now: Optional[float] = None) -> dict:
    """What the chat's limit card shows: the message, when it resets (epoch seconds, or None) and if it's daily."""
    text = str(exc)
    secs = wait_seconds(text)
    daily = "per day" in text.lower() or "daily" in text.lower()
    resets = (now or time.time()) + max(60.0, secs) if secs is not None else None
    if resets is not None:
        message = (f"Krish AI's free AI has reached its {'daily' if daily else 'short-term'} limit. "
                   f"It works again {limits._when(resets)}. You can also pick another model from the menu at the top.")
    elif daily:
        message = ("Krish AI's free AI has reached its daily limit. It works again in a few hours (the limit resets "
                   "once a day). You can also pick another model from the menu at the top.")
    else:
        message = ("Krish AI's free AI is at its limit right now. Try again in about a minute, or pick another model "
                   "from the menu at the top.")
    return {"message": message, "resetsAt": int(resets) if resets else None, "daily": daily,
            "since": int(now or time.time())}


def limit_message(exc: Exception, now: Optional[float] = None) -> str:
    return limit_info(exc, now)["message"]


def friendly(exc: Exception) -> Optional[dict]:
    """The limit card for a usage-limit error, else None (the usual "tap Regenerate" note)."""
    return limit_info(exc) if is_limit(exc) else None


SHORT_ERROR = "The AI model had a problem with this reply. Tap Regenerate to try again."
