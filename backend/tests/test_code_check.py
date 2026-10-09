"""Apps and sites Krish writes in the chat are checked and fixed before the user sees them (code_check.py),
and follow-up changes edit the code in place. Offline: a stand-in model answers each kind of request."""
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import code_check  # noqa: E402
import code_edit  # noqa: E402

STYLE = "\n".join(f".item-{i} {{ padding: {i}px; color: #333; }}" for i in range(60))
TODO_PAGE = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>To-do list</title>
<style>
body {{ font-family: sans-serif; background: #ffffff; }}
header {{ background: #e11d48; color: white; padding: 16px; }}
{STYLE}
</style>
</head>
<body>
<header><h1>My tasks</h1></header>
<input id="task" placeholder="New task"><button id="add">Add</button>
<ul id="list"></ul>
<script>
const list = document.getElementById('list');
document.getElementById('add').onclick = () => {{
  const li = document.createElement('li');
  li.textContent = document.getElementById('task').value;
  list.appendChild(li);
}};
</script>
</body>
</html>"""
CUT_AT = TODO_PAGE.index("  list.appendChild(li);")


def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None),
                                                    finish_reason=None)])


class Model:
    """Answers chat turns with `self.chat` and fix requests the way a model would."""

    def __init__(self):
        self.chat = ""
        self.calls = []

    async def __call__(self, **kw):
        system = kw["messages"][0]["content"]
        prompt = kw["messages"][-1]["content"]
        if isinstance(system, list):
            system = system[0]["text"]
        if system == code_check.SYSTEM and "was cut off" in prompt:
            kind, text = "finish", "```html\n" + TODO_PAGE[CUT_AT:] + "\n```"
        elif system == code_check.SYSTEM and "was never written" in prompt:
            kind, text = "write", "```js app.js\ndocument.getElementById('go').onclick = () => alert('hi');\n```"
        elif system == code_edit.SYSTEM and "Fix these problems" in prompt:
            kind, text = "fix", "<<<<<<< SEARCH\nlet total = ;\n=======\nlet total = 0;\n>>>>>>> REPLACE\nSUMMARY: fixed total"
        elif system == code_edit.SYSTEM and "header blue" in prompt:
            kind = "edit"
            text = ("<<<<<<< SEARCH\nheader { background: #e11d48; color: white; padding: 16px; }\n=======\n"
                    "header { background: #2563eb; color: white; padding: 16px; }\n>>>>>>> REPLACE\nSUMMARY: made the header blue"
                    if "header {" in prompt else "NONE")
        else:
            kind, text = "chat", self.chat
        self.calls.append(kind)

        async def stream():
            for i in range(0, len(text), 300):
                yield _chunk(text[i:i + 300])
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
    model = Model()
    litellm.acompletion = model
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    try:
        with TestClient(server.app) as c:
            token = c.post("/api/auth/register", json={"name": "Sneha", "email": "sneha-check@test.com",
                                                       "password": "secret1"}).json()["token"]
            c.headers["Authorization"] = f"Bearer {token}"
            c.model = model
            yield c
    finally:
        litellm.acompletion = original


def _ask(client, text, chat_reply=""):
    client.model.chat = chat_reply
    client.model.calls.clear()
    cid = getattr(client, "cid", None) or client.post("/api/conversations", json={}).json()["id"]
    client.post(f"/api/conversations/{cid}/stream", json={"content": text, "model": "openai/gpt-oss-120b"})
    return cid, client.get(f"/api/conversations/{cid}").json()["messages"][-1]


def test_close_fence_and_replace_blocks():
    text, ticks = code_edit.close_fence("Here it is.\n\n```html index.html\n<html><body>")
    assert ticks == "```" and text.endswith("<html><body>\n```")
    assert code_edit.close_fence("```js a.js\nx\n```")[1] is None
    new = code_edit.replace_blocks("Built it.\n\n```html index.html\nold\n```\n\nEnjoy!", {"index.html": "new", "app.js": "go()"})
    assert new == "Built it.\n\n```html index.html\nnew\n```\n\nEnjoy!\n\n```js app.js\ngo()\n```"


def test_join_rest_drops_repeated_lines():
    assert code_check.join_rest("a\nb\nconst x = 1;\n", "const x = 1;\ny()\n") == "a\nb\nconst x = 1;\ny()\n"
    assert code_check.join_rest("<p>Hel", "lo</p>") == "<p>Hello</p>"


def test_new_builds_are_not_edits():
    for ask in ["make a gym website", "now create another game", "build me an app for notes", "ek new website banao"]:
        assert not code_edit.wants_edit(ask), ask
    for ask in ["make the header blue", "add a dark mode button", "make it responsive"]:
        assert code_edit.wants_edit(ask), ask


def test_cut_off_page_is_finished(client):
    """Before: the reply ran out of room mid-script and the preview showed a broken page."""
    client.cid = None
    _, msg = _ask(client, "make a to-do list app", "Here is your to-do app.\n\n```html index.html\n" + TODO_PAGE[:CUT_AT])
    assert client.model.calls == ["chat", "finish"]
    files = code_edit.code_files(msg["content"])
    assert files["index.html"].rstrip() == TODO_PAGE, "the page is whole again"
    assert "I tested the preview and fixed 1 problem" in msg["content"]
    assert msg["steps"][-1]["name"] == "check_preview" and msg["steps"][-1]["status"] == "done"


def test_missing_script_is_written(client):
    client.cid = None
    page = '<!DOCTYPE html><html><body><button id="go">Go</button><script src="app.js"></script></body></html>'
    _, msg = _ask(client, "make a greeting page", f"Built it.\n\n```html index.html\n{page}\n```")
    files = code_edit.code_files(msg["content"])
    assert "alert('hi')" in files["app.js"] and files["index.html"] == page


def test_script_error_is_fixed_in_place(client):
    client.cid = None
    page = "<!DOCTYPE html><html><body><p id='t'></p>\n<script>\nlet total = ;\ndocument.getElementById('t').textContent = total;\n</script>\n</body></html>"
    _, msg = _ask(client, "make a counter", f"Built it.\n\n```html index.html\n{page}\n```")
    assert "let total = 0;" in code_edit.code_files(msg["content"])["index.html"]
    assert client.model.calls == ["chat", "fix"]


def test_working_code_is_left_alone(client):
    client.cid = None
    _, msg = _ask(client, "make a to-do list app", f"Here it is.\n\n```html index.html\n{TODO_PAGE}\n```")
    assert client.model.calls == ["chat"] and not msg.get("steps")
    assert "tested the preview" not in msg["content"]


def test_follow_up_edits_krishs_own_page_in_place(client):
    """Before: "make the header blue" got a page rewritten from a trimmed memory of the old one."""
    client.cid = None
    cid, _ = _ask(client, "make a to-do list app", f"Here it is.\n\n```html index.html\n{TODO_PAGE}\n```")
    client.cid = cid
    _, msg = _ask(client, "make the header blue")
    client.cid = None
    assert client.model.calls == ["edit"]
    assert code_edit.code_files(msg["content"])["index.html"] == TODO_PAGE.replace("#e11d48", "#2563eb")
