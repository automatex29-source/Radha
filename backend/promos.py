"""Offer codes (e.g. LAUNCH50) that take a percentage off one Pro or Max payment.

The owner makes codes on the Users page. Each code has a percentage off (1 to 90, since Razorpay can't take a
payment of ₹0), an optional limit on how many payments can use it, an optional last day, and can be switched
off at any time. One person can use a code once. A use is counted when the payment goes through, not when
the checkout opens, so a closed checkout doesn't waste a use.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

MAX_PERCENT = 90
CODE_RE = re.compile(r"^[A-Z0-9_-]{3,24}$")


class PromoError(Exception):
    """Why a code can't be used, worded for the user."""


def normalize(code: str) -> str:
    return (code or "").strip().upper()


def discounted(amount_paise: int, percent_off: int) -> int:
    """The price after the discount, rounded to whole rupees and never under ₹1."""
    rupees = round(amount_paise * (100 - percent_off) / 100 / 100)
    return max(1, rupees) * 100


def public(doc: dict) -> dict:
    return {"code": doc["code"], "percentOff": doc["percentOff"], "maxUses": doc.get("maxUses") or 0,
            "uses": doc.get("uses", 0), "expiresAt": doc.get("expiresAt"), "active": doc.get("active", True),
            "createdAt": doc.get("createdAt")}


async def create(db, code: str, percent_off: int, max_uses: int = 0, expires_at: Optional[str] = None) -> dict:
    code = normalize(code)
    if not CODE_RE.match(code):
        raise PromoError("A code is 3 to 24 letters or numbers, like LAUNCH50.")
    if not 1 <= int(percent_off) <= MAX_PERCENT:
        raise PromoError(f"The discount must be between 1% and {MAX_PERCENT}%.")
    if await db.promo_codes.find_one({"code": code}):
        raise PromoError("That code already exists.")
    if expires_at:
        expires_at = _end_of_day(expires_at)
    doc = {"code": code, "percentOff": int(percent_off), "maxUses": max(0, int(max_uses or 0)), "uses": 0,
           "expiresAt": expires_at or None, "active": True, "createdAt": datetime.now(timezone.utc).isoformat()}
    await db.promo_codes.insert_one(doc)
    return public(doc)


def _end_of_day(day: str) -> str:
    """A last day like 2026-11-30 means the code works until midnight India time at the end of that day."""
    try:
        d = datetime.strptime(day[:10], "%Y-%m-%d")
    except ValueError:
        raise PromoError("Give the last day as a date, like 2026-11-30.")
    ist = timezone(timedelta(hours=5, minutes=30))
    return (d.replace(tzinfo=ist) + timedelta(days=1)).astimezone(timezone.utc).isoformat()


async def set_active(db, code: str, active: bool) -> Optional[dict]:
    await db.promo_codes.update_one({"code": normalize(code)}, {"$set": {"active": bool(active)}})
    doc = await db.promo_codes.find_one({"code": normalize(code)})
    return public(doc) if doc else None


async def list_all(db) -> list:
    docs = await db.promo_codes.find({}).sort("createdAt", -1).to_list(500)
    return [public(d) for d in docs]


async def check(db, code: str, user_id: str, plan: str) -> dict:
    """The code's details when this user can use it on this plan now; PromoError otherwise."""
    doc = await db.promo_codes.find_one({"code": normalize(code)})
    if not doc or not doc.get("active", True):
        raise PromoError("That code isn't valid.")
    if doc.get("expiresAt") and doc["expiresAt"] < datetime.now(timezone.utc).isoformat():
        raise PromoError("That code has expired.")
    if doc.get("maxUses") and doc.get("uses", 0) >= doc["maxUses"]:
        raise PromoError("That code has been used up.")
    if await db.payments.find_one({"userId": user_id, "promoCode": doc["code"], "status": "paid"}):
        raise PromoError("You've already used that code.")
    return public(doc)


async def count_use(db, code: str) -> None:
    await db.promo_codes.update_one({"code": normalize(code)}, {"$inc": {"uses": 1}})
