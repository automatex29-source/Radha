"""More backend for built apps (appcloud.py): AI, email-the-owner inbox, files, outside APIs, webhooks, Data tab."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")
mongomock_motor = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import appcloud  # noqa: E402
import appdata  # noqa: E402
from auth import create_access_token  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret-that-is-long-enough-for-hs256")
    for key in ("BREVO_API_KEY", "RESEND_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    appcloud._hits.clear()
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    appdata.init(database)
    appcloud.init(database)
    app = FastAPI()
    app.include_router(appdata.router)
    app.include_router(appcloud.router)
    app.include_router(appcloud.owner_router)
    with TestClient(app) as c:
        c.portal.call(database.apps.insert_one, {"id": "app1", "userId": "u1", "name": "Cake Shop"})
        c.portal.call(database.users.insert_one, {"id": "u1", "email": "owner@x.com"})
        c.owner = {"Authorization": f"Bearer {create_access_token('u1', 'owner@x.com')}"}
        c.stranger = {"Authorization": f"Bearer {create_access_token('u2', 'other@x.com')}"}
        yield c


def test_notify_saves_to_owner_inbox_only(client):
    r = client.post("/api/appdata/app1/notify", json={"message": "I want 2 cakes", "replyTo": "a@b.com",
                                                      "fields": {"name": "Ann", "phone": "123"}})
    assert r.json() == {"ok": True, "emailed": False}  # no email provider in tests
    assert client.get("/api/appdata/app1/db/inbox").json() == []  # visitors never see the inbox
    overview = client.get("/api/apps/app1/data", headers=client.owner).json()
    assert overview["collections"] == [{"name": "inbox", "count": 1}]
    assert "key=" in overview["hookUrl"]
    msg = client.get("/api/apps/app1/data/docs/inbox", headers=client.owner).json()[0]["data"]
    assert msg["message"] == "I want 2 cakes" and msg["fields"]["name"] == "Ann"
    assert client.get("/api/apps/app1/data", headers=client.stranger).status_code == 404


def test_notify_emails_owner_when_mail_is_set_up(client, monkeypatch):
    sent = []

    async def fake_send(to, subject, html, text):
        sent.append((to, subject, html))

    monkeypatch.setattr(appcloud.mailer, "configured", lambda: True)
    monkeypatch.setattr(appcloud.mailer, "send", fake_send)
    r = client.post("/api/appdata/app1/notify", json={"subject": "Order", "message": "<b>hi</b>"})
    assert r.json()["emailed"] is True
    to, subject, html = sent[0]
    assert to == "owner@x.com" and subject == "[Cake Shop] Order" and "&lt;b&gt;" in html


def test_notify_is_rate_limited(client):
    codes = [client.post("/api/appdata/app1/notify", json={"message": "x"}).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[-1] == 429


def test_where_filter_and_limit(client):
    for status, n in (("open", 1), ("done", 2), ("open", 3)):
        client.post("/api/appdata/app1/db/tasks", json={"data": {"status": status, "n": n}})
    rows = client.get('/api/appdata/app1/db/tasks?where={"status":"open"}').json()
    assert [r["data"]["n"] for r in rows] == [3, 1]
    assert [r["data"]["n"] for r in client.get("/api/appdata/app1/db/tasks?limit=1&oldest=1").json()] == [1]
    assert client.get('/api/appdata/app1/db/tasks?where={"$where":"1"}').status_code == 400
    assert client.get('/api/appdata/app1/db/tasks?where={"status":{"$ne":1}}').status_code == 400


def test_webhook_needs_the_key(client):
    key = appcloud.hook_key("app1")
    assert client.post("/api/appdata/app1/hook/leads?key=wrong", json={"a": 1}).status_code == 403
    assert client.post(f"/api/appdata/app1/hook/leads?key={key}", json={"email": "z@z.com"}).status_code == 200
    assert client.post(f"/api/appdata/app1/hook/leads?key={key}", data={"name": "Form"}).status_code == 200
    assert client.post(f"/api/appdata/app1/hook/secret?key={key}&private=1", json=[1, 2]).status_code == 200
    rows = client.get("/api/appdata/app1/db/leads").json()
    assert sorted(str(r["data"]) for r in rows) == ["{'email': 'z@z.com'}", "{'name': 'Form'}"]
    assert client.get("/api/appdata/app1/db/secret").json() == []
    assert client.get("/api/apps/app1/data/docs/secret", headers=client.owner).json()[0]["data"] == {"value": [1, 2]}


def test_files_upload_serve_and_rules(client):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = client.post("/api/appdata/app1/files", files={"file": ("cake.png", png, "image/png")}).json()
    assert r["name"] == "cake.png" and r["url"].endswith(f"/api/appdata/app1/files/{r['id']}")
    got = client.get(f"/api/appdata/app1/files/{r['id']}")
    assert got.content == png and got.headers["content-type"] == "image/png"
    # pages and scripts can't be uploaded (they could run as the app); plain text downloads, never renders
    assert client.post("/api/appdata/app1/files", files={"file": ("x.html", b"<script>", "text/html")}).status_code == 415
    assert client.post("/api/appdata/app1/files", files={"file": ("x.svg", b"<svg/>", "image/svg+xml")}).status_code == 415
    txt = client.post("/api/appdata/app1/files", files={"file": ("a.txt", b"hello", "text/plain")}).json()
    assert client.get(f"/api/appdata/app1/files/{txt['id']}").headers["content-disposition"] == "attachment"
    big = b"0" * (appcloud.MAX_FILE_BYTES + 1)
    assert client.post("/api/appdata/app1/files", files={"file": ("b.png", big, "image/png")}).status_code == 413
    assert len(client.get("/api/apps/app1/data/files", headers=client.owner).json()) == 2


@pytest.mark.parametrize("url", ["http://localhost/x", "http://127.0.0.1:8001/api", "http://169.254.169.254/latest",
                                 "http://10.0.0.5/", "http://[::1]/", "file:///etc/passwd", "http://a:b@example.com/",
                                 "http://example.com:22/"])
def test_fetch_refuses_private_addresses(client, url):
    assert client.post("/api/appdata/app1/fetch", json={"url": url}).status_code == 400


def test_ai_answers_with_free_model(client, monkeypatch):
    seen = {}

    async def fake_stream(model, messages, tools):
        seen["model"], seen["messages"] = model, messages
        yield {"type": "text", "text": '{"answer": '}
        yield {"type": "text", "text": "42}"}

    monkeypatch.setattr(appcloud, "ai_model", lambda: "cerebras/gpt-oss-120b")
    monkeypatch.setattr(appcloud.llm, "stream_completion", fake_stream)
    r = client.post("/api/appdata/app1/ai", json={"prompt": "meaning of life?", "json": True,
                                                  "history": [{"role": "user", "content": "hi"}]}).json()
    assert r["data"] == {"answer": 42}
    assert [m["role"] for m in seen["messages"]] == ["system", "user", "user"]
    assert "valid JSON" in seen["messages"][0]["content"]


def test_ai_unavailable_and_never_paid(client, monkeypatch):
    monkeypatch.setattr(appcloud, "ai_model", lambda: None)
    assert client.post("/api/appdata/app1/ai", json={"prompt": "hi"}).status_code == 503
    monkeypatch.undo()
    monkeypatch.delenv("APP_AI_MODEL", raising=False)
    monkeypatch.setattr(appcloud.llm, "configured", lambda m: True)
    assert appcloud.ai_model() in appcloud.FREE_AI_MODELS


def test_owner_can_delete_users_and_docs(client):
    client.post("/api/appdata/app1/auth/signup", json={"email": "a@x.com", "password": "secret1"})
    users = client.get("/api/apps/app1/data/users", headers=client.owner).json()
    assert users[0]["email"] == "a@x.com" and "passwordHash" not in users[0]
    client.delete(f"/api/apps/app1/data/users/{users[0]['id']}", headers=client.owner)
    assert client.get("/api/apps/app1/data", headers=client.owner).json()["users"] == 0


def test_sdk_has_new_helpers():
    sdk = appdata.sdk_script("app1")
    for name in ("ai:ai", "files:files", "notify:notify", "fetch:rfetch", "watch:function"):
        assert name in sdk
