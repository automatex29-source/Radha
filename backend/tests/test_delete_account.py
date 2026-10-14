"""Deleting an account asks for the password, then removes the user and their data. MongoDB is mongomock."""
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
                      AI_MODEL="openai/gpt-oss-120b")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        yield c


def _account(client, email):
    r = client.post("/api/auth/register", json={"name": "Ravi", "email": email, "password": "secret1"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_wrong_password_keeps_the_account(client):
    h = _account(client, "ravi-keep@test.com")
    r = client.post("/api/auth/delete-account", json={"password": "nope"}, headers=h)
    assert r.status_code == 403
    assert client.get("/api/auth/me", headers=h).status_code == 200


def test_delete_removes_user_and_their_data(client):
    other = _account(client, "other@test.com")
    other_conv = client.post("/api/conversations", json={}, headers=other).json()["id"]
    h = _account(client, "ravi-go@test.com")
    conv = client.post("/api/conversations", json={}, headers=h).json()["id"]
    client.post("/api/projects", json={"name": "Mine"}, headers=h)
    client.post("/api/memory", json={"content": "likes tea"}, headers=h)

    r = client.post("/api/auth/delete-account", json={"password": "secret1"}, headers=h)
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ravi-go@test.com", "password": "secret1"}).status_code == 401

    import asyncio
    import server

    async def counts():
        return [await server.db.conversations.count_documents({"id": conv}),
                await server.db.projects.count_documents({"name": "Mine"}),
                await server.db.memories.count_documents({"content": "likes tea"}),
                await server.db.conversations.count_documents({"id": other_conv})]
    assert asyncio.run(counts()) == [0, 0, 0, 1]  # someone else's chat is untouched
    # The same email can sign up again afterwards.
    assert client.post("/api/auth/register", json={"name": "Ravi", "email": "ravi-go@test.com",
                                                   "password": "secret2"}).status_code == 200


def test_security_headers(client):
    r = client.get("/api/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
