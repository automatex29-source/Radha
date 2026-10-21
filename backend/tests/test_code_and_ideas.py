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


def answering_model(monkeypatch, question, model="gemini-3.5-flash-lite", key=True, **kw):
    """The model that answers a plain chat turn, and the model the chat keeps."""
    server = _server()
    import mongomock_motor
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    if key:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    else:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)
    seen = []

    async def fake_gather(*a, **k):
        return {"context": None, "sources": [], "queries": []}

    async def fake_stream(req):
        seen.append(req.model)
        yield "An answer."
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        await db.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                      "content": question, "createdAt": "1"})
        [c async for c in server.run_turn("c1", model, **kw)]
        conv = await db.conversations.find_one({"id": "c1"})
        return seen[0], conv["model"]
    return asyncio.run(go())


def test_coding_questions_go_to_krish_coder(monkeypatch):
    server = _server()
    assert server.CODER_MODEL == "openrouter/qwen/qwen3-coder:free"
    answered, kept = answering_model(monkeypatch, "fix this python KeyError")
    assert answered == server.CODER_MODEL
    assert kept == "gemini-3.5-flash-lite"  # the chat stays on the model the user picked
    assert answering_model(monkeypatch, "hi there")[0] == "gemini-3.5-flash-lite"
    assert answering_model(monkeypatch, "fix this python KeyError", key=False)[0] == "gemini-3.5-flash-lite"
    assert answering_model(monkeypatch, "fix my python code", voice=True)[0] == "gemini-3.5-flash-lite"


def test_krish_coder_hands_over_when_its_free_allowance_runs_out(monkeypatch):
    from agent import llm
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    model = "openrouter/qwen/qwen3-coder:free"
    assert llm.provider_for(model) == "openrouter" and not llm.paid(model) and not llm.lean(model)
    assert llm.fallbacks_for(model, [])[0] == "openai/gpt-oss-120b"
    assert llm.litellm_model(model) == model
    assert llm.reasoning_effort(model, True) is None
    assert server_router_supports(model)


def server_router_supports(model):
    server = _server()
    return server.model_router.resolve(model).name == "openrouter"


def _chat(*turns):
    roles = ["user", "assistant"]
    return [{"role": roles[i % 2], "content": text} for i, text in enumerate(turns)]


def test_follow_ups_in_a_coding_chat_stay_coding_questions():
    server = _server()
    code_reply = "Here it is:\n```python\nprint('hi')\n```"
    for follow_up in ["still not working", "add a dark mode", "now in java", "make it faster",
                      "isme login bhi daal do"]:
        assert server._coding_turn(_chat("make a todo app", code_reply, follow_up)), follow_up
    assert server._coding_turn(_chat("fix my python KeyError", "Check the key exists first.", "didn't help"))
    for follow_up in ["thanks!", "ok", "give me business ideas for a cafe", "latest news on isro today"]:
        assert not server._coding_turn(_chat("make a todo app", code_reply, follow_up)), follow_up
    assert not server._coding_turn(_chat("hi", "Hello! How can I help?", "still not working"))
    assert not server._coding_turn(_chat("make a todo app", code_reply, "x" * (server.FOLLOW_UP_CHARS + 1)))
    assert not server._coding_turn([])


def test_coding_prompt_asks_for_finished_tagged_reviewed_code():
    server = _server()
    for rule in ["never a bare ```", "Never stop mid-file", "review the code once", "latest version of the code",
                 "how to run it", "non-deprecated"]:
        assert rule in server.CODE_PROMPT, rule


def test_code_answers_get_more_room(monkeypatch):
    from ai_runtime import _backend
    from agent import llm
    seen = []

    async def fake_stream(model, messages, tools, think=False, max_output=None):
        seen.append(max_output)
        yield {"type": "text", "text": "ok"}
    monkeypatch.setattr(llm, "stream_completion", fake_stream)

    async def go(**kw):
        req = server_types().AIRequest(messages=[], model="openai/gpt-oss-120b", **kw)
        return [t async for t in _backend.stream_via_litellm(req)]
    asyncio.run(go())
    asyncio.run(go(long_answer=True))
    assert seen == [llm.PLAIN_OUTPUT, llm.CODE_OUTPUT] and llm.CODE_OUTPUT > llm.PLAIN_OUTPUT


def server_types():
    from ai_runtime import types
    return types


def test_coding_turns_ask_for_long_answers(monkeypatch):
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)
    seen = []

    async def fake_gather(*a, **k):
        return {"context": None, "sources": [], "queries": []}

    async def fake_stream(req):
        seen.append((req.long_answer, server.CODE_PROMPT in req.system))
        yield "An answer."
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    async def go(conv, *turns):
        await db.conversations.insert_one({"id": conv, "userId": "u1"})
        for i, (role, text) in enumerate(zip(["user", "assistant"] * 3, turns)):
            await db.messages.insert_one({"id": f"{conv}{i}", "conversationId": conv, "role": role,
                                          "content": text, "createdAt": str(i)})
        [c async for c in server.run_turn(conv, "openai/gpt-oss-120b")]
    asyncio.run(go("c1", "make a calculator in python", "```python\nprint(1)\n```", "still not working"))
    asyncio.run(go("c2", "hi there"))
    assert seen == [(True, True), (False, False)]
