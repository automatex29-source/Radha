"""Aaj (Today): a small card on the home screen that gives people a reason to open Krish every morning.

It shows today's date the Indian way (tithi, paksha, lunar month and any festival), the Gita line of the day,
one top headline, and how many days in a row the person has opened Krish. None of it uses AI: the panchang is
worked out from the Sun and Moon (panchang.py), the verse comes from a fixed list (daily_verse.py) and the
headline is the free Google News feed that Discover already reads (and keeps for a few minutes).

The panchang is for New Delhi unless the browser sends a place (lat / lon), which only changes sunrise by
minutes; festivals and tithi are the same across India on almost every day.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import daily_verse
import discover
import panchang

logger = logging.getLogger("radha.today")

IST = daily_verse.IST
DELHI = (28.6139, 77.2090)
_cache: dict = {}  # (day, rounded lat, rounded lon) -> panchang; one sum per place per day


def _panchang(day: date, lat: float, lon: float) -> dict:
    key = (day.isoformat(), round(lat), round(lon))
    if key not in _cache:
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = panchang.day_panchang(day, lat, lon, IST)
    return _cache[key]


def _short_tithi(p: dict) -> str:
    """'Shukla Ekadashi' style: the paksha's first word and the tithi."""
    tithi = p.get("tithi") or ""
    if tithi in ("Purnima", "Amavasya") or tithi.startswith(("Shukla", "Krishna")):
        return tithi
    return f"{(p.get('paksha') or '').split(' ')[0]} {tithi}".strip()


async def mark_visit(db, user_id: str, today: str) -> dict:
    """Counts today as a visit and returns {days, best, new}: days in a row, the longest run, and whether this
    is the first visit today. Missing a day starts again from 1."""
    user = await db.users.find_one({"id": user_id}, {"visits": 1}) or {}
    v = user.get("visits") or {}
    last, days, best = v.get("last"), int(v.get("streak") or 0), int(v.get("best") or 0)
    if last == today:
        return {"days": max(days, 1), "best": max(best, days, 1), "new": False}
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    days = days + 1 if last == yesterday else 1
    best = max(best, days)
    await db.users.update_one({"id": user_id}, {"$set": {"visits": {"last": today, "streak": days, "best": best}}})
    return {"days": days, "best": best, "new": True}


async def card(db, user_id: str, lat: Optional[float] = None, lon: Optional[float] = None,
               lang: str = "en") -> dict:
    now = datetime.now(IST)
    day = now.date()
    today = day.isoformat()
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat, lon = DELHI
    out = {"date": today, "weekday": now.strftime("%A"), "dateLabel": f"{now.day} {now:%B}"}
    try:
        p = _panchang(day, lat, lon)
        out["panchang"] = {"tithi": _short_tithi(p), "month": (p.get("month") or "").replace(" (amanta)", ""),
                           "nakshatra": p.get("nakshatra"), "sunrise": (p.get("sunrise") or "").split(", ")[-1],
                           "festivals": p.get("festivals") or []}
    except Exception as exc:  # a sum gone wrong never blocks the home screen
        logger.warning("Today panchang failed: %s", exc)
        out["panchang"] = None
    ref, meaning = daily_verse.verse_for(today)
    out["verse"] = {"ref": ref, "text": meaning}
    try:
        stories = await discover.stories("top", lang, 3)
        out["news"] = stories[0] if stories else None
    except Exception as exc:
        logger.info("Today headline failed: %s", exc)
        out["news"] = None
    out["streak"] = await mark_visit(db, user_id, today)
    return out
