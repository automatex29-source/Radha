"""The Counsellor tab: its own prompt and chat list, no tools, no memory, and helplines in a crisis.

Offline: MongoDB is mongomock and the model is a fake, so no keys or network are needed.
"""
import os
import sys
import time
import types
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CALLS = []


class _Stream:
    def __init__(self, text):
        self.parts = [text]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.parts:
            raise StopAsyncIteration
        delta = types.SimpleNamespace(content=self.parts.pop(0), tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)])


async def _fake_completion(**kw):
    CALLS.append(kw)
    if kw.get("stream"):
        return _Stream("I hear you. Bhagavad Gita 2.47 reminds us to focus on our actions.")
    msg = types.SimpleNamespace(content='{"add": ["Name is Meera."], "remove": []}')
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
    import motor.motor_asyncio
    import litellm
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    litellm.acompletion = _fake_completion
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        token = c.post("/api/auth/register", json={"name": "Meera", "email": "meera@test.com", "password": "secret1"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def _send(client, cid, text):
    CALLS.clear()
    body = client.post(f"/api/conversations/{cid}/stream", json={"content": text, "agent": True}).text
    return next(k for k in CALLS if k.get("stream")), body


def test_counsellor_chats_have_their_own_list(client):
    normal = client.post("/api/conversations", json={}).json()
    calm = client.post("/api/conversations", json={"mode": "counsellor"}).json()
    assert calm["mode"] == "counsellor" and normal["mode"] is None
    assert [c["id"] for c in client.get("/api/conversations").json()] == [normal["id"]]
    assert [c["id"] for c in client.get("/api/conversations?mode=counsellor").json()] == [calm["id"]]


def test_counsellor_uses_gita_prompt_without_tools_or_memory(client):
    client.delete("/api/memory")
    client.put("/api/memory/settings", json={"auto": True})
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    call, body = _send(client, cid, "My name is Meera and I feel lost after failing my exam")
    system = call["messages"][0]["content"]
    assert "Bhagavad Gita" in system and "Tele-MANAS 14416" in system
    assert not call.get("tools")
    assert "14416" not in body  # no crisis, no helpline block
    time.sleep(0.5)
    assert client.get("/api/memory").json() == []  # counselling is never saved to memory


@pytest.mark.parametrize("text", ["I want to die", "मैं आत्महत्या करना चाहता हूँ", "my husband beats me"])
def test_crisis_reply_always_has_helplines(client, text):
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    call, body = _send(client, cid, text)
    assert "may describe a crisis" in call["messages"][0]["content"]
    assert "14416" in body and "1800-599-0019" in body and "112" in body
    saved = client.get(f"/api/conversations/{cid}").json()["messages"][-1]["content"]
    assert "Tele-MANAS: 14416" in saved


def test_crisis_words_are_not_matched_loosely():
    import counsellor
    assert not counsellor.is_crisis("I love grapes and want to end my day with a walk")
    assert counsellor.is_crisis("mujhe jeena nahi hai")
