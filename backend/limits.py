"""Free plan limits.

Chats, pictures and new decks are counted per user per day (the day resets at
midnight India time). Automations are counted as the total the user has now, so
deleting one frees a slot. Counsellor chats are never counted.

A user whose account has plan "pro" has no limits. Set FREE_LIMITS=off to
switch every limit off (for testing).
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

DAILY = {"chat": 30, "picture": 3, "deck": 4}
TOTAL = {"automation": 1}

IST = timezone(timedelta(hours=5, minutes=30))

MESSAGES = {
    "chat": "You've used your 30 free chats for today. They refill at midnight, see you then! "
            "The Counsellor is always free.",
    "picture": "You've made your 3 free pictures for today. You can make more after midnight.",
    "deck": "You've made your 4 free decks for today. You can make more after midnight.",
    "automation": "The free plan has 1 automation. Delete your current one to make a new one.",
}


class LimitReached(Exception):
    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(MESSAGES[kind])


def enabled() -> bool:
    return os.environ.get("FREE_LIMITS", "on").strip().lower() not in ("off", "0", "false", "no")


def today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


async def _unlimited(db, user_id: str) -> bool:
    if not enabled():
        return True
    user = await db.users.find_one({"id": user_id}, {"plan": 1})
    return bool(user and user.get("plan") == "pro")


async def is_pro(db, user_id: str) -> bool:
    """True for Pro accounts (paid models are theirs)."""
    user = await db.users.find_one({"id": user_id}, {"plan": 1})
    return bool(user and user.get("plan") == "pro")


async def use(db, user_id: str, kind: str) -> None:
    """Count one chat, picture or deck for today. Raises LimitReached if the day's allowance is used up."""
    if await _unlimited(db, user_id):
        return
    doc = await db.usage.find_one_and_update(
        {"_id": f"{user_id}:{today()}"},
        {"$inc": {kind: 1}, "$setOnInsert": {"userId": user_id, "day": today()}},
        upsert=True, return_document=True,
    )
    if doc[kind] > DAILY[kind]:
        await refund(db, user_id, kind)
        raise LimitReached(kind)


async def check_daily(db, user_id: str, kind: str) -> None:
    """Raise LimitReached if today's allowance is already used up, without counting a use."""
    if await _unlimited(db, user_id):
        return
    doc = await db.usage.find_one({"_id": f"{user_id}:{today()}"}) or {}
    if doc.get(kind, 0) >= DAILY[kind]:
        raise LimitReached(kind)


async def refund(db, user_id: str, kind: str) -> None:
    """Give back one use, e.g. when a picture failed to be made."""
    if not enabled():
        return
    await db.usage.update_one({"_id": f"{user_id}:{today()}", kind: {"$gt": 0}}, {"$inc": {kind: -1}})


async def check_total(db, user_id: str, kind: str) -> None:
    """Raise LimitReached if the user already has as many automations as the free plan keeps."""
    if await _unlimited(db, user_id):
        return
    collection = {"automation": db.automations}[kind]
    if await collection.count_documents({"userId": user_id}) >= TOTAL[kind]:
        raise LimitReached(kind)


def http_error(exc: LimitReached) -> HTTPException:
    return HTTPException(status_code=429, detail=str(exc))


async def require(db, user_id: str, kind: str, peek: bool = False) -> None:
    """use() or check_total() for an endpoint: turns a reached limit into a friendly 429.

    With peek=True a daily allowance is only checked, not used."""
    try:
        if kind in DAILY and peek:
            await check_daily(db, user_id, kind)
        elif kind in DAILY:
            await use(db, user_id, kind)
        else:
            await check_total(db, user_id, kind)
    except LimitReached as exc:
        raise http_error(exc)


async def summary(db, user_id: str) -> dict:
    """What the user has used and their limits, for the app to show."""
    if await _unlimited(db, user_id):
        return {"plan": "unlimited"}
    doc = await db.usage.find_one({"_id": f"{user_id}:{today()}"}) or {}
    return {
        "plan": "free",
        "chats": {"used": doc.get("chat", 0), "limit": DAILY["chat"]},
        "pictures": {"used": doc.get("picture", 0), "limit": DAILY["picture"]},
        "decks": {"used": doc.get("deck", 0), "limit": DAILY["deck"]},
        "automations": {"used": await db.automations.count_documents({"userId": user_id}), "limit": TOTAL["automation"]},
    }
