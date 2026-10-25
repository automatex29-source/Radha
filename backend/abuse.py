"""Spam protection: keeps bots from making fake accounts and from running up the AI bill.

- Sign-ups with throwaway email addresses (mailinator and friends) or with an email domain that can't receive
  mail are turned away.
- One internet address can make only a few accounts an hour.
- Each account can send only so many messages a minute and an hour. A person typing never gets near it;
  a script hammering the server does.

Counts are kept in memory, per server. That is enough to stop a flood; a restart simply starts them again.
Set ABUSE_LIMITS=off to switch the rate limits off (for testing).
"""
import logging
import os
import time
from collections import deque

from fastapi import HTTPException, Request

logger = logging.getLogger("radha.abuse")

SIGNUPS_PER_HOUR = 5
LIMITS = {
    # kind: [(how many, seconds), ...]
    "chat": [(20, 60), (200, 3600)],
    "media": [(15, 60), (120, 3600)],
    "signup": [(SIGNUPS_PER_HOUR, 3600)],
    "report": [(20, 3600)],
}

DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "sharklasers.com",
    "10minutemail.com", "10minutemail.net", "tempmail.com", "temp-mail.org", "temp-mail.io", "tempmail.net",
    "tempmailo.com", "tempr.email", "throwawaymail.com", "yopmail.com", "yopmail.net", "getnada.com", "nada.email",
    "trashmail.com", "trashmail.de", "dispostable.com", "maildrop.cc", "mailnesia.com", "mintemail.com",
    "mohmal.com", "fakeinbox.com", "emailondeck.com", "spamgourmet.com", "mailcatch.com", "moakt.com",
    "burnermail.io", "inboxkitten.com", "mail.tm", "mailpoof.com", "33mail.com", "spambox.us", "tmail.ws",
    "tmpmail.org", "tmpmail.net", "emailfake.com", "fakemail.net", "luxusmail.org", "minuteinbox.com",
    "discard.email", "mailsac.com", "getairmail.com", "dropmail.me", "linshiyouxiang.net", "1secmail.com",
    "1secmail.net", "1secmail.org", "byom.de", "wegwerfmail.de", "harakirimail.com", "spam4.me", "grr.la",
}

_hits: dict = {}  # key -> deque of monotonic times


def enabled() -> bool:
    return os.environ.get("ABUSE_LIMITS", "on").strip().lower() not in ("off", "0", "false", "no")


def client_ip(request: Request) -> str:
    # On Render (and most hosts) the app sits behind a proxy that puts the visitor's address first here.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def allow(kind: str, who: str) -> bool:
    """Count one request of `kind` from `who`. False when that would go over a limit (and it isn't counted)."""
    if not enabled():
        return True
    now = time.monotonic()
    key = f"{kind}:{who}"
    times = _hits.setdefault(key, deque())
    longest = max(seconds for _, seconds in LIMITS[kind])
    while times and times[0] < now - longest:
        times.popleft()
    for count, seconds in LIMITS[kind]:
        if sum(1 for t in times if t > now - seconds) >= count:
            return False
    times.append(now)
    if len(_hits) > 100000:  # keep memory bounded under a flood of made-up keys
        _hits.clear()
    return True


MESSAGES = {
    "chat": "You're sending messages very fast. Please wait a minute and try again.",
    "media": "That's a lot of requests in a short time. Please wait a minute and try again.",
    "signup": "Too many accounts were made from this internet connection. Please try again later.",
    "report": "Thanks, we've got enough reports from you for now.",
}


def require(kind: str, who: str) -> None:
    if not allow(kind, who):
        raise HTTPException(status_code=429, detail=MESSAGES[kind])


async def _domain_takes_mail(domain: str) -> bool:
    """False only when DNS says plainly that the domain doesn't exist or has nowhere to deliver mail."""
    try:
        import dns.asyncresolver
        import dns.exception
        import dns.resolver
    except ImportError:
        return True
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 3
    for record in ("MX", "A"):
        try:
            await resolver.resolve(domain, record)
            return True
        except dns.resolver.NXDOMAIN:
            return False
        except dns.resolver.NoAnswer:
            continue
        except dns.resolver.NoNameservers:  # the DNS servers failed to answer, so we can't tell: let them in
            return True
        except Exception:  # a timeout or other DNS trouble: don't block real people
            return True
    return False


async def check_signup_email(email: str) -> None:
    """Turn away throwaway and made-up email domains with a clear message."""
    domain = email.rsplit("@", 1)[-1].lower().strip(".")
    if domain in DISPOSABLE or any(domain.endswith("." + d) for d in DISPOSABLE):
        raise HTTPException(status_code=400, detail="Please use your own email address, not a temporary one.")
    if os.environ.get("EMAIL_DNS_CHECK", "on").lower() in ("off", "0", "false", "no"):
        return
    if not await _domain_takes_mail(domain):
        raise HTTPException(status_code=400, detail=f"Emails can't be delivered to {domain}. Check the address for typos.")
