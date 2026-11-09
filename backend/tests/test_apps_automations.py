"""Offline tests for the app builder (files, versions, git export, serving) and automations."""
import asyncio
import io
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")

mongomock_motor = pytest.importorskip("mongomock_motor")

import apps  # noqa: E402
import automations  # noqa: E402


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db():
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    apps.init(database)
    return database


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class TestPaths:
    @pytest.mark.parametrize("good,expected", [("index.html", "index.html"), ("./src/app.js", "src/app.js"),
                                               ("tests/a b.test.mjs", "tests/a b.test.mjs")])
    def test_accepts(self, good, expected):
        assert apps.clean_path(good) == expected

    @pytest.mark.parametrize("bad", ["", "/etc/passwd", "../x", "a/../../x", ".git/config", "a//b", "a\x00b", "x" * 201])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            apps.clean_path(bad)


class TestAppVersions:
    def test_commit_diff_restore_and_git_export(self, db):
        async def scenario():
            await db.apps.insert_one({"id": "a", "userId": "u", "name": "My App!", "createdAt": "", "updatedAt": ""})
            await apps.write_file("a", "index.html", "<h1>v1</h1>\n")
            first = await apps.commit("a", "First", author="Krish AI")
            assert await apps.commit("a", "noop") is None
            await apps.write_file("a", "index.html", "<h1>v2</h1>\n")
            await apps.write_file("a", "src/app.js", "x = 1\n")
            assert await apps.changed_paths("a") == {"index.html": "modified", "src/app.js": "added"}
            second = await apps.commit("a", "Second")
            head = await apps.head_commit("a")
            diff = apps.unified_diff(await apps.commit_files(await db.app_commits.find_one({"id": first["id"]})),
                                     await apps.commit_files(head))
            assert [(d["path"], d["status"]) for d in diff] == [("index.html", "modified"), ("src/app.js", "added")]
            assert "+<h1>v2</h1>" in diff[0]["diff"]
            restored = await apps.restore("a", first["id"])
            assert restored["message"].startswith(f"Restore version {first['id']}")
            assert await apps.snapshot("a") == {"index.html": "<h1>v1</h1>\n"}
            await apps.write_file("a", "notes.md", "draft")  # uncommitted
            return await apps.export_zip(await db.apps.find_one({"id": "a"})), second

        data, second = run(scenario())
        tmp = tempfile.mkdtemp()
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        root = os.path.join(tmp, "my-app")
        assert sorted(os.listdir(root)) == [".git", "index.html", "notes.md"]
        log = subprocess.run(["git", "-C", root, "log", "--format=%s|%an"], capture_output=True, text=True)
        if log.returncode != 0:
            pytest.skip("git not installed")
        lines = log.stdout.splitlines()
        assert lines[1:] == ["Second|You", "First|Krish AI"]
        assert lines[0].startswith("Restore version ") and lines[0].endswith(": First|You")
        status = subprocess.run(["git", "-C", root, "status", "--short"], capture_output=True, text=True).stdout
        assert status.strip() == "?? notes.md"

    def test_limits(self, db):
        async def scenario():
            await db.apps.insert_one({"id": "a", "userId": "u", "name": "x", "createdAt": "", "updatedAt": ""})
            with pytest.raises(ValueError, match="too large"):
                await apps.write_file("a", "big.txt", "x" * (apps.MAX_FILE_BYTES + 1))

        run(scenario())


class TestServing:
    def test_preview_injects_bridge_and_sandboxes(self):
        resp = apps._serve({"index.html": "<html><head></head><body>x</body></html>"}, "", bridge=True, cache="no-store")
        body = resp.body.decode()
        assert "radha-preview" in body and body.index("radha-preview") < body.index("<body>")
        assert resp.headers["content-security-policy"].startswith("sandbox allow-scripts")
        assert "allow-same-origin" not in resp.headers["content-security-policy"]

    def test_spa_fallback_and_404(self):
        files = {"index.html": "<p>home</p>", "app.js": "1"}
        assert apps._serve(files, "dashboard/settings", False, "x").body.endswith(b"<p>home</p>")  # after the injected shims
        assert apps._serve(files, "missing.js", False, "x").status_code == 404
        assert apps._serve(files, "app.js", False, "x").headers["content-type"].startswith("text/javascript")

    def test_preview_token_roundtrip(self):
        token = apps.preview_token("app1", "u1")
        assert apps._decode_preview(token)["sub"] == "app1"
        with pytest.raises(Exception):
            apps._decode_preview("nope")


class TestSchedules:
    def test_interval(self):
        assert automations.next_run({"type": "interval", "minutes": 90}, utc(2026, 1, 1, 10, 0)) == utc(2026, 1, 1, 11, 30)

    def test_daily_later_today_and_tomorrow(self):
        s = {"type": "daily", "time": "09:30", "timezone": "UTC"}
        assert automations.next_run(s, utc(2026, 1, 1, 8, 0)) == utc(2026, 1, 1, 9, 30)
        assert automations.next_run(s, utc(2026, 1, 1, 9, 30)) == utc(2026, 1, 2, 9, 30)

    def test_daily_in_timezone_across_dst(self):
        s = {"type": "daily", "time": "09:00", "timezone": "America/New_York"}
        # Before the March 8, 2026 DST change 09:00 EST = 14:00 UTC, after it 09:00 EDT = 13:00 UTC.
        assert automations.next_run(s, utc(2026, 3, 7, 15, 0)) == utc(2026, 3, 8, 13, 0)

    def test_weekly(self):
        s = {"type": "weekly", "time": "07:00", "weekday": 0, "timezone": "Asia/Kolkata"}  # Mondays 07:00 IST
        assert automations.next_run(s, utc(2026, 9, 23, 0, 0)) == utc(2026, 9, 28, 1, 30)

    def test_manual(self):
        assert automations.next_run({"type": "manual"}, utc(2026, 1, 1)) is None

    def test_describe(self):
        assert automations.describe_schedule({"type": "interval", "minutes": 180}) == "Every 3 hours"
        assert automations.describe_schedule({"type": "weekly", "time": "07:00", "weekday": 4, "timezone": "UTC"}) == "Every Friday at 07:00 (UTC)"


class TestScheduler:
    def test_due_automation_runs_once_and_records_result(self, monkeypatch):
        database = mongomock_motor.AsyncMongoMockClient()["s"]
        calls = []

        async def fake_turn(conv_id, model, agent=False, **kw):
            calls.append((conv_id, agent, kw))
            await database.messages.insert_one({"id": "m", "conversationId": conv_id, "role": "assistant",
                                                "content": "Report ready", "media": [], "steps": [{}], "createdAt": "z"})
            yield "data: \"Report ready\"\n\n"

        automations.init(database, fake_turn, "claude-sonnet-4-6")

        async def scenario():
            await database.automations.insert_one({
                "id": "a1", "userId": "u", "name": "Daily brief", "prompt": "Summarise the news",
                "schedule": {"type": "interval", "minutes": 60}, "enabled": True,
                "nextRunAt": "2000-01-01T00:00:00+00:00", "lockedUntil": None, "createdAt": "x"})
            await asyncio.gather(automations.tick(), automations.tick())  # concurrent ticks must not double-fire
            await asyncio.gather(*list(automations._running))
            runs = await database.automation_runs.find({}).to_list(10)
            auto = await database.automations.find_one({"id": "a1"})
            return runs, auto

        runs, auto = run(scenario())
        assert len(calls) == 1 and calls[0][1] is True
        assert calls[0][2]["max_steps"] == automations.STEPS_NORMAL
        assert "autonomous agent" in calls[0][2]["extra_system"]
        assert len(runs) == 1 and runs[0]["status"] == "succeeded" and runs[0]["output"] == "Report ready"
        assert auto["lastStatus"] == "succeeded" and auto["lockedUntil"] is None
        assert auto["nextRunAt"] > datetime.now(timezone.utc).isoformat()

    def test_failed_turn_is_recorded(self):
        database = mongomock_motor.AsyncMongoMockClient()["f"]

        async def failing_turn(conv_id, model, agent=False, **kw):
            yield 'event: error\ndata: "No API key"\n\n'

        automations.init(database, failing_turn, "m")

        async def scenario():
            auto = {"id": "a2", "userId": "u", "name": "x", "prompt": "p", "schedule": {"type": "manual"}}
            await database.automations.insert_one(dict(auto))
            await automations.start_run(auto, "webhook", '{"event": "push"}')
            await asyncio.gather(*list(automations._running))
            run_doc = await database.automation_runs.find_one({})
            first_msg = await database.messages.find_one({"role": "user"})
            return run_doc, first_msg

        run_doc, first_msg = run(scenario())
        assert run_doc["status"] == "failed" and run_doc["error"] == "No API key" and run_doc["trigger"] == "webhook"
        assert '"event": "push"' in first_msg["content"]


class TestAgentAutomations:
    def test_memory_steps_and_webhook_delivery(self, monkeypatch):
        database = mongomock_motor.AsyncMongoMockClient()["g"]
        seen, posted = [], []

        async def fake_turn(conv_id, model, agent=False, **kw):
            seen.append(kw)
            await database.messages.insert_one({
                "id": conv_id, "conversationId": conv_id, "role": "assistant", "content": f"Result {len(seen)}",
                "media": [{"id": "x", "name": "brief.pdf"}], "createdAt": "z",
                "steps": [{"id": "1", "name": "web_search", "label": "Web search", "status": "done",
                           "summary": "5 results", "output": "long" * 500}]})
            yield "data: \"ok\"\n\n"

        async def fake_check(url):
            return url

        class FakeClient:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json):
                posted.append((url, json))
                return type("R", (), {"status_code": 204})()

        monkeypatch.setattr(automations, "check_notify_url", fake_check)
        monkeypatch.setattr(automations.httpx, "AsyncClient", FakeClient)
        automations.init(database, fake_turn, "m")

        async def scenario():
            await database.users.insert_one({"id": "u", "plan": "max"})  # Thorough mode is a Max feature
            auto = {"id": "a3", "userId": "u", "name": "News", "prompt": "p", "schedule": {"type": "manual"},
                    "thorough": True, "notifyUrl": "https://discord.example/hook"}
            await database.automations.insert_one(dict(auto))
            for _ in range(2):
                await automations.start_run(auto, "manual")
                await asyncio.gather(*list(automations._running))
            return await database.automation_runs.find({}).sort("startedAt", 1).to_list(10)

        runs = run(scenario())
        assert seen[0]["max_steps"] == automations.STEPS_THOROUGH
        assert "Memory:" not in seen[0]["extra_system"]
        assert "Memory:" in seen[1]["extra_system"] and "Result 1" in seen[1]["extra_system"]
        step = runs[0]["steps"][0]
        assert step == {"label": "Web search", "name": "web_search", "status": "done", "summary": "5 results"}
        assert runs[0]["delivery"] == [{"channel": "webhook", "ok": True, "error": None}]
        assert posted[0][0] == "https://discord.example/hook"
        assert "News: finished" in posted[0][1]["content"] and "brief.pdf" in posted[0][1]["content"]

    def test_email_delivery_failure_is_recorded_not_raised(self, monkeypatch):
        database = mongomock_motor.AsyncMongoMockClient()["e"]
        automations.init(database, None, "m")
        monkeypatch.setattr(automations.mailer, "configured", lambda: False)
        out = run(automations._deliver({"name": "x", "userId": "u", "emailResult": True},
                                       {"status": "succeeded", "output": "hi"}))
        assert out[0]["channel"] == "email" and out[0]["ok"] is False and "BREVO_API_KEY" in out[0]["error"]

    @pytest.mark.parametrize("url", ["http://example.com/hook", "https://127.0.0.1/x", "https://10.0.0.5/x",
                                     "https://localhost/x", "notaurl"])
    def test_notify_url_rejects_unsafe(self, url):
        with pytest.raises(ValueError):
            run(automations.check_notify_url(url))

    def test_parse_plan_keeps_valid_values(self):
        plan = automations.parse_plan({"name": "Price watch", "task": "1. Search...",
                                       "schedule": {"type": "weekly", "time": "25:00", "weekday": 9}}, "goal")
        assert plan == {"name": "Price watch", "prompt": "1. Search...",
                        "schedule": {"type": "weekly", "time": "08:00", "weekday": 6, "minutes": 60},
                        "emailResult": False, "sendTo": []}
        once = automations.parse_plan({"name": "Call mum", "task": "Remind me", "deliver": ["whatsapp", "fax", "email"],
                                       "schedule": {"type": "once", "date": "2026-12-01", "time": "17:00"}}, "g")
        assert once["schedule"]["type"] == "once" and once["schedule"]["date"] == "2026-12-01"
        assert once["emailResult"] is True and once["sendTo"] == ["whatsapp"]
        assert automations.parse_plan({"schedule": {"type": "once", "date": "soon"}}, "g")["schedule"]["type"] == "manual"
        assert automations.parse_plan({"schedule": "bad"}, "Watch prices daily")["schedule"]["type"] == "manual"


class TestPlanRulesAndReliability:
    def _db(self, name):
        database = mongomock_motor.AsyncMongoMockClient()[name]
        return database

    def test_plan_rules_refuse_what_the_plan_lacks(self):
        database = self._db("rules")
        automations.init(database, None, "m")
        from fastapi import HTTPException

        async def scenario():
            await database.users.insert_many([{"id": "free"}, {"id": "pro", "plan": "pro"}, {"id": "max", "plan": "max"}])
            out = {}
            cases = [("free", {"type": "interval", "minutes": 60}, None, False),
                     ("free", {"type": "daily", "time": "08:00"}, "krish-pro", False),
                     ("free", {"type": "daily", "time": "08:00"}, None, False),
                     ("pro", {"type": "interval", "minutes": 15}, None, False),
                     ("pro", {"type": "interval", "minutes": 60}, "krish-pro", False),
                     ("pro", {"type": "daily", "time": "08:00"}, None, True),
                     ("max", {"type": "interval", "minutes": 15}, "krish-pro", True)]
            for i, (user, schedule, model, thorough) in enumerate(cases):
                try:
                    await automations.check_plan_rules(user, schedule, model, thorough)
                    out[i] = "ok"
                except HTTPException as exc:
                    assert exc.status_code == 402
                    out[i] = exc.detail
            return out

        out = run(scenario())
        assert "once a day or once a week" in out[0] and "Upgrade to Pro" in out[0]
        assert "premium" in out[1]
        assert out[2] == "ok"
        assert "every hour at most" in out[3]
        assert out[4] == "ok"
        assert "Max plan" in out[5]
        assert out[6] == "ok"

    def test_short_interval_waits_as_long_as_the_plan_allows(self):
        now = utc(2026, 1, 1, 12, 0)
        assert automations.next_run({"type": "interval", "minutes": 15}, now, 60) == utc(2026, 1, 1, 13, 0)
        assert automations.next_run({"type": "interval", "minutes": 15}, now, None) == utc(2026, 1, 2, 12, 0)
        assert automations.next_run({"type": "interval", "minutes": 15}, now, 15) == utc(2026, 1, 1, 12, 15)

    def test_downgrade_pauses_automations_past_the_plan_count(self):
        database = self._db("down")
        started = []

        async def fake_turn(conv_id, model, agent=False, **kw):
            started.append(conv_id)
            yield "data: \"ok\"\n\n"

        automations.init(database, fake_turn, "m")

        async def scenario():
            await database.users.insert_one({"id": "u"})  # back on Basic, which keeps 1 automation
            for i in range(3):
                await database.automations.insert_one({
                    "id": f"a{i}", "userId": "u", "name": "x", "prompt": "p",
                    "schedule": {"type": "daily", "time": "08:00", "timezone": "UTC"}, "enabled": True,
                    "nextRunAt": "2000-01-01T00:00:00+00:00", "lockedUntil": None, "createdAt": f"2026-01-0{i + 1}"})
            await automations.tick()
            await asyncio.gather(*list(automations._running))
            return await database.automations.find({}).sort("createdAt", 1).to_list(10)

        docs = run(scenario())
        assert len(started) == 1
        assert docs[0]["enabled"] is True and not docs[0].get("pausedReason")
        assert all(d["enabled"] is False and "keeps 1 automation" in d["pausedReason"] for d in docs[1:])

    def test_lost_run_is_marked_failed(self):
        database = self._db("lost")
        automations.init(database, None, "m")

        async def scenario():
            await database.automations.insert_one({"id": "a", "userId": "u", "lastStatus": "running"})
            await database.automation_runs.insert_many([
                {"id": "old", "automationId": "a", "status": "running", "startedAt": "2000-01-01T00:00:00+00:00",
                 "heartbeatAt": "2000-01-01T00:00:00+00:00"},
                {"id": "new", "automationId": "a", "status": "running", "startedAt": automations._iso(automations._now()),
                 "heartbeatAt": automations._iso(automations._now())}])
            await automations.recover_lost_runs()
            return {r["id"]: r for r in await database.automation_runs.find({}).to_list(10)}

        runs = run(scenario())
        assert runs["old"]["status"] == "failed" and "restarted" in runs["old"]["error"]
        assert runs["new"]["status"] == "running"

    def test_stop_cancels_a_running_run(self):
        database = self._db("stop")

        async def slow_turn(conv_id, model, agent=False, **kw):
            await database.messages.insert_one({"id": "m", "conversationId": conv_id, "role": "assistant",
                                                "content": "Half done", "createdAt": "z"})
            yield "data: \"Half\"\n\n"
            await asyncio.sleep(30)
            yield "data: \"never\"\n\n"

        automations.init(database, slow_turn, "m")

        async def scenario():
            auto = {"id": "a", "userId": "u", "name": "x", "prompt": "p", "schedule": {"type": "manual"},
                    "enabled": True, "createdAt": "1"}
            await database.automations.insert_one(dict(auto))
            r = await automations.start_run(auto, "manual")
            await asyncio.sleep(0.05)
            await automations.stop_run("a", r["id"], user_id="u")
            await asyncio.gather(*list(automations._running))
            return await database.automation_runs.find_one({"id": r["id"]})

        doc = run(scenario())
        assert doc["status"] == "stopped" and doc["output"] == "Half done" and "delivery" not in doc

    def test_old_runs_are_pruned(self, monkeypatch):
        database = self._db("prune")
        monkeypatch.setattr(automations, "KEEP_RUNS", 3)

        async def fake_turn(conv_id, model, agent=False, **kw):
            yield "data: \"ok\"\n\n"

        automations.init(database, fake_turn, "m")

        async def scenario():
            auto = {"id": "a", "userId": "u", "name": "x", "prompt": "p", "schedule": {"type": "manual"},
                    "enabled": True, "createdAt": "1"}
            await database.automations.insert_one(dict(auto))
            for _ in range(5):
                await automations.start_run(auto, "manual")
                await asyncio.gather(*list(automations._running))
                await asyncio.sleep(0.002)
            return (await database.automation_runs.count_documents({}),
                    await database.conversations.count_documents({}))

        assert run(scenario()) == (3, 3)


class TestOneTimeJobs:
    def test_once_runs_at_its_local_time_then_never_again(self):
        sched = {"type": "once", "date": "2026-12-01", "time": "17:00", "timezone": "Asia/Kolkata"}
        at = utc(2026, 12, 1, 11, 30)
        assert automations.next_run(sched, utc(2026, 11, 30)) == at
        assert automations.next_run(sched, at) is None
        assert "Once, on" in automations.describe_schedule(sched) and "17:00" in automations.describe_schedule(sched)

    def test_once_needs_a_valid_date(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            automations.validate_schedule(automations.Schedule(type="once", time="17:00", date="tomorrow"))
        ok = automations.validate_schedule(automations.Schedule(type="once", time="17:00", date="2026-12-01"))
        assert ok.date == "2026-12-01"

    def test_tick_turns_a_one_time_job_off_after_it_starts(self):
        database = mongomock_motor.AsyncMongoMockClient()["once"]

        async def fake_turn(conv_id, model, agent=False, **kw):
            yield "data: \"ok\"\n\n"

        automations.init(database, fake_turn, "m")

        async def scenario():
            await database.automations.insert_one({
                "id": "a", "userId": "u", "name": "x", "prompt": "p", "enabled": True, "createdAt": "1",
                "schedule": {"type": "once", "date": "2000-01-01", "time": "08:00", "timezone": "UTC"},
                "nextRunAt": "2000-01-01T08:00:00+00:00", "lockedUntil": None})
            await automations.tick()
            await asyncio.gather(*list(automations._running))
            return await database.automations.find_one({"id": "a"}), await database.automation_runs.count_documents({})

        auto, n = run(scenario())
        assert n == 1 and auto["enabled"] is False and auto["nextRunAt"] is None
