"""The Counsellor tab: its own prompt and chat list, no tools, no memory, and helplines in a crisis.

Offline: MongoDB is mongomock and the model is a fake, so no keys or network are needed.
"""
import os
import sys
import time
import types
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CALLS = []
REPLY = ["I hear you. Small steps still count, and you took one by reaching out."]


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
    CALLS.append(kw)
    if kw.get("stream"):
        return _Stream(REPLY[0])
    msg = types.SimpleNamespace(content='{"add": ["Name is Meera."], "remove": []}')
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


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
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        token = c.post("/api/auth/register", json={"name": "Meera", "email": "meera@test.com", "password": "secret1"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def _send(client, cid, text):
    CALLS.clear()
    body = client.post(f"/api/conversations/{cid}/stream", json={"content": text, "agent": True}).text
    return next(k for k in CALLS if k.get("stream")), body


def test_counsellor_chats_have_their_own_list(client):
    normal = client.post("/api/conversations", json={}).json()
    calm = client.post("/api/conversations", json={"mode": "counsellor"}).json()
    assert calm["mode"] == "counsellor" and normal["mode"] is None
    assert [c["id"] for c in client.get("/api/conversations").json()] == [normal["id"]]
    assert [c["id"] for c in client.get("/api/conversations?mode=counsellor").json()] == [calm["id"]]


def test_counsellor_is_krish_robo_without_religion_tools_or_memory(client):
    client.delete("/api/memory")
    client.put("/api/memory/settings", json={"auto": True})
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    import counsellor
    call, body = _send(client, cid, "My name is Meera and I feel lost after failing my exam")
    system = call["messages"][0]["content"]
    assert "You are Krish Robo" in system and "Tele-MANAS 14416" in system and "988" in system
    assert "Gita" not in system and "Krishna" not in system  # global and not religious
    assert system.endswith(counsellor.BRIEF)  # short replies by default
    assert counsellor.REPLIES in system and "Make them feel known" in system
    assert "Never call anyone \"bestie\"" in system
    assert not call.get("tools")
    assert "14416" not in body  # no crisis, no helpline block
    time.sleep(0.5)
    assert client.get("/api/memory").json() == []  # counselling is never saved to memory


@pytest.mark.parametrize("text", ["I want to die", "मैं आत्महत्या करना चाहता हूँ", "my husband beats me"])
def test_crisis_reply_always_has_helplines(client, text):
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    call, body = _send(client, cid, text)
    assert "may describe a crisis" in call["messages"][0]["content"]
    assert "Replies:" not in call["messages"][0]["content"]  # no tap-to-answer chips in a crisis
    assert "14416" in body and "1800-599-0019" in body and "112" in body
    saved = client.get(f"/api/conversations/{cid}").json()["messages"][-1]["content"]
    assert "Tele-MANAS: 14416" in saved


def test_crisis_words_are_not_matched_loosely():
    import counsellor
    assert not counsellor.is_crisis("I love grapes and want to end my day with a walk")
    assert counsellor.is_crisis("mujhe jeena nahi hai")


def test_counsellor_offers_tap_to_answer_replies(client):
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    REPLY[0] = "That sounds tiring 💛\n\nWhat made today heavy?\n\nReplies: Work was a lot | I just need to vent | Not sure, honestly"
    try:
        _, body = _send(client, cid, "I'm feeling tired right now 😴.")
    finally:
        REPLY[0] = "I hear you. Small steps still count, and you took one by reaching out."
    assert "event: related" in body
    saved = client.get(f"/api/conversations/{cid}").json()["messages"][-1]
    assert saved["content"].endswith("What made today heavy?")
    assert saved["related"] == ["Work was a lot", "I just need to vent", "Not sure, honestly"]


def _set_plan(client, plan):
    import server

    async def go():
        await server.db.users.update_many({}, {"$set": {"plan": plan}})
    client.portal.call(go)


def test_pro_counsellor_remembers_the_last_talk(client):
    import counsellor
    for c in client.get("/api/conversations?mode=counsellor").json():
        client.delete(f"/api/conversations/{c['id']}")
    first = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    _send(client, first, "My maths exam is on Friday and I am scared")
    second = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    call, _ = _send(client, second, "Hi again")
    assert "Your last talk with them" not in call["messages"][0]["content"]  # Basic starts fresh
    _set_plan(client, "pro")
    try:
        third = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
        call, _ = _send(client, third, "Hey")
    finally:
        _set_plan(client, "basic")
    system = call["messages"][0]["content"]
    assert "Your last talk with them" in system and "Hi again" in system  # the latest earlier talk
    assert counsellor.last_talk_note({"title": "x"}, [{"role": "assistant", "content": "hello"}]) == ""


def test_stray_script_is_cut_from_a_hinglish_reply(client):
    # A free model once wrote an Urdu word into a Hinglish answer ("bardasht ke بابر hai").
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    REPLY[0] = "Sneha, tera gussa valid hai. Ye kisi ke liye bhi bardasht ke بابر hai 💔"
    try:
        _, body = _send(client, cid, "maine sab kiya phir bhi mere sath galat hua, bht jada")
    finally:
        REPLY[0] = "I hear you. Small steps still count, and you took one by reaching out."
    assert "بابر" not in body
    saved = client.get(f"/api/conversations/{cid}").json()["messages"][-1]["content"]
    assert saved == "Sneha, tera gussa valid hai. Ye kisi ke liye bhi bardasht ke hai 💔"


def test_script_guard_keeps_the_persons_own_script():
    import counsellor
    hindi = counsellor.allowed_scripts(["मैं बहुत थक गया हूँ"])
    assert counsellor.keep_scripts("तुम अकेले नहीं हो 💛", hindi) == "तुम अकेले नहीं हो 💛"
    assert counsellor.keep_scripts("तुम ठीक হবে हो", hindi) == "तुम ठीक  हो"  # a stray Bengali word goes
    roman = counsellor.allowed_scripts(["yaar bahut tension hai"])
    assert roman == frozenset()
    assert counsellor.keep_scripts("Café, naïve — 2.47 ✨", roman) == "Café, naïve — 2.47 ✨"
    assert counsellor.keep_scripts("dil se 心 kar", roman) == "dil se  kar"
    # The Settings language, the language spoken and a language asked for by name are allowed too.
    assert counsellor.allowed_scripts(["hi"], "ur") == {"arabic"}
    assert counsellor.allowed_scripts(["hi"], None, "ta") == {"tamil"}
    assert counsellor.allowed_scripts(["say it in Tamil please"]) == {"tamil"}
    assert counsellor.tidy("ke  hai , yaar") == "ke hai, yaar"


def test_counsellor_rules_stay_in_the_prompt():
    import counsellor
    for rule in ("same script", "no religious teachings", "respect every faith", "no slang and no jokes",
                 "Give real answers, not just chat", "answer out loud in the language they speak"):
        assert rule in counsellor.PROMPT
    assert "No religious quotes" in counsellor.BRIEF and "script" in counsellor.BRIEF
    assert "answer it directly" in counsellor.BRIEF
    assert "findahelpline.com" in counsellor.HELPLINES


def test_counsellor_talks_are_with_krish_robo_on_every_plan(client):
    import counsellor
    assert set(counsellor.AGENTS) == {"krish_robo"}
    conv = client.post("/api/conversations", json={"mode": "counsellor", "agent": "krish_robo"}).json()
    assert conv["agent"] == "krish_robo"  # Basic too
    assert client.post("/api/conversations", json={"agent": "krish_robo"}).status_code == 400
    for gone in ("krishna", "radha", "nobody"):
        assert client.post("/api/conversations", json={"mode": "counsellor", "agent": gone}).status_code == 400
    call, _ = _send(client, conv["id"], "aaj mood off hai")
    system = call["messages"][0]["content"]
    assert "You are Krish Robo" in system and system.endswith(counsellor.BRIEF)


def test_app_shows_the_same_agents():
    import re
    import counsellor
    js = (Path(__file__).resolve().parents[2] / "frontend/src/lib/counselAgents.js").read_text()
    assert re.findall(r'\{ id: "(\w+)"', js) == list(counsellor.AGENTS)


def test_welcome_questions_reach_the_prompt(client):
    import counsellor
    me = client.get("/api/auth/me").json()
    assert me["needsWelcome"] is True and "suggestedAgents" not in me
    assert client.put("/api/auth/about", json={"does": "astronaut"}).status_code == 422
    assert client.put("/api/auth/about", json={"uses": ["study", "coding", "talk", "work"]}).status_code == 422
    me = client.put("/api/auth/about", json={"callMe": " Meeru ", "does": "student", "uses": ["study", "talk"],
                                             "country": "India"}).json()
    assert me["needsWelcome"] is False and me["about"]["callMe"] == "Meeru"
    cid = client.post("/api/conversations", json={"mode": "counsellor"}).json()["id"]
    call, _ = _send(client, cid, "exams are close and I panic")
    system = call["messages"][0]["content"]
    assert 'call them "Meeru"' in system and "they are a student" in system and "they live in India" in system
    assert "they mostly use Krish AI for studying and homework, life advice" in system
    # Skipping saves nothing but stops the questions.
    me = client.put("/api/auth/about", json={"skipped": True}).json()
    assert me["needsWelcome"] is False and me["about"] is None
