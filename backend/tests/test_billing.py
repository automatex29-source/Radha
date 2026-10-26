"""Razorpay payments for Pro and Max: orders, the signed checkout result and the webhook. MongoDB is mongomock."""
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SECRET = "key-secret"
HOOK = "hook-secret"


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b", RAZORPAY_KEY_ID="rzp_test_abc",
                      RAZORPAY_KEY_SECRET=SECRET, RAZORPAY_WEBHOOK_SECRET=HOOK)
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        yield c
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
        os.environ.pop(k, None)


@pytest.fixture(autouse=True)
def fake_razorpay(monkeypatch):
    import billing
    count = {"n": 0}

    async def create(amount, receipt, notes):
        count["n"] += 1
        return {"id": f"order_{count['n']}_{receipt[:6]}", "amount": amount}

    monkeypatch.setattr(billing, "_create_razorpay_order", create)


def _user(client, email):
    r = client.post("/api/auth/register", json={"name": "Asha", "email": email, "password": "secret1"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _sig(secret, msg: bytes):
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _pay(client, h, order, payment_id="pay_1"):
    sig = _sig(SECRET, f"{order['orderId']}|{payment_id}".encode())
    return client.post("/api/billing/verify", headers=h,
                       json={"orderId": order["orderId"], "paymentId": payment_id, "signature": sig})


def test_paying_for_pro_switches_it_on_for_30_days(client):
    h = _user(client, "pay1@test.com")
    usage = client.get("/api/usage", headers=h).json()
    assert usage["paymentsOn"] is True and usage["plan"] == "basic" and usage["planExpiresAt"] is None
    order = client.post("/api/billing/order", headers=h, json={"plan": "pro"}).json()
    assert order["amount"] == 29900 and order["currency"] == "INR" and order["keyId"] == "rzp_test_abc"

    bad = client.post("/api/billing/verify", headers=h,
                      json={"orderId": order["orderId"], "paymentId": "pay_1", "signature": "nope"})
    assert bad.status_code == 400
    assert client.get("/api/auth/me", headers=h).json()["plan"] == "basic"

    r = _pay(client, h, order)
    assert r.status_code == 200 and r.json()["plan"] == "pro"
    expires = datetime.fromisoformat(r.json()["planExpiresAt"])
    assert timedelta(days=29) < expires - datetime.now(timezone.utc) <= timedelta(days=30)
    assert client.get("/api/usage", headers=h).json()["meter"]["session"]["limit"] == 400

    # The same payment coming back again (or by webhook) doesn't add more days.
    assert _pay(client, h, order).json()["planExpiresAt"] == r.json()["planExpiresAt"]

    # A second month of Pro adds to what is left.
    again = client.post("/api/billing/order", headers=h, json={"plan": "pro"}).json()
    later = datetime.fromisoformat(_pay(client, h, again, "pay_2").json()["planExpiresAt"])
    assert timedelta(days=59) < later - datetime.now(timezone.utc) <= timedelta(days=60)


def test_cant_pay_for_someone_elses_order_or_a_lower_plan(client):
    h = _user(client, "pay2@test.com")
    other = _user(client, "pay3@test.com")
    order = client.post("/api/billing/order", headers=h, json={"plan": "max"}).json()
    assert _pay(client, other, order).status_code == 400
    assert _pay(client, h, order).json()["plan"] == "max"
    r = client.post("/api/billing/order", headers=h, json={"plan": "pro"})
    assert r.status_code == 400 and "Max" in r.json()["detail"]
    assert client.post("/api/billing/order", headers=h, json={"plan": "basic"}).status_code == 422


def test_webhook_upgrades_even_if_the_app_never_came_back(client):
    h = _user(client, "pay4@test.com")
    order = client.post("/api/billing/order", headers=h, json={"plan": "pro"}).json()
    event = {"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_w", "order_id": order["orderId"], "amount": 29900}}}}
    body = json.dumps(event).encode()
    assert client.post("/api/billing/webhook", content=body, headers={"X-Razorpay-Signature": "bad"}).status_code == 400
    assert client.get("/api/auth/me", headers=h).json()["plan"] == "basic"
    r = client.post("/api/billing/webhook", content=body, headers={"X-Razorpay-Signature": _sig(HOOK, body)})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=h).json()["plan"] == "pro"


def test_webhook_ignores_a_wrong_amount(client):
    h = _user(client, "pay5@test.com")
    order = client.post("/api/billing/order", headers=h, json={"plan": "max"}).json()
    event = {"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_x", "order_id": order["orderId"], "amount": 100}}}}
    body = json.dumps(event).encode()
    client.post("/api/billing/webhook", content=body, headers={"X-Razorpay-Signature": _sig(HOOK, body)})
    assert client.get("/api/auth/me", headers=h).json()["plan"] == "basic"


def test_expired_plan_is_basic_again():
    import limits
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    assert limits.plan_from({"plan": "pro", "planExpiresAt": past}) == "basic"
    assert limits.plan_from({"plan": "pro", "planExpiresAt": future}) == "pro"
    assert limits.plan_from({"plan": "max"}) == "max"  # set by hand, never runs out
    assert limits.plan_from({"plan": "gold"}) == "basic"


def test_an_old_pro_order_paid_later_never_steps_max_down(client):
    h = _user(client, "pay6@test.com")
    old_pro = client.post("/api/billing/order", headers=h, json={"plan": "pro"}).json()
    max_order = client.post("/api/billing/order", headers=h, json={"plan": "max"}).json()
    first = _pay(client, h, max_order).json()
    assert first["plan"] == "max"
    after = _pay(client, h, old_pro, "pay_old").json()
    assert after["plan"] == "max" and after["planExpiresAt"] > first["planExpiresAt"]


def test_order_never_returns_the_secret(client):
    h = _user(client, "pay7@test.com")
    order = client.post("/api/billing/order", headers=h, json={"plan": "pro"})
    assert SECRET not in order.text and HOOK not in order.text
    assert SECRET not in client.get("/api/usage", headers=h).text


@pytest.fixture
def fake_rzp_api(monkeypatch):
    """Razorpay's plans / subscriptions / cancel calls, recorded."""
    import billing
    calls = []

    async def rzp(method, path, body=None):
        calls.append((method, path, body))
        if path == "/plans":
            return {"id": f"plan_{uuid.uuid4().hex[:8]}"}
        if path == "/subscriptions":
            return {"id": f"sub_{uuid.uuid4().hex[:10]}"}
        return {"id": path.split("/")[2], "status": "cancelled"}

    monkeypatch.setattr(billing, "_rzp", rzp)
    return calls


def _sub_pay(client, h, sub, payment_id):
    sig = _sig(SECRET, f"{payment_id}|{sub['subscriptionId']}".encode())
    return client.post("/api/billing/subscribe/verify", headers=h,
                       json={"subscriptionId": sub["subscriptionId"], "paymentId": payment_id, "signature": sig})


def _hook(client, event):
    body = json.dumps(event).encode()
    return client.post("/api/billing/webhook", content=body, headers={"X-Razorpay-Signature": _sig(HOOK, body)})


def _charged(sub_id, payment_id, amount):
    return {"event": "subscription.charged", "payload": {
        "subscription": {"entity": {"id": sub_id, "status": "active"}},
        "payment": {"entity": {"id": payment_id, "amount": amount}}}}


def test_autopay_renews_every_month_until_cancelled(client, fake_rzp_api):
    h = _user(client, "auto1@test.com")
    sub = client.post("/api/billing/subscribe", headers=h, json={"plan": "pro"}).json()
    assert sub["amount"] == 29900 and sub["subscriptionId"].startswith("sub_")
    assert [c[1] for c in fake_rzp_api] == ["/plans", "/subscriptions"]
    # A second subscribe reuses the Razorpay plan made the first time.
    client.post("/api/billing/subscribe", headers=_user(client, "auto1b@test.com"), json={"plan": "pro"})
    assert [c[1] for c in fake_rzp_api].count("/plans") == 1

    assert client.post("/api/billing/subscribe/verify", headers=h, json={
        "subscriptionId": sub["subscriptionId"], "paymentId": "pay_a1", "signature": "bad"}).status_code == 400
    first = _sub_pay(client, h, sub, "pay_a1").json()
    assert first["plan"] == "pro"
    usage = client.get("/api/usage", headers=h).json()
    assert usage["autopay"]["plan"] == "pro" and usage["autopay"]["status"] == "active"

    # The webhook for the same first payment adds nothing; next month's charge adds 30 days.
    _hook(client, _charged(sub["subscriptionId"], "pay_a1", 29900))
    assert client.get("/api/auth/me", headers=h).json()["planExpiresAt"] == first["planExpiresAt"]
    _hook(client, _charged(sub["subscriptionId"], "pay_a2", 29900))
    later = client.get("/api/auth/me", headers=h).json()["planExpiresAt"]
    gap = datetime.fromisoformat(later) - datetime.fromisoformat(first["planExpiresAt"])
    assert timedelta(days=29) < gap <= timedelta(days=30)
    # A wrong amount is ignored.
    _hook(client, _charged(sub["subscriptionId"], "pay_a3", 100))
    assert client.get("/api/auth/me", headers=h).json()["planExpiresAt"] == later

    # While autopay is on, buying the same plan again is refused (no double charge).
    assert client.post("/api/billing/subscribe", headers=h, json={"plan": "pro"}).status_code == 400
    assert client.post("/api/billing/order", headers=h, json={"plan": "pro"}).status_code == 400

    # Turning it off cancels at Razorpay; the paid days stay.
    assert client.post("/api/billing/autopay/cancel", headers=h).status_code == 200
    assert ("POST", f"/subscriptions/{sub['subscriptionId']}/cancel", {"cancel_at_cycle_end": 0}) in fake_rzp_api
    me = client.get("/api/auth/me", headers=h).json()
    assert me["plan"] == "pro" and me["planExpiresAt"] == later
    assert client.get("/api/usage", headers=h).json()["autopay"] is None
    assert client.post("/api/billing/autopay/cancel", headers=h).status_code == 400


def test_moving_to_max_stops_the_pro_autopay(client, fake_rzp_api):
    h = _user(client, "auto2@test.com")
    pro = client.post("/api/billing/subscribe", headers=h, json={"plan": "pro"}).json()
    _sub_pay(client, h, pro, "pay_b1")
    mx = client.post("/api/billing/subscribe", headers=h, json={"plan": "max"}).json()
    assert mx["amount"] == 69900
    assert _sub_pay(client, h, mx, "pay_b2").json()["plan"] == "max"
    assert ("POST", f"/subscriptions/{pro['subscriptionId']}/cancel", {"cancel_at_cycle_end": 0}) in fake_rzp_api
    assert client.get("/api/usage", headers=h).json()["autopay"]["plan"] == "max"


def test_halted_autopay_is_off(client, fake_rzp_api):
    h = _user(client, "auto3@test.com")
    sub = client.post("/api/billing/subscribe", headers=h, json={"plan": "pro"}).json()
    _sub_pay(client, h, sub, "pay_c1")
    _hook(client, {"event": "subscription.halted", "payload": {"subscription": {"entity": {"id": sub["subscriptionId"]}}}})
    assert client.get("/api/usage", headers=h).json()["autopay"] is None
    assert client.get("/api/auth/me", headers=h).json()["plan"] == "pro"  # paid days stay


def test_autopay_unavailable_says_503_so_the_app_pays_once(client, monkeypatch):
    import billing

    async def refused(method, path, body=None):
        raise billing.GatewayError("Payments aren't working right now.")

    monkeypatch.setattr(billing, "_rzp", refused)
    h = _user(client, "auto4@test.com")
    assert client.post("/api/billing/subscribe", headers=h, json={"plan": "pro"}).status_code == 503
    assert client.post("/api/billing/order", headers=h, json={"plan": "pro"}).status_code == 200
