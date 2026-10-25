"""The owner dashboard: sign-ins, active people, plans sold, revenue and profit, use per person and what people
ask (never counsellor chats). Owner only. MongoDB is mongomock."""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b", OWNER_EMAIL="dash-boss@test.com")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        c.server = server
        yield c
    os.environ.pop("OWNER_EMAIL", None)


def _register(client, email, name="Someone"):
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": "secret1"})
    assert r.status_code == 200
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}"}



def test_only_the_owner_sees_the_dashboard(client):
    boss = _register(client, "dash-boss@test.com", "Boss")
    other = _register(client, "dash-nosy@test.com")
    assert client.get("/api/admin/dashboard", headers=_h(other["token"])).status_code == 404
    assert client.get("/api/admin/dashboard").status_code == 401
    assert client.put("/api/admin/dashboard/costs", json={"chat": 9}, headers=_h(other["token"])).status_code == 404
    r = client.get("/api/admin/dashboard?range=24h", headers=_h(boss["token"]))
    assert r.status_code == 200
    assert client.get("/api/admin/dashboard?range=forever", headers=_h(boss["token"])).status_code == 422


def test_dashboard_numbers(client):
    db = client.server.db
    boss = client.post("/api/auth/login", json={"email": "dash-boss@test.com", "password": "secret1"}).json()
    asha = _register(client, "dash-asha@test.com", "Asha")
    client.post("/api/auth/login", json={"email": "dash-asha@test.com", "password": "secret1"})
    now = datetime.now(timezone.utc).isoformat()

    async def seed():
        await db.payments.insert_one({"orderId": "o1", "userId": asha["user"]["id"], "plan": "pro", "amount": 29900,
                                      "status": "paid", "createdAt": now, "paidAt": now})
        await db.payments.insert_one({"orderId": "o2", "userId": asha["user"]["id"], "plan": "max", "amount": 69900,
                                      "status": "created", "createdAt": now})
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        await db.payments.insert_one({"orderId": "o3", "userId": asha["user"]["id"], "plan": "max", "amount": 69900,
                                      "status": "paid", "createdAt": old, "paidAt": old})
        for conv_id, mode, text in (("c1", "chat", "Write python code for my app, mail me at a@b.com or 9876543210"),
                                    ("c2", "counsellor", "I feel very anxious about my exams")):
            await db.conversations.insert_one({"id": conv_id, "userId": asha["user"]["id"], "mode": mode, "createdAt": now})
            await db.messages.insert_one({"id": conv_id + "m", "conversationId": conv_id, "role": "user",
                                          "content": text, "createdAt": now})
        await client.server.monitor.count(db, asha["user"]["id"], "chat", "web")
        await client.server.monitor.count(db, asha["user"]["id"], "picture")
    client.portal.call(seed)

    d = client.get("/api/admin/dashboard?range=24h", headers=_h(boss["token"])).json()
    assert d["bucket"] == "hour" and len(d["series"]) == 24
    k = d["kpis"]
    assert k["revenue"]["value"] == 299 and k["activeUsers"]["value"] >= 1 and k["logins"]["value"] >= 2
    assert k["signups"]["value"] >= 2 and k["onlineNow"] >= 1
    pro = next(p for p in d["plans"]["sold"] if p["plan"] == "pro")
    assert pro["count"] == 1 and pro["revenue"] == 299
    assert d["plans"]["checkoutsStarted"] == 2 and d["plans"]["checkoutsPaid"] == 1
    m = d["money"]
    assert m["aiCost"] == pytest.approx(0.05 + 0.20 + 2.00)
    assert m["profit"] == pytest.approx(299 - m["aiCost"] - m["hostingCost"] - m["paymentFees"], abs=0.02)
    assert sum(r["revenue"] for r in d["series"]) == 299 and sum(r["messages"] for r in d["series"]) >= 1
    assert sum(sum(row) for row in d["heat"]) >= 2 and len(d["heat"]) == 7 and len(d["heat"][0]) == 24
    r = d["ratios"]
    assert r["checkoutConversion"] == 50.0 and r["avgOrder"] == 299 and r["arpu"] > 0
    assert r["newActive"] + r["returningActive"] == k["activeUsers"]["value"]
    me = next(p for p in d["people"] if p["email"] == "dash-asha@test.com")
    assert me["messages"] == 1 and me["made"] == 1 and me["paid"] == 299
    assert any(x["email"] == "dash-asha@test.com" and x["method"] == "password" for x in d["logins"])

    asks = d["asks"]
    assert asks["total"] == 1  # the counsellor chat is private
    assert all("anxious" not in r["text"] for r in asks["recent"])
    q = asks["recent"][0]
    assert "a@b.com" not in q["text"] and "9876543210" not in q["text"] and q["topic"] == "Coding & apps"

    assert next(c for c in d["content"] if c["key"] == "conversations")["period"] >= 2
    assert d["subscriptions"]["newCustomers"] == 0 and d["subscriptions"]["returningCustomers"] == 1
    assert d["subscriptions"]["lifetimeRevenue"] == 299 + 699 and d["subscriptions"]["customersEver"] == 1
    assert d["engagement"]["mau"] >= 1 and d["growth"]["signupMethods"]["email"] >= 2
    assert d["quality"]["satisfaction"] is None and d["health"]["total"] >= 0

    week = client.get("/api/admin/dashboard?range=7d", headers=_h(boss["token"])).json()
    assert week["bucket"] == "day" and len(week["series"]) == 7
    assert week["kpis"]["revenue"]["value"] == 299 + 699
    assert week["kpis"]["messages"]["value"] >= 1
    assert sum(r["revenue"] for r in week["series"]) == 299 + 699
    assert all("prevActive" in r and r["cost"] > 0 for r in week["series"])


def test_owner_sets_costs(client):
    boss = client.post("/api/auth/login", json={"email": "dash-boss@test.com", "password": "secret1"}).json()
    r = client.put("/api/admin/dashboard/costs", json={"hostingMonthly": 1500, "chat": 0.5}, headers=_h(boss["token"]))
    assert r.status_code == 200 and r.json()["hostingMonthly"] == 1500 and r.json()["chat"] == 0.5
    d = client.get("/api/admin/dashboard?range=30d", headers=_h(boss["token"])).json()
    assert d["costs"]["hostingMonthly"] == 1500 and d["money"]["hostingCost"] == 1500
    assert client.put("/api/admin/dashboard/costs", json={"chat": -1}, headers=_h(boss["token"])).status_code == 422
