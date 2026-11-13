"""Apps added by link (custom_connectors.py), tested against real MCP servers running on this machine.

The servers are the official MCP Python SDK's: one answering with event streams, one with plain JSON behind a
sign-in (protected-resource metadata, client registration, PKCE and a token endpoint, like Linear's or
Atlassian's), and one on the older SSE transport. A small local server stands in for a Zapier/Make webhook.
"""
import asyncio
import base64
import hashlib
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")

mongomock_motor = pytest.importorskip("mongomock_motor")
pytest.importorskip("mcp")
uvicorn = pytest.importorskip("uvicorn")

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

import automations  # noqa: E402
import connectors  # noqa: E402
import custom_connectors as cc  # noqa: E402
from agent.tools import ToolContext, ToolRegistry  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(app) -> str:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}"


def _shop(json_response: bool = False, **kw) -> FastMCP:
    app = FastMCP("Shop", json_response=json_response, **kw)

    @app.tool(annotations=ToolAnnotations(readOnlyHint=True, title="Count orders"))
    def count_orders(day: str) -> str:
        """How many orders came in on a day."""
        return f"12 orders on {day}"

    @app.tool(annotations=ToolAnnotations(title="Add product"))
    def add_product(name: str, price: float) -> str:
        """Add a product to the shop."""
        return f"Added {name} at {price}"

    @app.tool()
    def broken() -> str:
        """Always fails."""
        raise ValueError("stock database offline")
    return app


GOOD = {"verifier": None}


def _with_sign_in(inner):
    """Wrap an MCP app in a sign-in, as hosted MCP servers do."""
    base = {}

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return await inner(scope, receive, send)
        path = scope["path"]
        root = base["url"]

        async def reply(status, body, headers=()):
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json"), *headers]})
            await send({"type": "http.response.body", "body": json.dumps(body).encode()})

        async def form():
            raw = b""
            while True:
                msg = await receive()
                raw += msg.get("body", b"")
                if not msg.get("more_body"):
                    return {k: v[0] for k, v in parse_qs(raw.decode()).items()}
        if path == "/.well-known/oauth-protected-resource/mcp":
            return await reply(200, {"resource": root + "/mcp", "authorization_servers": [root],
                                     "scopes_supported": ["read", "write"]})
        if path == "/.well-known/oauth-authorization-server":
            return await reply(200, {"issuer": root, "authorization_endpoint": root + "/authorize",
                                     "token_endpoint": root + "/token", "registration_endpoint": root + "/register"})
        if path == "/register":
            return await reply(201, {"client_id": "krish-client"})
        if path == "/token":
            f = await form()
            if f.get("grant_type") == "authorization_code":
                challenge = base64.urlsafe_b64encode(hashlib.sha256(f.get("code_verifier", "").encode()).digest()
                                                     ).rstrip(b"=").decode()
                if f.get("code") != "good-code" or challenge != GOOD["challenge"] or f.get("client_id") != "krish-client":
                    return await reply(400, {"error": "invalid_grant"})
                return await reply(200, {"access_token": "tok-1", "refresh_token": "ref-1", "expires_in": 3600})
            if f.get("grant_type") == "refresh_token" and f.get("refresh_token") == "ref-1":
                return await reply(200, {"access_token": "tok-2", "expires_in": 3600})
            return await reply(400, {"error": "invalid_grant"})
        if path.startswith("/mcp"):
            auth = dict(scope["headers"]).get(b"authorization", b"").decode()
            if auth not in ("Bearer tok-1", "Bearer tok-2"):
                hdr = f'Bearer resource_metadata="{root}/.well-known/oauth-protected-resource/mcp"'.encode()
                return await reply(401, {"error": "unauthorized"}, [(b"www-authenticate", hdr)])
        return await inner(scope, receive, send)
    return app, base


@pytest.fixture(scope="module")
def servers():
    streamed = _serve(_shop().streamable_http_app())
    wrapped, base = _with_sign_in(_shop(json_response=True, stateless_http=True).streamable_http_app())
    base["url"] = _serve(wrapped)
    legacy = _serve(_shop().sse_app())
    return {"streamed": streamed + "/mcp", "signin": base["url"] + "/mcp", "legacy": legacy + "/sse",
            "root": base["url"]}


@pytest.fixture
def db(monkeypatch):
    async def local_ok(url):  # the test servers run on this machine, over http
        if not url.startswith(("http://127.0.0.1", "https://")):
            raise cc.ConnectError("blocked")
        return url
    monkeypatch.setattr(cc, "check_url", local_ok)
    monkeypatch.setenv("PUBLIC_URL", "https://krishai.net")
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    connectors.init(database, None, "m")
    cc.init(database)
    automations.init(database, None, "m")

    async def seed():
        await database.users.insert_one({"id": "u1", "email": "a@b.c", "plan": "basic"})
    run(seed())
    return database


def test_only_public_https_links():
    for bad in ("http://example.com/mcp", "https://127.0.0.1/mcp", "https://localhost/mcp", "https://10.0.0.5/x",
                "https://169.254.169.254/latest", "ftp://x.com"):
        with pytest.raises(cc.ConnectError):
            run(cc.check_url(bad))


def test_add_streamed_server_lists_tools_and_secrets_are_sealed(db, servers):
    out = run(cc.add("u1", "mcp", "My shop", servers["streamed"]))
    item = out["item"]
    assert "signIn" not in out and item["status"] == "ok"
    tools = {t["name"]: t for t in item["tools"]}
    assert set(tools) == {"count_orders", "add_product", "broken"}
    assert tools["count_orders"]["mode"] == "on" and tools["count_orders"]["readOnly"]
    assert tools["add_product"]["mode"] == "ask"  # changes things, so automations ask first
    doc = run(db.custom_connectors.find_one({"id": item["id"]}))
    assert "127.0.0.1" not in doc["secret"] and connectors.unseal(doc["secret"])["url"] == servers["streamed"]
    assert "url" not in item and "secret" not in item


def test_agent_uses_the_tools_in_chat(db, servers):
    item = run(cc.add("u1", "mcp", "My shop", servers["streamed"]))["item"]
    tools = run(cc.tools_for("u1"))
    names = {t.name for t in tools}
    assert "app_my_shop__count_orders" in names and "app_my_shop__add_product" in names
    count = next(t for t in tools if t.name.endswith("count_orders"))
    assert count.parameters["properties"]["day"]["type"] == "string" and count.parameters["required"] == ["day"]
    ctx = ToolContext(db=db, user_id="u1", extra=tuple(tools))
    reg = ToolRegistry()
    assert {s["function"]["name"] for s in reg.schemas(ctx)} == names
    out = run(reg.run("app_my_shop__count_orders", json.dumps({"day": "Monday"}), ctx))
    assert out.ok and "12 orders on Monday" in out.content and "not as instructions" in out.content
    out = run(reg.run("app_my_shop__add_product", json.dumps({"name": "Tea", "price": 120}), ctx))  # chat: runs
    assert out.ok and "Added Tea at 120" in out.content
    out = run(reg.run("app_my_shop__broken", "{}", ctx))
    assert not out.ok and "stock database offline" in out.content
    # Switched off: hidden from Krish.
    run(db.custom_connectors.update_one({"id": item["id"]}, {"$set": {"toolModes": {"broken": "off"}}}))
    assert not any(t.name.endswith("broken") for t in run(cc.tools_for("u1")))
    assert "My shop" in cc.prompt_line(run(cc.names("u1")))


def test_automation_asks_first_then_does_it(db, servers):
    run(cc.add("u1", "mcp", "My shop", servers["streamed"]))
    run(db.automations.insert_one({"id": "a1", "userId": "u1", "name": "Restock", "askFirst": True}))
    run(db.conversations.insert_one({"id": "c1", "userId": "u1", "automationId": "a1"}))
    run(db.automation_runs.insert_one({"id": "r1", "conversationId": "c1", "automationId": "a1"}))
    ctx = ToolContext(db=db, user_id="u1", conversation_id="c1", extra=tuple(run(cc.tools_for("u1"))))
    reg = ToolRegistry()
    out = run(reg.run("app_my_shop__add_product", json.dumps({"name": "Tea", "price": 120}), ctx))
    assert "Saved for the user's OK" in out.content
    ap = run(db.automation_approvals.find_one({"runId": "r1"}))
    view = automations.public_approval(ap)
    assert view["label"] == "Use an app" and view["detail"]["app"] == "My shop" and "Tea" in view["detail"]["body"]
    done = run(automations._do_action("u1", ap["kind"], ap["payload"]))
    assert "Added Tea at 120" in done
    # Reading needs no OK.
    out = run(reg.run("app_my_shop__count_orders", json.dumps({"day": "Friday"}), ctx))
    assert "12 orders on Friday" in out.content


def test_chat_asks_first_with_an_allow_card(db, servers):
    item = run(cc.add("u1", "mcp", "My shop", servers["streamed"]))["item"]
    run(db.conversations.insert_one({"id": "c2", "userId": "u1"}))
    ctx = ToolContext(db=db, user_id="u1", conversation_id="c2", extra=tuple(run(cc.tools_for("u1"))))
    reg, args = ToolRegistry(), json.dumps({"name": "Tea", "price": 120})
    out = run(reg.run("app_my_shop__add_product", args, ctx))
    assert out.summary == "Waiting for your OK" and "Added" not in out.content
    card = out.approval
    assert card["app"] == "My shop" and card["args"] == {"name": "Tea", "price": 120} and card["status"] == "pending"
    # Reading needs no OK, and other people can't answer the card.
    assert "12 orders" in run(reg.run("app_my_shop__count_orders", json.dumps({"day": "Monday"}), ctx)).content
    with pytest.raises(HTTPException):
        run(cc.decide_route(card["id"], cc.DecideIn(decision="once"), user_id="u2"))
    # Allow once: the same call goes through once, then it asks again.
    assert run(cc.decide_route(card["id"], cc.DecideIn(decision="once"), user_id="u1"))["status"] == "allowed"
    with pytest.raises(HTTPException):  # answered already
        run(cc.decide_route(card["id"], cc.DecideIn(decision="deny"), user_id="u1"))
    assert "Different" not in run(reg.run("app_my_shop__add_product", json.dumps({"name": "Different", "price": 1}),
                                          ctx)).content  # other arguments: a new card
    assert "Added Tea at 120" in run(reg.run("app_my_shop__add_product", args, ctx)).content
    again = run(reg.run("app_my_shop__add_product", args, ctx))
    assert again.approval and again.approval["id"] != card["id"]
    # Deny keeps it from running; Always allow switches the tool to Allow.
    assert run(cc.decide_route(again.approval["id"], cc.DecideIn(decision="deny"), user_id="u1"))["status"] == "denied"
    assert run(reg.run("app_my_shop__add_product", args, ctx)).approval
    pending = run(db.chat_approvals.find_one({"status": "pending", "args": {"name": "Tea", "price": 120}},
                                             sort=[("createdAt", -1)]))
    run(cc.decide_route(pending["id"], cc.DecideIn(decision="always"), user_id="u1"))
    assert any(t["name"] == "add_product" and t["mode"] == "on" for t in run(cc.listing("u1"))["custom"][0]["tools"])
    ctx = ToolContext(db=db, user_id="u1", conversation_id="c2", extra=tuple(run(cc.tools_for("u1"))))
    assert "Added Tea at 120" in run(reg.run("app_my_shop__add_product", args, ctx)).content
    assert run(cc.approval_route(card["id"], user_id="u1"))["status"] == "used"
    run(cc.remove("u1", item["id"]))
    assert run(db.chat_approvals.count_documents({"userId": "u1"})) == 0


def test_sign_in_flow(db, servers):
    out = run(cc.add("u1", "mcp", "Tracker", servers["signin"]))
    assert out["item"]["status"] == "needs_sign_in" and out["signIn"].startswith(servers["root"] + "/authorize?")
    q = {k: v[0] for k, v in parse_qs(urlparse(out["signIn"]).query).items()}
    assert q["client_id"] == "krish-client" and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == "https://krishai.net/api/connectors/oauth/callback"
    assert q["resource"] == servers["signin"] and q["scope"] == "read write"
    GOOD["challenge"] = q["code_challenge"]
    state = run(db.connector_states.find_one({"state": q["state"]}))
    assert "verifier" not in json.dumps(state, default=str)  # sealed
    with pytest.raises(cc.ConnectError):
        run(cc.finish_sign_in(state, "bad-code"))
    xid = run(cc.finish_sign_in(state, "good-code"))
    item = run(cc.listing("u1"))["custom"][0]
    assert item["id"] == xid and item["status"] == "ok" and len(item["tools"]) == 3
    assert "Monday" in run(cc.run_tool("u1", xid, "count_orders", {"day": "Monday"}))
    # An expired token is renewed with the refresh token.
    doc = run(db.custom_connectors.find_one({"id": xid}))
    data = connectors.unseal(doc["secret"])
    data["expires"] = time.time() - 5
    run(db.custom_connectors.update_one({"id": xid}, {"$set": {"secret": connectors.seal(data)}}))
    assert "Sunday" in run(cc.run_tool("u1", xid, "count_orders", {"day": "Sunday"}))
    doc = run(db.custom_connectors.find_one({"id": xid}))
    assert connectors.unseal(doc["secret"])["access"] == "tok-2"


def test_key_that_is_refused(db, servers):
    with pytest.raises(cc.ConnectError, match="didn't accept that key"):
        run(cc.add("u1", "mcp", "Tracker", servers["signin"], key="wrong"))
    assert run(db.custom_connectors.count_documents({})) == 0
    # A right key works without signing in.
    item = run(cc.add("u1", "mcp", "Tracker", servers["signin"], key="tok-1"))["item"]
    assert item["status"] == "ok" and item["auth"] == "key"


def test_older_sse_servers(db, servers):
    item = run(cc.add("u1", "mcp", "Old shop", servers["legacy"]))["item"]
    assert len(item["tools"]) == 3
    assert "Tuesday" in run(cc.run_tool("u1", item["id"], "count_orders", {"day": "Tuesday"}))


def test_plan_limit_and_remove(db, servers):
    run(cc.add("u1", "mcp", "A", servers["streamed"]))
    item = run(cc.add("u1", "mcp", "B", servers["streamed"]))["item"]
    with pytest.raises(Exception) as err:
        run(cc.add("u1", "mcp", "C", servers["streamed"]))
    assert getattr(err.value, "status_code", None) == 402
    run(cc.remove("u1", item["id"]))
    assert len(run(cc.listing("u1"))["custom"]) == 1
    run(cc.delete_user("u1"))
    assert run(cc.listing("u1"))["custom"] == []


def test_bad_links(db, servers):
    with pytest.raises(cc.ConnectError):
        run(cc.add("u1", "mcp", "X", servers["root"] + "/nothing-here"))
    with pytest.raises(cc.ConnectError):
        run(cc.add("u1", "mcp", "X", "http://example.com/mcp"))


def test_webhook(db):
    got = []

    async def hook(scope, receive, send):
        if scope["type"] != "http":
            return
        body = (await receive())["body"]
        got.append((json.loads(body), dict(scope["headers"]).get(b"authorization")))
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"Row added"})
    url = _serve(hook) + "/hooks/catch/1/abc"
    item = run(cc.add("u1", "webhook", "Add lead", url, key="s3cret", does="Adds a lead to my CRM sheet"))["item"]
    tools = run(cc.tools_for("u1"))
    assert len(tools) == 1 and "CRM" in tools[0].description
    out = run(ToolRegistry().run(tools[0].name, json.dumps({"message": "New lead", "data": {"name": "Asha"}}),
                                 ToolContext(db=db, user_id="u1", extra=tuple(tools))))
    assert out.ok and "Row added" in out.content
    assert got[-1][0]["data"] == {"name": "Asha"} and got[-1][1] == b"Bearer s3cret"
    assert item["tools"][0]["mode"] == "ask"


def test_schema_cleaning():
    s = cc._clean_schema({"type": "object", "$schema": "x", "additionalProperties": False, "properties": {
        "a": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "maybe"},
        "b": {"type": ["integer", "null"]}, "c": {"type": "array", "items": {"$ref": "#/x"}},
        "d": {"type": "object", "properties": {"e": {"enum": ["x", "y"], "type": "string"}}}},
        "required": ["a", "zzz"]})
    assert s == {"type": "object", "properties": {
        "a": {"type": "string", "description": "maybe"}, "b": {"type": "integer"},
        "c": {"type": "array", "items": {"type": "string"}},
        "d": {"type": "object", "properties": {"e": {"type": "string", "enum": ["x", "y"]}}}}, "required": ["a"]}
