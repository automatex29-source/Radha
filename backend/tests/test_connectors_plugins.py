"""Settings > Connectors and Plugins: linking apps, tool gating, Telegram linking, plugins and the panchang."""
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")

mongomock_motor = pytest.importorskip("mongomock_motor")

import automations  # noqa: E402
import connector_tools  # noqa: E402
import connectors  # noqa: E402
import panchang  # noqa: E402
import plugins  # noqa: E402
from agent.tools import ToolContext, ToolRegistry  # noqa: E402


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(monkeypatch):
    for key in ("GOOGLE_CLIENT_SECRET", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "NOTION_CLIENT_ID",
                "TELEGRAM_BOT_TOKEN", "WHATSAPP_TOKEN", "VIDEO_GENERATION"):
        monkeypatch.delenv(key, raising=False)
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    connectors.init(database, None, "m")
    plugins.init(database)

    async def seed():
        await database.users.insert_one({"id": "u1", "email": "a@b.c", "plan": "basic"})
        await database.users.insert_one({"id": "u2", "email": "p@b.c", "plan": "pro", "planExpiresAt": "2999-01-01T00:00:00+00:00"})
    run(seed())
    return database


def test_secrets_are_encrypted():
    sealed = connectors.seal({"access": "ghp_secret"})
    assert "ghp_secret" not in sealed
    assert connectors.unseal(sealed) == {"access": "ghp_secret"}
    assert connectors.unseal("garbage") == {}


def test_listing_shows_plan_and_readiness(db, monkeypatch):
    items = {c["id"]: c for c in run(connectors.listing("u1"))}
    assert items["github"]["how"] == "token" and items["github"]["ready"] and items["github"]["help"]
    assert items["gmail"]["locked"] and items["whatsapp"]["locked"]
    assert not items["google_drive"]["ready"]  # no Google client secret on the server
    assert not items["telegram"]["ready"]
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "x.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "s")
    items = {c["id"]: c for c in run(connectors.listing("u2"))}
    assert items["google_drive"]["ready"] and items["github"]["how"] == "oauth"
    assert not items["gmail"]["locked"] and items["whatsapp"]["locked"]


def test_webhook_links_are_checked(db, monkeypatch):
    sent = []

    async def fake_post(url, text):
        sent.append((url, text))
    monkeypatch.setattr(connectors, "_post_webhook", fake_post)
    with pytest.raises(connectors.ConnectError):
        run(connectors.connect_with("u1", "slack", "https://evil.example.com/hook"))
    run(connectors.connect_with("u1", "slack", "https://hooks.slack.com/services/T1/B2/abc"))
    assert sent and "connected" in sent[0][1]
    assert run(connectors.active("u1")) == {"slack"}
    run(connectors.send("u1", "slack", "**Report** ready [1]"))
    assert sent[-1][1] == "Report ready"


def test_plan_hides_tools_of_pro_apps(db):
    run(connectors._save("u1", "gmail", {"access": "t"}, "a@b.c"))
    run(connectors._save("u2", "gmail", {"access": "t"}, "p@b.c"))
    assert run(connectors.active("u1")) == set()
    assert run(connectors.active("u2")) == {"gmail"}


def test_tools_only_show_for_connected_apps_and_plugins_on():
    reg = ToolRegistry()
    connector_tools.register_tools(reg)
    plugins.register_tools(reg)
    names = lambda ctx: {t.name for t in reg.active(ctx)}  # noqa: E731
    plain = names(ToolContext(db=None, user_id="u"))
    assert "drive_search" not in plain and "get_weather" in plain and "get_panchang" in plain
    linked = names(ToolContext(db=None, user_id="u", connected=frozenset({"google_drive", "telegram"})))
    assert {"drive_search", "drive_read", "send_to_telegram"} <= linked and "gmail_search" not in linked
    off = names(ToolContext(db=None, user_id="u", plugins_off=frozenset({"weather"})))
    assert "get_weather" not in off


def test_plugins_defaults_and_plan(db):
    state = run(plugins.state("u1"))
    assert state["weather"] and state["panchang"] and not state["auto_search"]
    assert not state["video"]  # making videos is off on this server
    run(db.users.update_one({"id": "u1"}, {"$set": {"plugins.weather": False, "plugins.auto_search": True}}))
    state = run(plugins.state("u1"))
    assert not state["weather"] and state["auto_search"]
    assert "weather" in run(plugins.turned_off("u1"))


def test_telegram_link_by_code(db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:abc")
    said = []

    async def fake_send(chat, text):
        said.append((chat, text))
    monkeypatch.setattr(connectors, "_telegram_send", fake_send)
    run(connectors.on_message("telegram", "555", "@ann", "hello"))
    assert "Settings > Connectors > Telegram" in said[-1][1]
    code = run(connectors._link_code("u1", "telegram"))
    run(connectors.on_message("telegram", "555", "@ann", f"/start {code}"))
    assert said[-1][1].startswith("Connected")
    link = run(db.connections.find_one({"connector": "telegram"}))
    assert link["userId"] == "u1" and link["account"] == "@ann"
    assert connectors.unseal(link["secret"]) == {"chat": "555"}
    run(connectors.on_message("telegram", "556", "@bob", f"/start {code}"))  # a used code can't link another chat
    assert "expired" in said[-1][1]


def test_disconnect_and_delete_user(db):
    run(connectors._save("u1", "notion", {"access": "t"}, "Home"))
    run(connectors.disconnect("u1", "notion"))
    assert run(db.connections.count_documents({})) == 0
    run(connectors._save("u1", "github", {"access": "t"}, "@a"))
    run(connectors.delete_user("u1"))
    assert run(db.connections.count_documents({})) == 0


def test_automation_send_to_keeps_messaging_apps():
    assert automations._clean_send_to(["discord", "gmail", "telegram"]) == ["telegram", "discord"]


def test_plain_text_for_chat_apps():
    assert connectors.plain("## Title\n**Bold** see [docs](https://x.y) [2]") == "Title\nBold see docs (https://x.y)"


@pytest.mark.parametrize("day,name", [
    (date(2026, 11, 8), "Diwali (Lakshmi Puja)"), (date(2026, 3, 4), "Holi"),
    (date(2026, 9, 4), "Krishna Janmashtami"), (date(2026, 8, 28), "Raksha Bandhan"),
    (date(2026, 1, 14), "Makar Sankranti / Pongal"),
])
def test_festivals_2026(day, name):
    assert name in panchang.festivals_on(day, 28.61, 77.21)


def test_panchang_day():
    from zoneinfo import ZoneInfo
    p = panchang.day_panchang(date(2026, 10, 25), 28.61, 77.21, ZoneInfo("Asia/Kolkata"))
    assert p["tithi"] == "Shukla Chaturdashi" and p["month"].startswith("Ashwin")
    assert p["vara"].startswith("Ravivara")
