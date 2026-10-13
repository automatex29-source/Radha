"""Web search runs only when the user turns it on or asks for it; otherwise Krish suggests it when it would help."""
import asyncio

import live_search
from agent.tools import ToolContext, default_registry
from tests.test_builder_models import _server


def test_asks_for_search_in_words():
    assert live_search.asks_for_search("search the web for cheap flights to Goa")
    assert live_search.asks_for_search("google it")
    assert live_search.asks_for_search("internet pe dekh ke batao")
    assert not live_search.asks_for_search("write a poem about rain")


def test_suggests_web_only_for_fresh_facts():
    assert live_search.suggests_web("latest news on the election")
    assert live_search.suggests_web("WHAT IS DOLLAR RATE TODA")
    assert live_search.suggests_web("best phones under 20000")
    assert not live_search.suggests_web("explain photosynthesis")
    assert not live_search.suggests_web("best way to learn python")
    assert not live_search.suggests_web("hi")
    assert not live_search.suggests_web("who made Krish AI")


def test_web_tools_hidden_when_web_is_off():
    names = lambda web: {t["function"]["name"] for t in default_registry().schemas(ToolContext(db=None, user_id="u", web=web))}
    assert "web_search" in names(True) and "deep_research" in names(True)
    assert "web_search" not in names(False) and "deep_research" not in names(False)
    assert "fetch_url" in names(False)  # a link the user pasted can still be read


def turn(monkeypatch, question, **kw):
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)
    calls = []

    async def fake_gather(*a, **k):
        calls.append(k)
        return {"context": None, "sources": [], "queries": []}

    async def fake_stream(req):
        yield "An answer."
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        await db.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                      "content": question, "createdAt": "1"})
        chunks = [c async for c in server.run_turn("c1", "openai/gpt-oss-120b", **kw)]
        saved = await db.messages.find_one({"role": "assistant"})
        return calls[0], any(c.startswith("event: web_hint") for c in chunks), saved.get("webHint")
    return asyncio.run(go())


def test_no_search_by_default_but_a_hint_for_fresh_questions(monkeypatch):
    call, hinted, saved = turn(monkeypatch, "latest news on electric cars")
    assert call["search"] is False and hinted and saved


def test_no_hint_for_timeless_questions(monkeypatch):
    call, hinted, saved = turn(monkeypatch, "explain how a rainbow forms")
    assert call["search"] is False and not hinted and not saved


def test_web_button_searches(monkeypatch):
    call, hinted, _ = turn(monkeypatch, "latest news on electric cars", web=True)
    assert call["search"] is True and call["force"] is True and not hinted


def test_asking_in_words_searches(monkeypatch):
    call, hinted, _ = turn(monkeypatch, "search the web for electric car news")
    assert call["search"] is True and not hinted
