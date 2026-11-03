"""The faster App Builder: files shown while they are typed (agent/drafts.py), the first version written in one
streamed reply with a starter on screen at once (fast_build.py), and the one-tap next ideas (apps.next_ideas).

Offline: the model is a fake stream and the app's files live in a dict.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402
import fast_build  # noqa: E402
from agent import drafts, runtime  # noqa: E402
from agent.tools import ToolContext  # noqa: E402

HTML = '<!doctype html>\n<html><body><h1 id="t">Cakes</h1><script src="app.js"></script></body></html>'
JS = 'document.getElementById("t").textContent = "Cake shop";'


# ------------------------------------------------------------------ drafts
def test_partial_string_reads_unfinished_json():
    raw = json.dumps({"path": "index.html", "content": 'a "quote"\n\tline ✓ 😀 end'})
    for cut in range(len(raw)):
        part = drafts.partial_string(raw[:cut], "content")
        full = 'a "quote"\n\tline ✓ 😀 end'
        assert part is None or full.startswith(part), (cut, part)
    assert drafts.partial_string(raw, "content") == 'a "quote"\n\tline ✓ 😀 end'
    assert drafts.partial_string('{"path": "a.js"', "content") is None


def test_tracker_sends_new_code_in_pieces_and_restarts_on_a_retry():
    t = drafts.DraftTracker("s0")
    body = "x" * 500
    raw = json.dumps({"path": "app.js", "content": body})
    shown = ""
    for cut in range(0, len(raw), 7):
        ev = t.update({"index": 0, "name": "write_file", "arguments": raw[:cut]})
        if ev:
            assert ev["path"] == "app.js" and ev["key"] == "s0-0"
            shown += ev["text"]
    last = t.update({"index": 0, "name": "write_file", "arguments": raw}, force=True)
    shown += last["text"] if last else ""
    assert shown == body
    # The model was asked again and started over: the shown file is replaced.
    again = t.update({"index": 0, "name": "write_file", "arguments": json.dumps({"path": "app.js", "content": "y" * 200})})
    assert again["reset"] and again["text"] == "y" * 200
    assert t.update({"index": 0, "name": "read_file", "arguments": raw}) is None


def test_run_agent_yields_code_drafts_before_the_tool_runs():
    raw = json.dumps({"path": "index.html", "content": HTML * 5})

    async def stream_fn(model, messages, tools):
        if not tools or any(m.get("role") == "tool" for m in messages):
            yield {"type": "text", "text": "Done."}
            return
        for cut in range(10, len(raw), 40):
            yield {"type": "tool_draft", "index": 0, "name": "write_file", "arguments": raw[:cut]}
        yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "write_file", "arguments": raw}]}

    class Registry:
        def schemas(self, ctx):
            return [{"type": "function", "function": {"name": "write_file", "parameters": {}}}]

        def active(self, ctx):
            return []

        async def run(self, name, arguments, ctx):
            from agent.tools import ToolOutput
            return ToolOutput(content="ok", summary="Wrote index.html")

    async def go():
        return [ev async for ev in runtime.run_agent(stream_fn, Registry(), ToolContext(None, "u"), "m", [])]

    events = asyncio.run(go())
    kinds = [e["type"] for e in events]
    assert kinds.index("code_draft") < kinds.index("tool_start")
    assert "".join(e["text"] for e in events if e["type"] == "code_draft") == HTML * 5


# --------------------------------------------------------------- fast build
def _store(monkeypatch, files):
    async def snapshot(app_id):
        return dict(files)

    async def write_file(app_id, path, content):
        files[apps.clean_path(path)] = content
        return path

    async def delete_file(app_id, path):
        return files.pop(path, None) is not None

    monkeypatch.setattr(apps, "snapshot", snapshot)
    monkeypatch.setattr(apps, "write_file", write_file)
    monkeypatch.setattr(apps, "delete_file", delete_file)


def test_fresh_template_and_picking_a_starter():
    assert fast_build.fresh_template(dict(apps.TEMPLATES["blank"])) == "blank"
    assert fast_build.fresh_template({**apps.TEMPLATES["todo"], "samples/a.log": "x"}) == "todo"
    assert fast_build.fresh_template({**apps.TEMPLATES["blank"], "index.html": "<p>mine</p>"}) is None
    assert fast_build.pick_template("make a todo app") == "todo"
    assert fast_build.pick_template("A restaurant website with a menu") == "restaurant"
    assert fast_build.pick_template("booking app for my salon") == "booking"
    assert fast_build.pick_template("an AI chatbot") == "chat"
    assert fast_build.pick_template("portfolio for a designer") == "portfolio"
    assert fast_build.pick_template("xyz") is None
    for tid in ("portfolio", "restaurant", "booking", "chat"):
        assert {"index.html", "app.js"} <= set(apps.TEMPLATES[tid])


def test_wanted_only_for_the_first_build_of_a_fresh_app():
    user = {"role": "user", "content": "make a cake shop"}
    blank = dict(apps.TEMPLATES["blank"])
    big = "cerebras/gpt-oss-120b"
    assert fast_build.wanted([user], blank, big)
    assert not fast_build.wanted([user], blank, "openai/gpt-oss-120b")  # Groq: no room for a whole app
    assert not fast_build.wanted([user, {"role": "assistant", "content": "ok"}, user], blank, big)
    assert not fast_build.wanted([user], {**blank, "index.html": "<p>mine</p>"}, big)
    assert not fast_build.wanted([user], {**blank, "samples/log.txt": "x"}, big)
    assert not fast_build.wanted([{"role": "user", "content": "```html\n<p></p>\n```"}], blank, big)


def test_draft_streams_plan_and_files_and_saves_each_file(monkeypatch):
    files = dict(apps.TEMPLATES["blank"])
    _store(monkeypatch, files)
    reply = ("- A menu of cakes\n- A cart with a total\n\n```html index.html\n" + HTML + "\n```\n\n"
             "```js\n" + JS + "\n```\n\nBuilt a cake shop.")

    async def stream_fn(model, messages, tools):
        assert tools == [] and fast_build.DRAFT_RULES in messages[-1]["content"]
        for i in range(0, len(reply), 9):
            yield {"type": "text", "text": reply[i:i + 9]}

    async def go():
        return [ev async for ev in fast_build.draft(stream_fn, "a1", "m", [{"role": "user", "content": "cake shop"}])]

    events = asyncio.run(go())
    done = events[-1]
    assert done["type"] == "draft_done" and done["files"] == ["index.html", "app.js"]
    assert done["plan"] == ["A menu of cakes", "A cart with a total"]
    assert files["index.html"] == HTML + "\n" and files["app.js"] == JS + "\n"
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "```" not in text and "Built a cake shop." in text and "A menu of cakes" in text
    code = "".join(e["text"] for e in events if e["type"] == "code_draft" and e["path"] == "index.html")
    assert code == HTML + "\n"
    ends = [e for e in events if e["type"] == "tool_end"]
    assert len(ends) == 2 and all(e["ok"] for e in ends)


def test_cut_off_reply_still_saves_what_was_written(monkeypatch):
    files = dict(apps.TEMPLATES["blank"])
    _store(monkeypatch, files)

    async def stream_fn(model, messages, tools):
        yield {"type": "text", "text": "- Plan\n```html index.html\n<html><body>half"}

    async def go():
        return [ev async for ev in fast_build.draft(stream_fn, "a1", "m", [])]

    done = asyncio.run(go())[-1]
    assert done["files"] == ["index.html"] and files["index.html"].startswith("<html><body>half")


def test_instant_start_shows_the_matching_starter_and_tidy_removes_leftovers(monkeypatch):
    files = dict(apps.TEMPLATES["blank"])
    _store(monkeypatch, files)

    async def go():
        return [ev async for ev in fast_build.instant_start("a1", "a booking app for my salon", dict(files))]

    events = asyncio.run(go())
    assert events[0]["name"] == "start_template" and events[-1]["ok"]
    assert files == dict(apps.TEMPLATES["booking"])
    # The new app wrote index.html and main.js: the starter's app.js goes.
    files["index.html"] = '<script src="main.js"></script>'
    files["main.js"] = "1"
    asyncio.run(fast_build.tidy_starter("a1", "booking", ["index.html", "main.js"]))
    assert set(files) == {"index.html", "main.js"}


def test_server_runs_the_fast_build_then_checks_and_commits(monkeypatch):
    from tests.test_app_problems import _server

    server = _server()
    files = dict(apps.TEMPLATES["blank"])
    _store(monkeypatch, files)
    monkeypatch.setattr(server.agent_browser, "available", lambda: False)
    commits = []

    async def commit(app_id, message, author="You"):
        commits.append(message)
        return {"id": "v1", "message": message}

    async def no_agent(*a, **k):
        raise AssertionError("the tool loop should not run when the fast build wrote the app")
        yield

    async def features(ctx, model, items):
        yield {"type": "problems", "problems": []}

    monkeypatch.setattr(server.apps, "commit", commit)
    monkeypatch.setattr(server, "run_agent", no_agent)
    monkeypatch.setattr(server, "_feature_events", features)
    reply = "- Shows a cake title\n```html index.html\n" + HTML + "\n```\n```js app.js\n" + JS + "\n```\nDone."

    async def stream_fn(model, messages, tools):
        yield {"type": "text", "text": reply}

    async def go():
        ctx = server.ToolContext(None, "u", app_id="a1")
        return [ev async for ev in server._agent_events(stream_fn, ctx, "m", [{"role": "user", "content": "cake shop"}],
                                                        True, 8, fast_for="a cake shop")]

    events = asyncio.run(go())
    assert commits == ["First version"]
    assert files["app.js"] == JS + "\n" and "still has a problem" not in "".join(
        e.get("text", "") for e in events if e["type"] == "text")
    assert any(e["type"] == "tool_start" and e["name"] == "start_template" for e in events)


# ------------------------------------------------------------------- ideas
def test_next_ideas_offer_what_the_app_lacks():
    ideas = apps.next_ideas({"index.html": "<form><input></form>", "app.js": "x"})
    labels = [i["label"] for i in ideas]
    assert len(ideas) == apps.MAX_IDEAS and "Add a dark mode switch" in labels
    rich = apps.next_ideas({"index.html": "<body class='dark'> theme<form></form> search RADHA.auth RADHA.notify",
                            "app.js": "localStorage RADHA.ai chart reveal @media"})
    assert [i["label"] for i in rich] == []
    assert apps.next_ideas({"samples/x.log": "a"}) == []
