"""On a small server (Render's free 512MB plan) uploads must not load the embedding model, which got the
server killed mid-upload and showed a 502. Files are still read and found by keyword search. MongoDB is mongomock."""
import io
import os
import sys
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


MODEL_LOADS = []


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b", EMBEDDINGS="0")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    sys.modules.pop("embeddings", None)
    import embeddings

    def no_model():
        MODEL_LOADS.append(1)
        raise RuntimeError("the embedding model was loaded on a small server")
    embeddings._load = no_model
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        token = c.post("/api/auth/register", json={"name": "Asha", "email": "asha-small@test.com",
                                                   "password": "secret1"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    os.environ.pop("EMBEDDINGS", None)
    sys.modules.pop("embeddings", None)


def test_chat_file_upload_reads_text_without_the_model(client):
    conv = client.post("/api/conversations", json={}).json()
    text = b"The quarterly budget for Mumbai is forty lakh rupees. " * 30
    r = client.post(f"/api/conversations/{conv['id']}/files", files={"file": ("budget.txt", io.BytesIO(text), "text/plain")})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready" and r.json()["chunkCount"] > 0
    download = client.get(f"/api/files/{r.json()['id']}/download")
    assert download.status_code == 200 and download.content == text
    assert not MODEL_LOADS


def test_found_by_keyword_search(client):
    import asyncio
    import embeddings
    chunks = [{"id": "1", "text": "the budget for Mumbai"}, {"id": "2", "text": "a recipe for cake"}]
    ranked = asyncio.run(embeddings.rank("what is the Mumbai budget?", chunks, top_k=1))
    assert [c["id"] for c in ranked] == ["1"]
    assert not MODEL_LOADS


def test_setting_and_memory_limit(monkeypatch):
    import embeddings
    monkeypatch.setenv("EMBEDDINGS", "1")
    monkeypatch.setattr(embeddings, "_memory_limit_mb", lambda: 512)
    assert embeddings._enabled()
    monkeypatch.delenv("EMBEDDINGS")
    assert not embeddings._enabled()
    monkeypatch.setattr(embeddings, "_memory_limit_mb", lambda: 2048)
    assert embeddings._enabled()
    monkeypatch.setattr(embeddings, "_memory_limit_mb", lambda: None)
    assert embeddings._enabled()
