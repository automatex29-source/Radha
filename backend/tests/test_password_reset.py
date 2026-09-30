"""Forgot password: a one-time, time-limited link is emailed and sets a new password.

Offline: MongoDB is mongomock and the email provider is replaced by a recorder.
"""
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SENT = []


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b", APP_URL="https://krish.example")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import mailer

    async def fake_send(to, subject, html, text):
        SENT.append({"to": to, "subject": subject, "html": html, "text": text})

    mailer.send = fake_send
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        c.post("/api/auth/register", json={"name": "Ravi", "email": "ravi@test.com", "password": "oldpass1"})
        yield c, server


def _link_token():
    m = re.search(r"https://krish\.example/reset-password\?token=([\w-]+)", SENT[-1]["text"])
    assert m, SENT[-1]["text"]
    return m.group(1)


def test_without_email_provider_nothing_is_sent(client, monkeypatch):
    c, _ = client
    for k in ("BREVO_API_KEY", "RESEND_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    SENT.clear()
    r = c.post("/api/auth/forgot-password", json={"email": "ravi@test.com"})
    assert r.json() == {"ok": True, "emailConfigured": False}
    assert SENT == []


def test_reset_flow_sets_new_password_once(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("BREVO_API_KEY", "k")
    monkeypatch.setenv("MAIL_FROM", "me@gmail.com")
    SENT.clear()
    assert c.post("/api/auth/forgot-password", json={"email": "RAVI@test.com"}).json()["emailConfigured"] is True
    assert len(SENT) == 1 and SENT[0]["to"] == "ravi@test.com"
    token = _link_token()
    assert c.get(f"/api/auth/reset-password/check?token={token}").json() == {"valid": True}

    r = c.post("/api/auth/reset-password", json={"token": token, "password": "newpass1"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "ravi@test.com" and r.json()["token"]
    assert c.post("/api/auth/login", json={"email": "ravi@test.com", "password": "newpass1"}).status_code == 200
    assert c.post("/api/auth/login", json={"email": "ravi@test.com", "password": "oldpass1"}).status_code == 401

    # The link works only once.
    assert c.post("/api/auth/reset-password", json={"token": token, "password": "another1"}).status_code == 400
    assert c.get(f"/api/auth/reset-password/check?token={token}").json() == {"valid": False}


def test_unknown_email_looks_the_same_and_sends_nothing(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("BREVO_API_KEY", "k")
    monkeypatch.setenv("MAIL_FROM", "me@gmail.com")
    SENT.clear()
    r = c.post("/api/auth/forgot-password", json={"email": "nobody@test.com"})
    assert r.json() == {"ok": True, "emailConfigured": True}
    assert SENT == []


def test_expired_and_wrong_tokens_are_rejected(client, monkeypatch):
    c, server = client
    monkeypatch.setenv("RESEND_API_KEY", "k")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    user = c.post("/api/auth/login", json={"email": "ravi@test.com", "password": "newpass1"}).json()["user"]
    tok = "x" * 43
    c.portal.call(server.db.password_resets.insert_one, {
        "id": "old", "userId": user["id"], "tokenHash": server._reset_hash(tok),
        "createdAt": past, "expiresAt": past, "usedAt": None})
    assert c.post("/api/auth/reset-password", json={"token": tok, "password": "newpass2"}).status_code == 400
    assert c.post("/api/auth/reset-password", json={"token": "y" * 43, "password": "newpass2"}).status_code == 400


def test_second_request_within_a_minute_is_not_resent(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("BREVO_API_KEY", "k")
    monkeypatch.setenv("MAIL_FROM", "me@gmail.com")
    SENT.clear()
    c.post("/api/auth/forgot-password", json={"email": "ravi@test.com"})
    c.post("/api/auth/forgot-password", json={"email": "ravi@test.com"})
    assert len(SENT) == 1
