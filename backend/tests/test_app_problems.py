"""The App Builder's static check (crashing id lookups, missing files) and its automatic repair round."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402

CAKE_HTML = '<html><body><h1>My Cake Shop</h1><script type="module" src="app.js"></script></body></html>'
CAKE_JS = 'document.getElementById("cart-btn").onclick = () => {};'


def test_cake_shop_crash_is_found():
    problems = apps.app_problems({"index.html": CAKE_HTML, "app.js": CAKE_JS})
    assert len(problems) == 1 and "#cart-btn" in problems[0] and "app.js" in problems[0]


def test_working_app_has_no_problems():
    files = {
        "index.html": '<div id="cart-btn"></div><link rel="stylesheet" href="styles.css">'
                      '<script src="https://cdn.tailwindcss.com"></script><script type="module" src="./js/app.js"></script>',
        "styles.css": "body{}",
        "js/app.js": 'import { items } from "./data.js";\nconst el = document.createElement("p"); el.id = "made";\n'
                     'document.querySelector("#made"); document.getElementById("cart-btn");\n'
                     'document.getElementById(`row-${1}`);',
        "js/data.js": "export const items = [];",
    }
    assert apps.app_problems(files) == []


def test_missing_files_and_index_are_found():
    problems = apps.app_problems({"page.html": '<script src="app.js"></script><link href="../x/site.css" rel=stylesheet>'})
    assert any("no index.html" in p for p in problems)
    assert any("app.js" in p for p in problems) and any("x/site.css" in p for p in problems)


def _server():
    if "server" not in sys.modules:
        import os
        import mongomock_motor
        import motor.motor_asyncio
        os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                          AI_MODEL="openai/gpt-oss-120b")
        motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import server
    return server


def _fake_agent(monkeypatch, server, files, rounds):
    """run_agent replaced by scripted rounds; each round may change `files` and says some text."""
    calls = []

    async def run_agent(stream_fn, registry, ctx, model, messages, use_tools=True, max_steps=8):
        calls.append({"messages": list(messages), "max_steps": max_steps})
        change, text = rounds[len(calls) - 1]
        if change:
            files.update(change)
            yield {"type": "tool_end", "id": "c", "name": "write_file", "ok": True}
        yield {"type": "text", "text": text}

    async def snapshot(app_id):
        return dict(files)

    monkeypatch.setattr(server, "run_agent", run_agent)
    monkeypatch.setattr(server.apps, "snapshot", snapshot)
    monkeypatch.setattr(server.agent_browser, "available", lambda: False)  # browser tests: see test_builder_smoke.py
    return calls


def _texts(server, ctx):
    async def go():
        return [ev["text"] async for ev in server._agent_events(None, ctx, "m", [], True, 8) if ev["type"] == "text"]
    return "".join(asyncio.run(go()))


def test_broken_build_gets_a_repair_round(monkeypatch):
    server = _server()
    files = {}
    calls = _fake_agent(monkeypatch, server, files, [
        ({"index.html": CAKE_HTML, "app.js": CAKE_JS}, "Built it."),
        ({"index.html": CAKE_HTML.replace("<h1>", '<button id="cart-btn">Cart</button><h1>')}, "Added the cart button."),
    ])
    out = _texts(server, server.ToolContext(None, "u", app_id="a1"))
    assert len(calls) == 2 and calls[1]["max_steps"] == server.REPAIR_STEPS
    assert "#cart-btn" in calls[1]["messages"][-1]["content"]
    assert "fixing it" in out and "Added the cart button." in out and "still has a problem" not in out


def test_unfixed_problem_is_told_to_the_user(monkeypatch):
    server = _server()
    files = {}
    calls = _fake_agent(monkeypatch, server, files, [({"index.html": CAKE_HTML, "app.js": CAKE_JS}, "")]
                        + [(None, "")] * server.REPAIR_ROUNDS)
    out = _texts(server, server.ToolContext(None, "u", app_id="a1"))
    assert "still has a problem" in out and "#cart-btn" in out
    assert len(calls) == 1 + server.REPAIR_ROUNDS


def test_no_repair_when_nothing_changed_or_no_app(monkeypatch):
    server = _server()
    files = {"index.html": CAKE_HTML, "app.js": CAKE_JS}
    calls = _fake_agent(monkeypatch, server, files, [(None, "Here is how it works.")])
    _texts(server, server.ToolContext(None, "u", app_id="a1"))
    assert len(calls) == 1


def test_cut_off_javascript_is_found():
    files = {"index.html": '<main id="menu"></main><script type="module" src="app.js"></script>',
             "app.js": 'const cakes = [{name: "Red Velvet"}];\ndocument.getElementById("menu").innerHTML = cakes.map((c) => `<h2>${c.na'}
    problems = asyncio.run(apps.check_app(files))
    assert len(problems) == 1 and "app.js has a syntax error" in problems[0] and "append_file" in problems[0]
    files["app.js"] += 'me}</h2>`).join("");\n'
    assert asyncio.run(apps.check_app(files)) == []
    # A classic script (no type=module, no import) is checked as one, so top-level `return`-free code passes too.
    assert asyncio.run(apps.check_app({"index.html": '<script src="a.js"></script>', "a.js": "var x = 1;"})) == []


def test_append_file_builds_a_long_file_in_parts(monkeypatch):
    store = {}

    async def write_file(app_id, path, content):
        store[path] = content
        return path

    class Files:
        async def find_one(self, query, *_a):
            return {"content": store[query["path"]]} if query["path"] in store else None

    async def snapshot(app_id):
        return dict(store)

    monkeypatch.setattr(apps, "write_file", write_file)
    monkeypatch.setattr(apps, "snapshot", snapshot)
    monkeypatch.setattr(apps, "db", type("DB", (), {"app_files": Files()})())
    ctx = type("Ctx", (), {"app_id": "a1"})()
    asyncio.run(apps._t_append(ctx, {"path": "app.js", "content": "const a = 1;"}))
    out = asyncio.run(apps._t_append(ctx, {"path": "app.js", "content": "const b = 2;\n"}))
    assert store["app.js"] == "const a = 1;\nconst b = 2;\n" and "Added" in out.content


def test_cut_off_tool_call_says_to_write_in_parts():
    from agent import Tool, ToolContext, ToolRegistry, ToolOutput

    async def h(ctx, args):
        return ToolOutput(content="")

    reg = ToolRegistry().register(Tool("write_file", "Write", {"type": "object"}, h, scope="app"))
    out = asyncio.run(reg.run("write_file", '{"path": "index.html", "content": "<html><body><h1>Cake', ToolContext(None, "u", app_id="a")))
    assert not out.ok and "append_file" in out.content


VIDEO_REPLY = ('I am generating a 12-second reel of kids playing.\n\n```json data.json\n'
               '{"prompt": "Happy children playing on a sunny playground", "seconds": 12, "style": "social_reel", '
               '"scenes": ["Wide shot", "Slide"], "made_up": 1}\n```')


def test_video_call_written_as_json_is_run_for_real(monkeypatch):
    server = _server()
    assert server.written_media_call(VIDEO_REPLY, "MAKE AVIDEOO ONN KIDS PLAYING")[0] == "generate_video"
    assert server.written_media_call("```json\n{\"name\": \"x\"}\n```", "make a video") is None  # not a tool call
    assert server.written_media_call("```json\n{\"prompt\": \"a cat\"}\n```", "explain json") is None
    calls = _fake_agent(monkeypatch, server, {}, [(None, VIDEO_REPLY)])
    ran = []

    async def run(name, raw, ctx):
        ran.append((name, raw))
        from agent import ToolOutput
        return ToolOutput(content="done", summary="Video ready", media=[{"id": "v1", "contentType": "video/mp4"}])
    monkeypatch.setattr(server.tool_registry, "run", run)

    async def go():
        return [ev async for ev in server._agent_events(None, server.ToolContext(None, "u"), "m",
                                                        [{"role": "user", "content": "MAKE AVIDEOO ONN KIDS PLAYING"}], True, 8)]
    events = asyncio.run(go())
    assert len(calls) == 1 and ran and ran[0][0] == "generate_video" and "made_up" not in ran[0][1]
    assert [e["type"] for e in events if e["type"] != "text"] == ["drop_text", "tool_start", "tool_end"]
    assert next(e for e in events if e["type"] == "tool_end")["media"][0]["id"] == "v1"
