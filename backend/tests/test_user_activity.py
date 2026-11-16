"""The owner's per-person activity page and the overall activity numbers: features used, how often and when,
tokens, plan and what people made. Never chat text, prompts or counsellor use. MongoDB is mongomock."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b", OWNER_EMAIL="act-boss@test.com")
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


def test_only_the_owner_sees_activity(client):
    _register(client, "act-boss@test.com", "Boss")
    other = _register(client, "act-nosy@test.com")
    uid = other["user"]["id"]
    assert client.get("/api/admin/activity", headers=_h(other["token"])).status_code == 404
    assert client.get(f"/api/admin/users/{uid}/activity", headers=_h(other["token"])).status_code == 404
    assert client.get(f"/api/admin/users/{uid}/activity").status_code == 401


def test_person_activity_shows_use_but_never_what_they_wrote(client):
    db, monitor = client.server.db, client.server.monitor
    boss = client.post("/api/auth/login", json={"email": "act-boss@test.com", "password": "secret1"}).json()
    ravi = _register(client, "act-ravi@test.com", "Ravi")
    uid = ravi["user"]["id"]
    now = datetime.now(timezone.utc).isoformat()
    secret = "my secret plan to propose to Priya"

    async def seed():
        await db.conversations.insert_one({"id": "ac1", "userId": uid, "title": secret, "createdAt": now})
        await db.messages.insert_one({"id": "am1", "conversationId": "ac1", "role": "user", "content": secret,
                                      "createdAt": now})
        await db.conversations.insert_one({"id": "ac2", "userId": uid, "mode": "counsellor", "createdAt": now})
        await monitor.count(db, uid, "chat", "web")
        await monitor.count(db, uid, "chat")
        await monitor.count(db, uid, "counsellor")
        await monitor.count(db, uid, "picture")
        await monitor.tokens(db, uid, 4200, "chat")
        await monitor.tokens(db, uid, 800, "build")
        await db.docs.insert_one({"id": "d1", "userId": uid, "title": "Shop price list", "content": secret, "createdAt": now})
        await db.decks.insert_one({"id": "k1", "userId": uid, "title": "Pitch deck", "prompt": secret,
                                   "slides": [{}, {}, {}], "createdAt": now})
        await db.apps.insert_one({"id": "p1", "userId": uid, "name": "Todo app", "published": {"slug": "todo"}, "createdAt": now})
        await db.automations.insert_one({"id": "u1", "userId": uid, "name": "Morning news", "prompt": secret,
                                         "schedule": {"type": "daily"}, "enabled": True, "createdAt": now})
        await db.automation_runs.insert_one({"id": "r1", "automationId": "u1", "userId": uid, "status": "done",
                                             "output": secret, "startedAt": now})
        await db.media.insert_one({"id": "m1", "userId": uid, "kind": "generated", "name": "chart.xlsx",
                                   "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   "size": 1200, "conversationId": "ac1", "createdAt": now})
        await db.media.insert_one({"id": "m2", "userId": uid, "kind": "generated", "name": "private.png",
                                   "contentType": "image/png", "size": 10, "conversationId": "ac2", "createdAt": now})
    client.portal.call(seed)

    r = client.get(f"/api/admin/users/{uid}/activity?days=7", headers=_h(boss["token"]))
    assert r.status_code == 200
    d = r.json()
    raw = json.dumps(d)
    assert secret not in raw and "Priya" not in raw  # no chat text, titles, prompts or outputs
    assert "counsellor" not in raw.lower() and "private.png" not in raw
    f = {x["kind"]: x for x in d["features"]}
    assert f["chat"]["count"] == 2 and f["web"]["count"] == 1 and f["picture"]["count"] == 1
    assert f["doc"]["count"] == 1 and f["app"]["count"] == 1 and f["automation"]["count"] == 1
    assert f["chat"]["first"] and f["chat"]["last"]
    assert d["usage"]["tokens"] == 5000 and d["usage"]["tokensByKind"] == {"chat": 4200, "build": 800}
    assert d["user"]["email"] == "act-ravi@test.com" and d["user"]["plan"] == "basic"
    assert "password_hash" not in raw
    names = {m["name"] for m in d["made"]}
    assert {"Shop price list", "Pitch deck", "Todo app", "Morning news", "chart.xlsx"} <= names
    assert next(m for m in d["made"] if m["name"] == "chart.xlsx")["label"] == "Excel"
    assert next(m for m in d["made"] if m["name"] == "Todo app")["note"] == "Published"
    assert len(d["daily"]) == 7 and d["daily"][-1]["actions"] >= 6 and d["daily"][-1]["tokens"] == 5000
    assert d["summary"]["activeDays"] >= 1 and d["summary"]["chats"] == 1
    assert any(t["kinds"] == ["login"] for t in d["timeline"])

    assert client.get("/api/admin/users/nobody/activity", headers=_h(boss["token"])).status_code == 404

    o = client.get("/api/admin/activity?days=30", headers=_h(boss["token"])).json()
    assert "counsellor" not in json.dumps(o).lower()
    top = {x["kind"]: x for x in o["features"]}
    assert top["chat"]["count"] >= 2 and top["chat"]["people"] >= 1
    assert o["features"][0]["count"] >= o["features"][-1]["count"]  # most used first
    assert len(o["daily"]) == 30 and o["daily"][-1]["active"] >= 1
    me = next(p for p in o["topPeople"] if p["email"] == "act-ravi@test.com")
    assert me["tokens"] == 5000 and me["favourite"] == "Chat"
    assert o["summary"]["activePeople"] >= 1


def test_deleting_an_account_forgets_its_token_counts(client):
    db, monitor = client.server.db, client.server.monitor
    gone = _register(client, "act-gone@test.com")
    client.portal.call(monitor.tokens, db, gone["user"]["id"], 100, "chat")
    r = client.post("/api/auth/delete-account", headers=_h(gone["token"]),
                       json={"password": "secret1", "confirmEmail": "act-gone@test.com"})
    assert r.status_code == 200, r.text
    assert client.portal.call(db.token_daily.count_documents, {"userId": gone["user"]["id"]}) == 0
