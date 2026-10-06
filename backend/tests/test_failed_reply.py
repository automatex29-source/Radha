"""When the AI model fails before writing anything, the question still gets a visible, saved answer. Offline."""
import os
import sys
import time
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def _failing_completion(**kw):
    import litellm
    raise litellm.APIConnectionError(message="provider down", llm_provider="groq", model="openai/gpt-oss-120b")


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
    import motor.motor_asyncio
    import litellm
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    original = litellm.acompletion
    litellm.acompletion = _failing_completion
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    try:
        with TestClient(server.app) as c:
            token = c.post("/api/auth/register", json={"name": "Asha", "email": "asha-fail@test.com",
                                                       "password": "secret1"}).json()["token"]
            c.headers["Authorization"] = f"Bearer {token}"
            yield c
    finally:
        litellm.acompletion = original


@pytest.mark.parametrize("agent", [False, True])
def test_failed_model_leaves_a_saved_note_with_regenerate(client, agent):
    import server
    cid = client.post("/api/conversations", json={}).json()["id"]
    body = client.post(f"/api/conversations/{cid}/stream", json={"content": "hello there", "agent": agent}).text
    assert "event: error" in body
    messages = client.get(f"/api/conversations/{cid}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == server.STREAM_FAILED_NOTE
