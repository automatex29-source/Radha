"""App builder: projects with a virtual file system, version history, live preview,
sandboxed commands, one-click publishing and git export.

Storage (MongoDB):
  apps          one document per app
  app_files     the working copy: {appId, path, content}
  app_blobs     content-addressed file versions: {hash, content}
  app_commits   snapshots: {id, appId, parent, message, author, files: {path: hash}}

Preview and published sites are served from RADHA's API origin, so every response
carries a CSP `sandbox` header: the page runs in an opaque origin and can never
read RADHA's storage or call its API with the user's session.
"""
import difflib
import hashlib
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

from auth import JWT_ALGORITHM, _secret, decode_token, get_user_id_from_request
from agent import Tool, ToolOutput, sandbox
from agent import browser as agent_browser

router = APIRouter(prefix="/api")
db = None  # set by init()

MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 400
MAX_TOTAL_BYTES = 20 * 1024 * 1024
PREVIEW_TOKEN_HOURS = 12
_PATH_RE = re.compile(r"^[A-Za-z0-9_\-. ][A-Za-z0-9_\-./ ]*$")
SANDBOX_CSP = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads"
PREVIEW_ORIGIN = "https://app.radha.local/"

TEMPLATES = {
    "blank": {
        "index.html": """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>My App</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <main class="card">
    <h1>Hello from RADHA</h1>
    <p>Ask the builder to turn this into anything.</p>
    <button id="btn">Clicked 0 times</button>
  </main>
  <script src="app.js"></script>
</body>
</html>
""",
        "style.css": """* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: system-ui, sans-serif;
       background: #0b0d14; color: #e5e7eb; }
.card { padding: 2.5rem; border: 1px solid #262c3e; border-radius: 16px; background: #11141d; text-align: center; }
button { margin-top: 1rem; padding: .7rem 1.2rem; border: 0; border-radius: 10px; background: #6366f1; color: white;
         font-weight: 600; cursor: pointer; }
""",
        "app.js": """let clicks = 0;
document.getElementById("btn").addEventListener("click", (e) => {
  clicks += 1;
  e.target.textContent = `Clicked ${clicks} time${clicks === 1 ? "" : "s"}`;
});
""",
    },
    "react": {
        "index.html": """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>React App</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100">
  <div id="root"></div>
  <script type="module" src="app.js"></script>
</body>
</html>
""",
        "app.js": """import React, { useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);

function App() {
  const [count, setCount] = useState(0);
  return html`
    <main class="min-h-screen grid place-items-center">
      <div class="p-10 rounded-2xl border border-slate-800 bg-slate-900 text-center">
        <h1 class="text-3xl font-bold">React + Tailwind</h1>
        <p class="mt-2 text-slate-400">Built with RADHA</p>
        <button class="mt-6 px-5 py-2 rounded-lg bg-indigo-500 font-semibold" onClick=${() => setCount(count + 1)}>
          Count: ${count}
        </button>
      </div>
    </main>`;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
""",
    },
}

_CONSOLE_BRIDGE = """<script>(function(){function s(l,a){try{parent.postMessage({source:"radha-preview",level:l,message:Array.prototype.map.call(a,function(x){try{return typeof x==="string"?x:(x instanceof Error?x.message:JSON.stringify(x))}catch(e){return String(x)}}).join(" ")},"*")}catch(e){}}["log","info","warn","error"].forEach(function(l){var o=console[l];console[l]=function(){s(l,arguments);return o.apply(console,arguments)}});addEventListener("error",function(e){s("error",[e.message+(e.filename?" ("+e.filename.split("/").pop()+":"+e.lineno+")":"")])});addEventListener("unhandledrejection",function(e){s("error",["Unhandled promise rejection: "+((e.reason&&e.reason.message)||e.reason)])})})();</script>"""


def init(database):
    global db
    db = database


async def ensure_indexes():
    await db.apps.create_index([("userId", 1), ("updatedAt", -1)])
    await db.apps.create_index("published.slug", unique=True, sparse=True)
    await db.app_files.create_index([("appId", 1), ("path", 1)], unique=True)
    await db.app_blobs.create_index("hash", unique=True)
    await db.app_commits.create_index([("appId", 1), ("createdAt", -1)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def current_user_id(request: Request) -> str:
    return get_user_id_from_request(request)


def clean_path(path: str) -> str:
    path = (path or "").strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if (not path or len(path) > 200 or path.startswith("/") or ".." in path.split("/") or "//" in path
            or not _PATH_RE.match(path) or path.split("/")[0] in (".git", ".radha")):
        raise ValueError(f"Invalid file path '{path}'")
    return path


# ------------------------------------------------------------ core operations
async def owned_app(app_id: str, user_id: str) -> dict:
    app = await db.apps.find_one({"id": app_id, "userId": user_id})
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


async def snapshot(app_id: str) -> Dict[str, str]:
    return {f["path"]: f["content"] async for f in db.app_files.find({"appId": app_id})}


async def write_file(app_id: str, path: str, content: str):
    path = clean_path(path)
    size = len(content.encode("utf-8"))
    if size > MAX_FILE_BYTES:
        raise ValueError(f"{path} is too large (max {MAX_FILE_BYTES // 1024} KB)")
    existing = await db.app_files.find_one({"appId": app_id, "path": path}, {"_id": 1})
    if not existing:
        if await db.app_files.count_documents({"appId": app_id}) >= MAX_FILES:
            raise ValueError(f"Too many files (max {MAX_FILES})")
    total = sum([len(f["content"].encode("utf-8")) async for f in db.app_files.find({"appId": app_id, "path": {"$ne": path}})])
    if total + size > MAX_TOTAL_BYTES:
        raise ValueError("App is too large")
    await db.app_files.update_one({"appId": app_id, "path": path},
                                  {"$set": {"content": content, "updatedAt": _now()}}, upsert=True)
    await db.apps.update_one({"id": app_id}, {"$set": {"updatedAt": _now()}})
    return path


async def delete_file(app_id: str, path: str) -> bool:
    res = await db.app_files.delete_one({"appId": app_id, "path": clean_path(path)})
    await db.apps.update_one({"id": app_id}, {"$set": {"updatedAt": _now()}})
    return res.deleted_count > 0


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def head_commit(app_id: str) -> Optional[dict]:
    return await db.app_commits.find_one({"appId": app_id}, sort=[("createdAt", -1), ("seq", -1)])


async def commit_files(commit: dict) -> Dict[str, str]:
    hashes = commit["files"]
    blobs = {b["hash"]: b["content"] async for b in db.app_blobs.find({"hash": {"$in": list(set(hashes.values()))}})}
    return {path: blobs[h] for path, h in hashes.items()}


async def changed_paths(app_id: str) -> Dict[str, str]:
    """{path: added|modified|deleted} between the last commit and the working copy."""
    working = {p: _hash(c) for p, c in (await snapshot(app_id)).items()}
    head = await head_commit(app_id)
    committed = head["files"] if head else {}
    out = {}
    for p in working.keys() | committed.keys():
        if p not in committed:
            out[p] = "added"
        elif p not in working:
            out[p] = "deleted"
        elif working[p] != committed[p]:
            out[p] = "modified"
    return dict(sorted(out.items()))


async def commit(app_id: str, message: str, author: str = "You") -> Optional[dict]:
    files = await snapshot(app_id)
    hashes = {p: _hash(c) for p, c in files.items()}
    head = await head_commit(app_id)
    if head and head["files"] == hashes:
        return None
    for path, content in files.items():
        await db.app_blobs.update_one({"hash": hashes[path]}, {"$setOnInsert": {"content": content}}, upsert=True)
    doc = {
        "id": uuid.uuid4().hex[:12],
        "appId": app_id,
        "parent": head["id"] if head else None,
        "seq": (head.get("seq", 0) + 1) if head else 1,
        "message": (message or "Update").strip()[:500],
        "author": author,
        "files": hashes,
        "createdAt": _now(),
    }
    await db.app_commits.insert_one(doc)
    return public_commit(doc)


def public_commit(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("id", "parent", "message", "author", "createdAt")} | {"fileCount": len(doc["files"])}


def unified_diff(before: Dict[str, str], after: Dict[str, str]) -> List[dict]:
    out = []
    for path in sorted(before.keys() | after.keys()):
        a, b = before.get(path), after.get(path)
        if a == b:
            continue
        status = "added" if a is None else "deleted" if b is None else "modified"
        diff = "".join(difflib.unified_diff((a or "").splitlines(True), (b or "").splitlines(True),
                                            fromfile=f"a/{path}", tofile=f"b/{path}", n=3))
        out.append({"path": path, "status": status, "diff": diff[:60_000]})
    return out


async def restore(app_id: str, commit_id: str, author: str = "You") -> Optional[dict]:
    target = await db.app_commits.find_one({"appId": app_id, "id": commit_id})
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")
    files = await commit_files(target)
    await db.app_files.delete_many({"appId": app_id})
    if files:
        await db.app_files.insert_many([{"appId": app_id, "path": p, "content": c, "updatedAt": _now()} for p, c in files.items()])
    return await commit(app_id, f"Restore version {commit_id}: {target['message']}"[:200], author)


async def export_zip(app: dict, include_git: bool = True) -> bytes:
    working = await snapshot(app["id"])
    workdir = tempfile.mkdtemp(prefix="radha-export-")
    try:
        if include_git:
            commits = await db.app_commits.find({"appId": app["id"]}).sort([("createdAt", 1), ("seq", 1)]).to_list(5000)
            if commits:
                _build_git_repo(workdir, commits, {c["id"]: await commit_files(c) for c in commits})
        for path, content in working.items():
            target = os.path.join(workdir, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)
        buf = io.BytesIO()
        root = re.sub(r"[^\w\-]+", "-", app["name"]).strip("-").lower() or "app"
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _, filenames in os.walk(workdir):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    zf.write(full, os.path.join(root, os.path.relpath(full, workdir)))
        return buf.getvalue()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _build_git_repo(workdir: str, commits: List[dict], contents: Dict[str, Dict[str, str]]):
    """Real git history (one git commit per RADHA version) via dulwich."""
    from dulwich.objects import Blob, Commit, Tree
    from dulwich.repo import Repo

    repo = Repo.init(workdir)
    store = repo.object_store

    def build_tree(files: Dict[str, str]) -> bytes:
        nested: dict = {}
        for path, content in files.items():
            node = nested
            parts = path.split("/")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = content

        def make(node) -> bytes:
            tree = Tree()
            for name, value in node.items():
                if isinstance(value, dict):
                    tree.add(name.encode(), 0o040000, make(value))
                else:
                    blob = Blob.from_string(value.encode("utf-8"))
                    store.add_object(blob)
                    tree.add(name.encode(), 0o100644, blob.id)
            store.add_object(tree)
            return tree.id

        return make(nested)

    parent = None
    for c in commits:
        gc = Commit()
        gc.tree = build_tree(contents[c["id"]])
        gc.parents = [parent] if parent else []
        who = f"{c.get('author') or 'RADHA'} <radha@automatex.ai>".encode()
        gc.author = gc.committer = who
        ts = int(datetime.fromisoformat(c["createdAt"]).timestamp())
        gc.author_time = gc.commit_time = ts
        gc.author_timezone = gc.commit_timezone = 0
        gc.encoding = b"UTF-8"
        gc.message = (c["message"] + "\n").encode("utf-8")
        store.add_object(gc)
        parent = gc.id
    repo.refs[b"refs/heads/main"] = parent
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")
    # Check out the last commit and write the index, so `git status` is clean.
    from dulwich.index import build_index_from_tree

    build_index_from_tree(repo.path, repo.index_path(), store, store[parent].tree)
    repo.close()


def app_prompt_files(files: Dict[str, str]) -> str:
    return "\n".join(f"- {p} ({len(c.encode('utf-8'))} bytes)" for p, c in sorted(files.items())) or "(no files yet)"


async def app_prompt(database, app_id: str) -> str:
    app = await database.apps.find_one({"id": app_id})
    files = await snapshot(app_id)
    changes = await changed_paths(app_id)
    return (
        f"You are RADHA's app builder, working on the app “{app['name']}”"
        + (f" — {app['description']}" if app.get("description") else "") + ".\n"
        "The user sees the live preview, the files and the version history beside this chat.\n\n"
        f"Project files:\n{app_prompt_files(files)}\n"
        + (f"Uncommitted changes: {', '.join(f'{p} ({s})' for p, s in changes.items())}\n" if changes else "")
        + "\nHow to work:\n"
        "- The app is a static web app served from index.html. Use HTML/CSS/JS; load libraries from CDNs "
        "(esm.sh, unpkg, cdn.jsdelivr.net, cdn.tailwindcss.com). There is no npm install or build step.\n"
        "- Read files before editing them. Prefer edit_file for small changes and write_file for new or rewritten files.\n"
        "- After changing the UI, call check_preview to see a screenshot and any console errors, and fix them.\n"
        "- Put logic worth testing in plain modules and add tests (e.g. tests/*.test.mjs run with `node --test`, "
        "or Python unittest) and run them with run_command.\n"
        "- When a change works, call commit with a short message describing it.\n"
        "- Keep your chat replies short: say what you built or changed."
    )


def preview_token(app_id: str, user_id: str) -> str:
    payload = {"sub": app_id, "uid": user_id, "type": "preview",
               "exp": datetime.now(timezone.utc) + timedelta(hours=PREVIEW_TOKEN_HOURS)}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def _decode_preview(token: str) -> dict:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Preview link expired — reopen the preview")
    if payload.get("type") != "preview":
        raise HTTPException(status_code=401, detail="Invalid preview token")
    return payload


def _serve(files: Dict[str, str], path: str, bridge: bool, cache: str) -> Response:
    path = unquote(path or "").lstrip("/")
    if not path or path.endswith("/"):
        path += "index.html"
    content = files.get(path)
    if content is None and "." not in path.rsplit("/", 1)[-1]:
        content, path = files.get("index.html"), "index.html"  # single-page-app fallback
    headers = {"Content-Security-Policy": SANDBOX_CSP, "X-Content-Type-Options": "nosniff", "Cache-Control": cache,
               "Referrer-Policy": "no-referrer"}
    if content is None:
        return Response("Not found", status_code=404, media_type="text/plain", headers=headers)
    ctype = mimetypes.guess_type(path)[0] or "text/plain"
    if path.endswith((".js", ".mjs")):
        ctype = "text/javascript"
    if bridge and ctype == "text/html":
        lower = content.lower()
        idx = lower.find("<head>")
        content = content[:idx + 6] + _CONSOLE_BRIDGE + content[idx + 6:] if idx >= 0 else _CONSOLE_BRIDGE + content
    return Response(content, media_type=f"{ctype}; charset=utf-8" if ctype.startswith("text/") else ctype, headers=headers)


async def check_preview(files: Dict[str, str], path: str = "index.html") -> dict:
    """Load the working copy in headless Chromium; return console output, errors and a screenshot."""
    browser = await agent_browser.manager._ensure_browser()
    context = await browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=False)
    allowed: dict = {}
    logs: List[str] = []

    async def handler(route):
        url = route.request.url
        if url.startswith(PREVIEW_ORIGIN):
            rel = unquote(urlparse(url).path.lstrip("/"))
            resp = _serve(files, rel, bridge=False, cache="no-store")
            await route.fulfill(status=resp.status_code, body=resp.body,
                                headers={"Content-Type": resp.media_type or "text/plain"})
        else:
            await agent_browser.manager._guard(route, allowed)

    try:
        await context.route("**/*", handler)
        page = await context.new_page()
        page.on("console", lambda m: logs.append(f"[console.{m.type}] {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"[uncaught error] {e}"))
        page.on("requestfailed", lambda r: logs.append(f"[request failed] {r.url} ({r.failure})"))
        page.on("response", lambda r: logs.append(f"[http {r.status}] {r.url}") if r.status >= 400 else None)
        await page.goto(PREVIEW_ORIGIN + clean_path(path), wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(800)
        text = await page.evaluate("document.body ? document.body.innerText : ''")
        shot = await page.screenshot(type="jpeg", quality=65)
        return {"title": await page.title(), "text": text[:3000], "logs": logs[:60], "screenshot": shot}
    finally:
        await context.close()


# ------------------------------------------------------------- agent tools
def _tool_output(content: str, summary: str, ok: bool = True, media=None) -> ToolOutput:
    return ToolOutput(content=content, summary=summary[:160], ok=ok, media=media or [])


async def _t_list(ctx, args):
    files = await snapshot(ctx.app_id)
    return _tool_output(app_prompt_files(files), f"{len(files)} files")


async def _t_read(ctx, args):
    path = clean_path(args.get("path", ""))
    doc = await db.app_files.find_one({"appId": ctx.app_id, "path": path})
    if not doc:
        return _tool_output(f"{path} does not exist.", f"{path} not found", ok=False)
    numbered = "\n".join(f"{i + 1:4d}  {line}" for i, line in enumerate(doc["content"].split("\n")))
    return _tool_output(numbered, f"Read {path}")


async def _t_write(ctx, args):
    content = args.get("content")
    if not isinstance(content, str):
        raise ValueError("'content' is required")
    path = await write_file(ctx.app_id, args.get("path", ""), content)
    return _tool_output(f"Wrote {path} ({len(content)} chars).", f"Wrote {path}")


async def _t_edit(ctx, args):
    path = clean_path(args.get("path", ""))
    doc = await db.app_files.find_one({"appId": ctx.app_id, "path": path})
    if not doc:
        return _tool_output(f"{path} does not exist.", f"{path} not found", ok=False)
    old, new = args.get("old_text"), args.get("new_text", "")
    if not old:
        raise ValueError("'old_text' is required")
    count = doc["content"].count(old)
    if count != 1:
        return _tool_output(f"old_text must match exactly once in {path}; it matched {count} times. "
                            "Read the file and include more surrounding context.", f"Edit failed ({count} matches)", ok=False)
    await write_file(ctx.app_id, path, doc["content"].replace(old, new, 1))
    return _tool_output(f"Edited {path}.", f"Edited {path}")


async def _t_delete(ctx, args):
    path = clean_path(args.get("path", ""))
    ok = await delete_file(ctx.app_id, path)
    return _tool_output(f"Deleted {path}." if ok else f"{path} did not exist.", f"Deleted {path}", ok=ok)


async def _t_run(ctx, args):
    command = (args.get("command") or "").strip()
    if not command:
        raise ValueError("'command' is required")
    res = await sandbox.run_shell(command, await snapshot(ctx.app_id))
    body = format_run(res)
    ok = res.exit_code == 0 and not res.timed_out
    return _tool_output(body, f"`{command[:60]}` → " + ("ok" if ok else "timed out" if res.timed_out else f"exit {res.exit_code}"), ok=ok)


def format_run(res) -> str:
    parts = []
    if res.stdout:
        parts.append(f"stdout:\n{res.stdout}")
    if res.stderr:
        parts.append(f"stderr:\n{res.stderr}")
    parts.append("Timed out and was killed." if res.timed_out else f"exit code: {res.exit_code}")
    return "\n\n".join(parts)


async def _t_check(ctx, args):
    import media

    result = await check_preview(await snapshot(ctx.app_id), args.get("path") or "index.html")
    shot = await media.save_media(ctx.db, ctx.user_id, result["screenshot"], "image/jpeg", "screenshot",
                                  name="preview.jpg", conversation_id=ctx.conversation_id)
    errors = [l for l in result["logs"] if l.startswith(("[console.error]", "[uncaught", "[request failed]", "[http"))]
    body = (f"Title: {result['title']}\n\nConsole and network ({len(result['logs'])} entries):\n"
            + ("\n".join(result["logs"]) or "(none)") + f"\n\nVisible text:\n{result['text']}")
    summary = f"{len(errors)} error(s)" if errors else "No errors"
    return _tool_output(body, summary, ok=not errors, media=[shot])


async def _t_commit(ctx, args):
    result = await commit(ctx.app_id, args.get("message") or "Update", author="RADHA")
    if not result:
        return _tool_output("Nothing to commit — no changes since the last version.", "No changes")
    return _tool_output(f"Committed version {result['id']}: {result['message']}", f"Saved version {result['id']}")


def register_tools(registry):
    path_param = {"type": "string", "description": "File path relative to the app root, e.g. index.html or src/app.js"}
    specs = [
        ("list_files", "List files", "List the app's files with sizes.", {}, [], _t_list),
        ("read_file", "Read file", "Read a file from the app (with line numbers).", {"path": path_param}, ["path"], _t_read),
        ("write_file", "Write file", "Create or overwrite a file in the app with the full new content.",
         {"path": path_param, "content": {"type": "string"}}, ["path", "content"], _t_write),
        ("edit_file", "Edit file", "Replace one exact, unique snippet of text in a file.",
         {"path": path_param, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
         ["path", "old_text", "new_text"], _t_edit),
        ("delete_file", "Delete file", "Delete a file from the app.", {"path": path_param}, ["path"], _t_delete),
        ("run_command", "Terminal", "Run a shell command (sh) in a sandboxed copy of the app files: e.g. `node --test`, "
         "`python3 -m unittest`, `node script.js`. No network. File changes made by the command are not saved.",
         {"command": {"type": "string"}}, ["command"], _t_run),
        ("check_preview", "Check preview", "Open the app in a real browser: returns a screenshot, console logs, "
         "errors and failed requests. Use after UI changes.", {"path": {"type": "string", "description": "Page to open (default index.html)"}},
         [], _t_check),
        ("commit", "Save version", "Save the current files as a new version in the app's history (git commit).",
         {"message": {"type": "string"}}, ["message"], _t_commit),
    ]
    for name, label, desc, props, required, handler in specs:
        registry.register(Tool(name=name, label=label, description=desc,
                               parameters={"type": "object", "properties": props, "required": required},
                               handler=handler, scope="app",
                               available=(agent_browser.available if name == "check_preview" else (lambda: True))))


# ---------------------------------------------------------------- HTTP API
class AppIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    template: str = "blank"


class AppPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)


class FileIn(BaseModel):
    content: str


class CommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=2000)


class CommitIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


def public_app(doc: dict) -> dict:
    pub = doc.get("published")
    return {
        "id": doc["id"], "name": doc["name"], "description": doc.get("description"),
        "conversationId": doc.get("conversationId"), "createdAt": doc["createdAt"], "updatedAt": doc["updatedAt"],
        "published": {"slug": pub["slug"], "url": f"/api/sites/{pub['slug']}/", "commitId": pub.get("commitId"),
                      "publishedAt": pub.get("publishedAt")} if pub else None,
    }


@router.get("/apps")
async def list_apps(user_id: str = Depends(current_user_id)):
    docs = await db.apps.find({"userId": user_id}).sort("updatedAt", -1).to_list(500)
    return [public_app(d) for d in docs]


@router.post("/apps")
async def create_app(body: AppIn, user_id: str = Depends(current_user_id)):
    ts = _now()
    app_id = str(uuid.uuid4())
    conv = {"id": str(uuid.uuid4()), "userId": user_id, "title": f"App: {body.name.strip()}", "model": None,
            "projectId": None, "appId": app_id, "createdAt": ts, "updatedAt": ts}
    doc = {"id": app_id, "userId": user_id, "name": body.name.strip(), "description": (body.description or "").strip() or None,
           "conversationId": conv["id"], "published": None, "createdAt": ts, "updatedAt": ts}
    await db.conversations.insert_one(conv)
    await db.apps.insert_one(doc)
    for path, content in TEMPLATES.get(body.template, TEMPLATES["blank"]).items():
        await write_file(app_id, path, content)
    await commit(app_id, f"Create app from {body.template if body.template in TEMPLATES else 'blank'} template", author="RADHA")
    return public_app(doc)


@router.get("/apps/{app_id}")
async def get_app(app_id: str, user_id: str = Depends(current_user_id)):
    app = await owned_app(app_id, user_id)
    files = await db.app_files.find({"appId": app_id}, {"content": 0}).sort("path", 1).to_list(MAX_FILES)
    sizes = {f["path"]: len(f["content"].encode("utf-8")) async for f in db.app_files.find({"appId": app_id})}
    return {"app": public_app(app), "files": [{"path": f["path"], "size": sizes.get(f["path"], 0)} for f in files],
            "changes": await changed_paths(app_id)}


@router.patch("/apps/{app_id}")
async def update_app(app_id: str, body: AppPatch, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    updates = {k: (v.strip() or None) for k, v in body.model_dump(exclude_none=True).items()}
    if updates:
        updates["updatedAt"] = _now()
        await db.apps.update_one({"id": app_id}, {"$set": updates})
    return public_app(await db.apps.find_one({"id": app_id}))


@router.delete("/apps/{app_id}")
async def delete_app(app_id: str, user_id: str = Depends(current_user_id)):
    app = await owned_app(app_id, user_id)
    await db.app_files.delete_many({"appId": app_id})
    await db.app_commits.delete_many({"appId": app_id})
    if app.get("conversationId"):
        await db.messages.delete_many({"conversationId": app["conversationId"]})
        await db.conversations.delete_one({"id": app["conversationId"]})
    await db.apps.delete_one({"id": app_id})
    return {"ok": True}


@router.get("/apps/{app_id}/files/{path:path}")
async def read_app_file(app_id: str, path: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    doc = await db.app_files.find_one({"appId": app_id, "path": path})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    return {"path": doc["path"], "content": doc["content"]}


@router.put("/apps/{app_id}/files/{path:path}")
async def save_app_file(app_id: str, path: str, body: FileIn, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    try:
        saved = await write_file(app_id, path, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"path": saved, "changes": await changed_paths(app_id)}


@router.delete("/apps/{app_id}/files/{path:path}")
async def remove_app_file(app_id: str, path: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    try:
        if not await delete_file(app_id, path):
            raise HTTPException(status_code=404, detail="File not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "changes": await changed_paths(app_id)}


@router.post("/apps/{app_id}/run")
async def run_app_command(app_id: str, body: CommandIn, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    started = time.monotonic()
    res = await sandbox.run_shell(body.command, await snapshot(app_id))
    return {"stdout": res.stdout, "stderr": res.stderr, "exitCode": res.exit_code, "timedOut": res.timed_out,
            "networkIsolated": res.network_isolated, "seconds": round(time.monotonic() - started, 2)}


@router.get("/apps/{app_id}/commits")
async def list_commits(app_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    docs = await db.app_commits.find({"appId": app_id}).sort([("createdAt", -1), ("seq", -1)]).to_list(500)
    return [public_commit(d) for d in docs]


@router.post("/apps/{app_id}/commits")
async def create_commit(app_id: str, body: CommitIn, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    result = await commit(app_id, body.message, author="You")
    if not result:
        raise HTTPException(status_code=400, detail="No changes to save")
    return result


@router.get("/apps/{app_id}/commits/{commit_id}/diff")
async def commit_diff(app_id: str, commit_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    if commit_id == "working":
        head = await head_commit(app_id)
        return unified_diff(await commit_files(head) if head else {}, await snapshot(app_id))
    target = await db.app_commits.find_one({"appId": app_id, "id": commit_id})
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")
    parent = await db.app_commits.find_one({"appId": app_id, "id": target["parent"]}) if target.get("parent") else None
    return unified_diff(await commit_files(parent) if parent else {}, await commit_files(target))


@router.post("/apps/{app_id}/commits/{commit_id}/restore")
async def restore_commit(app_id: str, commit_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    return {"commit": await restore(app_id, commit_id), "changes": await changed_paths(app_id)}


@router.get("/apps/{app_id}/export")
async def export_app(app_id: str, request: Request, git: bool = Query(True), auth: Optional[str] = Query(None)):
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    app = await owned_app(app_id, decode_token(token)["sub"])
    data = await export_zip(app, include_git=git)
    name = re.sub(r"[^\w\-]+", "-", app["name"]).strip("-").lower() or "app"
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})


@router.get("/apps/{app_id}/preview-token")
async def get_preview_token(app_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    token = preview_token(app_id, user_id)
    return {"token": token, "url": f"/api/app-preview/{token}/"}


@router.post("/apps/{app_id}/publish")
async def publish_app(app_id: str, user_id: str = Depends(current_user_id)):
    app = await owned_app(app_id, user_id)
    head = await commit(app_id, "Publish", author="You") or public_commit(await head_commit(app_id))
    slug = (app.get("published") or {}).get("slug") or (
        (re.sub(r"[^a-z0-9]+", "-", app["name"].lower()).strip("-")[:30] or "app") + "-" + secrets.token_hex(3))
    await db.apps.update_one({"id": app_id}, {"$set": {"published": {
        "slug": slug, "commitId": head["id"], "publishedAt": _now()}, "updatedAt": _now()}})
    return public_app(await db.apps.find_one({"id": app_id}))


@router.delete("/apps/{app_id}/publish")
async def unpublish_app(app_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    await db.apps.update_one({"id": app_id}, {"$set": {"published": None, "updatedAt": _now()}})
    return public_app(await db.apps.find_one({"id": app_id}))


@router.get("/app-preview/{token}")
async def preview_root(token: str):
    return RedirectResponse(f"/api/app-preview/{token}/")


@router.get("/sites/{slug}")
async def site_root(slug: str):
    return RedirectResponse(f"/api/sites/{slug}/")


@router.get("/app-preview/{token}/{path:path}")
async def serve_preview(token: str, path: str = ""):
    payload = _decode_preview(token)
    app = await db.apps.find_one({"id": payload["sub"], "userId": payload["uid"]})
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return _serve(await snapshot(app["id"]), path, bridge=True, cache="no-store")


@router.get("/sites/{slug}/{path:path}")
async def serve_site(slug: str, path: str = ""):
    app = await db.apps.find_one({"published.slug": slug})
    if not app or not app.get("published"):
        return Response("This site is not published.", status_code=404, media_type="text/plain")
    version = await db.app_commits.find_one({"appId": app["id"], "id": app["published"]["commitId"]})
    return _serve(await commit_files(version), path, bridge=False, cache="public, max-age=60")
