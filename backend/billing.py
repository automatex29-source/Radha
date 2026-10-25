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

Pay by UPI (no gateway, no KYC): set UPI_ID (e.g. yourname@okaxis) and optionally UPI_NAME.
Users scan a QR for the exact amount, pay straight into that UPI account and type the
12-digit UPI reference (UTR). The owner checks it in their bank app and taps Approve on the
Users page > Payments, which gives the plan exactly like a Razorpay payment. When Razorpay
keys are set too, the Razorpay checkout is used instead.
"""
import asyncio
import hashlib
import re
import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx

import growth_mail
import limits
import mailer
import promos

logger = logging.getLogger("radha.billing")

API = "https://api.razorpay.com/v1"
DAYS = 30
_TASKS: set = set()  # emails being sent, kept so they finish


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


async def create_order(db, user: dict, plan: str, code: str = "") -> dict:
    """Make a Razorpay order for one month of `plan` and return what the checkout needs.

    `code` is an optional offer code (e.g. LAUNCH50) that takes a percentage off this payment."""
    if not enabled():
        raise BillingError("Payments are coming soon.")
    amount, promo = await _price(db, user, plan, code)
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
    if event.get("event") in ("order.paid", "payment.captured"):
        order_id = order.get("id") or payment.get("order_id")
        if order_id and payment.get("id"):
            await _activate(db, order_id, payment["id"], payment.get("amount"))
    return True


# ------------------------------------------------------------- pay by UPI
UTR = re.compile(r"^\d{12}$")


def upi_id() -> str:
    return os.environ.get("UPI_ID", "").strip()


def upi_enabled() -> bool:
    return bool(upi_id()) and "@" in upi_id()


def pay_with() -> str:
    """How the Plans page takes money: Razorpay's checkout, the owner's UPI, or not yet ("")."""
    return "razorpay" if enabled() else "upi" if upi_enabled() else ""


def upi_info() -> dict:
    return {"id": upi_id(), "name": os.environ.get("UPI_NAME", "").strip() or "Krish AI"}


async def _price(db, user: dict, plan: str, code: str):
    """The amount in paise for a month of `plan` with an optional offer code, and the code's details."""
    if plan not in limits.PLANS or not limits.PLANS[plan]["price"]:
        raise BillingError("Pick Pro or Max to upgrade.")
    current = limits.plan_from(user)
    if limits.ORDER.index(plan) < limits.ORDER.index(current):
        raise BillingError(f"You're on {limits.PLANS[current]['name']} already, which includes everything in "
                           f"{limits.PLANS[plan]['name']}.")
    amount = limits.PLANS[plan]["price"] * 100
    promo = None
    if code.strip():
        try:
            promo = await promos.check(db, code, user["id"], plan)
        except promos.PromoError as exc:
            raise BillingError(str(exc))
        amount = promos.discounted(amount, promo["percentOff"])
    return amount, promo


async def upi_request(db, user: dict, plan: str, utr: str, code: str = "") -> dict:
    """The user says they paid by UPI: keep it as a pending payment for the owner to approve."""
    if not upi_enabled():
        raise BillingError("Payments are coming soon.")
    utr = re.sub(r"\s", "", utr or "")
    if not UTR.match(utr):
        raise BillingError("The UPI reference is the 12-digit number in your UPI app's payment details "
                           "(called UTR, UPI Ref No. or Transaction ID).")
    if await db.payments.find_one({"method": "upi", "utr": utr, "status": {"$in": ["pending", "paid"]}}):
        raise BillingError("That UPI reference has already been sent.")
    if await db.payments.find_one({"userId": user["id"], "method": "upi", "status": "pending"}):
        raise BillingError("Your last UPI payment is still being checked. You'll get your plan as soon as it's approved.")
    amount, promo = await _price(db, user, plan, code)
    doc = {"orderId": f"upi_{uuid.uuid4().hex[:16]}", "userId": user["id"], "plan": plan, "amount": amount,
           "currency": "INR", "method": "upi", "utr": utr, "status": "pending", "createdAt": _now().isoformat(),
           "promoCode": promo["code"] if promo else None}
    await db.payments.insert_one(doc)
    logger.info("UPI payment to check: user %s, %s, ₹%s, UTR %s", user["id"], plan, amount // 100, utr)
    _tell_owner(user, doc)
    return public_upi(doc)


def _tell_owner(user: dict, doc: dict) -> None:
    """Email the owner (first OWNER_EMAIL) that a UPI payment is waiting to be checked."""
    owner = next((e.strip() for e in os.environ.get("OWNER_EMAIL", "").split(",") if e.strip()), "")
    if not owner or not mailer.configured():
        return
    rupees, name = doc["amount"] // 100, limits.PLANS[doc["plan"]]["name"]
    who = html.escape(f"{user.get('name', '')} ({user.get('email', '')})")
    link = f"{growth_mail.app_url()}/admin/users" if growth_mail.app_url() else "the Users page"
    text = (f"{user.get('name', '')} ({user.get('email', '')}) says they paid ₹{rupees} by UPI for {name}.\n"
            f"UPI reference: {doc['utr']}\n\nCheck your bank or UPI app, then approve it on {link} > Payments.")
    body = (f"<p>{who} says they paid <b>₹{rupees}</b> by UPI for <b>{name}</b>.</p>"
            f"<p>UPI reference: <b>{doc['utr']}</b></p><p>Check your bank or UPI app, then approve it on "
            f"<a href=\"{html.escape(link)}\">the Users page</a> &gt; Payments.</p>")
    task = asyncio.create_task(mailer.send(owner, f"UPI payment to check: ₹{rupees} for {name}", body, text))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


def public_upi(doc: dict) -> dict:
    return {"orderId": doc["orderId"], "plan": doc["plan"], "planName": limits.PLANS[doc["plan"]]["name"],
            "amount": doc["amount"] // 100, "utr": doc["utr"], "status": doc["status"], "createdAt": doc["createdAt"],
            "promoCode": doc.get("promoCode")}


async def upi_pending_for(db, user_id: str):
    doc = await db.payments.find_one({"userId": user_id, "method": "upi", "status": "pending"})
    return public_upi(doc) if doc else None


async def upi_list(db, status: str = "pending") -> list:
    """Owner: UPI payments to check (newest first), with who sent them."""
    docs = await db.payments.find({"method": "upi", "status": status}).sort("createdAt", -1).to_list(200)
    ids = list({d["userId"] for d in docs})
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": ids}}, {"id": 1, "name": 1, "email": 1})}
    return [{**public_upi(d), "name": users.get(d["userId"], {}).get("name", ""),
             "email": users.get(d["userId"], {}).get("email", "")} for d in docs]


async def upi_decide(db, order_id: str, approve: bool) -> dict:
    """Owner: approve (the money arrived, give the plan) or reject (it didn't) a pending UPI payment."""
    pay = await db.payments.find_one({"orderId": order_id, "method": "upi"})
    if not pay:
        raise BillingError("No such payment.")
    if pay["status"] != "pending":
        raise BillingError(f"This payment was already {'approved' if pay['status'] == 'paid' else 'rejected'}.")
    if approve:
        await _activate(db, order_id, f"utr_{pay['utr']}")
    else:
        await db.payments.update_one({"orderId": order_id, "status": "pending"},
                                     {"$set": {"status": "rejected", "rejectedAt": _now().isoformat()}})
    return public_upi(await db.payments.find_one({"orderId": order_id}))
