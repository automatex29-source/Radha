"""Offline tests for dashboards, animated stories and prototypes, and for agent-team automations."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")

mongomock_motor = pytest.importorskip("mongomock_motor")

import automations  # noqa: E402
from agent import tools, visuals  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def page_data(page: str) -> dict:
    start = page.index("const D = ") + len("const D = ")
    return json.loads(page[start:page.index(";\n", start)])


class TestDashboard:
    def test_cleans_numbers_and_builds_page(self):
        spec = visuals.clean_dashboard({
            "title": "Sales <Q3>", "kpis": [{"label": "Revenue", "value": "₹4.2 Cr", "change": "+12%"}, {"value": "x"}],
            "charts": [{"title": "By month", "type": "weird", "labels": ["Jul", "Aug"],
                        "series": [{"name": "2026", "values": ["1,200", 1400, "n/a"]}]},
                       {"title": "empty", "series": [{"values": ["?"]}]}],
            "table": {"columns": ["A"], "rows": [["1"], "bad"]}, "insights": ["Up", ""]})
        assert [k["label"] for k in spec["kpis"]] == ["Revenue"]
        assert len(spec["charts"]) == 1 and spec["charts"][0]["type"] == "bar"
        assert spec["charts"][0]["series"][0]["values"] == [1200.0, 1400, None]
        assert spec["table"]["rows"] == [["1"]] and spec["insights"] == ["Up"]
        page = visuals.build_dashboard(spec)
        assert "<title>Sales &lt;Q3&gt;</title>" in page and visuals.CHART_JS in page
        assert page_data(page)["title"] == "Sales <Q3>"

    def test_page_has_3d_charts_and_smart_notes(self):
        page = visuals.build_dashboard(visuals.clean_dashboard({"title": "x", "kpis": [{"label": "a", "value": "1",
                                                                                         "trend": [1, "2", "x", 3]}]}))
        assert "depth3d" in page and "function analyse" in page and "Spotted automatically" in page
        assert page_data(page)["kpis"][0]["trend"] == [1, 2.0, 3]

    def test_script_tags_in_data_cannot_break_out(self):
        page = visuals.build_dashboard(visuals.clean_dashboard({"title": "x", "insights": ["</script><b>"],
                                                                "kpis": [{"label": "a", "value": "1"}]}))
        assert "</script><b>" not in page

    def test_needs_some_content(self):
        with pytest.raises(ValueError):
            visuals.clean_dashboard({"title": "Empty", "kpis": "not a list"})


class TestStory:
    def test_scenes(self):
        spec = visuals.clean_story({"title": "Year", "seconds_per_scene": 99, "theme": "neon", "scenes": [
            {"type": "title", "heading": "Hello"}, {"type": "stat", "value": "72%"},
            {"type": "chart", "heading": "Users", "chart": {"labels": ["a", "b"], "values": [1, 2]}},
            {"type": "chart", "heading": "No data", "chart": {}}, {"type": "list", "items": "abc"}, {}]})
        assert [s["type"] for s in spec["scenes"]] == ["title", "stat", "chart", "text"]
        assert spec["scenes"][2]["chart"]["values"] == [1, 2]
        assert spec["seconds"] == 15.0 and spec["theme"] == "dark"
        assert page_data(visuals.build_story(spec))["scenes"][0]["heading"] == "Hello"

    def test_needs_a_scene(self):
        with pytest.raises(ValueError):
            visuals.clean_story({"title": "x", "scenes": [{"type": "text"}]})


class TestPrototype:
    def test_screens_device_and_accent(self):
        spec = visuals.clean_prototype({"title": "Shop", "device": "tablet", "accent": "red;}", "screens": [
            {"name": "Home", "html": "<button data-go='Cart'>Cart</button>"}, {"name": "Empty", "html": " "},
            {"html": "<p>Cart</p>"}]})
        assert [s["name"] for s in spec["screens"]] == ["Home", "Screen 2"]
        assert spec["device"] == "phone" and spec["accent"] == "#4f46e5"
        page = visuals.build_prototype(spec)
        assert visuals.TAILWIND in page and "data-go" in page

    def test_needs_a_screen(self):
        with pytest.raises(ValueError):
            visuals.clean_prototype({"title": "x", "screens": []})


class TestTools:
    def test_registered_and_hidden_from_tight_free_models(self, monkeypatch):
        reg = tools.default_registry()
        names = {t.name for t in reg.active(tools.ToolContext(db=None, user_id="u", model="claude-sonnet-4-6"))}
        assert {"create_dashboard", "create_story", "create_prototype"} <= names
        from agent import llm
        monkeypatch.setattr(llm, "lean", lambda m: True)
        monkeypatch.setattr(llm, "token_budget", lambda m="": 7700)
        lean_names = {t.name for t in reg.active(tools.ToolContext(db=None, user_id="u", model="groq/x"))}
        assert "create_dashboard" not in lean_names and "create_html" in lean_names

    def test_dashboard_tool_saves_html(self, monkeypatch):
        saved = {}

        async def fake_save(db, user_id, data, ctype, kind, name=None, conversation_id=None):
            saved.update(data=data, ctype=ctype, name=name)
            return {"id": "m1", "name": name, "contentType": ctype}

        monkeypatch.setattr(tools.media, "save_media", fake_save)
        out = run(tools.default_registry().run("create_dashboard", json.dumps(
            {"title": "Team KPIs", "kpis": [{"label": "Leads", "value": "120"}]}),
            tools.ToolContext(db=None, user_id="u", model="claude-sonnet-4-6")))
        assert out.ok and saved["ctype"] == "text/html" and saved["name"].endswith(".html")
        assert out.media[0]["id"] == "m1"


def _fake_turns(database, replies, calls):
    """A run_turn that answers with the next reply; an Exception in the list makes that attempt fail."""
    async def fake_turn(conv_id, model, agent=False, **kw):
        calls.append(conv_id)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            yield f'event: error\ndata: "{reply}"\n\n'
            return
        await database.messages.insert_one({"id": f"r{len(calls)}", "conversationId": conv_id, "role": "assistant",
                                            "content": reply, "media": [{"id": f"f{len(calls)}"}],
                                            "steps": [{"name": "web_search", "label": "Web search", "status": "done"}],
                                            "createdAt": f"z{len(calls)}"})
        yield "data: \"ok\"\n\n"
    return fake_turn


class TestAgentTeams:
    def test_stages_run_in_order_and_a_failed_stage_is_retried(self, monkeypatch):
        database = mongomock_motor.AsyncMongoMockClient()["teams"]
        calls = []
        monkeypatch.setattr(automations, "RETRY_DELAY_SECONDS", 0)
        automations.init(database, _fake_turns(database, ["Research done", RuntimeError("busy"), "Report written"],
                                               calls), "m")

        async def scenario():
            auto = {"id": "t1", "userId": "u", "name": "Market report", "prompt": "Report on EV sales",
                    "schedule": {"type": "manual"}, "stages": ["Research the numbers", "Write the report"]}
            await database.automations.insert_one(dict(auto))
            await automations.start_run(auto, "manual")
            await asyncio.gather(*list(automations._running))
            msgs = await database.messages.find({"role": "user"}).sort("createdAt", 1).to_list(10)
            return await database.automation_runs.find_one({}), msgs

        run_doc, msgs = run(scenario())
        assert len(calls) == 3
        assert "agent 1 of a team of 2" in msgs[0]["content"] and "Research the numbers" in msgs[0]["content"]
        assert "agent 2 of 2" in msgs[1]["content"] and "Write the report" in msgs[1]["content"]
        assert run_doc["status"] == "succeeded" and run_doc["output"] == "Report written" and run_doc["retries"] == 1
        assert [s["status"] for s in run_doc["stages"]] == ["done", "done"]
        assert [m["id"] for m in run_doc["media"]] == ["f1", "f3"] and len(run_doc["steps"]) == 2

    def test_stage_that_fails_twice_stops_the_run(self, monkeypatch):
        database = mongomock_motor.AsyncMongoMockClient()["fail2"]
        monkeypatch.setattr(automations, "RETRY_DELAY_SECONDS", 0)
        automations.init(database, _fake_turns(database, [RuntimeError("down"), RuntimeError("down")], []), "m")

        async def scenario():
            auto = {"id": "t2", "userId": "u", "name": "x", "prompt": "p", "schedule": {"type": "manual"},
                    "stages": ["a", "b"]}
            await database.automations.insert_one(dict(auto))
            await automations.start_run(auto, "manual")
            await asyncio.gather(*list(automations._running))
            return await database.automation_runs.find_one({})

        run_doc = run(scenario())
        assert run_doc["status"] == "failed" and run_doc["error"] == "down"
        assert [s["status"] for s in run_doc["stages"]] == ["failed", "waiting"]

    def test_quiet_run_skips_delivery_and_chain(self, monkeypatch):
        database = mongomock_motor.AsyncMongoMockClient()["quiet"]
        delivered = []

        async def fake_deliver(auto, run_doc):
            delivered.append(run_doc)
            return []

        monkeypatch.setattr(automations, "_deliver", fake_deliver)
        calls = []
        automations.init(database, _fake_turns(database, ["NOTHING NEW. Prices are the same."], calls), "m")

        async def scenario():
            await database.automations.insert_one({"id": "next", "userId": "u", "name": "n", "prompt": "p",
                                                   "schedule": {"type": "manual"}, "enabled": True})
            auto = {"id": "q1", "userId": "u", "name": "Price watch", "prompt": "p", "schedule": {"type": "manual"},
                    "onlyIfNew": True, "thenRun": "next", "emailResult": True}
            await database.automations.insert_one(dict(auto))
            await automations.start_run(auto, "manual")
            await asyncio.gather(*list(automations._running))
            return await database.automation_runs.find({}).to_list(10)

        runs = run(scenario())
        assert len(runs) == 1 and runs[0]["quiet"] is True and runs[0]["delivery"] == []
        assert not delivered and len(calls) == 1

    def test_chain_hands_result_to_next_and_stops_at_max_depth(self, monkeypatch):
        database = mongomock_motor.AsyncMongoMockClient()["chain"]
        replies = [f"Result {i}" for i in range(10)]
        calls = []
        automations.init(database, _fake_turns(database, replies, calls), "m")

        async def drain():
            while automations._running:
                await asyncio.gather(*list(automations._running))

        async def scenario():
            a = {"id": "A", "userId": "u", "name": "Finder", "prompt": "find", "schedule": {"type": "manual"},
                 "enabled": True, "thenRun": "B"}
            b = {"id": "B", "userId": "u", "name": "Writer", "prompt": "write", "schedule": {"type": "manual"},
                 "enabled": True, "thenRun": "A"}
            await database.automations.insert_many([dict(a), dict(b)])
            await automations.start_run(a, "manual")
            await drain()
            return await database.automation_runs.find({}).sort("startedAt", 1).to_list(10)

        runs = run(scenario())
        assert len(runs) == automations.MAX_CHAIN_DEPTH + 1  # A → B → A → B, then the loop stops
        assert runs[1]["trigger"] == "chain" and runs[1]["automationId"] == "B"

    def test_chain_payload_reaches_prompt(self):
        database = mongomock_motor.AsyncMongoMockClient()["payload"]
        automations.init(database, _fake_turns(database, ["ok"], []), "m")

        async def scenario():
            auto = {"id": "B", "userId": "u", "name": "Writer", "prompt": "write", "schedule": {"type": "manual"}}
            await automations.start_run(auto, "chain", "From 'Finder':\n5 leads", depth=1)
            await asyncio.gather(*list(automations._running))
            return await database.messages.find_one({"role": "user"})

        msg = run(scenario())
        assert "started by another automation" in msg["content"] and "5 leads" in msg["content"]

    def test_parse_plan_keeps_stages(self):
        plan = automations.parse_plan({"name": "x", "task": "t", "stages": ["Research", "", "Write", 3]}, "g")
        assert plan["stages"] == ["Research", "Write", "3"]
        assert "stages" not in automations.parse_plan({"name": "x", "task": "t", "stages": ["only one"]}, "g")

    def test_then_run_must_be_another_own_automation(self):
        database = mongomock_motor.AsyncMongoMockClient()["then"]
        automations.init(database, None, "m")

        async def scenario():
            await database.automations.insert_one({"id": "mine", "userId": "u"})
            ok = await automations._clean_then_run("mine", "u", "other")
            errors = []
            for target, own in (("mine", "mine"), ("theirs", "x")):
                try:
                    await automations._clean_then_run(target, "u", own)
                except automations.HTTPException as exc:
                    errors.append(exc.status_code)
            return ok, errors, await automations._clean_then_run("", "u", None)

        assert run(scenario()) == ("mine", [400, 400], None)
