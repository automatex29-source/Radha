"""Phase 2 backend tests for RADHA: Projects, Files (RAG), Memory, Isolation."""
import os
import io
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _hj(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"email": "demo@radha.ai", "password": "demo1234"})
    if r.status_code != 200:
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


@pytest.fixture(scope="module")
def demo_project(demo_token):
    r = requests.post(f"{API}/projects", json={
        "name": "TEST_Project_RAG",
        "description": "Phase 2 test project",
        "instructions": "Always respond concisely."
    }, headers=_hj(demo_token))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    requests.delete(f"{API}/projects/{pid}", headers=_h(demo_token))


# --------------- Projects CRUD
def test_projects_unauth():
    assert requests.get(f"{API}/projects").status_code == 401
    assert requests.post(f"{API}/projects", json={"name": "x"}).status_code == 401


def test_project_create_get_update(demo_token, demo_project):
    pid = demo_project
    # Get
    r = requests.get(f"{API}/projects/{pid}", headers=_h(demo_token))
    assert r.status_code == 200
    body = r.json()
    assert body["project"]["id"] == pid
    assert body["project"]["name"] == "TEST_Project_RAG"
    assert body["project"]["instructions"] == "Always respond concisely."
    assert body["files"] == []
    assert body["memories"] == []

    # List includes it
    r = requests.get(f"{API}/projects", headers=_h(demo_token))
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json())

    # Update instructions persists
    r = requests.patch(f"{API}/projects/{pid}",
                       json={"instructions": "Answer using uploaded files first."},
                       headers=_hj(demo_token))
    assert r.status_code == 200
    assert r.json()["instructions"] == "Answer using uploaded files first."
    # verify persistence
    r = requests.get(f"{API}/projects/{pid}", headers=_h(demo_token))
    assert r.json()["project"]["instructions"] == "Answer using uploaded files first."


# --------------- File upload + RAG processing
@pytest.fixture(scope="module")
def uploaded_file(demo_token, demo_project):
    content = (
        "PROJECT MEMO: The internal codename for the Phase-2 launch is "
        "BLUE FALCON. The launch is scheduled for March 15, 2026. "
        "The project lead is Ananya Rao. Do not share externally.\n"
    ).encode("utf-8")
    files = {"file": ("memo.txt", io.BytesIO(content), "text/plain")}
    r = requests.post(f"{API}/projects/{demo_project}/files", files=files, headers=_h(demo_token), timeout=120)
    assert r.status_code == 200, r.text
    return r.json()


def test_file_upload_ready(uploaded_file):
    assert uploaded_file["status"] == "ready", uploaded_file
    assert uploaded_file["chunkCount"] >= 1
    assert uploaded_file["filename"] == "memo.txt"


def test_project_shows_uploaded_file(demo_token, demo_project, uploaded_file):
    r = requests.get(f"{API}/projects/{demo_project}", headers=_h(demo_token))
    assert r.status_code == 200
    files = r.json()["files"]
    assert any(f["id"] == uploaded_file["id"] and f["status"] == "ready" for f in files)


# --------------- RAG grounded chat
def test_project_chat_grounded_answer(demo_token, demo_project, uploaded_file):
    # Create a conversation attached to the project
    r = requests.post(f"{API}/conversations",
                      json={"projectId": demo_project, "title": "TEST_rag_chat"},
                      headers=_hj(demo_token))
    assert r.status_code == 200
    cid = r.json()["id"]
    try:
        with requests.post(
            f"{API}/conversations/{cid}/stream",
            json={"content": "What is the codename for the Phase-2 launch?"},
            headers=_hj(demo_token),
            stream=True, timeout=120,
        ) as resp:
            assert resp.status_code == 200
            import json as _j
            got_sources = False
            full_text = []
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                if raw.startswith("event: sources"):
                    got_sources = True
                    continue
                if raw.startswith("data:"):
                    payload = raw[5:].strip()
                    try:
                        val = _j.loads(payload)
                    except Exception:
                        continue
                    if isinstance(val, str):
                        full_text.append(val)
            joined = "".join(full_text).upper()
            assert "BLUE FALCON" in joined, f"AI did not ground answer in file. Got: {joined[:400]}"
            assert got_sources, "No sources SSE event emitted"

        # Persisted message should have sources array with filename
        time.sleep(1)
        r = requests.get(f"{API}/conversations/{cid}", headers=_h(demo_token))
        msgs = r.json()["messages"]
        assistant = [m for m in msgs if m["role"] == "assistant"]
        assert assistant, "No assistant message persisted"
        assert assistant[-1].get("sources"), "Sources not persisted on message"
        assert any(s.get("fileName") == "memo.txt" for s in assistant[-1]["sources"])
    finally:
        requests.delete(f"{API}/conversations/{cid}", headers=_h(demo_token))


# --------------- Memory
def test_memory_crud_and_recall(demo_token, demo_project):
    # Add a project-scoped memory
    r = requests.post(f"{API}/memory",
                      json={"content": "The user's favorite color is turquoise-magenta-77.",
                            "projectId": demo_project},
                      headers=_hj(demo_token))
    assert r.status_code == 200
    mid = r.json()["id"]
    try:
        # List
        r = requests.get(f"{API}/memory?projectId={demo_project}", headers=_h(demo_token))
        assert any(m["id"] == mid for m in r.json())

        # Use in project chat
        cr = requests.post(f"{API}/conversations",
                           json={"projectId": demo_project, "title": "TEST_mem_chat"},
                           headers=_hj(demo_token))
        cid = cr.json()["id"]
        try:
            with requests.post(
                f"{API}/conversations/{cid}/stream",
                json={"content": "What is the user's favorite color? Reply with just the color name."},
                headers=_hj(demo_token),
                stream=True, timeout=120,
            ) as resp:
                assert resp.status_code == 200
                text = []
                import json as _j
                for raw in resp.iter_lines(decode_unicode=True):
                    if raw and raw.startswith("data:"):
                        try:
                            v = _j.loads(raw[5:].strip())
                        except Exception:
                            continue
                        if isinstance(v, str):
                            text.append(v)
                    if raw and raw.startswith("event: done"):
                        break
                joined = "".join(text).lower()
                assert "turquoise-magenta-77" in joined, f"Memory not used. Got: {joined[:400]}"
        finally:
            requests.delete(f"{API}/conversations/{cid}", headers=_h(demo_token))
    finally:
        requests.delete(f"{API}/memory/{mid}", headers=_h(demo_token))

    # After delete
    r = requests.get(f"{API}/memory?projectId={demo_project}", headers=_h(demo_token))
    assert not any(m["id"] == mid for m in r.json())


# --------------- Isolation
def test_project_isolation(demo_token, other_token, demo_project, uploaded_file):
    # Other cannot see demo's project
    r = requests.get(f"{API}/projects/{demo_project}", headers=_h(other_token))
    assert r.status_code == 404
    r = requests.patch(f"{API}/projects/{demo_project}", json={"name": "hax"}, headers=_hj(other_token))
    assert r.status_code == 404
    r = requests.delete(f"{API}/projects/{demo_project}", headers=_h(other_token))
    assert r.status_code == 404
    # Other cannot delete demo's file
    r = requests.delete(f"{API}/files/{uploaded_file['id']}", headers=_h(other_token))
    assert r.status_code == 404
    # Unauth
    assert requests.get(f"{API}/projects/{demo_project}").status_code == 401


# --------------- File & Project delete lifecycle (runs last)
def test_zz_file_delete(demo_token, demo_project):
    # Upload a throwaway file then delete it
    files = {"file": ("bye.txt", io.BytesIO(b"disposable content for delete test"), "text/plain")}
    r = requests.post(f"{API}/projects/{demo_project}/files", files=files, headers=_h(demo_token), timeout=120)
    assert r.status_code == 200
    fid = r.json()["id"]
    r = requests.delete(f"{API}/files/{fid}", headers=_h(demo_token))
    assert r.status_code == 200
    # Second delete -> 404
    r = requests.delete(f"{API}/files/{fid}", headers=_h(demo_token))
    assert r.status_code == 404


def test_zz_project_delete_detaches_conversations(demo_token):
    # Create a fresh project + conversation, then delete project
    r = requests.post(f"{API}/projects", json={"name": "TEST_del_proj"}, headers=_hj(demo_token))
    pid = r.json()["id"]
    cr = requests.post(f"{API}/conversations", json={"projectId": pid, "title": "TEST_detach"}, headers=_hj(demo_token))
    cid = cr.json()["id"]
    r = requests.delete(f"{API}/projects/{pid}", headers=_h(demo_token))
    assert r.status_code == 200
    # Conversation should still exist but detached
    r = requests.get(f"{API}/conversations/{cid}", headers=_h(demo_token))
    assert r.status_code == 200
    assert r.json()["conversation"].get("projectId") in (None, "")
    requests.delete(f"{API}/conversations/{cid}", headers=_h(demo_token))
