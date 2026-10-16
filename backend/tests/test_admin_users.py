"""Only the owner (OWNER_EMAIL) can see who has signed up and when they last signed in. MongoDB is mongomock."""
import os
import sys
import time
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b", OWNER_EMAIL=" Boss@Test.com , other-owner@test.com")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        yield c
    os.environ.pop("OWNER_EMAIL", None)


def _register(client, email, name="Someone"):
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": "secret1"})
    assert r.status_code == 200
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_sees_everyone_with_last_login(client):
    boss = _register(client, "boss@test.com", "Boss")
    asha = _register(client, "asha-admin@test.com", "Asha")
    assert boss["user"]["isOwner"] is True and asha["user"]["isOwner"] is False
    assert client.post("/api/auth/login", json={"email": "asha-admin@test.com", "password": "secret1"}).status_code == 200

    r = client.get("/api/admin/users", headers=_auth(boss["token"]))
    assert r.status_code == 200
    data = r.json()
    rows = {u["email"]: u for u in data["users"]}
    assert data["total"] == len(data["users"]) >= 2
    assert rows["asha-admin@test.com"]["loginCount"] == 2
    assert rows["asha-admin@test.com"]["lastLoginAt"] and rows["asha-admin@test.com"]["lastSeenAt"]
    assert data["users"][0]["email"] == "asha-admin@test.com"  # most recently active first
    assert all("password_hash" not in u for u in data["users"])


def test_other_users_cannot_see_the_list(client):
    other = _register(client, "nosy@test.com")
    assert client.get("/api/admin/users", headers=_auth(other["token"])).status_code == 404
    assert client.get("/api/admin/users").status_code == 401


def test_opening_the_app_counts_as_a_visit(client):
    user = _register(client, "visitor@test.com")
    before = client.get("/api/admin/users", headers=_auth(_login_boss(client))).json()
    seen_before = next(u["lastSeenAt"] for u in before["users"] if u["email"] == "visitor@test.com")
    time.sleep(0.01)
    assert client.get("/api/auth/me", headers=_auth(user["token"])).status_code == 200
    after = client.get("/api/admin/users", headers=_auth(_login_boss(client))).json()
    assert next(u["lastSeenAt"] for u in after["users"] if u["email"] == "visitor@test.com") > seen_before


def _login_boss(client):
    return client.post("/api/auth/login", json={"email": "boss@test.com", "password": "secret1"}).json()["token"]
