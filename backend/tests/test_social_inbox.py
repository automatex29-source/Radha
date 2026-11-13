"""Business inbox (social_inbox.py): Krish answers customers on the user's Instagram and WhatsApp Business.

Meta's Graph API is replaced by a recorded stand-in (httpx.MockTransport) that answers like Meta's documented
endpoints, and the model by a scripted function, so these test Krish's side: sign-in, webhooks, replies, drafts,
hand-overs, the 24-hour window, limits and the automation tools. They don't prove Meta accepts the calls.
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")

mongomock_motor = pytest.importorskip("mongomock_motor")

import automations  # noqa: E402
import connectors  # noqa: E402
import social_inbox as si  # noqa: E402
from agent.tools import ToolContext, ToolRegistry  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class Meta:
    """Answers like Meta's Graph API and records every call."""

    def __init__(self):
        self.calls, self.sent, self.fail_send = [], [], False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url, path = str(request.url), request.url.path
        body = request.content.decode() if request.content else ""
        self.calls.append((request.method, url, body))
        if "api.instagram.com/oauth/access_token" in url:
            return httpx.Response(200, json={"data": [{"access_token": "short", "user_id": 1}]})
        if path == "/access_token":
            return httpx.Response(200, json={"access_token": "ig-long", "expires_in": 5184000})
        if path == "/refresh_access_token":
            return httpx.Response(200, json={"access_token": "ig-renewed", "expires_in": 5184000})
        if path.endswith("/me") and request.method == "GET":
            return httpx.Response(200, json={"user_id": "17841400000", "username": "ashas_tea"})
        if path.endswith("/subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        if path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "wa-token"})
        if path.endswith("/register"):
            return httpx.Response(200, json={"success": True})
        if path.endswith("/1098765") and request.method == "GET":
            return httpx.Response(200, json={"display_phone_number": "+91 98765 43210", "verified_name": "Asha Teas"})
        if path.endswith("/messages"):
            if self.fail_send:
                return httpx.Response(400, json={"error": {"message": "outside window"}})
            self.sent.append((url, json.loads(body), request.headers.get("authorization")))
            if "graph.instagram.com" in url:
                return httpx.Response(200, json={"recipient_id": "x", "message_id": f"m_{len(self.sent)}"})
            return httpx.Response(200, json={"messages": [{"id": f"wamid.{len(self.sent)}"}]})
        return httpx.Response(404, json={"error": {"message": "unknown"}})


@pytest.fixture
def env(monkeypatch):
    for k, v in {"INSTAGRAM_APP_ID": "ig-app", "INSTAGRAM_APP_SECRET": "ig-secret", "META_APP_ID": "meta-app",
                 "META_APP_SECRET": "meta-secret", "WHATSAPP_CONFIG_ID": "cfg", "SOCIAL_VERIFY_TOKEN": "verify"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("WHATSAPP_PHONE_ID", raising=False)
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    connectors.init(database, None, "m")
    si.init(database)
    automations.init(database, None, "m")
    meta = Meta()
    monkeypatch.setattr(si, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(meta)))
    replies = []

    async def model(system, messages):
        replies.append((system, messages))
        last = messages[-1]["content"].lower()
        if "refund" in last or "manager" in last:
            return "[HANDOFF] Sorry about that! A team member will reply to you soon."
        if "ignore your rules" in last:
            return "I can help with our teas. What would you like?"
        return "Hi! Our masala chai is ₹180 for 250g. Would you like to order?"
    monkeypatch.setattr(si, "_complete", model)

    async def seed():
        await database.users.insert_one({"id": "u1", "email": "a@b.c", "plan": "pro",
                                         "planExpiresAt": "2999-01-01T00:00:00+00:00"})
        await database.users.insert_one({"id": "u2", "email": "f@b.c", "plan": "basic"})
    run(seed())
    return {"db": database, "meta": meta, "replies": replies}


def _instagram(env):
    acc = run(si.finish_instagram("u1", "code#_", "https://krishai.net/api/social/instagram/callback"))
    return acc


def _whatsapp(env):
    return run(si.finish_whatsapp("u1", "wa-code", "1098765", "5550001"))


def test_instagram_sign_in(env):
    url = si.instagram_auth_url("st", "https://krishai.net/api/social/instagram/callback")
    assert "instagram_business_manage_messages" in url and "client_id=ig-app" in url
    acc = _instagram(env)
    assert acc["externalId"] == "17841400000" and acc["name"] == "@ashas_tea"
    assert "ig-long" not in acc["secret"] and connectors.unseal(acc["secret"])["access"] == "ig-long"
    assert any("subscribed_fields=messages" in c[1] for c in env["meta"].calls)
    assert si.public_account(acc)["mode"] == "draft"  # starts safe: drafts for the user's OK


def test_whatsapp_sign_up(env):
    acc = _whatsapp(env)
    assert acc["name"] == "Asha Teas · +91 98765 43210" and acc["externalId"] == "1098765"
    assert any(c[1].endswith("/5550001/subscribed_apps") for c in env["meta"].calls)


def test_draft_mode_waits_for_ok_then_sends(env):
    acc = _whatsapp(env)
    tid = run(si.receive("whatsapp", "1098765", "919999", "Ravi", "price of masala chai?", "wamid.in1", wait=True))
    assert not env["meta"].sent
    draft = run(env["db"].social_messages.find_one({"threadId": tid, "status": "draft"}))
    assert "₹180" in draft["text"]
    # The model saw only the business's instructions and the chat: no tools, no private memory.
    system, msgs = env["replies"][-1]
    assert "Greet customers" in system and msgs[-1]["role"] == "user" and "Ravi" in msgs[0]["content"]
    run(si.send_reply("u1", tid, draft["text"], by="krish", draft_id=draft["id"]))
    url, body, auth = env["meta"].sent[-1]
    assert url.endswith("/1098765/messages") and body["to"] == "919999" and auth == "Bearer wa-token"
    assert run(env["db"].social_messages.find_one({"id": draft["id"]}))["status"] == "sent"


def test_auto_mode_replies_on_instagram_webhook(env):
    acc = _instagram(env)
    run(env["db"].social_accounts.update_one({"id": acc["id"]}, {"$set": {"settings.mode": "auto",
                                             "settings.instructions": "We sell tea. Masala chai ₹180/250g."}}))
    body = {"object": "instagram", "entry": [{"id": "17841400000", "messaging": [
        {"sender": {"id": "cust1"}, "recipient": {"id": "17841400000"}, "message": {"mid": "mid1", "text": "hi, price?"}}]}]}

    async def go():
        await si.handle(body)
        await si.handle(body)  # Meta repeats events: answered once
        await asyncio.gather(*list(si._tasks))
    run(go())
    assert len(env["meta"].sent) == 1
    url, payload, _ = env["meta"].sent[0]
    assert "graph.instagram.com" in url and payload["recipient"] == {"id": "cust1"}
    assert "We sell tea" in env["replies"][-1][0]


def test_hand_over_and_owner_takes_over(env, monkeypatch):
    acc = _instagram(env)
    run(env["db"].social_accounts.update_one({"id": acc["id"]}, {"$set": {"settings.mode": "auto"}}))
    told = []

    async def fake_notify(a, t):
        told.append(t["id"])
    monkeypatch.setattr(si, "_notify_owner", fake_notify)
    tid = run(si.receive("instagram", "17841400000", "cust2", "", "I want a refund now", "mid2", wait=True))
    thread = run(env["db"].social_threads.find_one({"id": tid}))
    assert thread["handoff"] and told == [tid]
    assert env["meta"].sent[-1][1]["message"]["text"] == "Sorry about that! A team member will reply to you soon."
    sent = len(env["meta"].sent)
    run(si.receive("instagram", "17841400000", "cust2", "", "hello??", "mid3", wait=True))
    assert len(env["meta"].sent) == sent  # Krish stays out of a handed-over chat
    # The owner answers by hand in Instagram (an echo): Krish pauses there.
    run(si.resume(tid, "u1"))
    run(si.owner_replied("17841400000", "cust2", "mid-owner", "Hi, I'm Asha. Sorting it now."))
    run(si.receive("instagram", "17841400000", "cust2", "", "thanks", "mid4", wait=True))
    assert len(env["meta"].sent) == sent


def test_reply_window_and_limits(env):
    acc = _whatsapp(env)
    tid = run(si.receive("whatsapp", "1098765", "91888", "Meena", "hello", "w1", wait=True))
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    run(env["db"].social_threads.update_one({"id": tid}, {"$set": {"lastInboundAt": old}}))
    with pytest.raises(si.SocialError, match="24 hours"):
        run(si.send_reply("u1", tid, "follow up"))
    # Basic plan: no replies, and connecting is locked.
    run(env["db"].social_accounts.update_one({"id": acc["id"]}, {"$set": {"userId": "u2"}}))
    run(env["db"].social_messages.delete_many({}))
    n = len(env["replies"])
    run(si.receive("whatsapp", "1098765", "91777", "Raj", "hi", "w2", wait=True))
    assert len(env["replies"]) == n
    with pytest.raises(Exception) as err:
        run(si._check_plan("u2"))
    assert err.value.status_code == 402


def test_webhook_signature_and_routing(env, monkeypatch):
    raw = json.dumps({"object": "whatsapp_business_account"}).encode()
    good = "sha256=" + hmac.new(b"meta-secret", raw, hashlib.sha256).hexdigest()
    assert si.signature_ok(raw, good) and not si.signature_ok(raw, "sha256=bad")
    # Krish's own WhatsApp number still goes to the Krish bot.
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "42")
    assert not run(si.handle_whatsapp_value({"metadata": {"phone_number_id": "42"}, "messages": []}))
    assert run(si.handle_whatsapp_value({"metadata": {"phone_number_id": "1098765"}, "messages": []}))


def test_automation_tools_ask_first(env):
    _whatsapp(env)
    tid = run(si.receive("whatsapp", "1098765", "91555", "Kiran", "do you deliver to Pune?", "w9", wait=True))
    tools = run(si.tools_for("u1"))
    assert {t.name for t in tools} == {"social_chats", "social_reply"}
    run(env["db"].automations.insert_one({"id": "a1", "userId": "u1", "name": "Follow up", "askFirst": True}))
    run(env["db"].conversations.insert_one({"id": "c1", "userId": "u1", "automationId": "a1"}))
    run(env["db"].automation_runs.insert_one({"id": "r1", "conversationId": "c1", "automationId": "a1"}))
    ctx = ToolContext(db=env["db"], user_id="u1", conversation_id="c1", extra=tuple(tools))
    reg = ToolRegistry()
    out = run(reg.run("social_chats", "{}", ctx))
    assert "Kiran" in out.content and "Pune" in out.content and "can reply" in out.content
    out = run(reg.run("social_reply", json.dumps({"thread_id": tid, "text": "Yes, we deliver to Pune!"}), ctx))
    assert "Saved for the user's OK" in out.content
    ap = run(env["db"].automation_approvals.find_one({"kind": "social_send"}))
    assert automations.public_approval(ap)["detail"]["app"] == "WhatsApp Business"
    sent = len(env["meta"].sent)
    run(automations._do_action("u1", ap["kind"], ap["payload"]))
    assert len(env["meta"].sent) == sent + 1 and env["meta"].sent[-1][1]["text"]["body"] == "Yes, we deliver to Pune!"


def test_disconnect_deletes_chats(env):
    acc = _whatsapp(env)
    run(si.receive("whatsapp", "1098765", "91444", "A", "hi", "w5", wait=True))
    run(si.disconnect("u1", acc["id"]))
    assert run(env["db"].social_messages.count_documents({})) == 0
    assert run(env["db"].social_threads.count_documents({})) == 0
