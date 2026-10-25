"""Plan limits: Basic (free), Pro and Max.

Chat on Krish Basic is never limited. Everything that costs real money to make (app builds, pictures, decks,
videos and messages on the premium models) runs down one usage meter, like Claude's own limit: each request
uses credits by how big it really is (the length of what's asked, the seconds of video, a premium or free
engine), and the meter refills a few hours after the first use (a "session"). A weekly meter on top keeps a
heavy user's month safe on cost. Automations are counted as the total the user has now, so deleting one frees
a slot. Publishing apps is for Pro and Max only.

A user's plan is the `plan` field on their account ("basic" when missing). A paid
plan bought in the app also has `planExpiresAt` (an ISO time); once that passes the
user is back on Basic. A plan set by hand without an expiry never runs out.
Set FREE_LIMITS=off to switch every limit off (for testing).
"""
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

PLANS = {
    "basic": {
        "name": "Basic", "price": 0,
        "meter": {"session": 40, "week": 250},
        "total": {"automation": 1},
        "publish": False, "premium": False,
        "quality": {"media": "free", "videoSeconds": 8, "uploadMb": 20},
    },
    "pro": {
        "name": "Pro", "price": 299,
        "meter": {"session": 400, "week": 2000},
        "total": {"automation": 10},
        "publish": True, "premium": True,
        "quality": {"media": "premium", "videoSeconds": 12, "uploadMb": 50},
    },
    "max": {
        "name": "Max", "price": 699,
        "meter": {"session": 1200, "week": 6000},
        "total": {"automation": 30},
        "publish": True, "premium": True,
        "quality": {"media": "premium", "videoSeconds": 60, "uploadMb": 100},
    },
}
ORDER = ["basic", "pro", "max"]
METER_KINDS = ("build", "picture", "deck", "video", "chat")
TOTAL_KINDS = ("automation",)
SESSION_HOURS = 5
WEEK_DAYS = 7

IST = timezone(timedelta(hours=5, minutes=30))

PUBLISH_MESSAGE = "Publishing apps is part of the Pro and Max plans. You can still build, preview and download your app for free."


def cost(kind: str, size: Optional[int] = None, plan: str = "basic") -> int:
    """Credits one request uses, by how much it really asks for.

    build: 2, plus 1 for every 500 characters of the request (up to 20). chat (premium models only): 1, plus 1
    for every 3,000 characters sent (up to 10). picture: 10 on the premium engine, 2 on the free one. deck: 5.
    video: credits for each second, 10 on the premium engine, 1 on the free one."""
    premium = quality_of(plan)["media"] == "premium"
    if kind == "build":
        return min(20, 2 + int(size or 0) // 500)
    if kind == "chat":
        return min(10, 1 + int(size or 0) // 3000)
    if kind == "picture":
        return (10 if premium else 2) * max(1, int(size or 1))
    if kind == "deck":
        return 5
    if kind == "video":
        return (10 if premium else 1) * max(1, int(size or 8))
    raise ValueError(kind)


class LimitReached(Exception):
    def __init__(self, kind: str, plan: str = "basic", text: str = ""):
        self.kind = kind
        self.plan = plan
        super().__init__(text or message(kind, plan))


def _when(ts: float) -> str:
    at = datetime.fromtimestamp(ts, IST)
    left = max(0, ts - time.time())
    if left < 20 * 3600:
        hours, minutes = int(left // 3600), int(left % 3600 // 60)
        wait = f"{hours}h {minutes}m" if hours else f"{max(1, minutes)}m"
        return f"at {at.strftime('%-I:%M %p')} (in {wait})"
    return f"on {at.strftime('%a %-d %b')}"


def message(kind: str, plan: str, resets: Optional[float] = None, week: bool = False) -> str:
    info = PLANS[plan]
    nxt = ORDER[ORDER.index(plan) + 1] if plan != ORDER[-1] else None
    more = f" Upgrade to {PLANS[nxt]['name']} for more." if nxt else ""
    if kind == "automation":
        n = info["total"]["automation"]
        return (f"The {info['name']} plan keeps {n} automation{'s' if n != 1 else ''}. "
                f"Delete one to make a new one.{more}")
    which = "this week's" if week else "this session's"
    when = f" It refills {_when(resets)}." if resets else ""
    return (f"You've used {which} usage on the {info['name']} plan.{when}{more} "
            "Chat on Krish Basic is always unlimited.")


def enabled() -> bool:
    return os.environ.get("FREE_LIMITS", "on").strip().lower() not in ("off", "0", "false", "no")


def today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def plan_from(user: dict) -> str:
    """The plan a user account is on right now: an unknown or expired plan counts as Basic."""
    plan = (user or {}).get("plan") or "basic"
    if plan not in PLANS:
        return "basic"
    expires = (user or {}).get("planExpiresAt")
    if plan != "basic" and expires and expires <= datetime.now(timezone.utc).isoformat():
        return "basic"
    return plan


async def plan_of(db, user_id: str) -> str:
    return plan_from(await db.users.find_one({"id": user_id}, {"plan": 1, "planExpiresAt": 1}))


async def is_pro(db, user_id: str) -> bool:
    """True for paid plans (Pro or Max), which get the premium AI models."""
    return PLANS[await plan_of(db, user_id)]["premium"]


async def quality(db, user_id: str) -> dict:
    """What the user's plan gets beyond the daily counts: premium picture and video engines ("media"), the
    longest video and the biggest upload."""
    return quality_of(await plan_of(db, user_id))


async def upload_bytes(db, user_id: str) -> int:
    return quality_of(await plan_of(db, user_id))["uploadMb"] * 1024 * 1024


def quality_of(plan: str) -> dict:
    return PLANS[plan if plan in PLANS else "basic"]["quality"]


def _meter_id(user_id: str) -> str:
    return f"{user_id}:meter"  # starts with the user id, so deleting an account's usage removes it too


async def _meter(db, user_id: str) -> dict:
    """The user's meter, with a session or week that has run out started afresh."""
    now = time.time()
    doc = await db.usage.find_one({"_id": _meter_id(user_id)}) or {}
    fresh = {}
    if not doc.get("sessionStart") or now >= doc["sessionStart"] + SESSION_HOURS * 3600:
        fresh.update(sessionStart=now, sessionUsed=0)
    if not doc.get("weekStart") or now >= doc["weekStart"] + WEEK_DAYS * 86400:
        fresh.update(weekStart=now, weekUsed=0)
    if fresh:
        # Only the request that sees the old session resets it, so two at once don't wipe each other's use.
        match = {"_id": _meter_id(user_id), **({"sessionStart": doc["sessionStart"]} if "sessionStart" in fresh
                                               and doc.get("sessionStart") else {}),
                 **({"weekStart": doc["weekStart"]} if "weekStart" in fresh and doc.get("weekStart") else {})}
        await db.usage.update_one(match, {"$set": {**fresh, "userId": user_id}}, upsert=not doc)
        doc = await db.usage.find_one({"_id": _meter_id(user_id)}) or {**doc, **fresh}
    return doc


async def _spend(db, user_id: str, plan: str, kind: str, credits: int) -> None:
    limit = PLANS[plan]["meter"]
    doc = await _meter(db, user_id)
    done = await db.usage.find_one_and_update(
        {"_id": _meter_id(user_id), "sessionUsed": {"$lte": limit["session"] - credits},
         "weekUsed": {"$lte": limit["week"] - credits}},
        {"$inc": {"sessionUsed": credits, "weekUsed": credits}}, return_document=True)
    if done:
        return
    week = doc.get("weekUsed", 0) + credits > limit["week"]
    resets = doc["weekStart"] + WEEK_DAYS * 86400 if week else doc["sessionStart"] + SESSION_HOURS * 3600
    left = (limit["week"] - doc.get("weekUsed", 0)) if week else (limit["session"] - doc.get("sessionUsed", 0))
    text = message(kind, plan, resets, week)
    if left > 0 and credits > left:  # a big request when a little is left: say a smaller one still fits
        text = (f"This needs {credits} credits and you have {left} left. A smaller request uses fewer, "
                f"or the full meter is back {_when(resets)}.")
    raise LimitReached(kind, plan, text)


async def use_premium(db, user_id: str, size: int = 0) -> bool:
    """Use credits for one message on a premium model (Claude, GPT), by how much is sent. False when the meter
    is empty, so the chat answers with Krish Basic instead: premium messages cost money each."""
    if not enabled():
        return True
    plan = await plan_of(db, user_id)
    try:
        await _spend(db, user_id, plan, "chat", cost("chat", size, plan))
    except LimitReached:
        return False
    return True


async def use(db, user_id: str, kind: str, size: Optional[int] = None) -> None:
    """Use the credits one build, picture, deck or video takes (see cost). Raises LimitReached when the meter
    doesn't cover it."""
    if enabled():
        plan = await plan_of(db, user_id)
        await _spend(db, user_id, plan, kind, cost(kind, size, plan))
    if kind in ("picture", "deck", "video"):  # for the owner's numbers; builds are counted with their message
        import monitor  # imported here: monitor imports limits
        await monitor.count(db, user_id, kind)


async def check_left(db, user_id: str, kind: str, size: Optional[int] = None) -> None:
    """Raise LimitReached if the meter can't cover this request, without using anything."""
    if not enabled():
        return
    plan = await plan_of(db, user_id)
    doc, limit, need = await _meter(db, user_id), PLANS[plan]["meter"], cost(kind, size, plan)
    if doc.get("sessionUsed", 0) + need > limit["session"] or doc.get("weekUsed", 0) + need > limit["week"]:
        week = doc.get("weekUsed", 0) + need > limit["week"]
        raise LimitReached(kind, plan, message(kind, plan, doc["weekStart"] + WEEK_DAYS * 86400 if week
                                               else doc["sessionStart"] + SESSION_HOURS * 3600, week))


async def refund(db, user_id: str, kind: str, size: Optional[int] = None) -> None:
    """Give back what a request used, e.g. when a picture failed to be made."""
    if not enabled():
        return
    credits = cost(kind, size, await plan_of(db, user_id))
    await db.usage.update_one({"_id": _meter_id(user_id), "sessionUsed": {"$gte": credits}},
                              {"$inc": {"sessionUsed": -credits}})
    await db.usage.update_one({"_id": _meter_id(user_id), "weekUsed": {"$gte": credits}},
                              {"$inc": {"weekUsed": -credits}})


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


async def require(db, user_id: str, kind: str, peek: bool = False, size: Optional[int] = None) -> None:
    """use() or check_total() for an endpoint: turns a reached limit into a friendly 402.

    With peek=True the meter is only checked, not used."""
    try:
        if kind in METER_KINDS and peek:
            await check_left(db, user_id, kind, size)
        elif kind in METER_KINDS:
            await use(db, user_id, kind, size)
        else:
            await check_total(db, user_id, kind)
    except LimitReached as exc:
        raise http_error(exc)


async def require_publish(db, user_id: str) -> None:
    if not await can_publish(db, user_id):
        raise HTTPException(status_code=402, detail=PUBLISH_MESSAGE)


def public_plans() -> list:
    return [{"id": p, **PLANS[p]} for p in ORDER]


def meter_view(plan: str, doc: dict) -> dict:
    limit = PLANS[plan]["meter"]
    now = time.time()
    session_on = doc.get("sessionStart") and now < doc["sessionStart"] + SESSION_HOURS * 3600
    week_on = doc.get("weekStart") and now < doc["weekStart"] + WEEK_DAYS * 86400
    return {
        "session": {"used": doc.get("sessionUsed", 0) if session_on else 0, "limit": limit["session"],
                    "resetsAt": doc["sessionStart"] + SESSION_HOURS * 3600 if session_on else None,
                    "hours": SESSION_HOURS},
        "week": {"used": doc.get("weekUsed", 0) if week_on else 0, "limit": limit["week"],
                 "resetsAt": doc["weekStart"] + WEEK_DAYS * 86400 if week_on else None},
    }


async def summary(db, user_id: str) -> dict:
    """The user's plan, their usage meter and every plan, for the Plans page."""
    plan = await plan_of(db, user_id)
    doc = await db.usage.find_one({"_id": _meter_id(user_id)}) or {}
    used = {"automation": {"used": await db.automations.count_documents({"userId": user_id}),
                           "limit": PLANS[plan]["total"]["automation"]}}
    return {"plan": plan, "limitsOn": enabled(), "canPublish": await can_publish(db, user_id),
            "meter": meter_view(plan, doc), "usage": used, "plans": public_plans(),
            "costs": {"build": [cost("build", 0, plan), cost("build", 10**6, plan)],
                      "picture": cost("picture", 1, plan), "deck": cost("deck", None, plan),
                      "videoSecond": cost("video", 1, plan), "chat": [cost("chat", 0, plan), cost("chat", 10**6, plan)]}}
