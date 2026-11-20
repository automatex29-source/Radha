"""Answers keep being written when the browser leaves, and only Stop ends one early.

Leaving (closing the tab, switching apps, losing the connection) doesn't stop the reply: it is written on the
server and saved to the chat, and another device can follow it while it is written. Stop (POST .../stop) cancels
the model call, and the part already written is saved and marked stopped. A reply cut off by a restart is saved
from its draft when the server starts again.

Offline: MongoDB is mongomock and the model is a fake that writes one sentence and then waits until the test
lets it finish (or it is cancelled).
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
        if self.sent == "second":
            raise StopAsyncIteration
        try:
            await STATE["release"].wait()
        except asyncio.CancelledError:
            STATE["cancelled"] = True
            raise
        self.sent = "second"
        delta = types.SimpleNamespace(content=" And here is the end.", tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)])


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


def _asgi(client, method, path, body=None, until="first part", slow_send=False):
    """Make a request and read until `until` arrives, then close the connection like a browser that leaves."""
    import server

    async def run():
        seen = asyncio.Event()
        chunks = []
        raw = json.dumps(body).encode() if body is not None else b""
        sent_body = False

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": raw, "more_body": False}
            await seen.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                chunks.append(message["body"].decode())
                if until in "".join(chunks):
                    seen.set()
                    if slow_send:  # the browser stops reading while this chunk is still being sent
                        await asyncio.sleep(3600)

        path_only, _, query = path.partition("?")
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
                 "scheme": "http", "path": path_only, "raw_path": b"", "query_string": query.encode(),
                 "root_path": "", "server": ("test", 80), "client": ("test", 1),
                 "headers": [(b"content-type", b"application/json"),
                             (b"authorization", client.headers["Authorization"].encode())]}
        try:
            await asyncio.wait_for(server.app(scope, receive, send), 5)
        except asyncio.TimeoutError:
            pass  # a slow_send browser never finishes taking the chunk
        return "".join(chunks)

    return client.portal.call(run)


def _ask_and_leave(client, cid, slow_send=False):
    """Ask a question, read until the first words arrive, then leave (close the tab)."""
    STATE.clear()
    STATE["release"] = client.portal.call(_new_event)
    return _asgi(client, "POST", f"/api/conversations/{cid}/stream",
                 {"content": "tell me a long story", "agent": False}, slow_send=slow_send)


async def _new_event():
    return asyncio.Event()


def _wait_saved(client, cid, n=2):
    for _ in range(100):
        data = client.get(f"/api/conversations/{cid}").json()
        if len(data["messages"]) >= n and not data["live"]:
            return data
        time.sleep(0.05)
    raise AssertionError("the reply was not saved")


@pytest.mark.parametrize("slow_send", [False, True])
def test_leaving_does_not_stop_the_reply(client, slow_send):
    cid = client.post("/api/conversations", json={}).json()["id"]
    streamed = _ask_and_leave(client, cid, slow_send)
    assert "first part" in streamed and "event: done" not in streamed
    time.sleep(0.2)
    assert not STATE.get("cancelled"), "leaving the page stopped the reply"
    # Another device signed in to the same account sees that a reply is being written, and follows it.
    assert client.get(f"/api/conversations/{cid}").json()["live"] is True
    replay = _asgi(client, "GET", f"/api/conversations/{cid}/live?after=0")
    assert "first part" in replay
    # The reply finishes on the server and is saved to the chat.
    client.portal.call(_release)
    data = _wait_saved(client, cid)
    msgs = data["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Here is the first part of a long answer. And here is the end."
    assert msgs[1]["stopped"] is False
    # Following a finished reply: nothing left to stream; the chat has it.
    assert client.get(f"/api/conversations/{cid}/live?after=999").status_code == 204


async def _release():
    STATE["release"].set()


def test_follow_from_where_it_left_off(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    first = _ask_and_leave(client, cid)
    events = [e for e in first.split("\n\n") if e.strip() and not e.startswith(":")]
    client.portal.call(_release)
    _wait_saved(client, cid)
    rest = client.get(f"/api/conversations/{cid}/live?after={len(events)}").text
    assert "first part" not in rest and "the end" in rest and "event: done" in rest


def test_stop_keeps_the_partial_reply_and_cancels_the_model(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    _ask_and_leave(client, cid)
    assert client.post(f"/api/conversations/{cid}/stop").json() == {"stopped": True}
    assert STATE.get("cancelled"), "the model call kept running after Stop"
    msgs = _wait_saved(client, cid)["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Here is the first part of a long answer."
    assert msgs[1]["stopped"] is True
    assert msgs[0]["stopped"] is False
    assert client.post(f"/api/conversations/{cid}/stop").json() == {"stopped": False}


def test_other_accounts_cannot_follow_or_stop(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    _ask_and_leave(client, cid)
    token = client.post("/api/auth/register", json={"name": "Ravi", "email": "ravi-stop@test.com",
                                                    "password": "secret1"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/conversations/{cid}/live", headers=headers).status_code == 404
    assert client.post(f"/api/conversations/{cid}/stop", headers=headers).status_code == 404
    assert client.post(f"/api/conversations/{cid}/stop").json() == {"stopped": True}


def test_a_reply_cut_off_by_a_restart_is_saved_from_its_draft(client):
    import live_turns
    import server
    cid = client.post("/api/conversations", json={}).json()["id"]

    async def leave_draft():
        await server.db.conversations.update_one({"id": cid}, {"$set": {"liveDraft": {
            "text": "Half of an answer", "userId": "x", "startedAt": server.now_iso(), "updatedAt": server.now_iso()}}})
        return await live_turns.recover(server.db)

    assert client.portal.call(leave_draft) == 1
    msgs = client.get(f"/api/conversations/{cid}").json()["messages"]
    assert msgs[-1]["content"] == "Half of an answer" and msgs[-1]["stopped"] is True
    assert client.portal.call(live_turns.recover, server.db) == 0  # once only


def test_state_tells_an_open_chat_on_another_device_about_a_new_answer(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    assert client.get(f"/api/conversations/{cid}/state").json() == {"count": 0, "lastId": None, "live": False}
    _ask_and_leave(client, cid)
    state = client.get(f"/api/conversations/{cid}/state").json()
    assert state["count"] == 1 and state["live"] is True
    client.portal.call(_release)
    msgs = _wait_saved(client, cid)["messages"]
    assert client.get(f"/api/conversations/{cid}/state").json() == {"count": 2, "lastId": msgs[-1]["id"], "live": False}
