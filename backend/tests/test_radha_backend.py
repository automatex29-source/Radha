"""Backend tests for RADHA: auth, conversations CRUD, isolation, streaming."""
import os
import uuid
import time
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # Fallback: read from frontend/.env
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"email": "demo@radha.ai", "password": "demo1234"})
    if r.status_code != 200:
        # Try register
        r = requests.post(f"{API}/auth/register", json={"name": "Demo", "email": "demo@radha.ai", "password": "demo1234"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def other_token():
    r = requests.post(f"{API}/auth/login", json={"email": "other@radha.ai", "password": "other123"})
    if r.status_code != 200:
        r = requests.post(f"{API}/auth/register", json={"name": "Other", "email": "other@radha.ai", "password": "other123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ---------------- Health / root
def test_root():
    r = requests.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("service") == "RADHA"


# ---------------- Auth
def test_login_invalid():
    r = requests.post(f"{API}/auth/login", json={"email": "demo@radha.ai", "password": "wrong"})
    assert r.status_code == 401


def test_register_duplicate(demo_token):
    r = requests.post(f"{API}/auth/register", json={"name": "Demo", "email": "demo@radha.ai", "password": "demo1234"})
    assert r.status_code == 400


def test_register_new_user():
    email = f"test_{uuid.uuid4().hex[:8]}@radha.ai"
    r = requests.post(f"{API}/auth/register", json={"name": "TEST_User", "email": email, "password": "pw123456"})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data and data["user"]["email"] == email


def test_me(demo_token):
    r = requests.get(f"{API}/auth/me", headers=_auth_headers(demo_token))
    assert r.status_code == 200
    assert r.json()["email"] == "demo@radha.ai"


def test_me_unauth():
    r = requests.get(f"{API}/auth/me")
    assert r.status_code == 401


def test_models(demo_token):
    r = requests.get(f"{API}/models", headers=_auth_headers(demo_token))
    assert r.status_code == 200
    d = r.json()
    ids = [m["id"] for m in d["models"]]
    assert "claude-sonnet-4-6" in ids


# ---------------- Conversations CRUD
def test_conversations_unauth():
    r = requests.get(f"{API}/conversations")
    assert r.status_code == 401


def test_conversation_lifecycle(demo_token):
    # Create
    r = requests.post(f"{API}/conversations", json={"title": "TEST_conv"}, headers=_auth_headers(demo_token))
    assert r.status_code == 200
    conv = r.json()
    cid = conv["id"]
    assert conv["title"] == "TEST_conv"

    # List contains it
    r = requests.get(f"{API}/conversations", headers=_auth_headers(demo_token))
    assert r.status_code == 200
    assert any(c["id"] == cid for c in r.json())

    # Get
    r = requests.get(f"{API}/conversations/{cid}", headers=_auth_headers(demo_token))
    assert r.status_code == 200
    assert r.json()["conversation"]["id"] == cid
    assert r.json()["messages"] == []

    # Rename
    r = requests.patch(f"{API}/conversations/{cid}", json={"title": "TEST_renamed"}, headers=_auth_headers(demo_token))
    assert r.status_code == 200
    assert r.json()["title"] == "TEST_renamed"

    # Verify persistence
    r = requests.get(f"{API}/conversations/{cid}", headers=_auth_headers(demo_token))
    assert r.json()["conversation"]["title"] == "TEST_renamed"

    # Delete
    r = requests.delete(f"{API}/conversations/{cid}", headers=_auth_headers(demo_token))
    assert r.status_code == 200

    # Verify gone
    r = requests.get(f"{API}/conversations/{cid}", headers=_auth_headers(demo_token))
    assert r.status_code == 404


# ---------------- Isolation
def test_user_isolation(demo_token, other_token):
    r = requests.post(f"{API}/conversations", json={"title": "TEST_isolated"}, headers=_auth_headers(demo_token))
    cid = r.json()["id"]
    try:
        # Other user cannot access
        r2 = requests.get(f"{API}/conversations/{cid}", headers=_auth_headers(other_token))
        assert r2.status_code == 404
        r2 = requests.patch(f"{API}/conversations/{cid}", json={"title": "hax"}, headers=_auth_headers(other_token))
        assert r2.status_code == 404
        r2 = requests.delete(f"{API}/conversations/{cid}", headers=_auth_headers(other_token))
        assert r2.status_code == 404
        # Unauth
        r3 = requests.get(f"{API}/conversations/{cid}")
        assert r3.status_code == 401
    finally:
        requests.delete(f"{API}/conversations/{cid}", headers=_auth_headers(demo_token))


# ---------------- Streaming
def test_stream_message_persists(demo_token):
    r = requests.post(f"{API}/conversations", json={}, headers=_auth_headers(demo_token))
    cid = r.json()["id"]
    try:
        # Stream a short prompt
        with requests.post(
            f"{API}/conversations/{cid}/stream",
            json={"content": "Say 'hello' in one word."},
            headers=_auth_headers(demo_token),
            stream=True,
            timeout=60,
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            got_data = False
            got_done = False
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                if raw.startswith("data:") and not got_done:
                    got_data = True
                if raw.startswith("event: done"):
                    got_done = True
                if got_done and got_data:
                    break
            assert got_data, "No SSE data received"

        # Verify messages persisted
        time.sleep(1)
        r = requests.get(f"{API}/conversations/{cid}", headers=_auth_headers(demo_token))
        msgs = r.json()["messages"]
        roles = [m["role"] for m in msgs]
        assert "user" in roles
        assert "assistant" in roles, f"assistant not persisted: {roles}"
        # Auto-title should be applied
        assert r.json()["conversation"]["title"] != "New conversation"
    finally:
        requests.delete(f"{API}/conversations/{cid}", headers=_auth_headers(demo_token))
