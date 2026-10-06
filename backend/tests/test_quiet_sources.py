"""The automatic search on every answer only shows its source cards when the answer cites them."""
import asyncio
import json

from tests.test_builder_models import _server

CARD = {"type": "web", "title": "Tata", "url": "https://tata.test", "domain": "tata.test", "snippet": "x"}


def turn(monkeypatch, reply, **kw):
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)

    async def fake_gather(*a, **k):
        return {"context": "[1] Tata (https://tata.test)", "sources": [CARD], "queries": ["q"]}

    async def fake_stream(req):
        yield reply
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        await db.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                      "content": "tell me about tata", "createdAt": "1"})
        chunks = [c async for c in server.run_turn("c1", "openai/gpt-oss-120b", **kw)]
        saved = await db.messages.find_one({"role": "assistant"})
        shown = [json.loads(c.split("data: ", 1)[1]) for c in chunks if c.startswith("event: sources")]
        return shown, saved["sources"]
    return asyncio.run(go())


def test_uncited_search_stays_hidden(monkeypatch):
    shown, saved = turn(monkeypatch, "Tata is a big company.")
    assert shown == [] and saved is None


def test_cited_search_shows_its_sources(monkeypatch):
    shown, saved = turn(monkeypatch, "Tata is a big company [1].")
    assert shown == [[CARD]] and saved == [CARD]


def test_search_button_always_shows_sources(monkeypatch):
    shown, saved = turn(monkeypatch, "Tata is a big company.", web=True)
    assert shown == [[CARD]] and saved == [CARD]
