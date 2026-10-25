"""Invite a friend: everyone gets a personal link, and a friend who signs up through it gives both people
free days of Pro.

The link is the app address with ?ref=CODE. The app keeps the code while the friend signs up (by email or
Google) and sends it with the sign-up. The friend always gets their days, but the inviter is
rewarded only once (MAX_REWARDS), so inviting more friends or made-up accounts can't keep anyone on free Pro. Paid days are never lost: free days add to a running plan (see billing).
"""
import secrets
from datetime import datetime, timezone
from typing import Optional

import billing

REWARD_DAYS = 7
MAX_REWARDS = 1  # the inviter's reward is one-time
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so a code read aloud is typed right


def _new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(7))


async def code_for(db, user_id: str) -> str:
    """The user's invite code, made the first time it is asked for."""
    user = await db.users.find_one({"id": user_id}, {"referralCode": 1})
    if user and user.get("referralCode"):
        return user["referralCode"]
    for _ in range(5):
        code = _new_code()
        if not await db.users.find_one({"referralCode": code}):
            await db.users.update_one({"id": user_id, "referralCode": {"$exists": False}},
                                      {"$set": {"referralCode": code}})
            break
    return (await db.users.find_one({"id": user_id}, {"referralCode": 1}))["referralCode"]


async def apply(db, new_user: dict, code: str) -> Optional[dict]:
    """Called once when an account is made with an invite code. When the code is a real one, gives the friend
    their days (and the inviter theirs, up to the cap) and returns {inviter, rewarded, joined}; else None."""
    code = (code or "").strip().upper()
    if not code:
        return None
    inviter = await db.users.find_one({"referralCode": code}, {"id": 1, "name": 1, "email": 1})
    if not inviter or inviter["id"] == new_user["id"]:
        return None
    await db.users.update_one({"id": new_user["id"]}, {"$set": {"referredBy": inviter["id"]}})
    await billing.grant_days(db, new_user["id"], "pro", REWARD_DAYS)
    claimed = await db.users.find_one_and_update(
        {"id": inviter["id"], "$or": [{"referralRewards": {"$exists": False}}, {"referralRewards": {"$lt": MAX_REWARDS}}]},
        {"$inc": {"referralRewards": 1}})
    if claimed:
        await billing.grant_days(db, inviter["id"], "pro", REWARD_DAYS)
    await db.referrals.insert_one({"inviterId": inviter["id"], "friendId": new_user["id"], "rewarded": bool(claimed),
                                   "createdAt": datetime.now(timezone.utc).isoformat()})
    joined = await db.referrals.count_documents({"inviterId": inviter["id"], "rewarded": True})
    return {"inviter": inviter, "rewarded": bool(claimed), "joined": joined}


async def public_invite(db, code: str) -> Optional[dict]:
    """What the invite page may show to anyone with the link: the inviter's first name only."""
    code = (code or "").strip().upper()
    if not code or len(code) > 20:
        return None
    inviter = await db.users.find_one({"referralCode": code}, {"name": 1})
    if not inviter:
        return None
    return {"code": code, "name": (inviter.get("name") or "").strip().split(" ")[0][:30], "days": REWARD_DAYS}


async def summary(db, user_id: str) -> dict:
    """What the Invite page shows: the code, how many friends joined and how many free days were earned."""
    code = await code_for(db, user_id)
    joined = await db.referrals.count_documents({"inviterId": user_id})
    rewarded = await db.referrals.count_documents({"inviterId": user_id, "rewarded": True})
    return {"code": code, "joined": joined, "daysEarned": rewarded * REWARD_DAYS, "rewardDays": REWARD_DAYS,
            "maxRewards": MAX_REWARDS}
