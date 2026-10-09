"""The App Builder opens each app in a real browser and presses its buttons (apps.smoke_test), fixes what breaks,
and can make several edits in one edit_file call."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402

PAGE = """<!DOCTYPE html><html><body><h1 id="n">0</h1>
<button id="inc">Add one</button><button id="reset">Reset</button>
<script src="app.js"></script></body></html>"""
BROKEN_JS = """document.getElementById('inc').onclick = () => { document.getElementById('n').textContent++; };
document.getElementById('reset').onclick = () => { resetCounter(); };"""
FIXED_JS = BROKEN_JS.replace("resetCounter()", "document.getElementById('n').textContent = 0")


def _smoke(files):
    async def go():
        # A fresh browser for this event loop (the server keeps one for its own, long-lived loop).
        manager = apps.agent_browser.BrowserManager()
        apps.agent_browser.manager, before = manager, apps.agent_browser.manager
        try:
            return await apps.smoke_test(files)
        finally:
            apps.agent_browser.manager = before
            await manager.shutdown()
    try:
        return asyncio.run(asyncio.wait_for(go(), 60))
    except Exception as exc:  # no Chromium on this machine
        pytest.skip(f"no browser: {exc}")


def test_button_that_crashes_is_found():
    """Static checks miss this: the page loads fine, but pressing Reset throws."""
    assert asyncio.run(apps.check_app({"index.html": PAGE, "app.js": BROKEN_JS})) == []
    assert _smoke({"index.html": PAGE, "app.js": BROKEN_JS}) == [
        "Uncaught error after clicking “Reset”: resetCounter is not defined"]


def test_working_app_passes():
    assert _smoke({"index.html": PAGE, "app.js": FIXED_JS}) == []


def test_error_on_load_is_found():
    js = "const items = getItems();\n" + FIXED_JS
    assert _smoke({"index.html": PAGE, "app.js": js}) == ["Uncaught error on load: getItems is not defined"]


def _server():
    from test_app_problems import _server as make
    return make()


def test_browser_error_gets_fixed(monkeypatch):
    from test_app_problems import _fake_agent, _texts
    server = _server()
    files = {}
    calls = _fake_agent(monkeypatch, server, files, [
        ({"index.html": PAGE, "app.js": BROKEN_JS}, "Built the counter."),
        ({"app.js": FIXED_JS}, "Fixed the Reset button."),
    ])
    monkeypatch.setattr(server.agent_browser, "available", lambda: True)

    async def smoke(f, app_id=None):
        return ["Uncaught error after clicking “Reset”: resetCounter is not defined"] if "resetCounter" in f["app.js"] else []
    monkeypatch.setattr(server.apps, "smoke_test", smoke)

    async def go():
        return [ev async for ev in server._agent_events(None, server.ToolContext(None, "u", app_id="a1"), "m", [], True, 8)]
    events = asyncio.run(go())
    assert len(calls) == 2 and "after clicking “Reset”" in calls[1]["messages"][-1]["content"]
    tests = [e for e in events if e["type"] == "tool_end" and e["name"] == "check_preview"]
    assert [t["ok"] for t in tests] == [False, True]
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert "Fixed the Reset button." in text and "still has a problem" not in text


class _Files:
    """Just enough of the app_files collection for edit_file."""

    def __init__(self, content):
        self.content = content

    async def find_one(self, query, *args):
        return {"content": self.content}


def test_several_edits_in_one_call(monkeypatch):
    store = _Files("body { color: #111; }\nh1 { color: #e11d48; }\nbutton { background: #e11d48; }\n")
    monkeypatch.setattr(apps, "db", type("DB", (), {"app_files": store})())

    async def write(app_id, path, content):
        store.content = content

    async def no_problems(app_id, text):
        return text
    monkeypatch.setattr(apps, "write_file", write)
    monkeypatch.setattr(apps, "_with_problems", no_problems)
    ctx = type("Ctx", (), {"app_id": "a1"})()
    out = asyncio.run(apps._t_edit(ctx, {"path": "styles.css", "edits": [
        {"old_text": "h1 { color: #e11d48; }", "new_text": "h1 { color: #2563eb; }"},
        {"old_text": "button { background: #e11d48; }", "new_text": "button { background: #2563eb; }"}]}))
    assert out.ok and "2 changes" in out.summary and store.content.count("#2563eb") == 2

    before = store.content
    out = asyncio.run(apps._t_edit(ctx, {"path": "styles.css", "edits": [
        {"old_text": "body { color: #111; }", "new_text": "body { color: #000; }"},
        {"old_text": "footer { }", "new_text": "footer { color: red; }"}]}))
    assert not out.ok and "Edit 2 of 2" in out.content and store.content == before, "all or nothing"


def test_apps_on_the_backend_are_not_pressed(monkeypatch):
    """A click could email the owner (RADHA.notify) or change real data, so those apps get static checks only."""
    from test_app_problems import _fake_agent
    server = _server()
    files = {}
    _fake_agent(monkeypatch, server, files, [({"index.html": PAGE, "app.js": FIXED_JS + "\nRADHA.notify({message: 'hi'});"}, "Built it.")])
    monkeypatch.setattr(server.agent_browser, "available", lambda: True)

    async def smoke(f, app_id=None):
        raise AssertionError("must not run")
    monkeypatch.setattr(server.apps, "smoke_test", smoke)

    async def go():
        return [ev async for ev in server._agent_events(None, server.ToolContext(None, "u", app_id="a1"), "m", [], True, 8)]
    assert not any(e["type"] == "tool_start" for e in asyncio.run(go()))
