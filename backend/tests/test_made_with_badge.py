"""Published apps show a small "Made with Krish AI" link that the owner can turn off; previews never show it."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
mongomock_motor = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import apps  # noqa: E402

PAGE = "<!doctype html><html><head><title>Cakes</title></head><body><h1>Cakes</h1></body></html>"


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret-that-is-long-enough-for-hs256")
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(apps, "db", database)
    app = FastAPI()
    app.include_router(apps.router)
    app.dependency_overrides[apps.current_user_id] = lambda: "owner1"
    with TestClient(app) as c:
        c.portal.call(database.app_blobs.insert_one, {"hash": "h1", "content": PAGE})
        c.portal.call(database.app_commits.insert_one, {"appId": "app1", "id": "v1", "files": {"index.html": "h1"}})
        c.portal.call(database.apps.insert_one, {"id": "app1", "userId": "owner1", "name": "Cakes",
                                                 "createdAt": "x", "updatedAt": "x",
                                                 "published": {"slug": "cakes-abc", "commitId": "v1"}})
        yield c


def test_badge_on_published_site_and_owner_can_hide_it(env):
    c = env
    page = c.get("/api/sites/cakes-abc/").text
    assert "Made with Krish AI" in page and page.index("krish-made-with") > page.index("<h1>")
    assert "?from=made-with" in page
    r = c.put("/api/apps/app1/badge", json={"show": False})
    assert r.status_code == 200 and r.json()["badge"] is False
    assert "Made with Krish AI" not in c.get("/api/sites/cakes-abc/").text
    assert c.put("/api/apps/app1/badge", json={"show": True}).json()["badge"] is True
    assert "Made with Krish AI" in c.get("/api/sites/cakes-abc/").text


def test_preview_and_other_files_have_no_badge():
    files = {"index.html": PAGE, "app.js": "console.log(1)"}
    assert "Made with Krish AI" not in apps._serve(files, "", bridge=True, cache="no-store").body.decode()
    assert "Made with Krish AI" not in apps._serve(files, "app.js", bridge=False, cache="x", badge=True).body.decode()
