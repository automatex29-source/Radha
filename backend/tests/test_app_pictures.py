"""Apps that see pictures (RADHA.ai with images, RADHA.see) and make their own (RADHA.image)."""
import base64
import io
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")
mongomock_motor = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import appcloud  # noqa: E402
import appdata  # noqa: E402
import site_images  # noqa: E402


def png() -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 60, 60)).save(out, "PNG")
    return out.getvalue()


DATA_URL = "data:image/png;base64," + base64.b64encode(png()).decode()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret-that-is-long-enough-for-hs256")
    appcloud._hits.clear()
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    appdata.init(database)
    appcloud.init(database)
    site_images.init(database)
    app = FastAPI()
    app.include_router(appdata.router)
    app.include_router(appcloud.router)
    app.include_router(site_images.router)
    with TestClient(app) as c:
        c.portal.call(database.apps.insert_one, {"id": "app1", "userId": "u1", "name": "Plant doctor"})
        yield c


def test_ai_sees_a_picture_and_can_answer_in_json(client, monkeypatch):
    seen = {}

    async def fake_ask(images, question, system="", json_mode=False):
        seen.update(n=len(images), question=question, json=json_mode, first=images[0][:4])
        return '{"plant": "tulsi", "healthy": true}' if json_mode else "A red square."

    monkeypatch.setattr(appcloud.vision, "ask", fake_ask)
    r = client.post("/api/appdata/app1/ai", json={"prompt": "What is this?", "images": [DATA_URL]})
    assert r.status_code == 200 and r.json()["text"] == "A red square."
    assert seen["n"] == 1 and seen["first"] == b"\x89PNG"
    r = client.post("/api/appdata/app1/ai", json={"prompt": "Which plant?", "images": [DATA_URL], "json": True})
    assert r.json()["data"] == {"plant": "tulsi", "healthy": True} and seen["json"] is True


def test_pictures_can_be_the_apps_own_files_but_never_other_links(client, monkeypatch):
    async def fake_ask(images, question, system="", json_mode=False):
        return f"{len(images[0])} bytes"

    monkeypatch.setattr(appcloud.vision, "ask", fake_ask)
    up = client.post("/api/appdata/app1/files", files={"file": ("leaf.png", png(), "image/png")}).json()
    r = client.post("/api/appdata/app1/ai", json={"prompt": "Is it sick?", "images": [up["url"]]})
    assert r.status_code == 200 and r.json()["text"] == f"{len(png())} bytes"
    # the server never fetches a link a visitor names, and another app's files aren't reachable
    for bad in ("https://evil.example/x.png", "http://169.254.169.254/latest", up["url"].replace("app1", "app2"),
                "data:text/html;base64,PGgxPg=="):
        assert client.post("/api/appdata/app1/ai", json={"prompt": "x", "images": [bad]}).status_code == 400
    assert client.post("/api/appdata/app1/ai", json={"prompt": "x", "images": [DATA_URL] * 4}).status_code == 422


def test_without_a_vision_model_the_text_in_the_picture_goes_to_the_text_ai(client, monkeypatch):
    async def no_vision(*a, **k):
        return None

    asked = {}

    async def fake_stream(model, messages, tools):
        asked["prompt"] = messages[-1]["content"]
        yield {"type": "text", "text": "Total is 450"}

    monkeypatch.setattr(appcloud.vision, "ask", no_vision)
    monkeypatch.setattr(appcloud.vision, "ocr", lambda data: "TOTAL 450")
    monkeypatch.setattr(appcloud, "ai_model", lambda: "cerebras/gpt-oss-120b")
    monkeypatch.setattr(appcloud.llm, "stream_completion", fake_stream)
    r = client.post("/api/appdata/app1/ai", json={"prompt": "What's the total?", "images": [DATA_URL]})
    assert r.json()["text"] == "Total is 450" and "TOTAL 450" in asked["prompt"]


def test_app_makes_its_own_pictures(client, monkeypatch):
    made = []

    async def fake_make(prompt, w, h):
        made.append((prompt, w, h))
        from PIL import Image
        out = io.BytesIO()
        Image.new("RGB", (w, h), (len(made) * 40, 90, 200)).save(out, "WEBP")
        return out.getvalue()

    monkeypatch.setattr(site_images, "_make", fake_make)
    r = client.post("/api/appdata/app1/image", json={"prompt": "Watercolour fox reading!!", "width": 1000, "height": 700})
    assert r.status_code == 200
    url = r.json()["url"]
    assert "/api/site-image?prompt=Watercolour%20fox%20reading" in url and "w=1000&h=704" in url
    path = url.split("testserver", 1)[1]
    first = client.get(path)
    assert first.status_code == 200 and first.headers["content-type"] == "image/webp"
    assert client.get(path).content == first.content and len(made) == 1  # kept: the same words, the same picture
    other = client.post("/api/appdata/app1/image", json={"prompt": "Watercolour fox reading", "width": 1000,
                                                         "height": 700, "variant": 2}).json()["url"]
    assert "&v=2" in other
    assert client.get(other.split("testserver", 1)[1]).content != first.content and len(made) == 2
    assert client.post("/api/appdata/app1/image", json={"prompt": "!!!"}).status_code == 400
    assert client.post("/api/appdata/nope/image", json={"prompt": "fox"}).status_code == 404


def test_sdk_and_builder_know_about_pictures():
    import apps
    sdk = appdata.sdk_script("app1")
    assert "see:see" in sdk and "image:image" in sdk and "images:images" in sdk
    prompt = apps.BACKEND_GUIDE + apps.app_prompt.__doc__ if apps.app_prompt.__doc__ else apps.BACKEND_GUIDE
    assert "ctx.image" in prompt
