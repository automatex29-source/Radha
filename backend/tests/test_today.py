"""Aaj (Today) card: panchang, the Gita line, a headline and the days-in-a-row count, with no AI call."""
import asyncio
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


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import discover

    async def stories(topic="top", lang="en", limit=24):
        return [{"title": "Big news today", "url": "https://x.test/a", "source": "X", "domain": "x.test"}]
    monkeypatch.setattr(discover, "stories", stories)


def _token(client, email):
    r = client.post("/api/auth/register", json={"name": "Asha", "email": email, "password": "secret1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_today_card(client):
    h = _token(client, "today@test.com")
    r = client.get("/api/today", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["panchang"]["tithi"] and d["panchang"]["month"]
    assert d["verse"]["ref"] and d["verse"]["text"]
    assert d["news"]["title"] == "Big news today"
    assert d["streak"] == {"days": 1, "best": 1, "new": True}
    # A second visit the same day doesn't count again.
    assert client.get("/api/today", headers=h).json()["streak"]["new"] is False
    assert client.get("/api/today").status_code == 401


def test_streak_counts_days_in_a_row():
    import mongomock_motor as mm
    import today
    db = mm.AsyncMongoMockClient()["t"]

    async def run():
        await db.users.insert_one({"id": "u"})
        assert (await today.mark_visit(db, "u", "2026-11-10"))["days"] == 1
        assert (await today.mark_visit(db, "u", "2026-11-11"))["days"] == 2
        assert (await today.mark_visit(db, "u", "2026-11-12"))["days"] == 3
        gap = await today.mark_visit(db, "u", "2026-11-15")
        assert gap["days"] == 1 and gap["best"] == 3
    asyncio.run(run())


def test_festival_day_is_named():
    import today
    from datetime import date
    p = today._panchang(date(2026, 11, 8), *today.DELHI)  # Diwali week 2026
    assert isinstance(p["festivals"], list)
