"""Attachments like ChatGPT and Claude: documents show on the message they came with, the Counsellor reads files and
pictures too, and voice notes are kept (they play back) and answered from what was said.

Offline: MongoDB is mongomock and the model is a fake, so no keys or network are needed.
"""
import io
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
        return _Stream("Got it.")
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
    import media

    async def fake_transcribe(data, filename, lang, hint=None, context=None):
        return ("" if data == b"silence" else "I had a long day at college"), "en"
    media.transcribe_detect = fake_transcribe
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        token = c.post("/api/auth/register", json={"name": "Asha", "email": "asha@test.com", "password": "secret1"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def _system(call):
    return call["messages"][0]["content"]


def _send(client, cid, body):
    CALLS.clear()
    client.post(f"/api/conversations/{cid}/stream", json={"agent": True, **body})
    return next(k for k in CALLS if k.get("stream"))


def _upload(client, cid, name, text):
    r = client.post(f"/api/conversations/{cid}/files", files={"file": (name, io.BytesIO(text.encode()), "text/plain")})
    assert r.status_code == 200, r.text
    return r.json()


def test_counsellor_reads_attached_files_and_shows_them_on_the_message(client):
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    f = _upload(client, cid, "timetable.txt", "Exam timetable: Physics on Monday 9 March, Maths on Thursday 12 March.")
    call = _send(client, cid, {"content": "Help me plan my week", "files": [f["id"]]})
    system = _system(call)
    assert "Physics on Monday 9 March" in system  # the Counsellor reads files now
    assert "the user attached these files: [timetable.txt]" in system
    saved = client.get(f"/api/conversations/{cid}").json()["messages"][0]
    assert saved["files"] == [{"id": f["id"], "name": "timetable.txt", "contentType": "text/plain", "size": f["size"]}]


def test_only_files_of_this_chat_go_on_the_message(client):
    other = client.post("/api/conversations", json={}).json()["id"]
    elsewhere = _upload(client, other, "secret.txt", "not for this chat")
    cid = client.post("/api/conversations", json={}).json()["id"]
    _send(client, cid, {"content": "hello", "files": [elsewhere["id"], "nope"]})
    saved = client.get(f"/api/conversations/{cid}").json()["messages"][0]
    assert saved["files"] == []


def test_voice_note_is_kept_written_out_and_answered(client):
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    r = client.post("/api/audio/note", data={"conversationId": cid},
                    files={"file": ("voice-note.webm", io.BytesIO(b"OggS-fake-audio"), "audio/webm;codecs=opus")})
    assert r.status_code == 200, r.text
    note = r.json()
    assert note["text"] == "I had a long day at college" and note["media"]["contentType"] == "audio/webm"
    played = client.get(note["media"]["url"])
    assert played.status_code == 200 and played.content == b"OggS-fake-audio"

    call = _send(client, cid, {"content": note["text"], "audio": note["media"]["id"], "audioSeconds": 4.26})
    assert "Their message is a voice note" in _system(call)
    saved = client.get(f"/api/conversations/{cid}").json()["messages"][0]
    assert saved["audio"] == {"id": note["media"]["id"], "seconds": 4.3}
    assert saved["content"] == "I had a long day at college"


def test_voice_note_without_words_or_unknown_is_refused(client):
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    r = client.post("/api/audio/note", data={"conversationId": cid},
                    files={"file": ("voice-note.webm", io.BytesIO(b"silence"), "audio/webm")})
    assert r.status_code == 422 and "couldn't hear" in r.json()["detail"]
    r = client.post("/api/audio/note", data={"conversationId": cid},
                    files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")})
    assert r.status_code == 415
    r = client.post(f"/api/conversations/{cid}/stream", json={"content": "hi", "audio": "missing"})
    assert r.status_code == 400
