"""Krish reads the latest message for what it means before answering (understand.py): typos, Hinglish,
follow-ups that lean on earlier messages, several asks in one message, and the tool that fits."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import live_search  # noqa: E402
import understand  # noqa: E402
from tests.test_builder_models import _server  # noqa: E402


def user(text, **kw):
    return {"role": "user", "content": text, **kw}


def bot(text):
    return {"role": "assistant", "content": text}


def reading(**kw):
    base = {"question": "", "parts": [], "kind": "chat", "web": False, "search": "", "tool": "", "lang": "english"}
    return {**base, **kw}


# --- the reader itself ---------------------------------------------------------------------------------------

def test_parse_cleans_the_reply():
    text = 'Sure: {"question": "What is the price of the iPhone 16 in India?", "parts": ["one"], "kind": "facts", ' \
           '"web": true, "search": "iPhone 16 price India", "tool": "magic_tool", "lang": "Hinglish"}'
    got = understand.parse(text)
    assert got["question"] == "What is the price of the iPhone 16 in India?"
    assert got["parts"] == []  # one part is no list
    assert got["web"] is True and got["search"] == "iPhone 16 price India"
    assert got["tool"] == ""  # not a real tool
    assert got["lang"] == "hinglish" and got["kind"] == "facts"


def test_parse_rejects_junk():
    assert understand.parse("") is None
    assert understand.parse("no json here") is None
    assert understand.parse('{"question": ""}') is None
    assert understand.parse("{bad json}") is None
    # no web, no search query
    assert understand.parse('{"question": "hello there", "web": false, "search": "x"}')["search"] == ""


def test_skips_what_needs_no_reading():
    assert not understand.worth_reading([])
    assert not understand.worth_reading([user("hiii")])
    assert not understand.worth_reading([user("thanks!")])
    assert not understand.worth_reading([user("x" * 2000)])
    assert not understand.worth_reading([user("fix this ```print(1```")])
    assert understand.worth_reading([user("iphne 17 lanch kab h")])
    # "ok" or "haan" after an offer means "do it", so a short reply in a chat is read
    assert understand.worth_reading([user("make a quiz"), bot("Want 5 questions?"), user("haan")])


def test_prompt_carries_the_chat():
    history = [user("best phone under 30k?"), bot("The **Pixel 8a** is the best pick. Want the price?"),
               user("haan aur iska camera kaisa h"), ]
    text = understand.prompt_for(history)
    assert "Pixel 8a" in text and "Want the price?" in text
    assert text.rstrip().endswith("haan aur iska camera kaisa h")
    long = understand.prompt_for([user("a"), bot("start " + "x" * 3000 + " offer at the end"), user("yes")])
    assert "start" in long and "offer at the end" in long and len(long) < 800


def test_read_asks_a_small_model(monkeypatch):
    monkeypatch.setenv("UNDERSTAND", "1")
    monkeypatch.setattr(understand.llm, "configured", lambda m: m == "openai/gpt-oss-20b")
    seen = {}

    async def fake_stream(model, messages, tools, **kw):
        seen["model"] = model
        seen["prompt"] = messages[-1]["content"]
        yield {"type": "text", "text": json.dumps({"question": "When does the iPhone 17 launch?", "kind": "facts",
                                                   "web": True, "search": "iPhone 17 launch date"})}

    monkeypatch.setattr(understand.llm, "stream_completion", fake_stream)
    got = asyncio.run(understand.read([user("iphne 17 lanch kab h")]))
    assert seen["model"] == "openai/gpt-oss-20b" and "iphne 17 lanch kab h" in seen["prompt"]
    assert got["question"] == "When does the iPhone 17 launch?" and got["search"] == "iPhone 17 launch date"


def test_read_never_blocks_the_answer(monkeypatch):
    monkeypatch.setenv("UNDERSTAND", "1")
    monkeypatch.setattr(understand, "TIMEOUT", 0.05)
    monkeypatch.setattr(understand.llm, "configured", lambda m: True)

    async def slow(model, messages, tools, **kw):
        await asyncio.sleep(1)
        yield {"type": "text", "text": "{}"}

    async def broken(model, messages, tools, **kw):
        raise RuntimeError("rate limited")
        yield  # pragma: no cover

    for fake in (slow, broken):
        monkeypatch.setattr(understand.llm, "stream_completion", fake)
        assert asyncio.run(understand.read([user("kya scene h")])) is None
    monkeypatch.setenv("UNDERSTAND", "0")
    assert asyncio.run(understand.read([user("kya scene h")])) is None


def test_prompt_note():
    assert understand.prompt_note(None, "hi") == ""
    # the reading says nothing new: no note
    assert understand.prompt_note(reading(question="What is GST?"), "what is gst") == ""
    note = understand.prompt_note(reading(question="What is the price of the Pixel 8a in India?",
                                          parts=["Its price in India", "Where to buy it"], tool="web_search"),
                                  "aur iska price aur kaha milega")
    assert "Pixel 8a" in note and "2 things" in note and "1. Its price in India" in note
    assert "web_search" in note and "follow the chat" in note and "own language" in note


# --- the search looks up what was meant -----------------------------------------------------------------------

def test_search_looks_up_the_reading(monkeypatch):
    asked = []

    async def fake_search(text, limit=5, focus="web", model=""):
        asked.append(text)
        return None

    monkeypatch.setattr(live_search, "_search", fake_search)
    asyncio.run(live_search.gather(["best phone under 30k", "aur iska price?"], force=True,
                                   meant="Pixel 8a price in India"))
    assert asked == ["Pixel 8a price in India"]
    assert live_search.search_label(["aur iska price?"], meant="Pixel 8a price in India") == "Pixel 8a price in India"
    # no reading: the old way
    assert live_search.search_label(["plzzz latst nws abt isro"], force=True).startswith("latest news about isro")


# --- a whole chat turn ----------------------------------------------------------------------------------------

def turn(monkeypatch, history, read_as, model="openai/gpt-oss-120b", **kw):
    server = _server()
    import mongomock_motor
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)
    got = {"gather": [], "system": []}

    async def fake_read(history_docs):
        return read_as

    async def fake_gather(*a, **k):
        got["gather"].append(k)
        return {"context": None, "sources": [], "queries": []}

    async def fake_stream(req):
        got["system"].append(req.system)
        got["model"] = req.model
        got["tools"] = False  # plain chat: no tool list
        yield "An answer."

    async def fake_agent(stream_fn, ctx, model, llm_messages, use_tools, max_steps, **k):
        got["system"].append(llm_messages[0]["content"])
        got["tools"] = use_tools
        got["model"] = model
        yield {"type": "text", "text": "An answer."}

    monkeypatch.setattr(server.understand, "read", fake_read)
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)
    monkeypatch.setattr(server, "_agent_events", fake_agent)

    async def go():
        await db.conversations.insert_one({"id": "c1", "userId": "u1"})
        for n, m in enumerate(history):
            await db.messages.insert_one({"id": f"m{n}", "conversationId": "c1", "createdAt": str(n), **m})
        [c async for c in server.run_turn("c1", model, **kw)]
    asyncio.run(go())
    return got


def test_a_follow_up_is_searched_as_meant(monkeypatch):
    got = turn(monkeypatch, [user("best phone under 30k?"), bot("The **Pixel 8a**."), user("aur iska price?")],
               reading(question="What is the price of the Pixel 8a in India?", web=True,
                       search="Pixel 8a price India", lang="hinglish"))
    call = got["gather"][0]
    assert call["search"] is True and call["meant"] == "Pixel 8a price India"
    system = got["system"][0]
    assert "What is the price of the Pixel 8a in India?" in system
    assert system.rstrip().endswith(server_hinglish_note())  # the language line stays the last one


def server_hinglish_note():
    return _server().HINGLISH_NOTE


def test_several_asks_are_all_answered(monkeypatch):
    got = turn(monkeypatch, [user("gst kya h aur kitne type ke hote h")],
               reading(question="What is GST and how many types are there?",
                       parts=["What GST is", "How many types of GST there are"], lang="hinglish"))
    assert "2 things" in got["system"][0] and "How many types of GST there are" in got["system"][0]


def test_a_misspelt_file_ask_keeps_the_tools(monkeypatch):
    # "exel shet" isn't caught by the tool words, so Groq's quick chat would drop the tool list
    history = [user("mere kharche ki exel shet bna do")]
    plain = turn(monkeypatch, history, None, agent=True)
    assert plain["tools"] is False
    read = turn(monkeypatch, history, reading(question="Make an Excel sheet of my expenses.", kind="make",
                                             tool="create_spreadsheet", lang="hinglish"), agent=True)
    assert read["tools"] is True and "create_spreadsheet" in read["system"][0]


def test_a_misspelt_hard_question_gets_the_reasoning_model(monkeypatch):
    server = _server()
    monkeypatch.setattr(server.agent_llm, "configured", lambda m: True)
    history = [user("2 trens 60 aur 40 km/h pe chal rhi milengi kab")]
    got = turn(monkeypatch, history, reading(question="Two trains at 60 and 40 km/h: when do they meet?",
                                             kind="maths"), model=server.AUTO_MODEL)
    assert "gpt-oss-120b" in got["model"]


def test_no_reading_changes_nothing(monkeypatch):
    got = turn(monkeypatch, [user("explain how a rainbow forms")], None)
    assert got["gather"][0]["meant"] == "" and got["gather"][0]["search"] is False
    assert "quick reading" not in got["system"][0]


def test_asking_for_english_wins_over_hinglish(monkeypatch):
    got = turn(monkeypatch, [user("gst kya h, answer in english")],
               reading(question="What is GST? Answer in English.", lang="hinglish"))
    assert server_hinglish_note() not in got["system"][0]
