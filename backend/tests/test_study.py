"""Study mode for students: the class/exam profile, the tutor prompt and interactive practice quizzes.

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
        token = c.post("/api/auth/register", json={"name": "Meera", "email": "study@test.com", "password": "secret1"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def _send(client, cid, text):
    CALLS.clear()
    body = client.post(f"/api/conversations/{cid}/stream", json={"content": text, "agent": True}).text
    return next(k for k in CALLS if k.get("stream")), body


def test_study_profile_is_saved_and_cleaned(client):
    assert client.get("/api/auth/me").json()["study"] is None
    assert client.put("/api/auth/study", json={"level": "class-42"}).status_code == 422
    me = client.put("/api/auth/study", json={"level": "jee", "board": "cbse", "lang": "hinglish"}).json()
    assert me["study"] == {"level": "jee", "board": None, "lang": "hinglish"}  # a board is only for school
    me = client.put("/api/auth/study", json={"level": "class-9-10", "board": "cbse", "lang": "hi"}).json()
    assert me["study"] == {"level": "class-9-10", "board": "cbse", "lang": "hi"}
    assert client.get("/api/auth/me").json()["study"]["board"] == "cbse"


def test_study_mode_uses_the_profile(client):
    import study
    client.put("/api/auth/study", json={"level": "neet", "lang": "hinglish"})
    cid = client.post("/api/conversations", json={}).json()["id"]
    CALLS.clear()
    client.post(f"/api/conversations/{cid}/stream", json={"content": "photosynthesis samjhao", "agent": True,
                                                         "study": True})
    call = next(k for k in CALLS if k.get("stream"))
    system = call["messages"][0]["content"]
    assert study.PROMPT in system and "preparing for NEET" in system and "easy Hinglish" in system
    assert "don't ask which class" in system
    assert "create_quiz" in [t["function"]["name"] for t in call.get("tools") or []]


def test_study_question_outside_study_mode_does_not_ask_the_class_again(client):
    import server
    client.put("/api/auth/study", json={"level": "class-11-12", "board": "state"})
    cid = client.post("/api/conversations", json={}).json()["id"]
    call, _ = _send(client, cid, "kal physics ka paper hai, kya padhu?")
    system = call["messages"][0]["content"]
    assert "Class 11 or 12" in system and "a state board" in system
    assert server.STUDY_CLOSE_KNOWN in system and server.STUDY_CLOSE_NOTE not in system


def test_no_profile_line_without_a_profile():
    import study
    assert study.profile_line(None) == "" and study.profile_line({"level": "nope"}) == ""
    assert study.clean({"board": "cbse"}) is None


def test_quiz_cleans_questions():
    from agent import quiz
    qs = quiz.clean_questions([
        {"question": "2+2?", "options": ["3", "4", "5", "6"], "answer": 1, "explain": "Add them."},
        {"question": "Letter answer", "options": ["a", "b"], "answer": "B"},
        {"question": "Text answer", "options": ["Mars", "Venus"], "answer": "Venus"},
        {"question": "Bad index", "options": ["a", "b"], "answer": 5},
        {"question": "Same options", "options": ["a", "a"], "answer": 0},
        {"question": "One option", "options": ["a"], "answer": 0},
        {"question": "", "options": ["a", "b"], "answer": 0},
        {"question": "Bool", "options": ["a", "b"], "answer": True},
    ])
    assert [(q["q"], q["a"]) for q in qs] == [("2+2?", 1), ("Letter answer", 1), ("Text answer", 1)]
    with pytest.raises(ValueError):
        quiz.clean_questions([{"question": "x", "options": ["a"], "answer": 0}])
    many = quiz.clean_questions([{"question": f"Q{i}", "options": ["a", "b"], "answer": 0} for i in range(99)])
    assert len(many) == quiz.MAX_QUESTIONS


def test_quiz_page_escapes_and_marks():
    from agent import quiz
    qs = quiz.clean_questions([{"question": "</script><b>x</b>", "options": ["<i>", "b"], "answer": 0}])
    page = quiz.build_page("<Physics>", qs, exam_marking=True)
    assert "&lt;Physics&gt;" in page and "</script><b>" not in page and "EXAM = true" in page
    assert "EXAM = false" in quiz.build_page("T", qs)


def test_create_quiz_tool_saves_a_page():
    import asyncio
    from agent import tools as agent_tools
    saved = {}

    async def fake_save(ctx, data, fmt, name):
        saved.update(data=data, fmt=fmt, name=name)
        return {"id": "m1", "name": name + ".html"}
    orig = agent_tools._save_file
    agent_tools._save_file = fake_save
    try:
        out = asyncio.run(agent_tools._create_quiz(None, {"title": "Light", "exam_marking": True, "questions": [
            {"question": "Unit of power of a lens?", "options": ["Dioptre", "Watt"], "answer": 0}]}))
    finally:
        agent_tools._save_file = orig
    assert saved["fmt"] == "html" and b"Dioptre" in saved["data"] and out.media[0]["id"] == "m1"
    assert "1-question quiz" in out.summary


@pytest.mark.parametrize("text,found", [
    ("main class 10 CBSE me hoon, light chapter samjhao", {"level": "class-9-10", "board": "cbse"}),
    ("I'm in 12th class preparing for JEE", {"level": "jee"}),
    ("NEET 2027 ke liye biology plan", {"level": "neet"}),
    ("कक्षा 8 हिंदी माध्यम", {"level": "class-6-8", "lang": "hi"}),
    ("UP board class 11 physics", {"level": "class-11-12", "board": "state"}),
    ("SSC CGL maths tricks", {"level": "govt"}),
    ("explain photosynthesis", {}),
    ("class 3 maths", {}),
])
def test_detect_reads_the_class_from_a_message(text, found):
    import study
    assert study.detect(text) == found


def test_learn_only_returns_new_facts():
    import study
    assert study.learn(None, "what is a cell") is None
    p = study.learn(None, "class 10 cbse")
    assert p == {"level": "class-9-10", "board": "cbse", "lang": None}
    assert study.learn(p, "class 10 ka paper") is None  # nothing new
    assert study.learn(p, "ab NEET ki tayari") == {"level": "neet", "board": None, "lang": None}


def test_krish_learns_the_class_from_chat_and_uses_study_rules_without_study_mode(client):
    import study
    client.put("/api/auth/study", json={})
    cid = client.post("/api/conversations", json={}).json()["id"]
    call, _ = _send(client, cid, "Main class 9 ICSE me hoon, quiz me on motion")
    system = call["messages"][0]["content"]
    assert study.RULES.split("\n")[0] in system and study.PROMPT not in system  # rules, not the hint-first tutor
    assert "Class 9 or 10" in system and "ICSE" in system
    assert client.get("/api/auth/me").json()["study"] == {"level": "class-9-10", "board": "icse", "lang": None}
    cid = client.post("/api/conversations", json={}).json()["id"]
    call, _ = _send(client, cid, "kal maths ka paper hai")  # a new chat still knows
    assert "Class 9 or 10" in call["messages"][0]["content"]
    call, _ = _send(client, cid, "what's a good movie tonight?")  # not a study question: no study rules
    assert study.RULES.split("\n")[0] not in call["messages"][0]["content"]
