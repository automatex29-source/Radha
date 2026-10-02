"""Stop: closing the stream cancels the model call, and the part already written is saved and marked stopped.

Offline: MongoDB is mongomock and the model is a fake that writes one sentence and then never finishes.
"""
import asyncio
import json
import os
import sys
import time
import types
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STATE = {}


class _SlowStream:
    """Writes one sentence, then waits for more forever (until cancelled)."""

    def __init__(self):
        self.sent = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.sent:
            self.sent = True
            delta = types.SimpleNamespace(content="Here is the first part of a long answer.", tool_calls=None)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)])
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            STATE["cancelled"] = True
            raise
        raise StopAsyncIteration


async def _fake_completion(**kw):
    if kw.get("stream"):
        return _SlowStream()
    msg = types.SimpleNamespace(content='{"add": [], "remove": []}')
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
        token = c.post("/api/auth/register", json={"name": "Asha", "email": "asha-stop@test.com",
                                                   "password": "secret1"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def _stop_after_first_words(client, cid, slow_send=False):
    """POST a message, read until the first words arrive, then close the connection like the Stop button."""
    import server
    STATE.clear()

    async def run():
        first = asyncio.Event()
        chunks = []
        body = json.dumps({"content": "tell me a long story", "agent": False}).encode()
        sent_body = False

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": body, "more_body": False}
            await first.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                chunks.append(message["body"].decode())
                if "first part" in message["body"].decode():
                    first.set()
                    if slow_send:  # the browser stops reading while this chunk is still being sent
                        await asyncio.sleep(3600)

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
                 "scheme": "http", "path": f"/api/conversations/{cid}/stream", "raw_path": b"", "query_string": b"",
                 "root_path": "", "server": ("test", 80), "client": ("test", 1),
                 "headers": [(b"content-type", b"application/json"),
                             (b"authorization", client.headers["Authorization"].encode())]}
        await asyncio.wait_for(server.app(scope, receive, send), 10)
        return "".join(chunks)

    return client.portal.call(run)


@pytest.mark.parametrize("slow_send", [False, True])
def test_stop_keeps_the_partial_reply_and_cancels_the_model(client, slow_send):
    cid = client.post("/api/conversations", json={}).json()["id"]
    streamed = _stop_after_first_words(client, cid, slow_send)
    assert "first part" in streamed and "event: done" not in streamed
    if not slow_send:
        assert STATE.get("cancelled"), "the model call kept running after Stop"
    msgs = client.get(f"/api/conversations/{cid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Here is the first part of a long answer."
    assert msgs[1]["stopped"] is True
    assert msgs[0]["stopped"] is False
