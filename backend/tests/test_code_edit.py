"""Code the user gives Krish is changed in place, never swapped for a new page (code_edit.py). Offline."""
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import code_edit  # noqa: E402

BIG = (Path(__file__).parent / "fixtures" / "dark-audit-tool.html").read_text()
NAME = "Site-Acceptance-Audit-Tool-VI.html"
LIGHT = {"#0b1020": "#f7f8fc", "#121a33": "#ffffff", "#e6e9f5": "#1f2937", "#8a93b2": "#6b7280",
         "#26304f": "#e5e7eb", "#0f1730": "#eef2ff", "#ffffff": "#111827", "#1a2342": "#f1f5f9"}


def attached(text):
    """A message as the chat sends it with a code file attached."""
    return f"{text}\n\n```html {NAME}\n{BIG.rstrip()}\n```"


def test_finds_attached_file_under_its_own_name():
    files = code_edit.code_files(attached("make it light theme"))
    assert list(files) == [NAME] and files[NAME] == BIG.rstrip()
    assert code_edit.without_code(attached("make it light theme")) == "make it light theme"


def test_edit_asks_and_questions():
    for ask in ["make it light theme", "change the button colour to red", "isko light theme bana do", "add a footer"]:
        assert code_edit.wants_edit(ask), ask
    for ask in ["what does this code do?", "explain the script", "", "preview", "thanks"]:
        assert not code_edit.wants_edit(ask), ask


def test_follow_up_edits_the_users_earlier_file():
    history = [{"role": "user", "content": attached("render it and preview")},
               {"role": "assistant", "content": "Here is your file", "userCode": True},
               {"role": "user", "content": "make it light theme"}]
    files, ask = code_edit.should_edit(history)
    assert list(files) == [NAME] and ask == "make it light theme"


def test_small_code_krish_wrote_stays_with_the_normal_ai():
    history = [{"role": "user", "content": "make a cake shop page"},
               {"role": "assistant", "content": "```html index.html\n<html><body>Cakes</body></html>\n```"},
               {"role": "user", "content": "make it blue"}]
    assert code_edit.should_edit(history) is None


def test_parts_join_back_to_the_same_file():
    parts = code_edit.split_parts(BIG, 6000)
    assert len(parts) > 3 and "".join(parts) == BIG and all(len(p) <= 6200 for p in parts)


def test_apply_edit_tolerates_lost_indentation():
    text = "a {\n    color: #fff;\n}\n"
    assert code_edit.apply_edit(text, "color: #fff;", "color: #000;") == "a {\n    color: #000;\n}\n"
    assert code_edit.apply_edit(text, "a {\ncolor: #fff;\n}", "a {\ncolor: #000;\n}") == "a {\n    color: #000;\n}\n"
    assert code_edit.apply_edit(text, "color: red;", "x") is None


def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None),
                                                    finish_reason=None)])


class FakeModel:
    """Stands in for the model: answers each part with SEARCH/REPLACE edits that swap dark colours for light."""

    def __init__(self):
        self.requests = []

    async def __call__(self, **kw):
        self.requests.append(kw)
        prompt = kw["messages"][-1]["content"]
        part = re.search(r"````\w*\n(.*)\n````$", prompt, re.DOTALL).group(1)
        blocks = []
        wants_light = "light" in prompt.split("\n", 1)[0]
        for n, line in enumerate(part.split("\n") if wants_light else []):
            new = line
            for dark, light in LIGHT.items():
                new = re.sub(re.escape(dark) + r"\b", light, new, flags=re.IGNORECASE)
            if new != line:
                # Every other edit drops the indentation, as models often do.
                search, replace = (line, new) if n % 2 else (line.strip(), new.strip())
                blocks.append(f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE")
        text = ("\n\n".join(blocks) + "\nSUMMARY: Switched the dark colours to a light palette") if blocks else "NONE"

        async def stream():
            for i in range(0, len(text), 400):
                yield _chunk(text[i:i + 400])
        return stream()


@pytest.fixture(scope="module")
def client():
    mongomock_motor = pytest.importorskip("mongomock_motor")
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
    os.environ.pop("CEREBRAS_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)
    import motor.motor_asyncio
    import litellm
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    original = litellm.acompletion
    fake = FakeModel()
    litellm.acompletion = fake
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    try:
        with TestClient(server.app) as c:
            token = c.post("/api/auth/register", json={"name": "Sneha", "email": "sneha-edit@test.com",
                                                       "password": "secret1"}).json()["token"]
            c.headers["Authorization"] = f"Bearer {token}"
            c.fake = fake
            yield c
    finally:
        litellm.acompletion = original


def _check_light_version(reply):
    files = code_edit.code_files(reply)
    assert list(files) == [NAME], "the reply carries the user's file under its own name"
    out = files[NAME]
    want = BIG.rstrip()
    for dark, light in LIGHT.items():
        want = re.sub(re.escape(dark) + r"\b", light, want, flags=re.IGNORECASE)
    assert out == want, "every colour changed and every other byte kept"
    assert out.count("\n") == BIG.rstrip().count("\n")
    assert "Run check 120" in out and "function rule40" in out and "Vedang Cellular Services" in out


def test_attached_big_page_made_light_in_place(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    client.fake.requests.clear()
    body = client.post(f"/api/conversations/{cid}/stream",
                       json={"content": attached("make it light theme"), "model": "openai/gpt-oss-120b"}).text
    assert "event: done" in body and "event: tool" in body
    import agent.llm as agent_llm
    # Groq's free tier fits a part in each request: the code reached the model whole, never trimmed.
    assert len(client.fake.requests) > 1
    for kw in client.fake.requests:
        assert "chars omitted" not in kw["messages"][-1]["content"]
        assert agent_llm.estimate_tokens(kw["messages"]) + kw["max_tokens"] <= agent_llm.token_budget("openai/gpt-oss-120b")
    msgs = client.get(f"/api/conversations/{cid}").json()["messages"]
    reply = msgs[-1]["content"]
    assert reply.startswith("Done. I edited your " + NAME) and "light palette" in reply.lower()
    assert all(s["status"] == "done" for s in msgs[-1]["steps"])
    _check_light_version(reply)


def test_light_theme_asked_after_previewing_the_file(client):
    """The user's flow: attach the page to preview it, then ask "make it light theme" without attaching again."""
    cid = client.post("/api/conversations", json={}).json()["id"]
    first = client.post(f"/api/conversations/{cid}/stream", json={"content": attached("render it snd preview")}).text
    assert "exactly as you gave it" in first and f"html {NAME}" in first
    client.post(f"/api/conversations/{cid}/stream", json={"content": "make it light theme",
                                                          "model": "openai/gpt-oss-120b"})
    reply = client.get(f"/api/conversations/{cid}").json()["messages"][-1]["content"]
    _check_light_version(reply)
    # ...and a further change keeps building on the edited file.
    client.post(f"/api/conversations/{cid}/stream", json={"content": "change the accent colour to green"})
    last = client.get(f"/api/conversations/{cid}").json()["messages"][-1]
    assert last["role"] == "assistant" and "My Light-Theme" not in last["content"]


def test_nothing_matched_leaves_the_file_alone(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    client.post(f"/api/conversations/{cid}/stream", json={"content": attached("make the logo spin")})
    reply = client.get(f"/api/conversations/{cid}").json()["messages"][-1]["content"]
    assert reply.startswith("I couldn't make that change") and "```" not in reply
