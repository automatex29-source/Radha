"""Docs (Canvas-style writing), shared assistants and picture editing.

Offline: MongoDB is mongomock and the model is a fake, so no keys or network are needed.
"""
import io
import os
import sys
import time
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PROMPTS = []


async def _fake_complete(model, system, user):
    PROMPTS.append(user)
    if "Write this document" in user:
        return "```markdown\n# Leave letter\n\nDear Sir, I need leave.\n```"
    if "Change only this part" in user:
        return "I kindly request leave"
    if "make a video" in user:
        return "MAKE: I'll turn your script into a short video."
    if "Who is this for" in user:
        return "**ANSWER:** It's written for your manager."
    return "# Leave letter\n\nShort version."


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    import writer
    writer._complete = _fake_complete
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        def login(email):
            return c.post("/api/auth/register", json={"name": email[:4], "email": email, "password": "secret1"}).json()["token"]
        c.tokens = {"a": login("asha@test.com"), "b": login("bala@test.com")}
        c.headers["Authorization"] = f"Bearer {c.tokens['a']}"
        yield c


def test_doc_draft_edit_selection_undo_and_export(client):
    doc = client.post("/api/docs", json={"prompt": "a leave letter"}).json()
    assert doc["title"] == "Leave letter" and doc["content"].startswith("# Leave letter")
    edited = client.post(f"/api/docs/{doc['id']}/ai", json={"action": "formal", "selection": "I need leave"}).json()
    assert "I kindly request leave" in edited["content"] and "Dear Sir" in edited["content"] and edited["canUndo"]
    assert "professional tone" in PROMPTS[-1]
    whole = client.post(f"/api/docs/{doc['id']}/ai", json={"instruction": "shorten"}).json()
    assert whole["content"] == "# Leave letter\n\nShort version."
    back = client.post(f"/api/docs/{doc['id']}/undo").json()
    assert "I kindly request leave" in back["content"]
    stale = client.post(f"/api/docs/{doc['id']}/ai", json={"action": "shorter", "selection": "not in the doc"})
    assert stale.status_code == 409
    word = client.get(f"/api/docs/{doc['id']}/export", params={"format": "docx"})
    assert word.status_code == 200 and word.content[:2] == b"PK"
    pdf = client.get(f"/api/docs/{doc['id']}/export", params={"format": "pdf"})
    assert pdf.content[:4] == b"%PDF"
    client.patch(f"/api/docs/{doc['id']}", json={"title": "Mine"})
    assert [d["title"] for d in client.get("/api/docs").json()] == ["Mine"]


def test_ask_krish_answers_and_hands_off_without_changing_the_doc(client):
    doc = client.post("/api/docs", json={"content": "# Script\n\nHost: Hello kids!"}).json()
    answer = client.post(f"/api/docs/{doc['id']}/ai", json={"instruction": "Who is this for?"}).json()
    assert answer["kind"] == "reply" and answer["reply"] == "It's written for your manager."
    assert answer["content"] == doc["content"] and not answer["canUndo"]
    video = client.post(f"/api/docs/{doc['id']}/ai", json={"instruction": "make a video of this script"}).json()
    assert video["kind"] == "handoff" and "short video" in video["reply"]
    assert video["handoff"].startswith("make a video of this script") and "Host: Hello kids!" in video["handoff"]
    assert video["content"] == doc["content"] and not video["canUndo"]
    long = client.post("/api/docs", json={"content": "word " * 3000}).json()
    big = client.post(f"/api/docs/{long['id']}/ai", json={"instruction": "Who is this for?"}).json()
    assert big["kind"] == "handoff" and len(big["handoff"]) < 6200
    assert client.post(f"/api/docs/{long['id']}/ai", json={"action": "shorter"}).status_code == 413


def test_docs_are_private(client):
    doc = client.post("/api/docs", json={"content": "secret"}).json()
    other = client.get(f"/api/docs/{doc['id']}", headers={"Authorization": f"Bearer {client.tokens['b']}"})
    assert other.status_code == 404


def test_shared_assistant_copies_instructions_only(client):
    proj = client.post("/api/projects", json={"name": "Exam Tutor", "description": "Helps", "instructions": "Teach slowly"}).json()
    client.post(f"/api/projects/{proj['id']}/files", files={"file": ("notes.txt", b"private notes " * 20, "text/plain")})
    code = client.post(f"/api/projects/{proj['id']}/assistant-link").json()["code"]
    assert client.post(f"/api/projects/{proj['id']}/assistant-link").json()["code"] == code  # same link again
    bala = {"Authorization": f"Bearer {client.tokens['b']}"}
    info = client.get(f"/api/assistants/{code}", headers=bala).json()
    assert info["name"] == "Exam Tutor" and info["instructions"] == "Teach slowly" and not info["mine"]
    copy = client.post(f"/api/assistants/{code}/copy", headers=bala).json()
    mine = client.get(f"/api/projects/{copy['id']}", headers=bala).json()
    assert mine["project"]["instructions"] == "Teach slowly" and mine["files"] == []
    client.delete(f"/api/projects/{proj['id']}/assistant-link")
    assert client.get(f"/api/assistants/{code}", headers=bala).status_code == 404


def _png(color="red", size=(300, 200)):
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def test_edit_image_quick_edits_the_latest_picture(client):
    import asyncio
    import server
    from agent import ToolContext
    from PIL import Image

    cid = client.post("/api/conversations", json={}).json()["id"]
    client.post("/api/media", files={"file": ("cat.png", _png(), "image/png")}, data={"conversationId": cid})
    user_id = client.get("/api/auth/me").json()["id"]
    ctx = ToolContext(db=server.db, user_id=user_id, conversation_id=cid)
    tool = next(t for t in server.tool_registry.active() if t.name == "edit_image")
    out = asyncio.run(tool.handler(ctx, {"quick_edits": ["rotate_left", "black_and_white"]}))
    edited = out.media[0]
    assert edited["name"] == "cat-edited.jpg"
    doc = asyncio.run(server.db.media.find_one({"id": edited["id"]}))
    img = Image.open(io.BytesIO(bytes(doc["data"])))
    assert img.size == (200, 300)
    with pytest.raises(ValueError):
        asyncio.run(tool.handler(ctx, {"quick_edits": ["melt"]}))


def test_ai_image_edit_needs_a_key(monkeypatch):
    import asyncio
    import image_edit
    import media
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("POLLINATIONS_API_KEY", raising=False)
    with pytest.raises(media.MediaUnavailable):
        asyncio.run(image_edit.ai_edit(_png(), "make it blue"))
