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
            first = await apps.commit("a", "First", author="RADHA")
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
        assert lines[1:] == ["Second|You", "First|RADHA"]
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
        assert apps._serve(files, "dashboard/settings", False, "x").body == b"<p>home</p>"
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

        async def fake_turn(conv_id, model, agent=False):
            calls.append((conv_id, agent))
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
        assert len(runs) == 1 and runs[0]["status"] == "succeeded" and runs[0]["output"] == "Report ready"
        assert auto["lastStatus"] == "succeeded" and auto["lockedUntil"] is None
        assert auto["nextRunAt"] > datetime.now(timezone.utc).isoformat()

    def test_failed_turn_is_recorded(self):
        database = mongomock_motor.AsyncMongoMockClient()["f"]

        async def failing_turn(conv_id, model, agent=False):
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
