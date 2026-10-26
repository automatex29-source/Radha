"""Payments for the Pro and Max plans through Razorpay (UPI, cards, net banking, wallets).

Each payment buys 30 days of a plan. The app makes a Razorpay order for the plan's price,
the Razorpay checkout takes the money, and the plan is switched on either when the app
sends back the signed payment (verify) or when Razorpay's webhook says the order was paid,
whichever comes first. Both paths are safe to run twice: a payment upgrades the user once.

Autopay (the default): the checkout sets up a Razorpay subscription (UPI Autopay or a card
mandate) that charges the plan's price every month. Each charge (`subscription.charged`
webhook, or the checkout's own signed result for the first one) adds 30 days, once per
payment. The user can turn autopay off in Settings > Billing; the days already paid for stay.
A payment with an offer code is a one-time 30-day payment instead.

Paying again for the same plan adds 30 days to what is left. Moving from Pro to Max starts
a fresh 30 days of Max. A lower plan can't be bought while a higher one is still running.

Set on the server (Render > Environment):
  RAZORPAY_KEY_ID          rzp_live_... (or rzp_test_... while testing)
  RAZORPAY_KEY_SECRET      the secret shown once when the key is made
  RAZORPAY_WEBHOOK_SECRET  any password you choose, typed again when adding the webhook
Without the two key settings the Plans page keeps saying "Coming soon".
"""
import asyncio
import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx

import growth_mail
import limits
import promos

logger = logging.getLogger("radha.billing")

API = "https://api.razorpay.com/v1"
DAYS = 30
_TASKS: set = set()  # emails being sent, kept so they finish


class BillingError(Exception):
    """A problem the user should see, e.g. payments are off or the payment didn't check out."""


class GatewayError(BillingError):
    """Razorpay refused or failed a call (e.g. Subscriptions not switched on for the account yet)."""


def key_id() -> str:
    return os.environ.get("RAZORPAY_KEY_ID", "").strip()


def _secret() -> str:
    return os.environ.get("RAZORPAY_KEY_SECRET", "").strip()


def _webhook_secret() -> str:
    return os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()


def enabled() -> bool:
    return bool(key_id() and _secret())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def payment_signature_ok(order_id: str, payment_id: str, signature: str) -> bool:
    expected = _sign(_secret(), f"{order_id}|{payment_id}".encode())
    return bool(signature) and hmac.compare_digest(expected, signature)


def webhook_signature_ok(body: bytes, signature: str) -> bool:
    secret = _webhook_secret()
    return bool(secret and signature) and hmac.compare_digest(_sign(secret, body), signature)


async def _create_razorpay_order(amount: int, receipt: str, notes: dict) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API}/orders", auth=(key_id(), _secret()),
                              json={"amount": amount, "currency": "INR", "receipt": receipt, "notes": notes})
    if r.status_code >= 400:
        logger.warning("Razorpay order failed (%s): %s", r.status_code, r.text[:300])
        raise BillingError("Payments aren't working right now. Please try again in a few minutes.")
    return r.json()


async def create_order(db, user: dict, plan: str, code: str = "") -> dict:
    """Make a Razorpay order for one month of `plan` and return what the checkout needs.

    `code` is an optional offer code (e.g. LAUNCH50) that takes a percentage off this payment."""
    if not enabled():
        raise BillingError("Payments are coming soon.")
    if plan not in limits.PLANS or not limits.PLANS[plan]["price"]:
        raise BillingError("Pick Pro or Max to upgrade.")
    current = limits.plan_from(user)
    if limits.ORDER.index(plan) < limits.ORDER.index(current):
        raise BillingError(f"You're on {limits.PLANS[current]['name']} already, which includes everything in "
                           f"{limits.PLANS[plan]['name']}.")
    on = await autopay_of(db, user["id"])
    if on and limits.ORDER.index(on["plan"]) >= limits.ORDER.index(plan):
        raise BillingError(f"Autopay for {limits.PLANS[on['plan']]['name']} is on, so it renews by itself.")
    amount = limits.PLANS[plan]["price"] * 100  # paise
    promo = None
    if code.strip():
        try:
            promo = await promos.check(db, code, user["id"], plan)
        except promos.PromoError as exc:
            raise BillingError(str(exc))
        amount = promos.discounted(amount, promo["percentOff"])
    receipt = uuid.uuid4().hex[:20]
    notes = {"userId": user["id"], "plan": plan, **({"promoCode": promo["code"]} if promo else {})}
    order = await _create_razorpay_order(amount, receipt, notes)
    await db.payments.insert_one({
        "orderId": order["id"], "userId": user["id"], "plan": plan, "amount": amount, "currency": "INR",
        "receipt": receipt, "status": "created", "createdAt": _now().isoformat(),
        "promoCode": promo["code"] if promo else None,
    })
    return {"orderId": order["id"], "amount": amount, "currency": "INR", "keyId": key_id(),
            "plan": plan, "planName": limits.PLANS[plan]["name"],
            "promoCode": promo["code"] if promo else None, "percentOff": promo["percentOff"] if promo else 0,
            "name": user.get("name", ""), "email": user.get("email", "")}


async def _activate(db, order_id: str, payment_id: str, amount=None) -> bool:
    """Mark the order paid and give its user the plan. False when it was already done."""
    pay = await db.payments.find_one({"orderId": order_id})
    if not pay:
        logger.warning("Payment for an unknown order %s", order_id)
        return False
    if amount is not None and int(amount) != pay["amount"]:
        logger.warning("Order %s paid %s, expected %s", order_id, amount, pay["amount"])
        return False
    claimed = await db.payments.find_one_and_update(
        {"orderId": order_id, "status": {"$ne": "paid"}},
        {"$set": {"status": "paid", "paymentId": payment_id, "paidAt": _now().isoformat()}})
    if not claimed:
        return False
    if pay.get("promoCode"):
        await promos.count_use(db, pay["promoCode"])
    expires = await grant_days(db, pay["userId"], pay["plan"], DAYS)
    logger.info("User %s is on %s until %s (order %s)", pay["userId"], pay["plan"], expires, order_id)
    await _thank_you(db, pay["userId"], expires)
    return True


async def _thank_you(db, user_id: str, expires) -> None:
    """A personal "Pro is on" email with a picture, sent in the background after a payment."""
    base = growth_mail.app_url()
    user = await db.users.find_one({"id": user_id}, {"name": 1, "email": 1, "plan": 1, "planExpiresAt": 1}) or {}
    if not base or not user.get("email"):
        return
    until = datetime.fromisoformat(expires).astimezone(limits.IST).strftime("%d %b %Y") if expires else "you choose to stop"
    mail = growth_mail.plan_started(base, user.get("name", ""), limits.plan_from(user), until)
    task = asyncio.create_task(growth_mail.send(user["email"], mail))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def grant_days(db, user_id: str, plan: str, days: int):
    """Give a user `days` of `plan` (a payment, or a free gift such as a friend invite). Returns the new end time.

    Days on the same plan add to what is left. A higher plan the user is already on is never stepped down:
    the days go onto it instead. A plan set by hand that never runs out stays that way (returns None)."""
    user = await db.users.find_one({"id": user_id}, {"plan": 1, "planExpiresAt": 1}) or {}
    current = limits.plan_from(user)
    if limits.ORDER.index(current) > limits.ORDER.index(plan):
        plan = current
    if plan == current and plan != "basic" and not user.get("planExpiresAt"):
        return None
    start = _now()
    if plan == current and user.get("planExpiresAt"):
        start = max(start, datetime.fromisoformat(user["planExpiresAt"]))
    expires = (start + timedelta(days=days)).isoformat()
    await db.users.update_one({"id": user_id}, {"$set": {
        "plan": plan, "planExpiresAt": expires, "updatedAt": _now().isoformat()}})
    return expires


async def verify(db, user_id: str, order_id: str, payment_id: str, signature: str) -> None:
    """The checkout's success callback: check Razorpay's signature, then switch the plan on."""
    pay = await db.payments.find_one({"orderId": order_id, "userId": user_id})
    if not pay or not payment_signature_ok(order_id, payment_id, signature):
        raise BillingError("We couldn't confirm that payment. If money was taken, it will show up within a few "
                           "minutes, or write to us from the Help Center.")
    await _activate(db, order_id, payment_id)


async def webhook(db, body: bytes, signature: str, event: dict) -> bool:
    """Razorpay's webhook (order.paid / payment.captured). Returns False when the signature is wrong."""
    if not webhook_signature_ok(body, signature):
        return False
    payload = event.get("payload") or {}
    payment = (payload.get("payment") or {}).get("entity") or {}
    order = (payload.get("order") or {}).get("entity") or {}
    if (event.get("event") or "").startswith("subscription."):
        await _subscription_event(db, event["event"], payload)
    elif event.get("event") in ("order.paid", "payment.captured"):
        order_id = order.get("id") or payment.get("order_id")
        if order_id and payment.get("id"):
            await _activate(db, order_id, payment["id"], payment.get("amount"))
    return True


# ------------------------------------------------------------------ autopay
LIVE_SUB = ("created", "authenticated", "active", "pending")  # Razorpay states that can still charge


async def _rzp(method: str, path: str, body: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.request(method, f"{API}{path}", auth=(key_id(), _secret()), json=body)
    if r.status_code >= 400:
        logger.warning("Razorpay %s %s failed (%s): %s", method, path, r.status_code, r.text[:300])
        raise GatewayError("Payments aren't working right now. Please try again in a few minutes.")
    return r.json()


async def _rzp_plan(db, plan: str, amount: int) -> str:
    """The Razorpay plan id for a monthly `plan` at `amount` paise, made once per key (test and live differ)."""
    cache_id = f"{key_id()}:{plan}:{amount}"
    doc = await db.rzp_plans.find_one({"_id": cache_id})
    if doc:
        return doc["planId"]
    made = await _rzp("POST", "/plans", {"period": "monthly", "interval": 1, "item": {
        "name": f"Krish AI {limits.PLANS[plan]['name']}", "amount": amount, "currency": "INR",
        "description": f"Krish AI {limits.PLANS[plan]['name']}, every month"}})
    await db.rzp_plans.update_one({"_id": cache_id}, {"$setOnInsert": {"planId": made["id"]}}, upsert=True)
    return (await db.rzp_plans.find_one({"_id": cache_id}))["planId"]


async def autopay_of(db, user_id: str):
    """The user's subscription that is on (or being set up and already charged), or None."""
    return await db.subscriptions.find_one({"userId": user_id, "status": {"$in": ["active", "authenticated"]}},
                                           sort=[("createdAt", -1)])


def public_autopay(sub) -> dict:
    if not sub:
        return None
    return {"plan": sub["plan"], "planName": limits.PLANS[sub["plan"]]["name"], "amount": sub["amount"] // 100,
            "status": sub["status"], "since": sub.get("activatedAt") or sub["createdAt"]}


async def subscribe(db, user: dict, plan: str) -> dict:
    """Start autopay for `plan`: makes a Razorpay subscription for the checkout to open."""
    if not enabled():
        raise BillingError("Payments are coming soon.")
    if plan not in limits.PLANS or not limits.PLANS[plan]["price"]:
        raise BillingError("Pick Pro or Max to upgrade.")
    current = limits.plan_from(user)
    if limits.ORDER.index(plan) < limits.ORDER.index(current):
        raise BillingError(f"You're on {limits.PLANS[current]['name']} already, which includes everything in "
                           f"{limits.PLANS[plan]['name']}.")
    on = await autopay_of(db, user["id"])
    if on and limits.ORDER.index(on["plan"]) >= limits.ORDER.index(plan):
        raise BillingError(f"Autopay for {limits.PLANS[on['plan']]['name']} is already on, so it renews by itself.")
    amount = limits.PLANS[plan]["price"] * 100
    plan_id = await _rzp_plan(db, plan, amount)
    sub = await _rzp("POST", "/subscriptions", {"plan_id": plan_id, "total_count": 60, "quantity": 1,
                                                "customer_notify": 1, "notes": {"userId": user["id"], "plan": plan}})
    await db.subscriptions.insert_one({"id": sub["id"], "userId": user["id"], "plan": plan, "amount": amount,
                                       "status": "created", "createdAt": _now().isoformat()})
    return {"subscriptionId": sub["id"], "amount": amount, "currency": "INR", "keyId": key_id(), "plan": plan,
            "planName": limits.PLANS[plan]["name"], "name": user.get("name", ""), "email": user.get("email", "")}


def subscription_signature_ok(payment_id: str, subscription_id: str, signature: str) -> bool:
    expected = _sign(_secret(), f"{payment_id}|{subscription_id}".encode())
    return bool(signature) and hmac.compare_digest(expected, signature)


async def _charged(db, sub_id: str, payment_id: str, amount=None) -> bool:
    """One monthly autopay charge went through: add 30 days, once per payment. False if unknown or done."""
    sub = await db.subscriptions.find_one({"id": sub_id})
    if not sub:
        logger.warning("Charge for an unknown subscription %s", sub_id)
        return False
    if amount is not None and int(amount) != sub["amount"]:
        logger.warning("Subscription %s charged %s, expected %s", sub_id, amount, sub["amount"])
        return False
    res = await db.payments.update_one({"paymentId": payment_id}, {"$setOnInsert": {
        "orderId": f"sub_{payment_id}", "paymentId": payment_id, "subscriptionId": sub_id, "userId": sub["userId"],
        "plan": sub["plan"], "amount": sub["amount"], "currency": "INR", "status": "paid", "autopay": True,
        "createdAt": _now().isoformat(), "paidAt": _now().isoformat()}}, upsert=True)
    if res.upserted_id is None:
        return False
    first = sub["status"] not in ("active", "authenticated")
    await db.subscriptions.update_one({"id": sub_id}, {"$set": {
        "status": "active", **({"activatedAt": _now().isoformat()} if first else {})}})
    if first:
        await _stop_others(db, sub["userId"], sub_id)
    expires = await grant_days(db, sub["userId"], sub["plan"], DAYS)
    logger.info("Autopay: user %s is on %s until %s (subscription %s)", sub["userId"], sub["plan"], expires, sub_id)
    if first:
        await _thank_you(db, sub["userId"], expires)
    return True


async def _stop_others(db, user_id: str, keep: str) -> None:
    """Moving to a new plan's autopay (e.g. Pro to Max): the old one must not charge again."""
    async for old in db.subscriptions.find({"userId": user_id, "id": {"$ne": keep}, "status": {"$in": list(LIVE_SUB)}}):
        try:
            await _rzp("POST", f"/subscriptions/{old['id']}/cancel", {"cancel_at_cycle_end": 0})
        except BillingError:
            logger.warning("Couldn't cancel old subscription %s", old["id"])
        await db.subscriptions.update_one({"id": old["id"]}, {"$set": {"status": "cancelled", "cancelledAt": _now().isoformat()}})


async def verify_subscription(db, user_id: str, sub_id: str, payment_id: str, signature: str) -> None:
    sub = await db.subscriptions.find_one({"id": sub_id, "userId": user_id})
    if not sub or not subscription_signature_ok(payment_id, sub_id, signature):
        raise BillingError("We couldn't confirm that payment. If money was taken, it will show up within a few "
                           "minutes, or write to us from the Help Center.")
    await _charged(db, sub_id, payment_id)


async def cancel_autopay(db, user_id: str) -> None:
    """Settings > Billing: stop future charges now. The days already paid for stay."""
    found = False
    async for sub in db.subscriptions.find({"userId": user_id, "status": {"$in": list(LIVE_SUB)}}):
        found = True
        await _rzp("POST", f"/subscriptions/{sub['id']}/cancel", {"cancel_at_cycle_end": 0})
        await db.subscriptions.update_one({"id": sub["id"]}, {"$set": {"status": "cancelled", "cancelledAt": _now().isoformat()}})
    if not found:
        raise BillingError("Autopay isn't on.")


async def _subscription_event(db, event: str, payload: dict) -> None:
    sub = (payload.get("subscription") or {}).get("entity") or {}
    payment = (payload.get("payment") or {}).get("entity") or {}
    if not sub.get("id"):
        return
    if event == "subscription.charged" and payment.get("id"):
        await _charged(db, sub["id"], payment["id"], payment.get("amount"))
    elif event in ("subscription.cancelled", "subscription.halted", "subscription.completed"):
        await db.subscriptions.update_one({"id": sub["id"]}, {"$set": {
            "status": event.split(".")[1], "endedAt": _now().isoformat()}})
