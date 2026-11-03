"""Push an App Builder app to a GitHub repository with the user's personal access token.

The token is used for this one request and never stored. The repository is created (private by
default) if it doesn't exist; files are added or updated on its default branch in one commit.
"""
import re
from typing import Dict, Optional

import httpx

API = "https://api.github.com"
_REPO_RE = re.compile(r"^(?:([A-Za-z0-9-]{1,39})/)?([A-Za-z0-9._-]{1,100})$")


class PushError(Exception):
    pass


def _raise(resp: httpx.Response, what: str):
    if resp.status_code == 401:
        raise PushError("GitHub rejected the token. Create a new one with the \"repo\" permission and try again.")
    if resp.status_code == 403:
        raise PushError(f"The token isn't allowed to {what}. Give it the \"repo\" permission.")
    try:
        detail = resp.json().get("message", "")
    except ValueError:
        detail = resp.text[:200]
    raise PushError(f"GitHub couldn't {what}: {detail or resp.status_code}")


async def push(files: Dict[str, str], token: str, repo: str, message: str, private: bool = True,
               transport: Optional[httpx.AsyncBaseTransport] = None) -> dict:
    m = _REPO_RE.match((repo or "").strip())
    if not m or m.group(2) in (".", ".."):
        raise PushError("Use a repository name like my-app or your-name/my-app.")
    if not files:
        raise PushError("The app has no files to push.")
    headers = {"Authorization": f"Bearer {token.strip()}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30, transport=transport) as gh:
        me = await gh.get("/user")
        if me.status_code != 200:
            _raise(me, "read your account")
        login = me.json()["login"]
        owner, name = m.group(1) or login, m.group(2)

        r = await gh.get(f"/repos/{owner}/{name}")
        created = False
        if r.status_code == 404:
            if owner.lower() != login.lower():
                raise PushError(f"Repository {owner}/{name} doesn't exist, and Krish AI can only create repositories in your own account.")
            r = await gh.post("/user/repos", json={"name": name, "private": private, "auto_init": True,
                                                   "description": "Built with Krish AI"})
            if r.status_code != 201:
                _raise(r, "create the repository")
            created = True
        elif r.status_code != 200:
            _raise(r, "open the repository")
        info = r.json()
        full, branch = info["full_name"], info.get("default_branch") or "main"

        ref = await gh.get(f"/repos/{full}/git/ref/heads/{branch}")
        if ref.status_code != 200:
            # An empty repository has no branch yet: create one with a first file.
            init = await gh.put(f"/repos/{full}/contents/README.md",
                                json={"message": "Initial commit", "content": "IyBCdWlsdCB3aXRoIFJBREhBCg==", "branch": branch})
            if init.status_code not in (200, 201):
                _raise(init, "start the repository")
            ref = await gh.get(f"/repos/{full}/git/ref/heads/{branch}")
            if ref.status_code != 200:
                _raise(ref, "read the branch")
        parent = ref.json()["object"]["sha"]
        base_tree = (await gh.get(f"/repos/{full}/git/commits/{parent}")).json()["tree"]["sha"]

        tree = await gh.post(f"/repos/{full}/git/trees", json={
            "base_tree": base_tree,
            "tree": [{"path": p, "mode": "100644", "type": "blob", "content": c} for p, c in sorted(files.items())],
        })
        if tree.status_code != 201:
            _raise(tree, "upload the files")
        commit = await gh.post(f"/repos/{full}/git/commits",
                               json={"message": message, "tree": tree.json()["sha"], "parents": [parent]})
        if commit.status_code != 201:
            _raise(commit, "create the commit")
        upd = await gh.patch(f"/repos/{full}/git/refs/heads/{branch}", json={"sha": commit.json()["sha"]})
        if upd.status_code != 200:
            _raise(upd, "update the branch")
    return {"url": info["html_url"], "repo": full, "branch": branch, "created": created,
            "commit": commit.json()["sha"]}


# ------------------------------------------------------------------ import a repository into the App Builder
import io
import tarfile

_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?"
                     r"(?:/tree/([^/?#]+))?/?(?:[?#].*)?$")
_SHORT_RE = re.compile(r"^([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})$")
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "out", "coverage", ".cache", "vendor", "__pycache__",
              ".venv", "venv", ".turbo", ".vercel"}
_TEXT_EXTS = {"html", "htm", "css", "scss", "js", "mjs", "cjs", "jsx", "ts", "tsx", "json", "md", "txt", "svg", "xml",
              "yml", "yaml", "toml", "py", "csv", "env.example", "gitignore", "webmanifest", "vue", "svelte"}
_SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"}
MAX_IMPORT_FILES = 300
MAX_IMPORT_FILE_BYTES = 512 * 1024
MAX_IMPORT_BYTES = 8 * 1024 * 1024


def parse_repo(text: str):
    """(owner, name, branch or None) from a GitHub link or owner/name, else PushError."""
    text = (text or "").strip()
    m = _URL_RE.match(text) or _SHORT_RE.match(text)
    if not m:
        raise PushError("Paste a GitHub link like https://github.com/owner/repo, or owner/repo.")
    groups = m.groups()
    return groups[0], groups[1], (groups[2] if len(groups) > 2 else None)


def _wanted(path: str, size: int) -> bool:
    parts = path.split("/")
    if any(p in _SKIP_DIRS for p in parts[:-1]) or parts[-1] in _SKIP_FILES or size > MAX_IMPORT_FILE_BYTES:
        return False
    name = parts[-1].lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    return ext in _TEXT_EXTS or name in ("license", "readme", "dockerfile", ".gitignore")


def files_from_tarball(data: bytes) -> Dict[str, str]:
    """The project's text files from a GitHub tarball (its top folder removed), skipping dependencies, build
    output, lock files and anything binary or too big."""
    files, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            path = member.name.split("/", 1)[1] if "/" in member.name else member.name
            if not path or not _wanted(path, member.size):
                continue
            raw = tar.extractfile(member).read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if "\x00" in text:
                continue
            total += len(raw)
            if total > MAX_IMPORT_BYTES or len(files) >= MAX_IMPORT_FILES:
                raise PushError("That repository is too big to open in the App Builder (over "
                                f"{MAX_IMPORT_FILES} files or {MAX_IMPORT_BYTES // (1024 * 1024)} MB of code).")
            files[path] = text
    return files


async def download(repo: str, token: str = "", transport: Optional[httpx.AsyncBaseTransport] = None) -> dict:
    """{"name", "description", "files"} for a repository: public ones without a token, private ones with the
    user's connected GitHub account."""
    owner, name, branch = parse_repo(repo)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=60, follow_redirects=True,
                                 transport=transport) as gh:
        info = await gh.get(f"/repos/{owner}/{name}")
        if info.status_code == 404:
            raise PushError("GitHub can't find that repository. If it's private, connect your GitHub account first.")
        if info.status_code >= 400:
            _raise(info, "open that repository")
        meta = info.json()
        tar = await gh.get(f"/repos/{owner}/{name}/tarball/{branch or meta.get('default_branch') or ''}".rstrip("/"))
        if tar.status_code >= 400:
            _raise(tar, "download that repository")
    files = files_from_tarball(tar.content)
    if not files:
        raise PushError("That repository has no code files the App Builder can open.")
    return {"name": meta.get("name") or name, "description": meta.get("description") or "", "files": files,
            "url": meta.get("html_url") or f"https://github.com/{owner}/{name}"}
