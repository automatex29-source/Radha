"""Hard questions get more reasoning from the free models; the chat prompt asks for careful, specific answers."""
import asyncio

from tests.test_builder_models import _server


def test_hard_questions_are_spotted():
    server = _server()
    for text in ["what is 18% GST on 2499", "solve x^2 - 5x + 6 = 0", "why is the sky blue",
                 "compare iPhone 16 vs Pixel 9", "my python code throws KeyError, debug it",
                 "EMI for a 10 lakh loan at 9% for 5 years",
                 "a train leaves at 9:40 and takes 3h 35m, when does it arrive",
                 "how many days until Diwali", "aasman neela kyu hota hai",
                 "should i buy or rent a flat in Pune", "a" * 300]:
        assert server._hard_ask(text), text
    for text in ["hi", "thanks!", "tell me a joke", "write a poem about rain", "who made Krish AI", ""]:
        assert not server._hard_ask(text), text


def test_prompts_ask_for_careful_answers():
    server = _server()
    assert "Get it right before you write it" in server.SYSTEM_PROMPT
    assert "Answer first" in server.SYSTEM_PROMPT  # the answer style users liked stays
    assert "a second way" in server.THINK_PROMPT


def test_prompts_ask_for_spaced_highlighted_answers():
    server = _server()
    import counsellor
    assert "Never send one long block of text" in server.SYSTEM_PROMPT
    assert "meaningful or personal questions" in server.SYSTEM_PROMPT
    for text in (counsellor.PROMPT, counsellor.BRIEF):
        assert "never one dense paragraph" in text and "**bold**" in text
    assert "Deep questions" in counsellor.PROMPT


def reasoning_for(monkeypatch, question, **kw):
    """The `think` level a plain chat turn asks the model for."""
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)
    seen = []

    async def fake_gather(*a, **k):
        return {"context": None, "sources": [], "queries": []}

    async def fake_stream(req):
        seen.append(req.think)
        yield "An answer."
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        await db.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                      "content": question, "createdAt": "1"})
        [c async for c in server.run_turn("c1", "openai/gpt-oss-120b", **kw)]
        return seen[0]
    return asyncio.run(go())


def test_hard_questions_reason_more(monkeypatch):
    from agent import llm
    assert reasoning_for(monkeypatch, "why do onions make you cry") == llm.DEEPER
    assert reasoning_for(monkeypatch, "hi there") is False
    assert reasoning_for(monkeypatch, "why do onions make you cry", think=True) is True
    assert reasoning_for(monkeypatch, "why do onions make you cry", voice=True) is False  # voice stays quick
