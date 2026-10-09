"""Check the app, site or game Krish just wrote in the chat, and fix what would break it before the user sees it.

Free models often run out of room part-way through a page (the preview then shows half a site), forget a file
that index.html loads, or leave a JavaScript slip that stops every button working. After a reply with code, the
files are checked like the App Builder checks them (apps.check_app: missing files and elements, `node --check`
on every script), plus pages and replies that stop mid-way. What's found is fixed with small, targeted model
calls: a cut-off file is finished from where it stopped, a missing file is written, other mistakes get
SEARCH/REPLACE edits (code_edit.py). The reply keeps its words, with the fixed files in place of the broken ones.
"""
import re
from typing import AsyncIterator, Dict, List, Optional

import apps
import code_edit

_WEB = (".html", ".htm", ".js", ".mjs", ".css", ".jsx")
_REST_OUTPUT = 8000  # tokens for the missing end of a file, or a whole missing file
_CONTEXT = 24000     # characters of a file shown to the model when finishing it

SYSTEM = ("You are Krish AI, an expert web developer fixing code you wrote. You write only what is asked, "
          "complete and working, matching the code that is already there.")


def _cut_page(path: str, code: str) -> bool:
    """A page that stops before its end (no closing </html>, or a <script>/<style> left open)."""
    if not path.endswith((".html", ".htm")):
        return False
    low = code.lower()
    if "<html" in low and "</html>" not in low:
        return True
    return low.count("<script") > low.count("</script") or low.count("<style") > low.count("</style")


async def problems(files: Dict[str, str], cut: Optional[str] = None) -> List[str]:
    """What would break the page: the app checks, plus a file cut off mid-way (`cut` names one the reply ended in)."""
    found = [p for p in await apps.check_app(files) if not p.startswith("There is no index.html")]
    for path, code in files.items():
        if path == cut or _cut_page(path, code):
            found.insert(0, f"{path} is cut off: it stops before its end.")
    return found


def _strip_fence(text: str) -> str:
    m = re.search(r"(`{3,})[^\n]*\n(.*?)(?:\n[ \t]*\1|$)", text or "", re.DOTALL)
    return m.group(2) if m else (text or "").strip("\n")


def join_rest(code: str, rest: str) -> str:
    """`code` followed by its missing `rest`, without the overlap a model adds when it repeats the last lines."""
    if code.endswith("\n"):
        rest = rest.lstrip("\n")
    for size in range(min(len(code), len(rest), 2000), 9, -1):
        if code.endswith(rest[:size]):
            rest = rest[size:]
            break
    # Code blocks drop the file's last newline, so a file cut at a line end looks cut mid-line: a finished
    # statement or tag followed by a new one starts a new line.
    if rest and not code.endswith("\n") and not rest.startswith("\n") and re.search(r"[;{}>)\]]\s*$", code) \
            and not re.match(r"[;,.)\]}]", rest.lstrip()):
        return code + "\n" + rest
    return code + rest


async def _ask(model: str, prompt: str, ask_model) -> AsyncIterator[dict]:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    async for ev in ask_model(model, messages, _REST_OUTPUT):
        yield ev


async def _collect(model: str, prompt: str, ask_model, out: list) -> AsyncIterator[dict]:
    async for ev in _ask(model, prompt, ask_model):
        if ev["type"] == "text":
            out.append(ev["text"])
        elif ev["type"] == "heartbeat":
            yield ev


def _others(files: Dict[str, str], path: str) -> str:
    names = [p for p in files if p != path]
    return f" The other files are: {', '.join(names)}." if names else ""


async def repair(model: str, files: Dict[str, str], found: List[str], ask_model=code_edit._default_ask) -> AsyncIterator[dict]:
    """Fix `found` in `files`. Yields heartbeats and {"type": "fixing", "what"}, then one
    {"type": "result", "files": the fixed files (new ones included), "fixed": problems that went away}."""
    fixed = dict(files)
    # 1. Files that stop part-way: write the rest, from exactly where they stop.
    for path in [p for p in files if any(f.startswith(f"{p} is cut off") or (f.startswith(f"{p} has a syntax error")
                                                                             and "cut off" in f) for f in found)]:
        yield {"type": "fixing", "what": f"Finishing {path}"}
        code = fixed[path]
        shown = code[-_CONTEXT:]
        prompt = (f"This file, {path}, was cut off before its end.{_others(files, path)} Write ONLY the missing rest, "
                  "starting exactly where it stops (mid-line if it stops mid-line), and finish everything so the "
                  "file is complete and works: close every open tag, rule, function and block. Don't repeat what is "
                  f"already there and don't explain. Reply with one code block.\n\n"
                  f"{'The end of the file' if len(code) > _CONTEXT else 'The file so far'}:\n"
                  f"{code_edit.fence_for(shown)}\n{shown}\n{code_edit.fence_for(shown)}")
        text: list = []
        async for ev in _collect(model, prompt, ask_model, text):
            yield ev
        rest = _strip_fence("".join(text))
        if rest.strip():
            fixed[path] = join_rest(code, rest)
    # 2. Local files a page loads that were never written.
    missing = [m for f in found for m in re.findall(r"loads (\S+), which doesn't exist yet", f)]
    for path in dict.fromkeys(missing):
        yield {"type": "fixing", "what": f"Writing {path}"}
        pages = {p: c for p, c in fixed.items() if p.endswith((".html", ".htm", ".js", ".jsx"))}
        context = "\n\n".join(code_edit.block(p, c[:_CONTEXT // max(1, len(pages))]) for p, c in pages.items())
        prompt = (f"The app below loads {path}, but it was never written. Write the complete {path} so the app "
                  "works: match every id, class and function name the other files use. Reply with one code block "
                  f"holding the whole file.\n\n{context}")
        text = []
        async for ev in _collect(model, prompt, ask_model, text):
            yield ev
        code = _strip_fence("".join(text))
        if code.strip():
            fixed[path] = code
    # 3. Everything else (an element that isn't there, a script that doesn't parse): small edits.
    others = [f for f in found if " is cut off" not in f and "which doesn't exist yet" not in f and "cut off" not in f]
    targets = {p: fixed[p] for p in fixed if any(f.startswith(p + " ") for f in others)}
    if targets:
        yield {"type": "fixing", "what": "Fixing " + ", ".join(targets)}
        ask = ("Fix these problems so the page works, and change nothing else:\n- " + "\n- ".join(others))
        async for ev in code_edit.run(model, targets, ask, ask_model):
            if ev["type"] == "heartbeat":
                yield ev
            elif ev["type"] == "result":
                fixed.update(ev["files"])
    left = await problems(fixed)
    yield {"type": "result", "files": fixed, "fixed": [f for f in found if f not in left]}


def web_files(text: str) -> tuple:
    """({path: code} of the web files in a reply, the file the reply was cut off in or None)."""
    closed, ticks = code_edit.close_fence(text)
    files = {p: c for p, c in code_edit.code_files(closed).items() if p.endswith(_WEB)}
    cut = None
    if ticks:
        last = list(code_edit.code_files(closed))
        cut = last[-1] if last else None
    # Only whole pages are checked: a snippet in an explanation ("how do I center a div?") is left as it is.
    if not any(p.endswith((".html", ".htm")) and re.search(r"<(?:!doctype|html|body)\b", c, re.IGNORECASE)
               for p, c in files.items()):
        return {}, None
    return files, cut if cut in files else None
