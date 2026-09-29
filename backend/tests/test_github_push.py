"""Push to GitHub (github_push.py) against a fake GitHub API."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import github_push  # noqa: E402


def fake_github(repo_exists=True, token_ok=True):
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.method, req.url.path, json.loads(req.content or b"null")))
        path, m = req.url.path, req.method
        if not token_ok:
            return httpx.Response(401, json={"message": "Bad credentials"})
        if path == "/user":
            return httpx.Response(200, json={"login": "ann"})
        if path.count("/") == 3 and path.startswith("/repos/") and m == "GET":
            if repo_exists:
                return httpx.Response(200, json={"full_name": "ann/site", "default_branch": "main", "html_url": "https://github.com/ann/site"})
            return httpx.Response(404, json={"message": "Not Found"})
        if path == "/user/repos":
            return httpx.Response(201, json={"full_name": "ann/site", "default_branch": "main", "html_url": "https://github.com/ann/site"})
        if path == "/repos/ann/site/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": "p1"}})
        if path == "/repos/ann/site/git/commits/p1":
            return httpx.Response(200, json={"tree": {"sha": "t0"}})
        if path == "/repos/ann/site/git/trees":
            return httpx.Response(201, json={"sha": "t1"})
        if path == "/repos/ann/site/git/commits":
            return httpx.Response(201, json={"sha": "c1"})
        if path == "/repos/ann/site/git/refs/heads/main":
            return httpx.Response(200, json={})
        return httpx.Response(500, json={"message": f"unexpected {m} {path}"})

    return httpx.MockTransport(handler), calls


def run(coro):
    return asyncio.run(coro)


def test_push_to_existing_repo():
    transport, calls = fake_github()
    res = run(github_push.push({"index.html": "<h1>hi</h1>", "app.js": "1"}, "ghp_token123", "site", "Update", transport=transport))
    assert res == {"url": "https://github.com/ann/site", "repo": "ann/site", "branch": "main", "created": False, "commit": "c1"}
    tree = next(body for m, p, body in calls if p.endswith("/git/trees"))
    assert tree["base_tree"] == "t0" and [e["path"] for e in tree["tree"]] == ["app.js", "index.html"]
    commit = next(body for m, p, body in calls if p.endswith("/git/commits") and m == "POST")
    assert commit == {"message": "Update", "tree": "t1", "parents": ["p1"]}


def test_creates_missing_repo_as_private():
    transport, calls = fake_github(repo_exists=False)
    res = run(github_push.push({"index.html": "x"}, "ghp_token123", "ann/site", "Update", transport=transport))
    assert res["created"] is True
    create = next(body for m, p, body in calls if p == "/user/repos")
    assert create["private"] is True and create["auto_init"] is True


def test_friendly_errors():
    transport, _ = fake_github(token_ok=False)
    with pytest.raises(github_push.PushError, match="rejected the token"):
        run(github_push.push({"a.html": "x"}, "bad_token123", "site", "m", transport=transport))
    with pytest.raises(github_push.PushError, match="repository name"):
        run(github_push.push({"a.html": "x"}, "tok_1234567", "bad repo name", "m"))
    transport, _ = fake_github(repo_exists=False)
    with pytest.raises(github_push.PushError, match="own account"):
        run(github_push.push({"a.html": "x"}, "tok_1234567", "someorg/site", "m", transport=transport))
