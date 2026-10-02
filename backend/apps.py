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
import asyncio
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
from pathlib import Path
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
import appdata
import github_push

router = APIRouter(prefix="/api")
db = None  # set by init()

MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 400
READ_CHARS = 12_000  # per read_file call, so a big file can't flood a small model's context
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
    <h1>Hello from Krish AI</h1>
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
        <p class="mt-2 text-slate-400">Built with Krish AI</p>
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

def _load_templates():
    """Ready-made starter apps in app_templates/<id>/ (to-do, dashboard, landing page, shop, game)."""
    root = os.path.join(os.path.dirname(__file__), "app_templates")
    if not os.path.isdir(root):
        return
    for tid in sorted(os.listdir(root)):
        folder = os.path.join(root, tid)
        if os.path.isdir(folder):
            TEMPLATES[tid] = {}
            for name in sorted(os.listdir(folder)):
                with open(os.path.join(folder, name), encoding="utf-8") as fh:
                    TEMPLATES[tid][name] = fh.read()


_load_templates()

# Shared by plain chat and the app builder so every generated app meets the same bar.
DESIGN_GUIDE = (
    "Quality bar for new apps you design yourself (work like a senior product designer and engineer):\n"
    "- Style it with Krish UI, the built-in design kit: put <link rel=\"stylesheet\" href=\"krish-ui.css\"> in the "
    "head (Krish AI adds that file itself: never write or edit it) and set the brand colours once with "
    "<style>:root{--accent:#db2777;--accent-2:#f97316}</style>. It makes plain HTML look premium, so write little CSS. "
    "Its classes: nav (sticky header) > container with brand, nav-links and a btn; hero (eyebrow, h1, p, actions; "
    "grid-2 to put a photo beside the text; hero-dark or hero-image for colour); section > container with section-title "
    "(eyebrow, h2, p); section-alt for a tinted band; grid-2, grid-3, grid-4; card (an img first in it becomes its "
    "cover photo; h3, p, row with price and a button; badge, stars, icon); btn, btn-outline, btn-light, btn-sm, btn-lg "
    "(a plain <button> is already styled); cta (gradient call-to-action box); footer; form, chip, toast (add class "
    "show), gradient-text, lead, muted, center, fade-up. Add Tailwind (<script src=\"https://cdn.tailwindcss.com\">"
    "</script>) classes only for extra tweaks, and Lucide icons if wanted (<script src=\"https://unpkg.com/lucide@latest\">"
    "</script>, <i data-lucide=\"cake\"></i>, then lucide.createIcons()).\n"
    "- Use real photos, never empty boxes: https://loremflickr.com/800/600/cake,chocolate?lock=1 (one or two English "
    "keywords for what the picture shows, a different lock number for each picture).\n"
    "- Make it look like a modern, premium product: a clear hierarchy with a proper header, generous spacing, one "
    "accent color over a cohesive palette, soft gradients, rounded-2xl cards with subtle borders and shadows, "
    "hover, focus and active states, smooth transitions, friendly empty states and toasts instead of alert().\n"
    "- Responsive from phone to desktop, with labelled inputs and good contrast.\n"
    "- Every feature works for real: all buttons do something, input is validated, data persists in localStorage "
    "when that helps, and sample content is realistic (no lorem ipsum, no TODOs, no placeholders). Add the extra "
    "features a user would expect (e.g. for a to-do app: edit, complete, delete, filter, counts, clear completed).\n"
    "- Need a library? Any npm package loads from https://esm.sh/<name> inside a <script type=\"module\">.\n"
    "- Before you finish, check your own code: every id and function used in JS exists in the HTML/JS, scripts run "
    "after the elements they use (put them at the end of body), and nothing throws in the console."
)

# Sandboxed pages have an opaque origin, where touching localStorage throws; give them an in-memory one.
_STORAGE_SHIM = """<script>(function(){try{window.localStorage.getItem("x")}catch(e){function S(){var m={};return{getItem:function(k){return Object.prototype.hasOwnProperty.call(m,k)?m[k]:null},setItem:function(k,v){m[k]=String(v)},removeItem:function(k){delete m[k]},clear:function(){m={}},key:function(i){return Object.keys(m)[i]||null},get length(){return Object.keys(m).length}}}try{Object.defineProperty(window,"localStorage",{value:S(),configurable:true});Object.defineProperty(window,"sessionStorage",{value:S(),configurable:true})}catch(e){}}})();</script>"""
_CONSOLE_BRIDGE = """<script>(function(){function s(l,a){try{parent.postMessage({source:"radha-preview",level:l,message:Array.prototype.map.call(a,function(x){try{return typeof x==="string"?x:(x instanceof Error?x.message:JSON.stringify(x))}catch(e){return String(x)}}).join(" ")},"*")}catch(e){}}["log","info","warn","error"].forEach(function(l){var o=console[l];console[l]=function(){s(l,arguments);return o.apply(console,arguments)}});addEventListener("error",function(e){s("error",[e.message+(e.filename?" ("+e.filename.split("/").pop()+":"+e.lineno+")":"")])});addEventListener("unhandledrejection",function(e){s("error",["Unhandled promise rejection: "+((e.reason&&e.reason.message)||e.reason)])})})();</script>"""


def init(database):
    global db
    db = database


async def ensure_indexes():
    await db.apps.create_index([("userId", 1), ("updatedAt", -1)])
    info = await db.apps.index_information()
    partial = {"published.slug": {"$type": "string"}}
    if "published.slug_1" in info and info["published.slug_1"].get("partialFilterExpression") != partial:
        await db.apps.drop_index("published.slug_1")
    await db.apps.create_index("published.slug", unique=True, partialFilterExpression=partial)
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
    await _add_kit(app_id, path, content)
    await db.apps.update_one({"id": app_id}, {"$set": {"updatedAt": _now()}})
    return path


KIT_NAME = "krish-ui.css"
KIT_CSS = (Path(__file__).parent / "app_kit" / KIT_NAME).read_text(encoding="utf-8")
_KIT_REF_RE = re.compile(r"""href\s*=\s*["']([^"']*krish-ui\.css)["']""", re.IGNORECASE)


async def _add_kit(app_id: str, path: str, content: str) -> None:
    """A page that links the built-in design kit (krish-ui.css) gets the file next to it, so the preview,
    the published site, the ZIP and GitHub all have it."""
    if not path.endswith((".html", ".htm")):
        return
    for ref in _KIT_REF_RE.findall(content):
        target = _resolve(path, ref)
        if target and not await db.app_files.find_one({"appId": app_id, "path": target}, {"_id": 1}):
            await db.app_files.update_one({"appId": app_id, "path": target},
                                          {"$set": {"content": KIT_CSS, "updatedAt": _now()}}, upsert=True)


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
        who = f"{c.get('author') or 'Krish AI'} <krish@empirex.ai>".encode()
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
        f"You are Krish AI's app builder, working on the app “{app['name']}”"
        + (f" — {app['description']}" if app.get("description") else "") + ".\n"
        "The user sees the live preview, the files and the version history beside this chat.\n\n"
        f"Project files:\n{app_prompt_files(files)}\n"
        + (f"Uncommitted changes: {', '.join(f'{p} ({s})' for p, s in changes.items())}\n" if changes else "")
        + "\nHow to work:\n"
        "- The app is a static web app served from index.html. Use HTML/CSS/JS; load libraries from CDNs "
        "(esm.sh, unpkg, cdn.jsdelivr.net, cdn.tailwindcss.com). There is no npm install or build step, but any npm "
        "package works as an ES module from esm.sh, e.g. import confetti from \"https://esm.sh/canvas-confetti\" in a "
        "<script type=\"module\">. For React, import react and react-dom/client from esm.sh and write components "
        "with htm (import htm from \"https://esm.sh/htm\") instead of JSX, since there is no build step.\n"
        "- When asked for a new app or a big change, first write a short plan in your reply (3 to 6 bullets: the "
        "screens, the features, the files), then build the whole working app right away with write_file. Replace the "
        "starter files instead of building around them. Don't stop at a skeleton or placeholders: every button, form "
        "and link must work, with sample content so the app looks alive on first open.\n"
        "- A short request like \"make a cake shop website\" still means a complete, polished, multi-section site: "
        "for a website, a nav bar, a hero with a call to action, the main content with real sample items (products with "
        "names, prices and images), about, reviews, contact and a footer; for an app, every screen it needs. Never "
        "ask questions first; pick sensible details yourself.\n"
        "- Write index.html first with all the markup and ids, then the CSS, then the JS, which may only use ids that "
        "index.html has.\n"
        "- Each of your steps has limited room. Write a long file in parts: write_file with the first part (about "
        "120 lines), then append_file with each next part, until the file is complete.\n"
        "- Split the app into small files, each under about 250 lines, so each one is written in a single step and "
        "edited easily: index.html (markup), styles.css (or Tailwind classes), and JS modules such as app.js, ui.js, "
        "data.js loaded with <script type=\"module\">. Write the files one by one, and never cut a file short.\n"
        "- Before you finish, read back the files you wrote and check that every id, class, import and function "
        "they use exists, and that the layout works on a phone. Fix what you find.\n"
        "- When the user gives you their own code (pasted HTML is saved for you unchanged as index.html), it is "
        "theirs: keep its structure, CSS, colors, layout and wording exactly, change only what they ask, and never "
        "rewrite or restyle it (the quality bar below is for apps you design yourself). Make each change with "
        "edit_file; use search_files and read_file with line ranges to find the spot in a large file.\n"
        "- Read files before editing them. Prefer edit_file for small changes and write_file for new or rewritten files.\n"
        + ("- After changing the UI, call check_preview to see a screenshot and any console errors, and fix them.\n"
           if agent_browser.available() else "")
        + "- Put logic worth testing in plain modules and add tests (e.g. tests/*.test.mjs run with `node --test`, "
        "or Python unittest) and run them with run_command.\n"
        "- When a change works, call commit with a short message describing it.\n"
        "- Backend: every app already has a database and user accounts with no setup, through the global RADHA "
        "object (works in the preview and on the published site): await RADHA.auth.signup(email, password, name), "
        "await RADHA.auth.login(email, password), RADHA.auth.user (null when signed out), RADHA.auth.logout(); "
        "await RADHA.db.list(collection, {mine: true}) returns [{id, data, ownerId, createdAt}] newest first; "
        "RADHA.db.add(collection, data, {private: true}), RADHA.db.update(collection, id, data), "
        "RADHA.db.remove(collection, id). All calls return promises and throw Error with a readable message. "
        "Use it when data must be shared between visitors or the app needs accounts; otherwise use localStorage.\n"
        "- Keep your chat replies short: say what you built or changed.\n\n"
        + DESIGN_GUIDE
    )


_HTML_BODY = r"((?:<!doctype html[^>]*>\s*)?<html[\s>].*</html>)"
_HTML_FENCED_RE = re.compile(r"```[ \t]*html?[^\n]*\n\s*" + _HTML_BODY + r"\s*?\n[ \t]*```", re.IGNORECASE | re.DOTALL)
_HTML_DOC_RE = re.compile(_HTML_BODY, re.IGNORECASE | re.DOTALL)
_NAMED_BLOCK_RE = re.compile(r"```[ \t]*\w*[ \t:]+([\w\-./]+\.(?:html?|css|m?js|json|svg|txt|md))[ \t]*\n(.*?)\n[ \t]*```", re.DOTALL)


def split_pasted_code(content: str):
    """Pull a whole pasted HTML page, and fenced blocks that name a file, out of a chat message.

    Returns ({path: code}, the rest of the message).
    """
    files, rest = {}, content or ""
    m = _HTML_FENCED_RE.search(rest) or _HTML_DOC_RE.search(rest)
    if m:
        files["index.html"] = m.group(1).strip() + "\n"
        rest = rest[:m.start()] + rest[m.end():]
    for m in list(_NAMED_BLOCK_RE.finditer(rest)):
        try:
            files[clean_path(m.group(1))] = m.group(2) + "\n"
        except ValueError:
            continue
        rest = rest.replace(m.group(0), "", 1)
    return files, rest.strip()


async def absorb_pasted_code(app_id: str, content: str):
    """Save code the user pasted into the builder chat exactly as given, before any AI sees it.

    Free models can't hold a large page in their context and would rebuild it from what they
    remember, losing the user's design. Returns None when nothing was pasted, else
    (the message to store and show the AI, a ready reply when the user gave no instructions).
    """
    files, rest = split_pasted_code(content)
    if not files:
        return None
    for path, code in files.items():
        await write_file(app_id, path, code)
    await commit(app_id, "Add your code: " + ", ".join(files), author="You")
    listing = ", ".join(f"{p} ({max(1, len(c.encode('utf-8')) // 1024)} KB)" for p, c in files.items())
    note = (f"[Pasted code saved exactly as given: {listing}. It is the user's own design: keep it as it is "
            "and change only what they ask, with small edit_file changes.]")
    stored = f"{rest}\n\n{note}" if rest else note
    reply = None if rest else (f"Saved your code exactly as you gave it ({listing}). It's in the preview now. "
                               "Tell me what you'd like to change and I'll change only that.")
    return stored, reply


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


def _serve(files: Dict[str, str], path: str, bridge: bool, cache: str, app_id: Optional[str] = None) -> Response:
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
    if ctype == "text/html":
        inject = _STORAGE_SHIM + (_CONSOLE_BRIDGE if bridge else "") + (appdata.sdk_script(app_id) if app_id else "")
        idx = content.lower().find("<head>")
        content = content[:idx + 6] + inject + content[idx + 6:] if idx >= 0 else inject + content
    return Response(content, media_type=f"{ctype}; charset=utf-8" if ctype.startswith("text/") else ctype, headers=headers)


async def check_preview(files: Dict[str, str], path: str = "index.html", app_id: Optional[str] = None) -> dict:
    """Load the working copy in headless Chromium; return console output, errors and a screenshot."""
    browser = await agent_browser.manager._ensure_browser()
    context = await browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=False)
    allowed: dict = {}
    logs: List[str] = []

    async def handler(route):
        url = route.request.url
        if url.startswith(PREVIEW_ORIGIN):
            rel = unquote(urlparse(url).path.lstrip("/"))
            resp = _serve(files, rel, bridge=False, cache="no-store", app_id=app_id)
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
_ID_DEF_RE = re.compile(r"""\bid\s*=\s*["'`]([\w\-:.]+)["'`]|\.id\s*=\s*["'`]([\w\-:.]+)["'`]|setAttribute\(\s*["']id["']\s*,\s*["'`]([\w\-:.]+)""")
_ID_USE_RE = re.compile(r"""getElementById\(\s*["'`]([\w\-:.]+)["'`]\s*\)|querySelector(?:All)?\(\s*["'`]#([\w\-]+)["'`]\s*\)|\$\(\s*["'`]#([\w\-]+)["'`]\s*\)""")
_LOCAL_REF_RE = re.compile(r"""<(?:script|link|img)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"'#?]+)""", re.IGNORECASE)
_IMPORT_RE = re.compile(r"""(?:\bimport\b[^'"]*?|\bimport\(\s*)["'](\.{1,2}/[^"']+)["']""")


def _resolve(base: str, ref: str) -> Optional[str]:
    """The app path a relative reference points to, or None for an outside URL."""
    if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//)", ref, re.IGNORECASE):
        return None
    parts = ([] if ref.startswith("/") else base.split("/")[:-1]) + ref.split("/")
    out = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if out:
                out.pop()
        else:
            out.append(part)
    return "/".join(out) or None


def app_problems(files: Dict[str, str]) -> List[str]:
    """Mistakes that leave a page blank or crash it, found without running it: elements the code looks up
    by id that no file creates, and local files that are loaded but don't exist."""
    problems = []
    if "index.html" not in files:
        problems.append("There is no index.html, so the preview is empty.")
    web = {p: c for p, c in files.items() if p.endswith((".html", ".htm", ".js", ".mjs", ".jsx"))}
    defined = {next(g for g in m.groups() if g) for c in web.values() for m in _ID_DEF_RE.finditer(c)}
    missing_ids = {}
    for path, content in web.items():
        for m in _ID_USE_RE.finditer(content):
            ident = next(g for g in m.groups() if g)
            if ident not in defined and "${" not in ident:
                missing_ids.setdefault(ident, path)
    for ident, path in list(missing_ids.items())[:8]:
        problems.append(f'{path} looks up the element #{ident}, but no HTML has id="{ident}" '
                        "(this crashes the page with \"Cannot read/set properties of null\").")
    missing_files = {}
    for path, content in web.items():
        refs = _LOCAL_REF_RE.findall(content) if path.endswith((".html", ".htm")) else []
        refs += _IMPORT_RE.findall(content)
        for ref in refs:
            target = _resolve(path, ref.strip())
            if target and target not in files and target.rsplit(".", 1)[-1].lower() in ("js", "mjs", "css", "jsx"):
                missing_files.setdefault(target, path)
    for target, path in list(missing_files.items())[:8]:
        problems.append(f"{path} loads {target}, which doesn't exist yet.")
    return problems


def _is_module(path: str, files: Dict[str, str]) -> bool:
    if path.endswith(".mjs"):
        return True
    name = path.rsplit("/", 1)[-1]
    tagged = any(re.search(r"<script[^>]*type=[\"']module[\"'][^>]*" + re.escape(name), c, re.IGNORECASE)
                 for p, c in files.items() if p.endswith((".html", ".htm")))
    return tagged or bool(re.search(r"^\s*(?:import\s|export\s)", files[path], re.MULTILINE))


async def _syntax_errors(files: Dict[str, str]) -> List[str]:
    """JavaScript files that don't parse (usually a file cut off mid-way), checked with `node --check`."""
    scripts = [p for p in files if p.endswith((".js", ".mjs"))]
    node = shutil.which("node")
    if not scripts or not node:
        return []
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        for path in scripts[:12]:
            target = os.path.join(tmp, re.sub(r"[^\w.-]", "_", path) + (".mjs" if _is_module(path, files) else ".cjs"))
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(files[path])
            try:
                proc = await asyncio.create_subprocess_exec(node, "--check", target, stdout=asyncio.subprocess.DEVNULL,
                                                            stderr=asyncio.subprocess.PIPE)
                _, err = await asyncio.wait_for(proc.communicate(), timeout=10)
            except (asyncio.TimeoutError, OSError):
                continue
            if proc.returncode:
                lines = [l for l in err.decode("utf-8", "replace").splitlines() if l.strip()]
                where = next((l.rsplit(":", 1)[-1] for l in lines if target in l and ":" in l), "")
                error = next((l for l in lines if "Error" in l), "a syntax error")
                at_end = where.isdigit() and int(where) >= len(files[path].rstrip().splitlines()) - 1
                cut = " The file looks cut off: add the missing rest with append_file." \
                    if at_end or "end of input" in error or "Unterminated" in error else ""
                problems.append(f"{path} has a syntax error{f' near line {where}' if where.isdigit() else ''} "
                                f"({error.strip()[:160]}), so none of it runs.{cut}")
    return problems


async def check_app(files: Dict[str, str]) -> List[str]:
    """Everything that would crash or blank the page: app_problems plus JavaScript syntax errors."""
    return app_problems(files) + await _syntax_errors(files)


async def _with_problems(app_id: str, text: str) -> str:
    problems = await check_app(await snapshot(app_id))
    if not problems:
        return text
    return text + "\nProblems in the app right now (fix them before you finish):\n- " + "\n- ".join(problems)


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
    lines = doc["content"].split("\n")
    start = max(1, int(args.get("start_line") or 1))
    end = min(len(lines), int(args.get("end_line") or len(lines)))
    numbered = "\n".join(f"{i:4d}  {lines[i - 1]}" for i in range(start, end + 1))
    if len(numbered) > READ_CHARS:
        cut = numbered[:READ_CHARS].rsplit("\n", 1)[0]
        last = start + cut.count("\n")
        numbered = cut + f"\n… (file has {len(lines)} lines; read more with start_line={last + 1})"
    return _tool_output(numbered, f"Read {path}" + (f" lines {start}-{end}" if (start, end) != (1, len(lines)) else ""))


async def _t_search(ctx, args):
    query = (args.get("query") or "").strip()
    if not query:
        raise ValueError("'query' is required")
    hits = []
    async for f in db.app_files.find({"appId": ctx.app_id}).sort("path", 1):
        for i, line in enumerate(f["content"].split("\n"), 1):
            if query.lower() in line.lower():
                hits.append(f"{f['path']}:{i}: {line.strip()[:200]}")
    shown = hits[:60]
    body = "\n".join(shown) + (f"\n… and {len(hits) - 60} more" if len(hits) > 60 else "")
    return _tool_output(body or f"No line contains “{query}”.", f"{len(hits)} match(es) for “{query[:40]}”")


async def _t_write(ctx, args):
    content = args.get("content")
    if not isinstance(content, str):
        raise ValueError("'content' is required")
    path = await write_file(ctx.app_id, args.get("path", ""), content)
    return _tool_output(await _with_problems(ctx.app_id, f"Wrote {path} ({len(content)} chars)."), f"Wrote {path}")


async def _t_append(ctx, args):
    content = args.get("content")
    if not isinstance(content, str):
        raise ValueError("'content' is required")
    path = clean_path(args.get("path", ""))
    doc = await db.app_files.find_one({"appId": ctx.app_id, "path": path}, {"content": 1})
    before = (doc or {}).get("content", "")
    joiner = "" if not before or before.endswith("\n") or content.startswith("\n") else "\n"
    await write_file(ctx.app_id, path, before + joiner + content)
    return _tool_output(await _with_problems(ctx.app_id, f"Added {len(content)} chars to {path} "
                                             f"(now {len(before) + len(joiner) + len(content)} chars)."), f"Wrote {path}")


_LINE_NO_RE = re.compile(r"(?m)^ *\d+  ")


def _strip_line_numbers(text: str) -> str:
    """Undo read_file's "  12  " prefixes when the model copies them into an edit."""
    lines = [l for l in text.split("\n") if l.strip()]
    return _LINE_NO_RE.sub("", text) if lines and all(_LINE_NO_RE.match(l) for l in lines) else text


def locate_snippet(content: str, old: str):
    """Find `old` in `content`: exactly, then without copied line numbers, then ignoring whitespace.

    Returns (start, end, None) for a unique match, else (None, None, a message for the model).
    """
    candidates = [old]
    stripped = _strip_line_numbers(old)
    if stripped != old:
        candidates.append(stripped)
    for cand in candidates:
        count = content.count(cand)
        if count == 1:
            i = content.index(cand)
            return i, i + len(cand), None
        if count > 1:
            lines = sorted({content.count("\n", 0, m.start()) + 1 for m in re.finditer(re.escape(cand), content)})
            return None, None, (f"old_text matches {count} places (lines {', '.join(map(str, lines[:10]))}). "
                                "Include a few more surrounding lines so it matches exactly one.")
    tokens = stripped.split()
    if tokens:
        matches = list(re.finditer(r"\s+".join(map(re.escape, tokens)), content))
        if len(matches) == 1:
            return matches[0].start(), matches[0].end(), None
        if len(matches) > 1:
            return None, None, f"old_text matches {len(matches)} places. Include more surrounding lines."
    # Point the model at the closest text so its next try can succeed.
    file_lines, want = content.split("\n"), [l.strip() for l in stripped.strip().split("\n")]
    n, best, best_at = max(1, len(want)), 0.0, 0
    for i in range(0, max(1, len(file_lines) - n + 1)):
        score = difflib.SequenceMatcher(None, "\n".join(l.strip() for l in file_lines[i:i + n]), "\n".join(want)).quick_ratio()
        if score > best:
            best, best_at = score, i
    lo, hi = max(0, best_at - 2), min(len(file_lines), best_at + n + 2)
    near = "\n".join(f"{i + 1:4d}  {file_lines[i]}" for i in range(lo, hi))
    return None, None, ("old_text was not found in the file. The closest text is below; copy old_text exactly "
                        f"from it (without the line numbers), or use write_file for a bigger change.\n{near}")


async def _t_edit(ctx, args):
    path = clean_path(args.get("path", ""))
    doc = await db.app_files.find_one({"appId": ctx.app_id, "path": path})
    if not doc:
        return _tool_output(f"{path} does not exist.", f"{path} not found", ok=False)
    old, new = args.get("old_text"), args.get("new_text", "")
    if not old:
        raise ValueError("'old_text' is required")
    start, end, problem = locate_snippet(doc["content"], old)
    if problem:
        return _tool_output(problem, "Edit didn't match; retrying", ok=False)
    if _strip_line_numbers(new) != new and _strip_line_numbers(old) != old:
        new = _strip_line_numbers(new)
    await write_file(ctx.app_id, path, doc["content"][:start] + new + doc["content"][end:])
    return _tool_output(await _with_problems(ctx.app_id, f"Edited {path}."), f"Edited {path}")


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

    result = await check_preview(await snapshot(ctx.app_id), args.get("path") or "index.html", app_id=ctx.app_id)
    shot = await media.save_media(ctx.db, ctx.user_id, result["screenshot"], "image/jpeg", "screenshot",
                                  name="preview.jpg", conversation_id=ctx.conversation_id)
    errors = [l for l in result["logs"] if l.startswith(("[console.error]", "[uncaught", "[request failed]", "[http"))]
    body = (f"Title: {result['title']}\n\nConsole and network ({len(result['logs'])} entries):\n"
            + ("\n".join(result["logs"]) or "(none)") + f"\n\nVisible text:\n{result['text']}")
    summary = f"{len(errors)} error(s)" if errors else "No errors"
    return _tool_output(body, summary, ok=not errors, media=[shot])


async def _t_commit(ctx, args):
    result = await commit(ctx.app_id, args.get("message") or "Update", author="Krish AI")
    if not result:
        return _tool_output("Nothing to commit — no changes since the last version.", "No changes")
    return _tool_output(f"Committed version {result['id']}: {result['message']}", f"Saved version {result['id']}")


def register_tools(registry):
    path_param = {"type": "string", "description": "File path relative to the app root, e.g. index.html or src/app.js"}
    specs = [
        ("list_files", "List files", "List the app's files with sizes.", {}, [], _t_list),
        ("read_file", "Read file", "Read a file from the app with line numbers; for a large file pass start_line and "
         "end_line to read part of it.", {"path": path_param, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
         ["path"], _t_read),
        ("search_files", "Search files", "Find every line containing some text (case-insensitive) across the app's "
         "files, with file names and line numbers.", {"query": {"type": "string"}}, ["query"], _t_search),
        ("write_file", "Write file", "Create or overwrite a file in the app with the full new content.",
         {"path": path_param, "content": {"type": "string"}}, ["path", "content"], _t_write),
        ("append_file", "Write file", "Add content to the end of a file (creates it if missing). Use it to write a long "
         "file in parts: write_file with the first part, then append_file with each next part.",
         {"path": path_param, "content": {"type": "string"}}, ["path", "content"], _t_append),
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
    files: Optional[Dict[str, str]] = None  # start from these files instead of a template (e.g. code from a chat)


class AppPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)


class FileIn(BaseModel):
    content: str


class CommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=2000)


class GitHubIn(BaseModel):
    repo: str = Field(min_length=1, max_length=140)
    token: str = Field(min_length=10, max_length=300)
    private: bool = True


class CommitIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


def public_app(doc: dict) -> dict:
    pub = doc.get("published")
    return {
        "id": doc["id"], "name": doc["name"], "description": doc.get("description"),
        "conversationId": doc.get("conversationId"), "createdAt": doc["createdAt"], "updatedAt": doc["updatedAt"],
        "published": {"slug": pub["slug"], "url": f"/api/sites/{pub['slug']}/", "commitId": pub.get("commitId"),
                      "publishedAt": pub.get("publishedAt")} if pub else None,
        "github": doc.get("github"),
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
    if body.files:
        if len(body.files) > MAX_FILES:
            raise HTTPException(status_code=400, detail=f"Too many files (max {MAX_FILES})")
        try:
            source = {clean_path(p): c for p, c in body.files.items()}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        label = "Create app from chat code"
    else:
        template = body.template if body.template in TEMPLATES else "blank"
        source, label = TEMPLATES[template], f"Create app from {template} template"
    await db.conversations.insert_one(conv)
    await db.apps.insert_one(doc)
    try:
        for path, content in source.items():
            await write_file(app_id, path, content)
    except ValueError as exc:
        await db.app_files.delete_many({"appId": app_id})
        await db.apps.delete_one({"id": app_id})
        await db.conversations.delete_one({"id": conv["id"]})
        raise HTTPException(status_code=400, detail=str(exc))
    await commit(app_id, label, author="Krish AI")
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
    await appdata.delete_app_data(app_id)
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


@router.post("/apps/{app_id}/github")
async def push_to_github(app_id: str, body: GitHubIn, user_id: str = Depends(current_user_id)):
    app = await owned_app(app_id, user_id)
    head = await head_commit(app_id)
    message = f"{app['name']}: {head['message']}" if head else f"{app['name']} from Krish AI"
    try:
        result = await github_push.push(await snapshot(app_id), body.token, body.repo, message, private=body.private)
    except github_push.PushError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.apps.update_one({"id": app_id}, {"$set": {"github": {"repo": result["repo"], "url": result["url"], "pushedAt": _now()}}})
    return result


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
    return _serve(await snapshot(app["id"]), path, bridge=True, cache="no-store", app_id=app["id"])


@router.get("/sites/{slug}/{path:path}")
async def serve_site(slug: str, path: str = ""):
    app = await db.apps.find_one({"published.slug": slug})
    if not app or not app.get("published"):
        return Response("This site is not published.", status_code=404, media_type="text/plain")
    version = await db.app_commits.find_one({"appId": app["id"], "id": app["published"]["commitId"]})
    return _serve(await commit_files(version), path, bridge=False, cache="public, max-age=60", app_id=app["id"])
