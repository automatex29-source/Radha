"""Launch additions: Google sign-in, invite a friend, offer codes, 👍 / 👎, crash and usage tracking,
spam protection and the daily Gita verse. MongoDB is mongomock; Google, Razorpay and push services are faked."""
import hashlib
import hmac
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SECRET = "key-secret"


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b", RAZORPAY_KEY_ID="rzp_test_abc", RAZORPAY_KEY_SECRET=SECRET,
                      OWNER_EMAIL="boss@test.com", GOOGLE_CLIENT_ID="test-client.apps.googleusercontent.com")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        yield c
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "OWNER_EMAIL", "GOOGLE_CLIENT_ID"):
        os.environ.pop(k, None)


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    import billing
    import google_signin
    count = {"n": 0}

    async def create(amount, receipt, notes):
        count["n"] += 1
        return {"id": f"order_{count['n']}_{receipt[:6]}", "amount": amount}

    async def verify(credential):
        if not credential.startswith("good-"):
            raise google_signin.GoogleSignInError("bad token")
        email = credential[5:].split("|")[0]
        return {"email": email, "name": "Gita G", "sub": f"sub-{email}", "picture": None}

    monkeypatch.setattr(billing, "_create_razorpay_order", create)
    monkeypatch.setattr(google_signin, "verify", verify)


def _register(client, email, ref=None):
    body = {"name": "Asha", "email": email, "password": "secret1", **({"ref": ref} if ref else {})}
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _days_left(user):
    return (datetime.fromisoformat(user["planExpiresAt"]) - datetime.now(timezone.utc)).days


# ------------------------------------------------------------- Google sign-in
def test_login_page_knows_google_is_on(client):
    assert client.get("/api/auth/config").json()["googleClientId"].endswith(".apps.googleusercontent.com")


def _google(email, ref=None):
    return {"credential": f"good-{email}|padding-for-length", **({"ref": ref} if ref else {})}


def test_google_makes_an_account_then_signs_the_same_one_in(client):
    first = client.post("/api/auth/google", json=_google("new@gmail.com"))
    assert first.status_code == 200
    user = first.json()["user"]
    assert user["email"] == "new@gmail.com" and user["google"] and not user["hasPassword"]
    again = client.post("/api/auth/google", json=_google("new@gmail.com")).json()
    assert again["user"]["id"] == user["id"]
    assert client.get("/api/auth/me", headers=_h(again["token"])).status_code == 200
    # There is no password to guess on the password login.
    assert client.post("/api/auth/login", json={"email": "new@gmail.com", "password": ""}).status_code == 401


def test_google_joins_an_existing_email_account(client):
    made = _register(client, "both@test.com")
    r = client.post("/api/auth/google", json=_google("both@test.com"))
    assert r.status_code == 200 and r.json()["user"]["id"] == made["user"]["id"]
    assert r.json()["user"]["hasPassword"] and r.json()["user"]["google"]
    assert client.post("/api/auth/login", json={"email": "both@test.com", "password": "secret1"}).status_code == 200


def test_bad_google_token_is_refused(client):
    r = client.post("/api/auth/google", json={"credential": "forged-" + "x" * 30})
    assert r.status_code == 401


def test_google_account_deletes_with_its_email(client):
    r = client.post("/api/auth/google", json=_google("leave@gmail.com")).json()
    h = _h(r["token"])
    assert client.post("/api/auth/delete-account", headers=h, json={"confirmEmail": "wrong@gmail.com"}).status_code == 403
    assert client.post("/api/auth/delete-account", headers=h, json={"confirmEmail": "Leave@Gmail.com"}).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


# ------------------------------------------------------------- invite a friend
def test_invite_gives_both_people_a_week_of_pro(client):
    inviter = _register(client, "inviter@test.com")
    code = client.get("/api/referrals", headers=_h(inviter["token"])).json()["code"]
    assert len(code) == 7
    friend = _register(client, "friend@test.com", ref=code.lower())
    assert friend["invited"] is True and friend["user"]["plan"] == "pro" and _days_left(friend["user"]) >= 6
    me = client.get("/api/auth/me", headers=_h(inviter["token"])).json()
    assert me["plan"] == "pro" and _days_left(me) >= 6
    summary = client.get("/api/referrals", headers=_h(inviter["token"])).json()
    assert summary["joined"] == 1 and summary["daysEarned"] == 7
    # A made-up code is simply ignored.
    assert _register(client, "nobody-ref@test.com", ref="ZZZZZZZ")["user"]["plan"] == "basic"


def test_invites_by_google_count_too_and_stop_paying_after_the_cap(client, monkeypatch):
    import referrals
    monkeypatch.setattr(referrals, "MAX_REWARDS", 1)
    inviter = _register(client, "capped@test.com")
    code = client.get("/api/referrals", headers=_h(inviter["token"])).json()["code"]
    g = client.post("/api/auth/google", json=_google("gfriend@gmail.com", code)).json()
    assert g["invited"] and g["user"]["plan"] == "pro"
    _register(client, "second-friend@test.com", ref=code)
    summary = client.get("/api/referrals", headers=_h(inviter["token"])).json()
    assert summary["joined"] == 2 and summary["daysEarned"] == 7
    me = client.get("/api/auth/me", headers=_h(inviter["token"])).json()
    assert 6 <= _days_left(me) <= 7


# ------------------------------------------------------------- offer codes
def _pay(client, h, order, payment_id):
    sig = hmac.new(SECRET.encode(), f"{order['orderId']}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return client.post("/api/billing/verify", headers=h,
                       json={"orderId": order["orderId"], "paymentId": payment_id, "signature": sig})


def test_owner_makes_a_code_and_a_buyer_uses_it_once(client):
    boss = _register(client, "boss@test.com")
    bh = _h(boss["token"])
    r = client.post("/api/admin/promos", headers=bh, json={"code": "launch50", "percentOff": 50, "maxUses": 2})
    assert r.status_code == 200 and r.json()["code"] == "LAUNCH50"
    assert client.post("/api/admin/promos", headers=bh, json={"code": "LAUNCH50", "percentOff": 10}).status_code == 400

    buyer = _h(_register(client, "buyer@test.com")["token"])
    assert client.post("/api/admin/promos", headers=buyer, json={"code": "MINE", "percentOff": 90}).status_code == 404
    check = client.post("/api/billing/check-code", headers=buyer, json={"plan": "pro", "code": "Launch50"}).json()
    assert check == {"code": "LAUNCH50", "percentOff": 50, "price": 150}
    order = client.post("/api/billing/order", headers=buyer, json={"plan": "pro", "code": "launch50"}).json()
    assert order["amount"] == 15000 and order["promoCode"] == "LAUNCH50"
    assert _pay(client, buyer, order, "pay_promo_1").json()["plan"] == "pro"
    codes = client.get("/api/admin/promos", headers=bh).json()["codes"]
    assert codes[0]["uses"] == 1
    again = client.post("/api/billing/order", headers=buyer, json={"plan": "pro", "code": "LAUNCH50"})
    assert again.status_code == 400 and "already used" in again.json()["detail"]

    client.put("/api/admin/promos/LAUNCH50", headers=bh, json={"active": False})
    other = _h(_register(client, "buyer2@test.com")["token"])
    off = client.post("/api/billing/check-code", headers=other, json={"plan": "pro", "code": "LAUNCH50"})
    assert off.status_code == 400 and "isn't valid" in off.json()["detail"]


def test_code_last_day_and_price_floor():
    import promos
    assert promos.discounted(29900, 90) == 3000
    assert promos.discounted(100, 90) == 100  # never under ₹1
    end = datetime.fromisoformat(promos._end_of_day("2026-11-30"))
    assert end == datetime(2026, 11, 30, 18, 30, tzinfo=timezone.utc)


# ------------------------------------------------------------- 👍 / 👎
def test_thumbs_down_keeps_the_answer_for_the_owner(client):
    import server
    boss = client.post("/api/auth/login", json={"email": "boss@test.com", "password": "secret1"}).json()
    user = _register(client, "rater@test.com")
    h = _h(user["token"])
    conv = client.post("/api/conversations", headers=h, json={}).json()
    now = datetime.now(timezone.utc)

    async def seed():
        await server.db.messages.insert_many([
            {"id": "q1", "conversationId": conv["id"], "role": "user", "content": "What is 2+2?",
             "createdAt": (now - timedelta(seconds=5)).isoformat()},
            {"id": "a1", "conversationId": conv["id"], "role": "assistant", "content": "It is 5.", "model": "m",
             "createdAt": now.isoformat()},
        ])
    client.portal.call(seed)

    url = f"/api/conversations/{conv['id']}/messages/a1/feedback"
    assert client.post(url, headers=h, json={"rating": "down"}).json() == {"rating": "down"}
    msgs = client.get(f"/api/conversations/{conv['id']}", headers=h).json()["messages"]
    assert next(m for m in msgs if m["id"] == "a1")["rating"] == "down"
    stats = client.get("/api/admin/stats", headers=_h(boss["token"])).json()
    assert stats["days"][0]["thumbsDown"] >= 1
    assert stats["disliked"][0]["question"] == "What is 2+2?" and stats["disliked"][0]["answer"] == "It is 5."

    assert client.post(url, headers=h, json={"rating": "up"}).status_code == 200
    stats = client.get("/api/admin/stats", headers=_h(boss["token"])).json()
    assert stats["days"][0]["thumbsUp"] >= 1 and not any(d["messageId"] == "a1" for d in stats["disliked"])
    # Someone else's chat can't be rated.
    other = _h(_register(client, "nosy@test.com")["token"])
    assert client.post(url, headers=other, json={"rating": "down"}).status_code == 404
    assert client.get("/api/admin/stats", headers=other).status_code == 404


# ------------------------------------------------------------- crash and usage tracking
def test_app_crashes_and_server_errors_reach_the_owner(client, monkeypatch):
    import mailer
    import monitor
    sent = []

    async def send(to, subject, html, text):
        sent.append((to, subject))
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", send)
    monkeypatch.setattr(monitor, "_last_alert", 0.0)

    r = client.post("/api/client-errors", json={"message": "TypeError: x is undefined", "stack": "at Chat", "path": "/"})
    assert r.status_code == 200
    boss = client.post("/api/auth/login", json={"email": "boss@test.com", "password": "secret1"}).json()
    stats = client.get("/api/admin/stats", headers=_h(boss["token"])).json()
    assert any(p["source"] == "app" and "TypeError" in p["message"] for p in stats["problems"])
    assert stats["days"][0]["problems"] >= 1 and stats["totalUsers"] >= 1
    assert sent and sent[0][0] == "boss@test.com" and "problem" in sent[0][1]


def test_daily_counts(client):
    import limits
    import monitor
    import server
    user = _register(client, "counted@test.com")

    async def go():
        await monitor.count(server.db, user["user"]["id"], "chat", "web")
        await monitor.count(server.db, user["user"]["id"], "chat")
        return await monitor.stats(server.db, 1)
    stats = client.portal.call(go)
    today = stats["days"][0]
    assert today["day"] == limits.today()
    assert today["features"]["chat"] >= 2 and today["features"]["web"] >= 1 and today["activeUsers"] >= 1
    assert today["signups"] >= 1


# ------------------------------------------------------------- spam protection
def test_throwaway_emails_are_turned_away(client):
    r = client.post("/api/auth/register", json={"name": "Bot", "email": "bot@mailinator.com", "password": "secret1"})
    assert r.status_code == 400 and "temporary" in r.json()["detail"]


def test_made_up_email_domain_is_turned_away(client, monkeypatch):
    import abuse

    async def no_mail(domain):
        return domain != "nowhere-zz.com"
    monkeypatch.setenv("EMAIL_DNS_CHECK", "on")
    monkeypatch.setattr(abuse, "_domain_takes_mail", no_mail)
    r = client.post("/api/auth/register", json={"name": "Bot", "email": "a@nowhere-zz.com", "password": "secret1"})
    assert r.status_code == 400 and "nowhere-zz.com" in r.json()["detail"]


def test_only_a_few_signups_an_hour_from_one_connection(client, monkeypatch):
    import abuse
    monkeypatch.setenv("ABUSE_LIMITS", "on")
    abuse._hits.clear()
    ip = {"X-Forwarded-For": "203.0.113.9"}
    for i in range(abuse.SIGNUPS_PER_HOUR):
        assert client.post("/api/auth/register", headers=ip,
                           json={"name": "N", "email": f"many{i}@test.com", "password": "secret1"}).status_code == 200
    r = client.post("/api/auth/register", headers=ip, json={"name": "N", "email": "many-x@test.com", "password": "secret1"})
    assert r.status_code == 429
    other_ip = {"X-Forwarded-For": "198.51.100.4"}
    assert client.post("/api/auth/register", headers=other_ip,
                       json={"name": "N", "email": "many-y@test.com", "password": "secret1"}).status_code == 200
    abuse._hits.clear()


def test_message_flood_is_slowed_down(monkeypatch):
    import abuse
    monkeypatch.setenv("ABUSE_LIMITS", "on")
    abuse._hits.clear()
    assert all(abuse.allow("chat", "flooder") for _ in range(20))
    assert not abuse.allow("chat", "flooder")
    assert abuse.allow("chat", "someone-else")
    abuse._hits.clear()


# ------------------------------------------------------------- daily Gita verse
def test_device_signs_up_and_gets_the_morning_verse_once(client, monkeypatch):
    import daily_verse
    import server
    sent = []

    def fake_send(sub, payload, pem):
        sent.append((sub["endpoint"], payload))
        return 410 if "gone" in sub["endpoint"] else 201
    monkeypatch.setattr(daily_verse, "_send_sync", fake_send)

    h = _h(_register(client, "verse@test.com")["token"])
    cfg = client.get("/api/push/config", headers=h).json()
    assert len(cfg["publicKey"]) > 60 and cfg["devices"] == 0 and cfg["verse"]["ref"]
    keys = {"p256dh": "k" * 20, "auth": "a" * 10}
    assert client.post("/api/push/subscribe", headers=h, json={"endpoint": "http://bad", "keys": keys}).status_code == 400
    for ep in ("https://push.example/me", "https://push.example/gone"):
        assert client.post("/api/push/subscribe", headers=h, json={"endpoint": ep, "keys": keys}).status_code == 200
    assert client.get("/api/push/config", headers=h).json()["devices"] == 2

    assert client.post("/api/push/test", headers=h).json() == {"sent": 1}
    assert "Gita verse" in sent[0][1]
    assert client.get("/api/push/config", headers=h).json()["devices"] == 1  # the gone device was forgotten

    class Morning(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 22, 7, 5, tzinfo=daily_verse.IST)
    monkeypatch.setattr(daily_verse, "datetime", Morning)
    sent.clear()
    assert client.portal.call(daily_verse.morning_send) == 1
    assert client.portal.call(daily_verse.morning_send) is None  # once a day
    assert len(sent) == 1

    client.post("/api/push/unsubscribe", headers=h, json={"endpoint": "https://push.example/me"})
    assert client.get("/api/push/config", headers=h).json()["devices"] == 0


def test_real_push_keys_are_made_once(client):
    import daily_verse
    daily_verse._keys.clear()
    first = client.portal.call(daily_verse.ensure_keys)["public"]
    daily_verse._keys.clear()
    assert client.portal.call(daily_verse.ensure_keys)["public"] == first
    from py_vapid import Vapid
    assert Vapid.from_pem(daily_verse._keys["private"].encode())
