"""Perplexity-style answers end to end: web sources, Related questions, Pages and Discover.

Offline: MongoDB is mongomock, the model and the web search are fakes.
"""
import os
import sys
import time
import types
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPLY = "Natarajan Chandrasekaran chairs Tata Sons [1].\n\nRelated: Who founded Tata? | What does Tata Sons own? | Tata Sons revenue"


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
    if kw.get("stream"):
        return _Stream(REPLY)
    msg = types.SimpleNamespace(content='{"add": [], "remove": []}')
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


async def _fake_search(query, limit=6):
    return [{"title": "Tata Sons leadership", "url": "https://www.tata.com/leadership", "snippet": "Chairman"}]


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
    from agent import web
    web.search = _fake_search
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        token = c.post("/api/auth/register", json={"name": "Asha", "email": "asha@test.com", "password": "secret1"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def _answer(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    stream = client.post(f"/api/conversations/{cid}/stream", json={"content": "Who runs Tata Sons?", "web": True}).text
    msgs = client.get(f"/api/conversations/{cid}").json()["messages"]
    return stream, msgs[-1]


def test_answer_has_sources_and_related(client):
    stream, msg = _answer(client)
    assert "event: related" in stream and "tata.com/leadership" in stream
    assert msg["content"] == "Natarajan Chandrasekaran chairs Tata Sons [1]."
    assert msg["related"] == ["Who founded Tata?", "What does Tata Sons own?", "Tata Sons revenue"]
    assert msg["sources"][0]["type"] == "web" and msg["sources"][0]["domain"] == "tata.com"


def test_page_is_public_and_private_bits_stay_out(client):
    _, msg = _answer(client)
    page = client.post("/api/pages", json={"messageId": msg["id"]}).json()
    assert page["title"] == "Who runs Tata Sons" and page["path"] == f"/page/{page['id']}"
    assert client.post("/api/pages", json={"messageId": msg["id"]}).json()["id"] == page["id"]
    auth = client.headers.pop("Authorization")
    try:
        public = client.get(f"/api/pages/{page['id']}")
        assert public.status_code == 200 and "asha@test.com" not in public.text and "userId" not in public.text
        assert public.json()["sources"][0]["url"] == "https://www.tata.com/leadership"
        assert client.post("/api/pages", json={"messageId": msg["id"]}).status_code == 401
    finally:
        client.headers["Authorization"] = auth
    assert client.delete(f"/api/pages/{page['id']}").json() == {"ok": True}
    assert client.get(f"/api/pages/{page['id']}").status_code == 404


def test_cannot_publish_someone_elses_answer(client):
    _, msg = _answer(client)
    auth = client.headers.pop("Authorization")
    try:
        token = client.post("/api/auth/register", json={"name": "Ravi", "email": "ravi@test.com", "password": "secret1"}).json()["token"]
        resp = client.post("/api/pages", json={"messageId": msg["id"]}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404
    finally:
        client.headers["Authorization"] = auth


def test_discover_endpoint(client, monkeypatch):
    import discover

    async def fake_stories(topic, lang, limit):
        assert topic == "tech" and lang == "en"
        return [{"title": "ISRO launch", "url": "https://news.test/a", "source": "The Hindu", "domain": "thehindu.com", "published": ""}]
    monkeypatch.setattr(discover, "stories", fake_stories)
    data = client.get("/api/discover", params={"topic": "tech"}).json()
    assert data["topic"] == "tech" and data["stories"][0]["source"] == "The Hindu" and "sports" in data["topics"]


def test_parse_google_news_feed():
    import discover
    xml = b"""<?xml version="1.0"?><rss><channel>
      <item><title>Rain lashes Mumbai - The Hindu</title><link>https://news.google.com/a</link>
        <pubDate>Sun, 05 Oct 2026 08:00:00 GMT</pubDate><source url="https://www.thehindu.com">The Hindu</source></item>
      <item><title>Rain lashes Mumbai - NDTV</title><link>https://news.google.com/b</link>
        <source url="https://www.ndtv.com">NDTV</source></item>
    </channel></rss>"""
    items = discover.parse_feed(xml, 10)
    assert items == [{"title": "Rain lashes Mumbai", "url": "https://news.google.com/a", "source": "The Hindu",
                      "domain": "thehindu.com", "published": "2026-10-05T08:00:00+00:00"}]
    assert "hl=hi-IN" in discover.feed_url("top", "hi") and "TECHNOLOGY" in discover.feed_url("tech", "en")


def test_empty_search_tells_the_model_to_search(client, monkeypatch):
    import litellm
    import server
    from agent import web
    prompts = []

    async def nothing(query, limit=6):
        return []

    async def recording(**kw):
        if kw.get("stream"):
            prompts.append(kw["messages"][0]["content"])
        return await _fake_completion(**kw)
    monkeypatch.setattr(web, "search", nothing)
    monkeypatch.setattr(litellm, "acompletion", recording)
    cid = client.post("/api/conversations", json={}).json()["id"]
    client.post(f"/api/conversations/{cid}/stream", json={"content": "Who is the CEO of Airtel?", "web": True})
    assert prompts and (server.NO_RESULTS_NOTE in prompts[0] or server.NO_RESULTS_NOTE_PLAIN in prompts[0])
