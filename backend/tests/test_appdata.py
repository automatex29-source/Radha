"""App database + accounts for built apps (appdata.py), offline with an in-memory MongoDB."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
mongomock_motor = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import appdata  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret-that-is-long-enough-for-hs256")
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    appdata.init(database)
    app = FastAPI()
    app.include_router(appdata.router)
    with TestClient(app) as c:
        c.portal.call(database.apps.insert_one, {"id": "app1"})
        yield c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_login_and_me(client):
    r = client.post("/api/appdata/app1/auth/signup", json={"email": "A@x.com", "password": "secret1", "name": "Ann"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "a@x.com"
    assert client.post("/api/appdata/app1/auth/signup", json={"email": "a@x.com", "password": "secret1"}).status_code == 409
    assert client.post("/api/appdata/app1/auth/login", json={"email": "a@x.com", "password": "nope"}).status_code == 401
    token = client.post("/api/appdata/app1/auth/login", json={"email": "a@x.com", "password": "secret1"}).json()["token"]
    assert client.get("/api/appdata/app1/auth/me", headers=auth(token)).json()["name"] == "Ann"
    # a token for one app is useless for another
    assert client.get("/api/appdata/other/auth/me", headers=auth(token)).status_code == 401


def test_unknown_app_is_rejected(client):
    assert client.post("/api/appdata/nope/db/posts", json={"data": {"a": 1}}).status_code == 404
    assert client.post("/api/appdata/nope/auth/signup", json={"email": "a@x.com", "password": "secret1"}).status_code == 404


def test_documents_and_ownership(client):
    ann = client.post("/api/appdata/app1/auth/signup", json={"email": "ann@x.com", "password": "secret1"}).json()["token"]
    bob = client.post("/api/appdata/app1/auth/signup", json={"email": "bob@x.com", "password": "secret1"}).json()["token"]
    public = client.post("/api/appdata/app1/db/posts", json={"data": {"title": "hi"}}).json()
    mine = client.post("/api/appdata/app1/db/posts", json={"data": {"title": "ann"}}, headers=auth(ann)).json()
    secret = client.post("/api/appdata/app1/db/posts", json={"data": {"title": "diary"}, "private": True}, headers=auth(ann)).json()

    anon = [d["data"]["title"] for d in client.get("/api/appdata/app1/db/posts").json()]
    assert sorted(anon) == ["ann", "hi"]
    assert len(client.get("/api/appdata/app1/db/posts", headers=auth(ann)).json()) == 3
    assert [d["id"] for d in client.get("/api/appdata/app1/db/posts?mine=1", headers=auth(ann)).json()] == [secret["id"], mine["id"]]
    assert client.get(f"/api/appdata/app1/db/posts/{secret['id']}", headers=auth(bob)).status_code == 404

    # only the owner may change an owned document; anonymous ones are open
    assert client.patch(f"/api/appdata/app1/db/posts/{mine['id']}", json={"data": {"title": "x"}}, headers=auth(bob)).status_code == 403
    r = client.patch(f"/api/appdata/app1/db/posts/{mine['id']}", json={"data": {"likes": 2}}, headers=auth(ann)).json()
    assert r["data"] == {"title": "ann", "likes": 2}
    assert client.delete(f"/api/appdata/app1/db/posts/{public['id']}").status_code == 200
    assert client.delete(f"/api/appdata/app1/db/posts/{mine['id']}").status_code == 403


def test_limits(client):
    assert client.post("/api/appdata/app1/db/bad name!", json={"data": {}}).status_code in (400, 404)
    assert client.post("/api/appdata/app1/db/posts", json={"data": {"x": "a" * 40000}}).status_code == 413
    assert client.post("/api/appdata/app1/db/posts", json={"data": {}, "private": True}).status_code == 401
    assert client.post("/api/appdata/app1/auth/signup", json={"email": "bad", "password": "secret1"}).status_code == 400
