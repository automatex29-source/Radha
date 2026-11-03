"""The App Builder's coding-assistant upgrades: JSX/TypeScript apps (jsx_compile.py), instant edits without AI,
custom domains, opening a GitHub repository, versions around each AI step, Pro builders and the code review.

Offline: GitHub is a fake transport, the model is a fake, and esbuild tests are skipped when it isn't installed.
"""
import asyncio
import io
import json
import sys
import tarfile
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402
import build_plan  # noqa: E402
import github_push  # noqa: E402
import jsx_compile  # noqa: E402

needs_esbuild = pytest.mark.skipif(not jsx_compile.available(), reason="esbuild is not installed")


# ------------------------------------------------------------------ React / JSX
def test_imports_become_browser_loadable():
    files = {"src/main.jsx": "", "src/App.jsx": "", "src/components/index.tsx": "", "src/index.css": ""}
    code = ('import React, { useState } from "react";\nimport App from "./App";\nimport { Card } from "./components";\n'
            'import "./index.css";\nexport * from "framer-motion";\nconst x = await import("canvas-confetti");\n'
            'import y from "https://esm.sh/htm";')
    out = jsx_compile.rewrite_imports("src/main.jsx", code, files)
    assert 'from "https://esm.sh/react"' in out and 'from "./App.jsx"' in out
    assert 'from "./components/index.tsx"' in out and 'from "https://esm.sh/framer-motion"' in out
    assert 'import("https://esm.sh/canvas-confetti")' in out and '"https://esm.sh/htm"' in out
    assert "index.css" in out and "createElement('link')" in out and 'import "./index.css"' not in out


def test_vite_page_links_become_relative():
    files = {"index.html": "", "src/main.jsx": "", "vite.svg": ""}
    html = '<link rel="icon" href="/vite.svg"><script type="module" src="/src/main.jsx"></script><a href="/about">x</a>'
    out = jsx_compile.relative_html("index.html", html, files)
    assert 'src="./src/main.jsx"' in out and 'href="./vite.svg"' in out and 'href="/about"' in out


def test_which_files_compile():
    assert jsx_compile.needs_compile("a.tsx", "") and jsx_compile.needs_compile("a.jsx", "")
    assert jsx_compile.needs_compile("a.js", 'import React from "react"; const A = () => <div/>;')
    assert not jsx_compile.needs_compile("a.js", "document.body.textContent = 1 < 2;")


@needs_esbuild
def test_jsx_is_compiled_when_served_and_errors_are_reported():
    files = {"index.html": '<div id="root"></div><script type="module" src="/src/main.jsx"></script>',
             "src/main.jsx": 'import { createRoot } from "react-dom/client";\nimport App from "./App";\n'
                             'createRoot(document.getElementById("root")).render(<App />);',
             "src/App.tsx": "export default function App(): JSX.Element { return <h1 className=\"t\">Hi</h1>; }"}
    js = apps._serve(files, "src/main.jsx", bridge=False, cache="no-store").body.decode()
    assert "<App" not in js and '"https://esm.sh/react-dom/client"' in js and '"./App.tsx"' in js
    assert '"https://esm.sh/react/jsx-runtime"' in js
    page = apps._serve(files, "index.html", bridge=False, cache="no-store").body.decode()
    assert 'src="./src/main.jsx"' in page
    broken = {**files, "src/App.tsx": "export default function App() { return <h1>Hi</h1 }"}
    assert "console.error" in apps._serve(broken, "src/App.tsx", bridge=False, cache="no-store").body.decode()
    problems = asyncio.run(apps._syntax_errors(broken))
    assert any("src/App.tsx doesn't compile" in p for p in problems)
    assert asyncio.run(apps._syntax_errors(files)) == []


# ------------------------------------------------------------------ instant edits
def test_text_is_replaced_only_when_written_once():
    files = {"index.html": "<h1>Order now</h1><p>Fresh cakes</p>", "app.js": 'btn.textContent = "Fresh cakes";',
             "samples/a.txt": "Order now"}
    assert apps.replace_text_once(files, "Order now", "Buy today") == ("index.html", "<h1>Buy today</h1><p>Fresh cakes</p>")
    assert apps.replace_text_once(files, "Fresh cakes", "x") is None  # in two places: Krish does it
    assert apps.replace_text_once(files, "Nowhere", "x") is None


def test_styles_go_into_one_block_and_merge():
    html = "<html><head><title>x</title></head><body></body></html>"
    once = apps.add_styles(html, "#hero > a.btn", {"color": "#ff0000"})
    assert '<style id="krish-edits">' in once and once.index("krish-edits") < once.index("</head>")
    twice = apps.add_styles(once, "#hero > a.btn", {"background": "#00ff00"})
    assert twice.count("krish-edits") == 1
    assert "#hero > a.btn { color: #ff0000 !important; background: #00ff00 !important; }" in twice


# ------------------------------------------------------------------ custom domains
def test_domains_are_cleaned_and_own_hosts_skipped(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://krish.example.app")
    assert apps.clean_domain("https://Shop.Example.com/path") == "shop.example.com"
    assert apps._DOMAIN_RE.match("shop.example.com") and not apps._DOMAIN_RE.match("localhost")
    assert "krish.example.app" in apps.own_hosts()
    assert asyncio.run(apps.site_for_host("krish.example.app")) is None


# ------------------------------------------------------------------ GitHub import
def _tarball(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(f"owner-repo-abc123/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_repo_links_are_understood():
    assert github_push.parse_repo("https://github.com/acme/shop") == ("acme", "shop", None)
    assert github_push.parse_repo("github.com/acme/shop.git") == ("acme", "shop", None)
    assert github_push.parse_repo("https://github.com/acme/shop/tree/dev") == ("acme", "shop", "dev")
    assert github_push.parse_repo("acme/shop")[:2] == ("acme", "shop")
    with pytest.raises(github_push.PushError):
        github_push.parse_repo("not a repo")


def test_download_keeps_code_and_skips_dependencies():
    tar = _tarball({"index.html": b"<div id=root></div>", "src/App.jsx": b"export default 1", "package.json": b"{}",
                    "node_modules/react/index.js": b"x", "dist/app.js": b"x", "package-lock.json": b"{}",
                    "logo.png": b"\x89PNG\x00\x00", "README.md": b"# Shop"})

    def handler(request):
        if request.url.path == "/repos/acme/shop":
            return httpx.Response(200, json={"name": "shop", "description": "A shop", "default_branch": "main",
                                             "html_url": "https://github.com/acme/shop"})
        assert request.url.path == "/repos/acme/shop/tarball/main"
        return httpx.Response(200, content=tar)

    repo = asyncio.run(github_push.download("https://github.com/acme/shop", transport=httpx.MockTransport(handler)))
    assert repo["name"] == "shop" and set(repo["files"]) == {"index.html", "src/App.jsx", "package.json", "README.md"}


def test_missing_repo_says_so():
    transport = httpx.MockTransport(lambda r: httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(github_push.PushError, match="can't find"):
        asyncio.run(github_push.download("acme/nope", transport=transport))


# ------------------------------------------------------------------ code review
def test_review_turns_bugs_into_problems(monkeypatch):
    async def ask(model, system, user, max_output):
        assert "=== app.js ===" in user and system == build_plan.REVIEW_PROMPT
        return json.dumps({"bugs": ["app.js: the Delete button removes the wrong item; use the item's id"]})

    monkeypatch.setattr(build_plan, "_ask", ask)
    bugs = asyncio.run(build_plan.review_code("claude-sonnet-5-5", {"index.html": "<p>", "app.js": "x"}))
    assert bugs == ["Code review found a bug: app.js: the Delete button removes the wrong item; use the item's id"]


def test_server_reviews_a_new_build_and_fixes_what_it_finds(monkeypatch):
    from tests.test_app_problems import _fake_agent, _server

    server = _server()
    files = {}
    html = '<html><body><h1 id="t"></h1><script src="app.js"></script></body></html>'
    calls = _fake_agent(monkeypatch, server, files, [
        ({"index.html": html, "app.js": 'document.getElementById("t").textContent = "x";'}, "Built it."),
        ({"app.js": 'document.getElementById("t").textContent = "fixed";'}, "Fixed the bug."),
    ])
    reviews = []

    async def review(model, snapshot):
        reviews.append(dict(snapshot))
        return ["Code review found a bug: app.js shows x"] if len(reviews) == 1 else []

    async def features(ctx, model, items):
        yield {"type": "problems", "problems": []}

    async def plan(ctx, model, request, llm_messages):
        yield {"type": "plan", "items": ["a title"]}

    monkeypatch.setattr(server.build_plan, "review_code", review)
    monkeypatch.setattr(server, "_feature_events", features)
    monkeypatch.setattr(server, "_plan_events", plan)

    async def go():
        ctx = server.ToolContext(None, "u", app_id="a1")
        return [ev async for ev in server._agent_events(None, ctx, "cerebras/gpt-oss-120b", [], True, 8,
                                                        plan_for="make a page")]

    events = asyncio.run(go())
    assert len(reviews) == 1 and len(calls) == 2  # reviewed once, then one repair round
    assert "app.js shows x" in calls[1]["messages"][-1]["content"]
    assert any(e["type"] == "tool_start" and e["name"] == "review_code" for e in events)
