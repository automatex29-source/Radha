"""👎 asks what went wrong and "Try again" fixes it; long chats keep a recap of what was dropped; pictures
show when Krish searches on its own about something visual."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import live_search  # noqa: E402
import search_modes  # noqa: E402
from agent import llm  # noqa: E402
from tests.test_builder_models import _server  # noqa: E402


def test_long_chat_keeps_a_recap_of_dropped_turns():
    msgs = [{"role": "system", "content": "rules"}]
    msgs += [{"role": "user", "content": "My dog is called Bruno and he is a beagle."},
             {"role": "assistant", "content": "Bruno sounds lovely! Beagles are very curious."}]
    for i in range(8):
        msgs += [{"role": "user", "content": f"question {i} " + "y" * 1500},
                 {"role": "assistant", "content": f"answer {i} " + "z" * 1500}]
    msgs.append({"role": "user", "content": "what breed is my dog again?"})
    fitted = llm.fit_messages(msgs, [], 6000)
    assert fitted[-1]["content"] == "what breed is my dog again?"
    assert not any("Bruno" in (m["content"] or "") for m in fitted[1:])  # the old turn itself was dropped
    assert "Earlier in this chat" in fitted[0]["content"] and "Bruno" in fitted[0]["content"]
    assert llm.estimate_tokens(fitted) <= 6000 - llm._MIN_OUTPUT


def test_no_recap_when_nothing_is_dropped():
    msgs = [{"role": "system", "content": "rules"}, {"role": "user", "content": "hi"}]
    assert llm.fit_messages(msgs, [], 6000) == msgs


def test_retry_note_carries_what_was_wrong():
    server = _server()
    note = server.retry_note("Off topic:  I asked about the   second phone")
    assert "Off topic: I asked about the second phone" in note and "Try again" in note


def _client(monkeypatch):
    server = _server()
    from fastapi.testclient import TestClient
    return server, TestClient(server.app)


def test_dislike_keeps_the_reason(monkeypatch):
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        await db.messages.insert_many([
            {"id": "m1", "conversationId": "c1", "role": "user", "content": "price of pixel 8a?", "createdAt": "1"},
            {"id": "m2", "conversationId": "c1", "role": "assistant", "content": "The iPhone costs...", "createdAt": "2"}])
        body = server.FeedbackIn(rating="down", reason="Off topic", note="I asked about the Pixel")
        await server.rate_message("c1", "m2", body, user_id="u1")
        return await db.message_feedback.find_one({"messageId": "m2"})
    saved = asyncio.run(go())
    assert saved["reason"] == "Off topic" and saved["note"] == "I asked about the Pixel"
    assert saved["question"] == "price of pixel 8a?"


def test_try_again_puts_the_fix_in_the_prompt(monkeypatch):
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)
    seen = []

    async def fake_gather(*a, **k):
        return {"context": None, "sources": [], "queries": []}

    async def fake_stream(req):
        seen.append(req.system)
        yield "A better answer."
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        await db.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                      "content": "explain rainbows", "createdAt": "1"})
        [c async for c in server.run_turn("c1", "openai/gpt-oss-120b", fix="Too long")]
    asyncio.run(go())
    assert "\"Too long\"" in seen[0]


def test_pictures_come_with_krish_s_own_searches(monkeypatch):
    asked = []

    async def fake_search(text, limit=5, focus="web", model=""):
        return None

    async def fake_images(query, limit=6):
        asked.append(limit)
        return [{"type": "image", "url": "https://example.com/a", "thumbnail": "https://example.com/a.jpg"}]

    monkeypatch.setattr(live_search, "_search", fake_search)
    monkeypatch.setattr(search_modes, "images", fake_images)
    found = asyncio.run(live_search.gather(["show me the Taj Mahal at night"], search=True))
    assert asked == [4] and any(s["type"] == "image" for s in found["sources"])
    asked.clear()
    asyncio.run(live_search.gather(["write a poem about a beach"], search=True))  # a writing task
    asyncio.run(live_search.gather(["gold price today"], search=True))
    assert asked == []
