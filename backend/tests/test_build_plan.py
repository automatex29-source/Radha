"""Plan first, then check the plan (build_plan.py): the free App Builder plans a new app, follows the plan, and
fixes what the plan asked for but the files don't do.

Offline: the model calls and run_agent are replaced with fakes.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_plan  # noqa: E402
from tests.test_app_problems import _fake_agent, _server  # noqa: E402

PLAN = "- A menu of 6 cakes with prices\n- An Add to cart button on each cake\n- A cart that totals the order\n- Files: index.html, app.js"
GOOD_HTML = '<html><body><div id="menu"></div><script type="module" src="app.js"></script></body></html>'
GOOD_JS = 'document.getElementById("menu").textContent = "cakes";'


def _user(text):
    return {"role": "user", "content": text}


def test_plan_only_for_a_new_app_or_a_big_change_on_a_free_model():
    free = "openai/gpt-oss-120b"
    assert build_plan.wants_plan([_user("make a cake shop website")], free)
    assert not build_plan.wants_plan([_user("make a cake shop website")], "claude-sonnet-5-5")
    later = [_user("make a cake shop"), {"role": "assistant", "content": "Built it."}]
    assert not build_plan.wants_plan(later + [_user("make the button red")], free)
    assert not build_plan.wants_plan(later + [_user("fix it")], free)
    big = "add a booking page where people pick a date, a cake size and a flavour, pay on delivery, and get an email " \
          "with their order, and show all bookings to the owner on an admin page"
    assert build_plan.wants_plan(later + [_user(big)], free)
    assert not build_plan.wants_plan([_user("```html\n<h1>hi</h1>\n```")], free)


def _fake_model(monkeypatch, replies):
    asked = []

    async def ask(model, system, user, max_output):
        asked.append({"system": system, "user": user})
        reply = replies[len(asked) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(build_plan, "_ask", ask)
    return asked


def test_plan_is_parsed_and_a_failed_plan_is_skipped(monkeypatch):
    _fake_model(monkeypatch, [PLAN, "Sure!", RuntimeError("rate limited")])
    items = asyncio.run(build_plan.make_plan("m", "make a cake shop", {}))
    assert items[0] == "A menu of 6 cakes with prices" and len(items) == 4
    assert asyncio.run(build_plan.make_plan("m", "make a cake shop", {})) == []  # not a checklist
    assert asyncio.run(build_plan.make_plan("m", "make a cake shop", {})) == []  # the build goes ahead without it


def test_missing_features_come_back_as_problems(monkeypatch):
    files = {"index.html": GOOD_HTML, "app.js": GOOD_JS, "assets/logo.png": "x"}
    asked = _fake_model(monkeypatch, ['{"missing": ["The cart has no total (app.js)"]}', '{"missing": []}', "no json"])
    assert asyncio.run(build_plan.missing_features("m", ["A cart"], files)) == ["Not done yet: The cart has no total (app.js)"]
    assert "=== app.js ===" in asked[0]["user"] and "logo.png" not in asked[0]["user"]
    assert asyncio.run(build_plan.missing_features("m", ["A cart"], files)) == []
    assert asyncio.run(build_plan.missing_features("m", ["A cart"], files)) == []
    assert asyncio.run(build_plan.missing_features("m", [], files)) == []  # no plan: no extra request
    assert len(asked) == 3


def test_free_builder_plans_follows_the_plan_and_finishes_what_is_missing(monkeypatch):
    server = _server()
    files = {}
    calls = _fake_agent(monkeypatch, server, files, [
        ({"index.html": GOOD_HTML, "app.js": GOOD_JS}, "Built it."),
        ({"app.js": GOOD_JS + "\nconst total = 0;"}, "Added the cart total."),
    ])
    _fake_model(monkeypatch, [PLAN, '{"missing": ["The cart has no total (app.js)"]}'])

    async def go():
        return [ev async for ev in server._agent_events(None, server.ToolContext(None, "u", app_id="a1"), "m",
                                                        [{"role": "system", "content": "Build apps."}], True, 8,
                                                        plan_for="make a cake shop")]
    events = asyncio.run(go())
    steps = [ev for ev in events if ev["type"] == "tool_end" and ev["name"] in ("plan_app", "check_features")]
    assert [s["name"] for s in steps] == ["plan_app", "check_features"]
    assert steps[0]["summary"] == "4 things to build" and not steps[1]["ok"]
    assert "Build plan" in calls[0]["messages"][0]["content"] and "6 cakes" in calls[0]["messages"][0]["content"]
    assert len(calls) == 2 and "The cart has no total" in calls[1]["messages"][-1]["content"]
    text = "".join(ev["text"] for ev in events if ev["type"] == "text")
    assert "Added the cart total." in text and "still has a problem" not in text  # checked against the plan once


def test_edit_asks_never_start_a_plan():
    free = "openai/gpt-oss-120b"
    assert not build_plan.wants_plan([_user("in index remove the dropdown menu from the header")], free)
    assert not build_plan.wants_plan([_user("index se footer hata do")], free)
