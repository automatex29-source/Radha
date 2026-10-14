"""Coding questions get senior-engineer guidance; requests for ideas get varied, specific ideas with a top pick."""
import asyncio

from tests.test_builder_models import _server


def test_coding_questions_are_spotted():
    server = _server()
    for text in ["my python code throws KeyError, debug it", "TypeError: x is undefined",
                 "write a function to reverse a list", "how do I join two tables in SQL",
                 "react useEffect runs twice", "```\nprint(1)\n```", "NullPointerException in my app"]:
        assert server._code_ask(text), text
    for text in ["hi", "my pin code is 110001", "what is a promo code", "wedding function for my sister",
                 "terror attack news", "there was an error in my bank statement", "what class is best for jee"]:
        assert not server._code_ask(text), text


def test_idea_requests_are_spotted():
    server = _server()
    for text in ["give me business ideas for a cafe", "names for my bakery", "brainstorm youtube video topics",
                 "how can i grow my instagram", "side hustle for students"]:
        assert server._ideas_ask(text), text
    for text in ["hi", "any idea why it fails?", "suggest a good phone under 20000", "ideas for a react app"]:
        assert not server._ideas_ask(text), text  # a code idea is a coding question


def system_for(monkeypatch, question, **kw):
    """The system prompt a plain chat turn sends."""
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)
    seen = []

    async def fake_gather(*a, **k):
        return {"context": None, "sources": [], "queries": []}

    async def fake_stream(req):
        seen.append(req.system)
        yield "An answer."
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        await db.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                      "content": question, "createdAt": "1"})
        [c async for c in server.run_turn("c1", "openai/gpt-oss-120b", **kw)]
        return seen[0], server
    return asyncio.run(go())


def test_prompts_follow_the_question(monkeypatch):
    system, server = system_for(monkeypatch, "fix this python error: KeyError 'name'")
    assert server.CODE_PROMPT in system and server.IDEAS_PROMPT not in system
    system, server = system_for(monkeypatch, "give me 5 business ideas for a small town")
    assert server.IDEAS_PROMPT in system and server.CODE_PROMPT not in system
    system, server = system_for(monkeypatch, "hi there")
    assert server.CODE_PROMPT not in system and server.IDEAS_PROMPT not in system
    system, server = system_for(monkeypatch, "fix my python code", voice=True)
    assert server.CODE_PROMPT not in system  # voice stays short


def test_coding_questions_reason_more(monkeypatch):
    from agent import llm
    from tests.test_answer_quality import reasoning_for
    assert reasoning_for(monkeypatch, "react useEffect runs twice") == llm.DEEPER
