"""Daily Gita verse: a gentle phone or laptop notification each morning for people who turn it on.

People switch it on in Settings (or from the Counsellor). The browser then gives the app a "push address" for
that device, which is saved here. Every morning at 7:00 India time the server sends one short verse to every
saved device; tapping it opens the Counsellor. On an iPhone this works once Krish is added to the home screen.

The push keys (VAPID) are made once and kept in the database, so nothing needs setting up. To use your own,
set VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY (PEM) on the server. Set DAILY_VERSE=off to stop the morning send.
"""
import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import help_center

logger = logging.getLogger("radha.verse")

IST = timezone(timedelta(hours=5, minutes=30))
SEND_HOUR = 7

# Well-known verses, with their meaning in plain words. One a day, in order, going round.
VERSES = [
    ("2.47", "You have a right to your work, but not to its results. Do your best and let go of the outcome."),
    ("2.14", "Heat and cold, pleasure and pain come and go. They don't last, so bear them patiently."),
    ("2.20", "The soul is never born and never dies. What you truly are can't be harmed."),
    ("2.48", "Do your work with a steady mind, the same in success and failure. That evenness is yoga."),
    ("2.50", "Yoga is skill in action. Act wisely, without being tied up in the fruits."),
    ("2.56", "One who isn't shaken by sorrow, doesn't crave pleasure, and is free of fear and anger is called wise."),
    ("2.62", "Dwelling on things breeds attachment, attachment breeds desire, and desire breeds anger. Watch your thoughts."),
    ("2.70", "Like the ocean that stays calm as rivers pour in, a peaceful person stays steady as desires come."),
    ("3.8", "Do your duty. Action is better than doing nothing; even keeping the body going needs action."),
    ("3.19", "Do the work that needs doing, without clinging to the result. That is how one reaches the highest."),
    ("3.21", "Whatever a great person does, others follow. The example you set matters."),
    ("3.35", "Better your own path done imperfectly than someone else's done well."),
    ("4.7", "Whenever goodness fades and wrong rises, the Divine comes forth to set things right."),
    ("4.38", "Nothing in this world purifies like knowledge. It comes in time to one who practises."),
    ("5.18", "The wise see the same Self in a learned person, a cow, an elephant, a dog and an outcast."),
    ("6.5", "Lift yourself up by your own mind; don't pull yourself down. The mind is your friend and your enemy."),
    ("6.6", "For one who has mastered the mind, it is the best friend. For one who hasn't, it acts like an enemy."),
    ("6.17", "Balance in eating, resting, working and sleeping ends sorrow. Moderation is the way."),
    ("6.26", "Whenever the restless mind wanders, gently bring it back again and again."),
    ("6.35", "The mind is restless and hard to hold, but it can be trained with practice and letting go."),
    ("9.22", "To those who remember the Divine with steady love, it brings what they lack and keeps what they have."),
    ("9.26", "Whoever offers with love even a leaf, a flower, a fruit or water, that offering is accepted."),
    ("12.13", "One who hates no one, is friendly and kind to all, free of ego, and patient in joy and pain is dear to God."),
    ("12.15", "One who doesn't disturb the world and isn't disturbed by it, free from excitement, anger and fear, is dear to God."),
    ("2.40", "On this path no effort is ever lost. Even a little practice protects you from great fear."),
    ("15.7", "A part of the Divine lives in every being. You carry that spark within you."),
    ("16.21", "Desire, anger and greed are three gates to suffering. Let them go."),
    ("17.15", "Speech that is truthful, kind, helpful and causes no hurt is the discipline of speech."),
    ("18.47", "Your own duty, even done imperfectly, is better than another's done perfectly."),
    ("18.58", "Keep your mind on the Divine and you will cross every difficulty."),
    ("18.66", "Let go of every worry and take refuge in the Divine. Do not grieve."),
]


def verse_for(day: str) -> tuple:
    n = datetime.strptime(day, "%Y-%m-%d").toordinal()
    return VERSES[n % len(VERSES)]


def today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


_db = None
_keys: dict = {}
_task: Optional[asyncio.Task] = None


def init(db) -> None:
    global _db
    _db = db


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _new_keys() -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"public": _b64url(public), "private": pem}


async def ensure_keys() -> dict:
    """The push keys: from the environment, or made once and kept in the database."""
    if _keys:
        return _keys
    if os.environ.get("VAPID_PUBLIC_KEY") and os.environ.get("VAPID_PRIVATE_KEY"):
        _keys.update(public=os.environ["VAPID_PUBLIC_KEY"], private=os.environ["VAPID_PRIVATE_KEY"].replace("\\n", "\n"))
        return _keys
    doc = await _db.settings.find_one({"id": "vapid"})
    if not doc:
        doc = {"id": "vapid", **_new_keys()}
        try:
            await _db.settings.insert_one(dict(doc))
        except Exception:  # another server made them first
            doc = await _db.settings.find_one({"id": "vapid"})
    _keys.update(public=doc["public"], private=doc["private"])
    return _keys


def _contact() -> str:
    return f"mailto:{help_center.HELP_EMAIL}"


def _send_sync(sub: dict, payload: str, private_pem: str) -> int:
    """Send one notification. Returns the push service's status (201 = sent, 404/410 = device gone)."""
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush
    try:
        resp = webpush({"endpoint": sub["endpoint"], "keys": sub["keys"]}, payload,
                       vapid_private_key=Vapid.from_pem(private_pem.encode()),
                       vapid_claims={"sub": _contact()}, ttl=6 * 3600, timeout=15)
        return getattr(resp, "status_code", 201)
    except WebPushException as exc:
        return getattr(exc.response, "status_code", 0) or 0


def payload_for(day: str) -> str:
    ref, meaning = verse_for(day)
    return json.dumps({"title": f"Today's Gita verse · {ref}", "body": meaning, "url": "/counsellor",
                       "tag": f"verse-{day}"})


async def send_to(subs: list, payload: str) -> int:
    """Send to these devices, forgetting any the push service says are gone. Returns how many were sent."""
    keys = await ensure_keys()
    sent = 0
    for i in range(0, len(subs), 20):
        batch = subs[i:i + 20]
        codes = await asyncio.gather(*[anyio.to_thread.run_sync(_send_sync, s, payload, keys["private"]) for s in batch])
        for sub, code in zip(batch, codes):
            if code in (404, 410):
                await _db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
            elif 200 <= code < 300:
                sent += 1
    return sent


async def morning_send() -> Optional[int]:
    """Send today's verse once, after 7:00 India time. None when it isn't time or was already sent."""
    now = datetime.now(IST)
    day = now.strftime("%Y-%m-%d")
    if now.hour < SEND_HOUR:
        return None
    try:  # claim today's send, so only one server sends it, once
        await _db.settings.find_one_and_update({"id": "verse_sent", "day": {"$ne": day}}, {"$set": {"day": day}},
                                               upsert=True)
    except Exception:  # already sent today (the upsert hit the existing record)
        return None
    subs = await _db.push_subscriptions.find({}, {"_id": 0}).to_list(None)
    sent = await send_to(subs, payload_for(day))
    logger.info("Daily verse sent to %s of %s devices", sent, len(subs))
    return sent


async def _loop():
    while True:
        try:
            await morning_send()
        except Exception:
            logger.exception("Daily verse send failed")
        await asyncio.sleep(300)


def start_scheduler() -> None:
    global _task
    if os.environ.get("DAILY_VERSE", "on").lower() in ("off", "0", "false", "no"):
        return
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop_scheduler() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None


# ------------------------------------------------------------------- routes
router = APIRouter(prefix="/api/push")


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: dict


class EndpointIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)


def routes(current_user_id):
    """The push routes, bound to the server's sign-in check."""

    @router.get("/config")
    async def config(user_id: str = Depends(current_user_id)):
        keys = await ensure_keys()
        on = await _db.push_subscriptions.count_documents({"userId": user_id})
        return {"publicKey": keys["public"], "devices": on, "verse": dict(zip(("ref", "meaning"), verse_for(today_ist())))}

    @router.post("/subscribe")
    async def subscribe(body: SubscriptionIn, user_id: str = Depends(current_user_id)):
        if not body.endpoint.startswith("https://") or not {"p256dh", "auth"} <= set(body.keys):
            raise HTTPException(status_code=400, detail="That device can't get notifications.")
        if await _db.push_subscriptions.count_documents({"userId": user_id}) >= 10:
            raise HTTPException(status_code=400, detail="Turn notifications off on an old device first.")
        await _db.push_subscriptions.update_one(
            {"endpoint": body.endpoint},
            {"$set": {"userId": user_id, "keys": {"p256dh": body.keys["p256dh"], "auth": body.keys["auth"]},
                      "createdAt": datetime.now(timezone.utc).isoformat()}}, upsert=True)
        return {"ok": True}

    @router.post("/unsubscribe")
    async def unsubscribe(body: EndpointIn, user_id: str = Depends(current_user_id)):
        await _db.push_subscriptions.delete_one({"endpoint": body.endpoint, "userId": user_id})
        return {"ok": True}

    @router.post("/test")
    async def test(user_id: str = Depends(current_user_id)):
        """Send today's verse to this person's devices now, so they can see what it looks like."""
        subs = await _db.push_subscriptions.find({"userId": user_id}, {"_id": 0}).to_list(None)
        return {"sent": await send_to(subs, payload_for(today_ist()))}

    return router
