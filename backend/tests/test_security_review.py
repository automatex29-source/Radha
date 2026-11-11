"""Holes found in the November security review, each shown closed. MongoDB is mongomock."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
mongomock_motor = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import appdata  # noqa: E402
import apps  # noqa: E402


# ------------------------------------------------------------------ custom domains
@pytest.mark.parametrize("domain", ["krishai.net", "www.krishai.net", "empirex.krishai.net", "KRISHAI.NET",
                                    "radha-x1.onrender.com", "my-site.pages.dev", "app.example.com"])
def test_krish_ais_own_addresses_cant_be_claimed_by_an_app(domain, monkeypatch):
    # Before: an app could claim krishai.net (it wasn't on the list of Krish AI's own addresses), and then
    # everybody opening krishai.net got that app, which could be a fake sign-in page.
    monkeypatch.delenv("SITE_URL", raising=False)
    monkeypatch.setenv("APP_URL", "https://app.example.com")
    assert apps.reserved_domain(apps.clean_domain(domain))


@pytest.mark.parametrize("domain", ["shop.example.org", "mykrishai.net", "krishai.net.example.org"])
def test_a_customers_own_domain_still_works(domain, monkeypatch):
    monkeypatch.delenv("SITE_URL", raising=False)
    assert not apps.reserved_domain(domain)


def test_an_app_already_on_krishai_net_is_not_served(monkeypatch):
    monkeypatch.delenv("SITE_URL", raising=False)

    class Apps:
        async def find_one(self, *a, **k):
            return {"id": "evil", "domain": "krishai.net", "published": {"commitId": "c"}}

    monkeypatch.setattr(apps, "db", type("DB", (), {"apps": Apps()})())
    apps._DOMAIN_CACHE.clear()
    assert asyncio.run(apps.site_for_host("krishai.net")) is None
    assert asyncio.run(apps.site_for_host("www.krishai.net")) is None
    assert asyncio.run(apps.site_for_host("shop.example.org")) is not None


# ------------------------------------------------------------------ App Builder app sign-in
@pytest.fixture()
def app_client(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret-that-is-long-enough-for-hs256")
    monkeypatch.setenv("ABUSE_LIMITS", "on")
    appdata._failures.clear()
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    appdata.init(database)
    app = FastAPI()
    app.include_router(appdata.router)
    with TestClient(app) as c:
        c.portal.call(database.apps.insert_one, {"id": "app1"})
        c.post("/api/appdata/app1/auth/signup", json={"email": "ann@x.com", "password": "secret1"})
        yield c
    appdata._failures.clear()


def _app_login(c, password, email="ann@x.com"):
    return c.post("/api/appdata/app1/auth/login", json={"email": email, "password": password}).status_code


def test_guessing_an_app_users_password_is_stopped(app_client):
    assert [_app_login(app_client, f"guess{i}") for i in range(10)] == [401] * 10
    assert _app_login(app_client, "secret1") == 429  # even the right password waits
    assert _app_login(app_client, "x", email="other@x.com") == 401  # other people aren't locked out


def test_right_app_password_clears_the_count(app_client):
    assert [_app_login(app_client, "wrong") for _ in range(9)] == [401] * 9
    assert _app_login(app_client, "secret1") == 200
    assert _app_login(app_client, "wrong") == 401


def test_one_connection_cant_try_many_app_accounts(app_client):
    codes = [_app_login(app_client, "pw", email=f"user{i}@x.com") for i in range(31)]
    assert codes[:30] == [401] * 30 and codes[30] == 429


def test_one_connection_cant_flood_an_app_with_accounts(app_client):
    codes = [app_client.post("/api/appdata/app1/auth/signup",
                             json={"email": f"bot{i}@x.com", "password": "secret1"}).status_code for i in range(21)]
    assert codes[:19] == [200] * 19 and codes[-1] == 429  # 20 an hour, the fixture's own sign-up included
