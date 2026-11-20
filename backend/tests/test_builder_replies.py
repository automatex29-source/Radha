"""App Builder replies that went wrong on Krish Basic (the free models):

- a big build cut off inside app.js was saved broken ("Unexpected end of input"): the reply is now continued;
- after reading a big file, the request was trimmed out of the prompt and the model answered "Namaste! How can I
  help you today?": the latest request is now always kept;
- repair rounds showed that chat to the user instead of fixing: a broken file is now rewritten in one reply, and
  the model's words are shown only when it changed a file;
- a small edit failed with "tap Regenerate" when the free model stopped: another free model now takes over.

Offline: the model is a fake stream and the app's files live in a dict.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402
import code_edit  # noqa: E402
import fast_build  # noqa: E402
from agent import llm  # noqa: E402

BIG_ASK = ("Build a fully functional enterprise dashboard with 4 interconnected modules, 10,000+ mock records, "
           "dynamic filters, sortable tables, charts, global search and real-time updates.")
HTML = '<!doctype html>\n<html><body><h1 id="t">Dashboard</h1><script src="app.js"></script></body></html>'
JS_HEAD = 'const rows = [];\nfor (let i = 0; i < 10000; i++) {\n  rows.push({ id: i });\n'
JS_TAIL = '}\ndocument.getElementById("t").textContent = rows.length + " records";'


def _store(monkeypatch, files):
    async def write_file(app_id, path, content):
        files[path] = content

    async def snapshot(app_id):
        return dict(files)

    monkeypatch.setattr(apps, "write_file", write_file)
    monkeypatch.setattr(apps, "snapshot", snapshot)


# ------------------------------------------------------------ cut-off files
def test_reply_cut_off_inside_a_file_is_continued(monkeypatch):
    files = {}
    _store(monkeypatch, files)
    asks = []

    async def stream_fn(model, messages, tools):
        asks.append(messages)
        if len(asks) == 1:  # ran out of room in the middle of app.js
            yield {"type": "text", "text": "- Four modules\n```html index.html\n" + HTML + "\n```\n```js app.js\n" + JS_HEAD}
        else:  # the model opens the block again, then goes on
            yield {"type": "text", "text": "```js "}
            yield {"type": "text", "text": "app.js\n" + JS_TAIL + "\n```\nBuilt the dashboard."}

    async def go():
        return [ev async for ev in fast_build.draft(stream_fn, "a1", "m", [{"role": "user", "content": BIG_ASK}])]

    done = asyncio.run(go())[-1]
    assert len(asks) == 2 and "cut off in the middle of app.js" in asks[1][-1]["content"]
    assert "rows.push" in asks[1][-1]["content"]  # where it stopped is repeated, even if older parts get trimmed
    assert files["app.js"] == JS_HEAD + JS_TAIL + "\n"
    assert done["files"] == ["index.html", "app.js"]


def test_continuing_stops_after_a_few_tries(monkeypatch):
    files = {}
    _store(monkeypatch, files)
    calls = []

    async def stream_fn(model, messages, tools):
        calls.append(1)
        yield {"type": "text", "text": "```js app.js\nlet a = 1;\n" if len(calls) == 1 else "let b = 2;\n"}

    async def go():
        return [ev async for ev in fast_build.draft(stream_fn, "a1", "m", [])]

    done = asyncio.run(go())[-1]
    assert len(calls) == 1 + fast_build.MAX_CONTINUE
    assert done["files"] == ["app.js"] and files["app.js"].startswith("let a = 1;\nlet b = 2;")


# ------------------------------------------------------ the request stays in view
def test_latest_request_is_kept_when_a_big_file_fills_the_prompt():
    big_file = "x" * 30000
    msgs = [{"role": "system", "content": "rules"},
            {"role": "user", "content": BIG_ASK},
            {"role": "assistant", "content": "Built it."},
            {"role": "user", "content": "Auto-fix: SyntaxError: Unexpected end of input"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "app.js"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": big_file}]
    # Room for the system prompt, the request and the read, but not the earlier turns: those go, the request stays.
    budget = llm.estimate_tokens([msgs[0], msgs[3], msgs[4], msgs[5]]) + llm._MIN_OUTPUT + 20
    fitted = llm.fit_messages(msgs, [], budget)
    users = [m["content"] for m in fitted if m["role"] == "user"]
    assert users == ["Auto-fix: SyntaxError: Unexpected end of input"]
    assert fitted[-1]["content"] == big_file and fitted[-2].get("tool_calls")


def test_dropping_turns_never_leaves_a_tool_result_without_its_call():
    msgs = [{"role": "system", "content": "rules"}, {"role": "user", "content": "build it"}]
    for i in range(6):
        msgs += [{"role": "assistant", "content": None, "tool_calls": [
                     {"id": f"c{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
                 {"role": "tool", "tool_call_id": f"c{i}", "content": "y" * 3000}]
    fitted = llm.fit_messages(msgs, [], 6000)
    assert fitted[1] == {"role": "user", "content": "build it"}
    ids = {c["id"] for m in fitted if m.get("tool_calls") for c in m["tool_calls"]}
    assert all(m["tool_call_id"] in ids for m in fitted if m["role"] == "tool")


# ------------------------------------------------------------- repair rounds
def _server_with(monkeypatch, files, agent_rounds):
    from tests.test_app_problems import _server

    server = _server()
    _store(monkeypatch, files)
    monkeypatch.setattr(server.agent_browser, "available", lambda: False)
    calls = []

    async def run_agent(stream_fn, registry, ctx, model, messages, use_tools=True, max_steps=8):
        calls.append(list(messages))
        change, text = agent_rounds[min(len(calls) - 1, len(agent_rounds) - 1)]
        yield {"type": "tool_start", "id": "r", "name": "read_file", "label": "Read", "args": {"path": "app.js"}}
        yield {"type": "tool_end", "id": "r", "name": "read_file", "ok": True, "summary": "", "output": "", "media": []}
        if change:
            files.update(change)
            yield {"type": "tool_end", "id": "c", "name": "write_file", "ok": True}
        yield {"type": "text", "text": text}

    monkeypatch.setattr(server, "run_agent", run_agent)
    return server, calls


def _run(server, stream_fn, ask):
    async def go():
        ctx = server.ToolContext(None, "u", app_id="a1")
        return [ev async for ev in server._agent_events(stream_fn, ctx, "m", [{"role": "user", "content": ask}], True, 8)]
    events = asyncio.run(go())
    return events, "".join(e.get("text", "") for e in events if e["type"] == "text")


def test_broken_file_is_rewritten_and_chat_is_never_shown(monkeypatch):
    files = {"index.html": HTML, "app.js": JS_HEAD}
    server, calls = _server_with(monkeypatch, files, [(None, "Namaste Mukesh! How can I help you today?")])
    asks = []

    async def stream_fn(model, messages, tools):
        asks.append(messages)
        yield {"type": "text", "text": "```js app.js\n" + JS_HEAD + JS_TAIL + "\n```\nFinished the cut-off loop in app.js."}

    events, text = _run(server, stream_fn, "Auto-fix: the preview shows this error after your last change.\n"
                                           "SyntaxError: Unexpected end of input")
    assert "Namaste" not in text and "How can I help" not in text
    assert files["app.js"] == JS_HEAD + JS_TAIL + "\n"
    assert "Finished the cut-off loop in app.js." in text and "still has a problem" not in text
    assert len(asks) == 1 and "app.js" in asks[0][-1]["content"] and not calls[1:]  # one rewrite, no tool rounds


def test_chat_only_repair_rounds_stop_and_say_what_is_still_wrong(monkeypatch):
    files = {"index.html": HTML, "app.js": JS_HEAD}
    server, calls = _server_with(monkeypatch, files, [(None, "Sure! Just let me know what you'd like to build.")])

    async def stream_fn(model, messages, tools):  # the rewrite fails too: the model only chats
        yield {"type": "text", "text": "I'm ready to help you build your app!"}

    events, text = _run(server, stream_fn, "fix it")
    assert "let me know" not in text and "ready to help" not in text
    assert "still has a problem" in text and "app.js" in text
    assert len(calls) == 1 + server.REPAIR_ROUNDS  # stops after a few tries


def test_big_build_summary_is_only_shown_with_real_changes(monkeypatch):
    files = {"index.html": HTML, "app.js": JS_HEAD + JS_TAIL}
    server, calls = _server_with(monkeypatch, files, [({"app.js": JS_HEAD + JS_TAIL + "\n// sorted"}, "Made the table sortable.")])
    events, text = _run(server, None, "make the table sortable")
    assert "Made the table sortable." in text and "still has a problem" not in text


# ---------------------------------------------------------- small edits
def test_small_edit_moves_to_another_free_model_when_one_stops(monkeypatch):
    monkeypatch.setattr(code_edit, "stand_ins", lambda model: [model, "cerebras/gpt-oss-120b"])
    tried = []

    async def ask_model(model, messages, max_output):
        tried.append(model)
        if model == "groq/openai/gpt-oss-20b":
            yield {"type": "text", "text": "<<<<<<< SEARCH\n"}
            raise RuntimeError("rate limited")
        yield {"type": "text", "text": "<<<<<<< SEARCH\nfont-size: 20px;\n=======\nfont-size: 14px;\n>>>>>>> REPLACE\n"
                                       "SUMMARY: made the font smaller"}

    async def go():
        return [ev async for ev in code_edit.run("groq/openai/gpt-oss-20b", {"index.html": "h1 {\n  font-size: 20px;\n}"},
                                                 "make the font size small", ask_model)]

    result = asyncio.run(go())[-1]
    assert tried == ["groq/openai/gpt-oss-20b", "cerebras/gpt-oss-120b"]
    assert result["files"]["index.html"] == "h1 {\n  font-size: 14px;\n}" and result["applied"] == 1
