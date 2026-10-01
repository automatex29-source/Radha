"""Help Center: bug reports and feedback are saved and emailed to the team.

Offline: MongoDB is mongomock and the email provider is replaced by a recorder.
"""
import os
import sys
import time
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SENT = []


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
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
        r = c.post("/api/auth/register", json={"name": "Asha", "email": "asha@test.com", "password": "secret1"})
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c


def test_requires_login(client):
    from fastapi.testclient import TestClient
    import server
    assert TestClient(server.app).post("/api/help/reports", json={"kind": "bug", "message": "hello"}).status_code == 401


def test_bug_report_is_saved_and_emailed(client, monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "k")
    monkeypatch.setenv("MAIL_FROM", "owner@test.com")
    monkeypatch.delenv("SUPPORT_EMAIL", raising=False)
    SENT.clear()
    r = client.post("/api/help/reports", json={"kind": "bug", "message": "Decks <b>won't</b> open\nsecond line",
                                               "area": "Decks", "page": "/decks", "device": "Android"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received"
    assert SENT and SENT[-1]["to"] == "owner@test.com"
    assert SENT[-1]["subject"] == "[Krish AI] Bug report: Decks <b>won't</b> open"
    assert "&lt;b&gt;" in SENT[-1]["html"] and "<b>won't" not in SENT[-1]["html"]
    assert "asha@test.com" in SENT[-1]["text"]
    mine = client.get("/api/help/reports").json()
    assert mine[0]["kind"] == "bug" and mine[0]["area"] == "Decks"


def test_feedback_goes_to_support_email(client, monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "k")
    monkeypatch.setenv("MAIL_FROM", "owner@test.com")
    monkeypatch.setenv("SUPPORT_EMAIL", "help@test.com")
    SENT.clear()
    r = client.post("/api/help/reports", json={"kind": "feedback", "message": "Love the Counsellor", "rating": 5})
    assert r.status_code == 200
    assert SENT[-1]["to"] == "help@test.com" and "5/5" in SENT[-1]["text"]


def test_saved_without_email(client, monkeypatch):
    for k in ("BREVO_API_KEY", "RESEND_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    SENT.clear()
    r = client.post("/api/help/reports", json={"kind": "question", "message": "How do I make a deck?"})
    assert r.status_code == 200 and not SENT


def test_validation_and_rate_limit(client):
    assert client.post("/api/help/reports", json={"kind": "spam", "message": "hello"}).status_code == 422
    assert client.post("/api/help/reports", json={"kind": "feedback", "message": "ok", "rating": 9}).status_code == 422
    codes = [client.post("/api/help/reports", json={"kind": "feedback", "message": f"note {i}"}).status_code
             for i in range(12)]
    assert codes[-1] == 429
