"""Password guessing is stopped after 10 wrong tries; the right password and a reset still work. MongoDB is mongomock."""
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
        c.post("/api/auth/register", json={"name": "Asha", "email": "asha-lock@test.com", "password": "secret1"})
        yield c


def _login(client, password, email="asha-lock@test.com"):
    return client.post("/api/auth/login", json={"email": email, "password": password}).status_code


def test_right_password_clears_the_count(client):
    assert [_login(client, "wrong") for _ in range(9)] == [401] * 9
    assert _login(client, "secret1") == 200
    assert _login(client, "wrong") == 401  # the count started again


def test_guessing_is_stopped_then_waits(client, monkeypatch):
    import server
    server._login_failures.clear()
    assert [_login(client, f"guess{i}") for i in range(10)] == [401] * 10
    assert _login(client, "guess-again") == 429
    assert _login(client, "secret1") == 429  # even the right password waits, so guessing can't continue
    assert _login(client, "x", email="ASHA-LOCK@test.com") == 429  # same account in capitals
    assert _login(client, "x", email="someone-else@test.com") == 401  # other accounts are not affected
    later = time.monotonic() + server.LOGIN_WINDOW_SECONDS + 1
    monkeypatch.setattr(server.time, "monotonic", lambda: later)
    assert _login(client, "secret1") == 200


def test_one_connection_guessing_many_accounts_is_stopped(client, monkeypatch):
    """A bot trying a leaked password list against many different emails is stopped by its internet address."""
    import server
    monkeypatch.setenv("ABUSE_LIMITS", "on")
    server._login_failures.clear()
    server._ip_failures.clear()
    bot = {"X-Forwarded-For": "203.0.113.9"}
    codes = [client.post("/api/auth/login", headers=bot, json={"email": f"victim{i}@test.com", "password": "123456"})
             .status_code for i in range(server.LOGIN_MAX_FAILURES_PER_IP)]
    assert codes == [401] * server.LOGIN_MAX_FAILURES_PER_IP
    assert client.post("/api/auth/login", headers=bot,
                       json={"email": "asha-lock@test.com", "password": "secret1"}).status_code == 429
    # Someone else on another connection signs in normally.
    assert client.post("/api/auth/login", headers={"X-Forwarded-For": "198.51.100.4"},
                       json={"email": "asha-lock@test.com", "password": "secret1"}).status_code == 200
    server._ip_failures.clear()


def test_very_long_passwords_are_refused_before_checking(client):
    assert _login(client, "x" * 5000) == 422
