"""Payments for the Pro and Max plans through Razorpay (UPI, cards, net banking, wallets).

Each payment buys 30 days of a plan. The app makes a Razorpay order for the plan's price,
the Razorpay checkout takes the money, and the plan is switched on either when the app
sends back the signed payment (verify) or when Razorpay's webhook says the order was paid,
whichever comes first. Both paths are safe to run twice: a payment upgrades the user once.

Paying again for the same plan adds 30 days to what is left. Moving from Pro to Max starts
a fresh 30 days of Max. A lower plan can't be bought while a higher one is still running.

Set on the server (Render > Environment):
  RAZORPAY_KEY_ID          rzp_live_... (or rzp_test_... while testing)
  RAZORPAY_KEY_SECRET      the secret shown once when the key is made
  RAZORPAY_WEBHOOK_SECRET  any password you choose, typed again when adding the webhook
Without the two key settings the Plans page keeps saying "Coming soon".
"""
import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx

import limits

logger = logging.getLogger("radha.billing")

API = "https://api.razorpay.com/v1"
DAYS = 30


class BillingError(Exception):
    """A problem the user should see, e.g. payments are off or the payment didn't check out."""


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


async def create_order(db, user: dict, plan: str) -> dict:
    """Make a Razorpay order for one month of `plan` and return what the checkout needs."""
    if not enabled():
        raise BillingError("Payments are coming soon.")
    if plan not in limits.PLANS or not limits.PLANS[plan]["price"]:
        raise BillingError("Pick Pro or Max to upgrade.")
    current = limits.plan_from(user)
    if limits.ORDER.index(plan) < limits.ORDER.index(current):
        raise BillingError(f"You're on {limits.PLANS[current]['name']} already, which includes everything in "
                           f"{limits.PLANS[plan]['name']}.")
    amount = limits.PLANS[plan]["price"] * 100  # paise
    receipt = uuid.uuid4().hex[:20]
    order = await _create_razorpay_order(amount, receipt, {"userId": user["id"], "plan": plan})
    await db.payments.insert_one({
        "orderId": order["id"], "userId": user["id"], "plan": plan, "amount": amount, "currency": "INR",
        "receipt": receipt, "status": "created", "createdAt": _now().isoformat(),
    })
    return {"orderId": order["id"], "amount": amount, "currency": "INR", "keyId": key_id(),
            "plan": plan, "planName": limits.PLANS[plan]["name"],
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
    user = await db.users.find_one({"id": pay["userId"]}, {"plan": 1, "planExpiresAt": 1}) or {}
    current = limits.plan_from(user)
    plan = pay["plan"]
    if limits.ORDER.index(current) > limits.ORDER.index(plan):
        # An older Pro order paid after the user moved to Max: never step them down, add the days to Max.
        plan = current
    if plan == current and plan != "basic" and not user.get("planExpiresAt"):
        return True  # a plan set by hand that never runs out stays that way
    start = _now()
    if plan == current and user.get("planExpiresAt"):
        start = max(start, datetime.fromisoformat(user["planExpiresAt"]))
    expires = (start + timedelta(days=DAYS)).isoformat()
    await db.users.update_one({"id": pay["userId"]}, {"$set": {
        "plan": plan, "planExpiresAt": expires, "updatedAt": _now().isoformat()}})
    logger.info("User %s is on %s until %s (order %s)", pay["userId"], plan, expires, order_id)
    return True


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
    if event.get("event") in ("order.paid", "payment.captured"):
        order_id = order.get("id") or payment.get("order_id")
        if order_id and payment.get("id"):
            await _activate(db, order_id, payment["id"], payment.get("amount"))
    return True
