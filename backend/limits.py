"""Plan limits: Basic (free), Pro and Max.

Chat on Krish Basic is unlimited on Pro and Max; the free plan gets BASIC_CHAT_SESSION messages a session, and a
taste of Krish Pro (PRO_TASTE_WEEK credits a week, on Claude Haiku). Everything else that costs real money to make (app builds, pictures, decks,
videos and messages on the premium models) runs down one usage meter, like Claude's own limit: each request
uses credits by how big it really is (the length of what's asked, the seconds of video, a premium or free
engine), and the meter refills a few hours after the first use (a "session"). A weekly meter on top keeps a
heavy user's month safe on cost. Automations are counted as the total the user has now, so deleting one frees
a slot. Publishing apps is for Pro and Max only.

On Pro and Max a credit is worth CREDIT_RUPEES of real AI cost, and each request uses what it really costs on
the engine that does it (Claude Haiku is about 20x cheaper than Claude Sonnet). So a paid plan's meter is its AI
budget: AI_SHARE of what the plan brings in after Razorpay's fee, spread over the weeks of a month. No paid user
can cost more than that, and raising a price raises its meter with it.

A user's plan is the `plan` field on their account ("basic" when missing). A paid
plan bought in the app also has `planExpiresAt` (an ISO time); once that passes the
user is back on Basic. A plan set by hand without an expiry never runs out.
Set FREE_LIMITS=off to switch every limit off (for testing).
"""
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

# Paid plans' credits: what a credit is worth, and how much of a plan's price the AI may use.
CREDIT_RUPEES = 0.10
RUPEES_PER_USD = float(os.environ.get("USD_INR", "88"))
AI_SHARE = 0.50
RAZORPAY_FEE = 0.0236  # 2% plus 18% GST on it
WEEKS_PER_MONTH = 4.33


def paid_meter(price: int) -> dict:
    """A paid plan's meter from its price: a week holds a week's share of its AI budget, a session most of it
    (so one big app build always fits)."""
    week = round(price * (1 - RAZORPAY_FEE) * AI_SHARE / WEEKS_PER_MONTH / CREDIT_RUPEES)
    return {"session": round(week * 0.75), "week": week}


PLANS = {
    "basic": {
        "name": "Basic", "price": 0,
        "meter": {"session": 40, "week": 250},
        "total": {"automation": 1},
        # What automations may do: the shortest repeat (None = daily or weekly only), Thorough mode, premium
        # models, starting on events (a new email) and acting without asking first.
        "automations": {"minInterval": None, "thorough": False, "premiumModels": False, "events": False,
                        "noAsk": False},
        "publish": False, "premium": False,
        "quality": {"media": "free", "videoSeconds": 8, "uploadMb": 20},
    },
    "pro": {
        "name": "Pro", "price": 499, "listPrice": 999,
        "meter": paid_meter(499),
        "total": {"automation": 10},
        "automations": {"minInterval": 60, "thorough": False, "premiumModels": True, "events": True,
                        "noAsk": False},
        "publish": True, "premium": True,
        "quality": {"media": "premium", "videoSeconds": 12, "uploadMb": 50},
    },
    "max": {
        "name": "Max", "price": 1299, "listPrice": 1999,
        "meter": paid_meter(1299),
        "total": {"automation": 30},
        "automations": {"minInterval": 15, "thorough": True, "premiumModels": True, "events": True,
                        "noAsk": True},
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


# What the premium chat models cost, in US dollars per million tokens (input, output). An unknown paid model is
# counted at the dearest price, so the meter never counts less than it costs. The old Haiku id runs on Haiku 5.5.
MODEL_USD = {
    "claude-haiku-5-5": (0.10, 0.50),
    "krish-basic-plus": (0.10, 0.50),
    "claude-haiku-4-5-20251001": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "gpt-5.4": (2.50, 15.00),
}
_DEAREST_USD = (5.00, 25.00)
_CHARS_PER_TOKEN = 3
_SAFETY = 1.3  # room for tool steps (web search, reading files) and longer answers than usual


def _model_usd(model: str) -> tuple:
    return MODEL_USD.get(model, _DEAREST_USD)


def _credits(usd: float) -> int:
    return max(1, math.ceil(usd * _SAFETY * RUPEES_PER_USD / CREDIT_RUPEES))


def chat_usd(model: str, size: int = 0, think: bool = False) -> float:
    """What one premium message costs: the chat sent (size characters), the system prompt (cached, a tenth of the
    price), and the answer (more with Think)."""
    usd_in, usd_out = _model_usd(model)
    tokens_in = int(size or 0) / _CHARS_PER_TOKEN + 3000 * 0.1
    tokens_out = 700 + (3000 if think else 0)
    return (tokens_in * usd_in + tokens_out * usd_out) / 1e6


def build_usd(model: str, size: int = 0) -> float:
    """What one App Builder turn costs on a premium model: about 8 steps, each sending the app's files and the
    request and writing code."""
    usd_in, usd_out = _model_usd(model)
    steps = 8
    tokens_in = steps * (7000 + int(size or 0) / _CHARS_PER_TOKEN)
    tokens_out = steps * 1200
    return (tokens_in * usd_in + tokens_out * usd_out) / 1e6


def picture_usd() -> float:
    """What a premium picture costs on the engine that makes it (see media.premium_picture_usd)."""
    import media  # imported here: media's tools import limits

    return media.premium_picture_usd()


VIDEO_SECOND_USD = 0.10


def cost(kind: str, size: Optional[int] = None, plan: str = "basic", model: Optional[str] = None,
         think: bool = False) -> int:
    """Credits one request uses, by how much it really asks for.

    Basic (free engines): build 2, plus 1 for every 500 characters of the request (up to 20); picture 2; deck 5;
    video 1 a second. On Pro and Max a credit is CREDIT_RUPEES of real cost: a premium message or an App Builder
    turn on a premium `model` uses what it costs on that model, a picture what the premium engine charges, a video
    second VIDEO_SECOND_USD. Builds on the free engines cost the same as on Basic."""
    premium = quality_of(plan)["media"] == "premium"
    paid_model = premium and bool(model) and model.startswith(("claude", "gpt"))
    if kind == "build":
        if paid_model:
            return _credits(build_usd(model, size))
        return min(20, 2 + int(size or 0) // 500)
    if kind == "chat":
        if premium:
            return _credits(chat_usd(model or "claude-haiku-5-5", size, think))
        return min(10, 1 + int(size or 0) // 3000)
    if kind == "picture":
        each = _credits(picture_usd()) if premium and picture_usd() else 2
        return each * max(1, int(size or 1))
    if kind == "deck":
        return 5
    if kind == "video":
        return (_credits(VIDEO_SECOND_USD) if premium else 1) * max(1, int(size or 8))
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
        wait = (f"{hours} hour{'s' if hours != 1 else ''}" + (f" {minutes} min" if minutes else "")) if hours \
            else f"{max(1, minutes)} min"
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
    chat = " Chat on Krish Basic stays unlimited." if plan != "basic" else ""
    return f"You've used {which} usage on the {info['name']} plan.{when}{more}{chat}"


# The free plan: Krish Basic messages a session, and a weekly taste of Krish Pro (in paid-plan credits, on Haiku).
BASIC_CHAT_SESSION = 40
PRO_TASTE_WEEK = 15
PRO_TASTE_MODEL = "claude-haiku-5-5"
BASIC_BOOST_WEEK = 50  # Krish Basic messages a week answered by Claude Haiku on the free plan, then the free engines


async def _count(db, key: str, user_id: str, seconds: int, limit: int, amount: int) -> tuple:
    """Add `amount` to a counter that starts afresh every `seconds`, if it stays within `limit`.
    Returns (added, when it refills, the counter's record)."""
    now = time.time()
    doc = await db.usage.find_one({"_id": key}) or {}
    if not doc.get("start") or now >= doc["start"] + seconds:
        match = {"_id": key, **({"start": doc["start"]} if doc.get("start") else {})}
        await db.usage.update_one(match, {"$set": {"start": now, "used": 0, "told": False, "userId": user_id}},
                                  upsert=not doc)
        doc = await db.usage.find_one({"_id": key}) or {"start": now, "used": 0}
    done = await db.usage.find_one_and_update({"_id": key, "used": {"$lte": limit - amount}},
                                              {"$inc": {"used": amount}}, return_document=True)
    return bool(done), doc["start"] + seconds, done or doc


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, IST).strftime("%-I:%M %p")


async def use_basic_chat(db, user_id: str) -> None:
    """Count one Krish Basic message on the free plan (Pro and Max chat on it without a limit). Raises
    LimitReached once the session's messages are used."""
    if not enabled() or await plan_of(db, user_id) != "basic":
        return
    ok, refills, _ = await _count(db, f"{user_id}:chat", user_id, SESSION_HOURS * 3600, BASIC_CHAT_SESSION, 1)
    if not ok:
        raise LimitReached("chat", "basic", "You've used this session's free messages. Upgrade to Pro, or wait "
                                            f"until {_clock(refills)}.")


async def use_basic_boost(db, user_id: str) -> bool:
    """True when this free-plan Krish Basic message is one of the week's first BASIC_BOOST_WEEK, which Claude
    Haiku answers; after them the free engines answer, with nothing said."""
    if not enabled():
        return False
    ok, _, _ = await _count(db, f"{user_id}:basic-boost", user_id, WEEK_DAYS * 86400, BASIC_BOOST_WEEK, 1)
    return ok


async def use_pro_taste(db, user_id: str, size: int = 0) -> tuple:
    """Use the free plan's weekly taste of Krish Pro for one message of `size` characters, on Claude Haiku.
    Returns (True, "") when it covers it, else (False, a message for the first time this week it doesn't, else "")."""
    if not enabled():
        return True, ""
    credits = _credits(chat_usd(PRO_TASTE_MODEL, size))
    key = f"{user_id}:pro-taste"
    ok, refills, doc = await _count(db, key, user_id, WEEK_DAYS * 86400, PRO_TASTE_WEEK, credits)
    if ok:
        return True, ""
    first = await db.usage.update_one({"_id": key, "told": {"$ne": True}}, {"$set": {"told": True}})
    day = datetime.fromtimestamp(refills, IST).strftime("%A")
    return False, ("You've used this week's free Krish Pro answers. Upgrade to Pro, or they refill on "
                   f"{day}." if first.modified_count else "")


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


async def use_premium(db, user_id: str, size: int = 0, model: Optional[str] = None, think: bool = False) -> bool:
    """Use credits for one message on a premium model (Claude, GPT), by what it costs on that model for how much
    is sent. False when the meter is empty, so the chat answers with Krish Basic instead: premium messages cost
    money each."""
    if not enabled():
        return True
    plan = await plan_of(db, user_id)
    try:
        await _spend(db, user_id, plan, "chat", cost("chat", size, plan, model, think))
    except LimitReached:
        return False
    return True


async def use(db, user_id: str, kind: str, size: Optional[int] = None, model: Optional[str] = None) -> None:
    """Use the credits one build, picture, deck or video takes (see cost). Raises LimitReached when the meter
    doesn't cover it."""
    if enabled():
        plan = await plan_of(db, user_id)
        await _spend(db, user_id, plan, kind, cost(kind, size, plan, model))
    if kind in ("picture", "deck", "video"):  # for the owner's numbers; builds are counted with their message
        import monitor  # imported here: monitor imports limits
        await monitor.count(db, user_id, kind)


# The meter also follows the tokens a reply really used: every TOKENS_PER_CREDIT tokens (what the AI read and
# wrote, across all of a build's steps) is one credit. The credits taken before the reply count toward it.
TOKENS_PER_CREDIT = 5000
MAX_TOKEN_CREDITS = 80  # one reply never takes more than this


def token_credits(tokens: int) -> int:
    return min(MAX_TOKEN_CREDITS, -(-max(0, int(tokens)) // TOKENS_PER_CREDIT))


async def charge_tokens(db, user_id: str, tokens: int, prepaid: int = 0) -> int:
    """After a reply: take the credits its tokens used beyond what was taken up front. It can take the meter
    past its limit (the work is done); the next request then waits for the refill. Returns the credits taken."""
    if not enabled() or not user_id:
        return 0
    extra = token_credits(tokens) - prepaid
    if extra <= 0:
        return 0
    await _meter(db, user_id)
    await db.usage.update_one({"_id": _meter_id(user_id)}, {"$inc": {"sessionUsed": extra, "weekUsed": extra}})
    return extra


# Fair use: every reply (chat included) adds the tokens it really used to a daily count per user, so no one
# account can use up the shared allowance our AI providers give us. Normal use never comes near it; a script or a
# copy-paste loop does. It resets at midnight India time. FAIR_USE_<PLAN> (tokens a day) overrides the default.
FAIR_USE_TOKENS = {"basic": 150_000, "pro": 1_500_000, "max": 4_000_000}


def fair_use_limit(plan: str) -> int:
    env = os.environ.get(f"FAIR_USE_{plan.upper()}", "").strip()
    return int(env) if env.isdigit() else FAIR_USE_TOKENS.get(plan, FAIR_USE_TOKENS["basic"])


def _fair_id(user_id: str) -> str:
    return f"{user_id}:fair"


def next_midnight() -> float:
    now = datetime.now(IST)
    return (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


async def _fair_used(db, user_id: str) -> int:
    doc = await db.usage.find_one({"_id": _fair_id(user_id)}) or {}
    return int(doc.get("tokens", 0)) if doc.get("day") == today() else 0


async def add_fair_use(db, user_id: str, tokens: int) -> None:
    if not user_id or tokens <= 0:
        return
    day = today()
    done = await db.usage.update_one({"_id": _fair_id(user_id), "day": day}, {"$inc": {"tokens": int(tokens)}})
    if not done.matched_count:  # a new day (or the first use): start the count again
        await db.usage.update_one({"_id": _fair_id(user_id)},
                                  {"$set": {"day": day, "tokens": int(tokens), "userId": user_id}}, upsert=True)


async def check_fair_use(db, user_id: str) -> None:
    """Raise LimitReached when today's fair-use allowance is used up."""
    if not enabled() or not user_id:
        return
    plan = await plan_of(db, user_id)
    if await _fair_used(db, user_id) >= fair_use_limit(plan):
        nxt = ORDER[ORDER.index(plan) + 1] if plan != ORDER[-1] else None
        more = f" {PLANS[nxt]['name']} gives you much more." if nxt else ""
        raise LimitReached("chat", plan, f"You've used today's AI allowance on the {PLANS[plan]['name']} plan. "
                                         f"It refills {_when(next_midnight())}.{more}")


async def require_fair_use(db, user_id: str) -> None:
    try:
        await check_fair_use(db, user_id)
    except LimitReached as exc:
        raise http_error(exc)


async def check_left(db, user_id: str, kind: str, size: Optional[int] = None, model: Optional[str] = None) -> None:
    """Raise LimitReached if the meter can't cover this request, without using anything."""
    if not enabled():
        return
    plan = await plan_of(db, user_id)
    doc, limit, need = await _meter(db, user_id), PLANS[plan]["meter"], cost(kind, size, plan, model)
    if doc.get("sessionUsed", 0) + need > limit["session"] or doc.get("weekUsed", 0) + need > limit["week"]:
        week = doc.get("weekUsed", 0) + need > limit["week"]
        raise LimitReached(kind, plan, message(kind, plan, doc["weekStart"] + WEEK_DAYS * 86400 if week
                                               else doc["sessionStart"] + SESSION_HOURS * 3600, week))


async def refund(db, user_id: str, kind: str, size: Optional[int] = None, model: Optional[str] = None) -> None:
    """Give back what a request used, e.g. when a picture failed to be made."""
    if not enabled():
        return
    credits = cost(kind, size, await plan_of(db, user_id), model)
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


def automation_rules(plan: str) -> dict:
    """What the plan's automations may do (every rule is open when limits are off)."""
    if not enabled():
        return {"minInterval": 15, "thorough": True, "premiumModels": True, "events": True, "noAsk": True}
    return PLANS[plan]["automations"]


async def can_publish(db, user_id: str) -> bool:
    return not enabled() or PLANS[await plan_of(db, user_id)]["publish"]


# 402 tells the app this is a plan limit, so it can offer the plans page.
def http_error(exc: LimitReached) -> HTTPException:
    return HTTPException(status_code=402, detail=str(exc))


async def require(db, user_id: str, kind: str, peek: bool = False, size: Optional[int] = None,
                  model: Optional[str] = None) -> None:
    """use() or check_total() for an endpoint: turns a reached limit into a friendly 402.

    With peek=True the meter is only checked, not used."""
    try:
        if kind in METER_KINDS and peek:
            await check_left(db, user_id, kind, size, model)
        elif kind in METER_KINDS:
            await use(db, user_id, kind, size, model)
        else:
            await check_total(db, user_id, kind)
    except LimitReached as exc:
        raise http_error(exc)


async def require_publish(db, user_id: str) -> None:
    if not await can_publish(db, user_id):
        raise HTTPException(status_code=402, detail=PUBLISH_MESSAGE)


def monthly(plan: str) -> Optional[dict]:
    """Roughly what a paid plan's meter buys in a month on Claude Sonnet, for the plan popup: premium answers
    (rounded down to tens) or app builds."""
    if not PLANS[plan]["premium"]:
        return None
    month = PLANS[plan]["meter"]["week"] * WEEKS_PER_MONTH
    answers = int(month // cost("chat", 0, plan, "claude-sonnet-5-5")) // 10 * 10
    return {"answers": answers, "builds": int(month // cost("build", 0, plan, "claude-sonnet-5-5"))}


def public_plans() -> list:
    return [{"id": p, **PLANS[p], "monthly": monthly(p)} for p in ORDER]


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
        "tokensPerCredit": TOKENS_PER_CREDIT,
    }


async def summary(db, user_id: str) -> dict:
    """The user's plan, their usage meter and every plan, for the Plans page."""
    plan = await plan_of(db, user_id)
    doc = await db.usage.find_one({"_id": _meter_id(user_id)}) or {}
    used = {"automation": {"used": await db.automations.count_documents({"userId": user_id}),
                           "limit": PLANS[plan]["total"]["automation"]}}
    meter = meter_view(plan, doc)
    used_today = await _fair_used(db, user_id)
    meter["today"] = {"used": used_today, "limit": fair_use_limit(plan),
                      "resetsAt": next_midnight() if used_today else None}
    return {"plan": plan, "limitsOn": enabled(), "canPublish": await can_publish(db, user_id),
            "meter": meter, "usage": used, "plans": public_plans(),
            "costs": {"build": [cost("build", 0, plan), cost("build", 0, plan, "claude-sonnet-5-5")],
                      "picture": cost("picture", 1, plan), "deck": cost("deck", None, plan),
                      "videoSecond": cost("video", 1, plan),
                      "chat": [cost("chat", 0, plan, "claude-haiku-5-5"), cost("chat", 0, plan, "claude-sonnet-5-5")]}}
