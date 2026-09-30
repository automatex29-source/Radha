"""Reading attached files and photos, memory that learns, and public share links.

Offline: MongoDB is mongomock and the model is a fake, so no keys or network are needed.
"""
import io
import json
import os
import shutil
import sys
import time
import types
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

needs_ocr = pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract OCR not installed")
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


def _reply(text):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))])


async def _fake_completion(**kw):
    CALLS.append(kw)
    if kw.get("stream"):
        return _Stream("ok")
    content = kw["messages"][0]["content"]
    if isinstance(content, list):
        raise RuntimeError("no vision model in tests")  # forces the OCR fallback
    message = content.split("User's new message")[-1].lower()
    if "forget" in message:
        return _reply(json.dumps({"add": [], "remove": ["Name is Raj."]}))
    return _reply(json.dumps({"add": ["Name is Raj.", "Runs a bakery in Pune."], "remove": []}))


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
    import motor.motor_asyncio
    import litellm
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    litellm.acompletion = _fake_completion
    import embeddings
    embeddings._failed_at = time.monotonic()  # no model download in tests: keyword search
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        token = c.post("/api/auth/register", json={"name": "Raj", "email": "raj@test.com", "password": "secret1"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def _conv(client):
    return client.post("/api/conversations", json={}).json()["id"]


def _send(client, cid, text, **extra):
    CALLS.clear()
    client.post(f"/api/conversations/{cid}/stream", json={"content": text, "agent": True, **extra})
    return next(k for k in CALLS if k.get("stream"))


def _text_image(text, fmt="PNG"):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (900, 200), "white")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 40)
    except OSError:
        font = ImageFont.load_default(40)
    ImageDraw.Draw(img).text((20, 70), text, fill="black", font=font)
    out = io.BytesIO()
    img.save(out, fmt)
    return out.getvalue()


def test_small_file_goes_in_whole(client):
    cid = _conv(client)
    doc = ("Invoice 42 for Asha Traders. Total due 18450 rupees by 5 October. " * 5).encode()
    f = client.post(f"/api/conversations/{cid}/files", files={"file": ("invoice.txt", doc, "text/plain")}).json()
    assert f["status"] == "ready" and f["chunkCount"] == 1
    call = _send(client, cid, "summarise this")
    system = call["messages"][0]["content"]
    assert "Asha Traders" in system and "- invoice.txt: read" in system
    assert not call.get("tools")  # Groq free tier: the document wins over the tool list


def test_big_file_is_searched(client):
    cid = _conv(client)
    filler = " ".join(f"word{i}" for i in range(4000))
    doc = f"{filler} The warranty lasts seven years. {filler}".encode()
    client.post(f"/api/conversations/{cid}/files", files={"file": ("manual.txt", doc, "text/plain")})
    system = _send(client, cid, "how long is the warranty?")["messages"][0]["content"]
    assert "seven years" in system


@needs_ocr
def test_scanned_pdf_and_photo_are_read(client):
    cid = _conv(client)
    f = client.post(f"/api/conversations/{cid}/files",
                    files={"file": ("scan.pdf", _text_image("RENT AGREEMENT", "PDF"), "application/pdf")}).json()
    assert f["status"] == "ready" and f["chunkCount"] == 1
    m = client.post("/api/media", files={"file": ("bill.png", _text_image("TOTAL 999"), "image/png")},
                    data={"conversationId": cid}).json()
    last = _send(client, cid, "what is the total?", images=[m["id"]])["messages"][-1]["content"]
    assert isinstance(last, str) and "999" in last  # gpt-oss can't see: the photo arrives as text


def test_memory_learns_forgets_and_can_be_turned_off(client):
    client.delete("/api/memory")
    client.put("/api/memory/settings", json={"auto": True})
    cid = _conv(client)
    _send(client, cid, "My name is Raj and I run a bakery in Pune")
    time.sleep(0.5)
    facts = {m["content"]: m["source"] for m in client.get("/api/memory").json()}
    assert facts == {"Name is Raj.": "auto", "Runs a bakery in Pune.": "auto"}
    assert "Runs a bakery in Pune." in _send(client, cid, "what should I post today?")["messages"][0]["content"]

    _send(client, cid, "please forget my name")
    time.sleep(0.5)
    assert [m["content"] for m in client.get("/api/memory").json()] == ["Runs a bakery in Pune."]

    client.put("/api/memory/settings", json={"auto": False})
    _send(client, cid, "I live in Mumbai now")
    time.sleep(0.5)
    assert not any(not k.get("stream") for k in CALLS)  # no learning call
    assert client.delete("/api/memory").json()["deleted"] == 1


def test_share_link(client):
    cid = _conv(client)
    m = client.post("/api/media", files={"file": ("pic.png", _text_image("HELLO"), "image/png")},
                    data={"conversationId": cid}).json()
    _send(client, cid, "look at this", images=[m["id"]])
    private = client.post("/api/media", files={"file": ("p.png", _text_image("SECRET"), "image/png")}).json()

    share = client.post(f"/api/conversations/{cid}/share").json()
    assert client.post(f"/api/conversations/{cid}/share").json()["shareId"] == share["shareId"]
    auth = client.headers.pop("Authorization")
    try:
        page = client.get(f"/api/share/{share['shareId']}")
        assert page.status_code == 200 and "raj@test.com" not in page.text and "userId" not in page.text
        image = page.json()["messages"][0]["images"][0]
        assert client.get(image).status_code == 200
        assert client.get(f"/api/share/{share['shareId']}/media/{private['id']}").status_code == 404
    finally:
        client.headers["Authorization"] = auth
    client.delete(f"/api/conversations/{cid}/share")
    assert client.get(f"/api/share/{share['shareId']}").status_code == 404
