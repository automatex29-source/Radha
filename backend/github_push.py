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
