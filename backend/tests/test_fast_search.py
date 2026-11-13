"""Web search is quick: a slow engine doesn't hold up the answer, the same search isn't repeated, and the chat
shows "Searching the web" while it runs."""
import asyncio
import json
import time

import live_search
from agent import web


def _engines(monkeypatch, ddg, bing, calls=None):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def engine(name, delay, result):
        async def run(client, query, limit):
            if calls is not None:
                calls.append(name)
            await asyncio.sleep(delay)
            return result
        run.__name__ = name
        return run
    monkeypatch.setattr(web, "_ddg", engine("ddg", *ddg))
    monkeypatch.setattr(web, "_bing", engine("bing", *bing))


A = [{"title": "A", "url": "https://a.test", "snippet": "a"}]
B = [{"title": "B", "url": "https://b.test", "snippet": "b"}]


def test_slow_engine_does_not_hold_up_the_search(monkeypatch):
    monkeypatch.setattr(web, "MERGE_GRACE", 0.2)
    _engines(monkeypatch, (0.0, A), (3.0, B))
    start = time.monotonic()
    found = asyncio.run(web.search("q"))
    assert time.monotonic() - start < 1.0
    assert [r["url"] for r in found] == ["https://a.test"]


def test_both_engines_merge_when_close(monkeypatch):
    _engines(monkeypatch, (0.0, A), (0.05, B))
    assert {r["url"] for r in asyncio.run(web.search("q"))} == {"https://a.test", "https://b.test"}


def test_an_empty_engine_waits_for_the_other(monkeypatch):
    monkeypatch.setattr(web, "MERGE_GRACE", 0.01)
    _engines(monkeypatch, (0.0, []), (0.2, B))
    assert [r["url"] for r in asyncio.run(web.search("q"))] == ["https://b.test"]


def test_same_search_is_reused_and_shared(monkeypatch):
    calls = []
    _engines(monkeypatch, (0.05, A), (0.05, B), calls)

    async def go():
        first, second = await asyncio.gather(web.search("Best phones  2026"), web.search("best phones 2026"))
        third = await web.search("best phones 2026")
        return first, second, third
    first, second, third = asyncio.run(go())
    assert calls == ["ddg", "bing"]  # asked once for all three
    assert first == second == third
    first[0]["title"] = "changed"  # callers get their own copies
    assert asyncio.run(web.search("best phones 2026"))[0]["title"] != "changed"


def test_failed_search_is_not_kept(monkeypatch):
    calls = []
    _engines(monkeypatch, (0.0, []), (0.0, []), calls)
    monkeypatch.setattr(web, "_ddg_lite", lambda *a: asyncio.sleep(0, []))
    monkeypatch.setattr(web, "_wikipedia", lambda *a: asyncio.sleep(0, []))
    asyncio.run(web.search("q"))
    asyncio.run(web.search("q"))
    assert calls == ["ddg", "bing", "ddg", "bing"]


def test_search_label():
    assert live_search.search_label(["hey krish who is the ceo of infosys?"]) == "who is the ceo of infosys"
    assert live_search.search_label(["hi"]) == ""
    assert live_search.search_label(["who is the ceo of infosys"], search=False) == ""


def test_chat_shows_searching_and_saves_queries(monkeypatch):
    from tests.test_builder_models import _server
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)
    card = {"type": "web", "title": "Infosys", "url": "https://infosys.test", "domain": "infosys.test", "snippet": "x"}

    async def fake_gather(*a, **k):
        return {"context": "[1] Infosys", "sources": [card], "queries": ["ceo of infosys"]}

    async def fake_stream(req):
        yield "Salil Parekh [1]."
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        await db.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                      "content": "who is the ceo of infosys", "createdAt": "1"})
        chunks = [c async for c in server.run_turn("c1", "openai/gpt-oss-120b", web=True)]
        return chunks, await db.messages.find_one({"role": "assistant"})
    chunks, saved = asyncio.run(go())
    names = [c.split("\n", 1)[0] for c in chunks if c.startswith("event: ")]
    assert names.index("event: searching") < names.index("event: sources")
    searching = next(c for c in chunks if c.startswith("event: searching"))
    assert json.loads(searching.split("data: ", 1)[1])["query"] == "who is the ceo of infosys"
    assert saved["searched"] == {"queries": ["ceo of infosys"]}
