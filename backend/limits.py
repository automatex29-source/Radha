"""Plan limits: Basic (free), Pro and Max.

Chat is never limited. The heavy features are: app builds (each message sent
in the App Builder), pictures, new decks and videos, counted per user per day
(the day resets at midnight India time). Automations are counted as the total
the user has now, so deleting one frees a slot. Publishing apps is for Pro and
Max only.

A user's plan is the `plan` field on their account ("basic" when missing).
Set FREE_LIMITS=off to switch every limit off (for testing).
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

PLANS = {
    "basic": {
        "name": "Basic", "price": 0,
        "daily": {"build": 5, "picture": 3, "deck": 4, "video": 1},
        "total": {"automation": 1},
        "publish": False, "premium": False,
    },
    "pro": {
        "name": "Pro", "price": 299,
        "daily": {"build": 30, "picture": 25, "deck": 15, "video": 5},
        "total": {"automation": 10},
        "publish": True, "premium": True,
    },
    "max": {
        "name": "Max", "price": 699,
        "daily": {"build": 100, "picture": 80, "deck": 50, "video": 20},
        "total": {"automation": 30},
        "publish": True, "premium": True,
    },
}
ORDER = ["basic", "pro", "max"]
DAILY_KINDS = ("build", "picture", "deck", "video")
TOTAL_KINDS = ("automation",)

IST = timezone(timedelta(hours=5, minutes=30))

WHAT = {"build": "app builds", "picture": "pictures", "deck": "new decks", "video": "videos"}
PUBLISH_MESSAGE = "Publishing apps is part of the Pro and Max plans. You can still build, preview and download your app for free."


class LimitReached(Exception):
    def __init__(self, kind: str, plan: str = "basic"):
        self.kind = kind
        self.plan = plan
        super().__init__(message(kind, plan))


def message(kind: str, plan: str) -> str:
    info = PLANS[plan]
    nxt = ORDER[ORDER.index(plan) + 1] if plan != ORDER[-1] else None
    more = f" Upgrade to {PLANS[nxt]['name']} for more." if nxt else ""
    if kind == "automation":
        n = info["total"]["automation"]
        return (f"The {info['name']} plan keeps {n} automation{'s' if n != 1 else ''}. "
                f"Delete one to make a new one.{more}")
    return (f"You've used today's {info['daily'][kind]} {WHAT[kind]} on the {info['name']} plan. "
            f"They refill at midnight.{more} Chat is always unlimited.")


def enabled() -> bool:
    return os.environ.get("FREE_LIMITS", "on").strip().lower() not in ("off", "0", "false", "no")


def today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


async def plan_of(db, user_id: str) -> str:
    user = await db.users.find_one({"id": user_id}, {"plan": 1})
    plan = (user or {}).get("plan") or "basic"
    return plan if plan in PLANS else "basic"


async def is_pro(db, user_id: str) -> bool:
    """True for paid plans (Pro or Max), which get the premium AI models."""
    return PLANS[await plan_of(db, user_id)]["premium"]


async def use(db, user_id: str, kind: str) -> None:
    """Count one build, picture, deck or video for today. Raises LimitReached if the day's allowance is used up."""
    if not enabled():
        return
    plan = await plan_of(db, user_id)
    doc = await db.usage.find_one_and_update(
        {"_id": f"{user_id}:{today()}"},
        {"$inc": {kind: 1}, "$setOnInsert": {"userId": user_id, "day": today()}},
        upsert=True, return_document=True,
    )
    if doc[kind] > PLANS[plan]["daily"][kind]:
        await refund(db, user_id, kind)
        raise LimitReached(kind, plan)


async def check_daily(db, user_id: str, kind: str) -> None:
    """Raise LimitReached if today's allowance is already used up, without counting a use."""
    if not enabled():
        return
    plan = await plan_of(db, user_id)
    doc = await db.usage.find_one({"_id": f"{user_id}:{today()}"}) or {}
    if doc.get(kind, 0) >= PLANS[plan]["daily"][kind]:
        raise LimitReached(kind, plan)


async def refund(db, user_id: str, kind: str) -> None:
    """Give back one use, e.g. when a picture failed to be made."""
    if not enabled():
        return
    await db.usage.update_one({"_id": f"{user_id}:{today()}", kind: {"$gt": 0}}, {"$inc": {kind: -1}})


async def check_total(db, user_id: str, kind: str) -> None:
    """Raise LimitReached if the user already has as many automations as their plan keeps."""
    if not enabled():
        return
    plan = await plan_of(db, user_id)
    collection = {"automation": db.automations}[kind]
    if await collection.count_documents({"userId": user_id}) >= PLANS[plan]["total"][kind]:
        raise LimitReached(kind, plan)


async def can_publish(db, user_id: str) -> bool:
    return not enabled() or PLANS[await plan_of(db, user_id)]["publish"]


# 402 tells the app this is a plan limit, so it can offer the plans page.
def http_error(exc: LimitReached) -> HTTPException:
    return HTTPException(status_code=402, detail=str(exc))


async def require(db, user_id: str, kind: str, peek: bool = False) -> None:
    """use() or check_total() for an endpoint: turns a reached limit into a friendly 402.

    With peek=True a daily allowance is only checked, not used."""
    try:
        if kind in DAILY_KINDS and peek:
            await check_daily(db, user_id, kind)
        elif kind in DAILY_KINDS:
            await use(db, user_id, kind)
        else:
            await check_total(db, user_id, kind)
    except LimitReached as exc:
        raise http_error(exc)


async def require_publish(db, user_id: str) -> None:
    if not await can_publish(db, user_id):
        raise HTTPException(status_code=402, detail=PUBLISH_MESSAGE)


def public_plans() -> list:
    return [{"id": p, **PLANS[p]} for p in ORDER]


async def summary(db, user_id: str) -> dict:
    """The user's plan, what they've used today and every plan, for the Plans page."""
    plan = await plan_of(db, user_id)
    doc = await db.usage.find_one({"_id": f"{user_id}:{today()}"}) or {}
    info = PLANS[plan]
    used = {k: {"used": doc.get(k, 0), "limit": info["daily"][k]} for k in DAILY_KINDS}
    used["automation"] = {"used": await db.automations.count_documents({"userId": user_id}),
                          "limit": info["total"]["automation"]}
    return {"plan": plan, "limitsOn": enabled(), "canPublish": await can_publish(db, user_id),
            "usage": used, "plans": public_plans()}
