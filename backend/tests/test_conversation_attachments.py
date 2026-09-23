"""Phase 3: Chat attachments (files attached to conversations, no project needed)."""
import os
import io
import time
import uuid
import json
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"

DEMO = {"email": "demo@radha.ai", "password": "demo1234"}
OTHER = {"email": "other@radha.ai", "password": "other123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO)


@pytest.fixture(scope="module")
def other_token():
    try:
        return _login(OTHER)
    except AssertionError:
        # Try register
        r = requests.post(f"{API}/auth/register", json={"name": "Other", **OTHER}, timeout=20)
        if r.status_code == 200:
            return r.json()["token"]
        pytest.skip("Could not obtain other user token")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_create_conversation_and_upload_attachment(demo_token):
    r = requests.post(f"{API}/conversations", json={"title": "TEST_attach_chat"}, headers=_h(demo_token), timeout=20)
    assert r.status_code == 200
    conv_id = r.json()["id"]

    fact = f"TEST_MASCOT_{uuid.uuid4().hex[:8].upper()}"
    content = f"The official mascot of RADHA project is a Golden Otter named {fact}.".encode()
    files = {"file": ("note.txt", io.BytesIO(content), "text/plain")}
    r = requests.post(f"{API}/conversations/{conv_id}/files", files=files, headers=_h(demo_token), timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready", body
    assert body.get("chunkCount", 0) >= 1
    assert body["conversationId"] == conv_id
    file_id = body["id"]

    # List conversation files
    r = requests.get(f"{API}/conversations/{conv_id}/files", headers=_h(demo_token), timeout=20)
    assert r.status_code == 200
    lst = r.json()
    assert any(f["id"] == file_id for f in lst)

    # Stream chat and assert file grounding + sources
    payload = {"content": f"What is the name of the RADHA mascot?"}
    r = requests.post(f"{API}/conversations/{conv_id}/stream", json=payload, headers=_h(demo_token), stream=True, timeout=90)
    assert r.status_code == 200
    got_sources = False
    full_text = ""
    current_event = "message"
    for line in r.iter_lines(decode_unicode=True):
        if line is None:
            continue
        if line == "":
            current_event = "message"
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
            continue
        if line.startswith("data:"):
            data = line[5:].strip()
            try:
                evt = json.loads(data)
            except Exception:
                continue
            if current_event == "sources" and isinstance(evt, list):
                got_sources = True
                assert any(s.get("fileName") == "note.txt" for s in evt)
            elif current_event == "message" and isinstance(evt, str):
                full_text += evt
            elif current_event == "done":
                break
    assert got_sources, "No SSE sources event received"
    assert fact in full_text or "Golden Otter" in full_text, f"Answer not grounded: {full_text[:400]}"

    # cleanup
    requests.delete(f"{API}/files/{file_id}", headers=_h(demo_token), timeout=20)
    requests.delete(f"{API}/conversations/{conv_id}", headers=_h(demo_token), timeout=20)


def test_delete_attachment(demo_token):
    r = requests.post(f"{API}/conversations", json={"title": "TEST_attach_delete"}, headers=_h(demo_token), timeout=20)
    conv_id = r.json()["id"]
    files = {"file": ("del.txt", io.BytesIO(b"hello test delete"), "text/plain")}
    r = requests.post(f"{API}/conversations/{conv_id}/files", files=files, headers=_h(demo_token), timeout=60)
    assert r.status_code == 200
    fid = r.json()["id"]
    r = requests.delete(f"{API}/files/{fid}", headers=_h(demo_token), timeout=20)
    assert r.status_code == 200
    r = requests.get(f"{API}/conversations/{conv_id}/files", headers=_h(demo_token), timeout=20)
    assert all(f["id"] != fid for f in r.json())
    requests.delete(f"{API}/conversations/{conv_id}", headers=_h(demo_token), timeout=20)


def test_isolation_other_cannot_access(demo_token, other_token):
    r = requests.post(f"{API}/conversations", json={"title": "TEST_iso"}, headers=_h(demo_token), timeout=20)
    conv_id = r.json()["id"]
    files = {"file": ("iso.txt", io.BytesIO(b"secret"), "text/plain")}
    r = requests.post(f"{API}/conversations/{conv_id}/files", files=files, headers=_h(demo_token), timeout=60)
    fid = r.json()["id"]

    # other user - 404 on list & upload
    r = requests.get(f"{API}/conversations/{conv_id}/files", headers=_h(other_token), timeout=20)
    assert r.status_code == 404
    r = requests.post(f"{API}/conversations/{conv_id}/files",
                     files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
                     headers=_h(other_token), timeout=20)
    assert r.status_code == 404
    # Delete file as other -> 404
    r = requests.delete(f"{API}/files/{fid}", headers=_h(other_token), timeout=20)
    assert r.status_code == 404

    # cleanup as demo
    requests.delete(f"{API}/files/{fid}", headers=_h(demo_token), timeout=20)
    requests.delete(f"{API}/conversations/{conv_id}", headers=_h(demo_token), timeout=20)


def test_unauth_401(demo_token):
    r = requests.post(f"{API}/conversations", json={"title": "TEST_unauth"}, headers=_h(demo_token), timeout=20)
    conv_id = r.json()["id"]
    r = requests.get(f"{API}/conversations/{conv_id}/files", timeout=20)
    assert r.status_code in (401, 403)
    r = requests.post(f"{API}/conversations/{conv_id}/files",
                     files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")}, timeout=20)
    assert r.status_code in (401, 403)
    requests.delete(f"{API}/conversations/{conv_id}", headers=_h(demo_token), timeout=20)
