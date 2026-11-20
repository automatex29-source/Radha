"""The App Builder's fast first build: the whole first version in one reply, shown as it is typed.

A new app used to be built with many small tool calls (write_file, append_file, read_file...), each one a full
round trip to the model, and on the free models each a chance of a broken tool call. For the first build of a
fresh app Krish now asks for every file in one reply instead, as fenced blocks that name the file:

    - a short plan, a few bullets
    ```html index.html
    ...
    ```

The reply is read as it streams: the plan is shown as text, each file is shown being typed (code_draft events)
and saved the moment its block closes, so the preview fills in file by file. The usual checks and repair rounds
run afterwards, with the plan used to check that every feature is there.

Before the model starts, a fresh blank app gets the starter template closest to the request (instant_start), so
something is on screen within a second while the real app is written.
"""
import re
import uuid
from typing import AsyncIterator, Dict, List, Optional

import apps
from agent import llm as agent_llm

# Starter template for words in the request: shown while the real app is written.
_TEMPLATE_WORDS = [
    ("todo", r"to-?do|task|checklist|habit|reminder|notes?\b|planner"),
    ("dashboard", r"dashboard|admin|analytics|stats|crm|tracker|report|expense|finance|inventory"),
    ("shop", r"shop|store|e-?commerce|cart|product|bakery|cake|boutique|sell"),
    ("game", r"game|snake|puzzle|quiz|tic.?tac|arcade|memory|score"),
    ("restaurant", r"restaurant|cafe|café|coffee|menu|food|pizza|bar\b|dhaba|kitchen"),
    ("booking", r"book(ing)?|appointment|salon|clinic|doctor|hotel|reservation|schedule|calendar|gym|spa"),
    ("portfolio", r"portfolio|resume|cv\b|personal (site|website)|photographer|designer|freelanc|about me"),
    ("chat", r"chat ?bot|chatbot|assistant|\bai\b|gpt|ask me|q ?& ?a|tutor"),
    ("landing", r"landing|startup|saas|website|site|agency|company|business|launch|marketing|product page"),
]
_SKIP_DIRS = (apps.SAMPLE_DIR + "/", apps.ASSET_DIR + "/")
_FENCE_OPEN = re.compile(r"^\s*```[ \t]*([\w+-]*)[ \t:]*([\w\-./]+\.\w+)?[ \t]*$")
_FENCE_CLOSE = re.compile(r"^\s*```\s*$")
_DEFAULT_NAMES = {"html": "index.html", "htm": "index.html", "css": "styles.css", "js": "app.js",
                  "javascript": "app.js", "mjs": "app.js", "json": "data.json"}
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)")
MAX_PLAN = 8

DRAFT_RULES = (
    "FAST FIRST BUILD. Don't call any tools this time: write the whole first version of the app in this one reply.\n"
    "1. Start with a plan of 3 to 6 short bullets (\"- \"), naming the screens and the features that must work. "
    "No heading, no other intro.\n"
    "2. Then write every file, each as one fenced code block whose first line names the file, like:\n"
    "```html index.html\n<!doctype html>...\n```\n"
    "```css styles.css\n...\n```\n"
    "```js app.js\n...\n```\n"
    "Write index.html first, then the CSS, then the JS. Replace the starter files completely (write index.html "
    "and app.js again even if they exist). Every file must be complete: never cut a file short, never write "
    "\"...\" or \"rest of the code\". Keep it to the files the app needs (usually 2 to 4).\n"
    "3. After the last file, one short line saying what you built. Nothing else."
)


MAX_CONTINUE = 3  # times a reply cut off inside a file is asked to go on


CONTINUE_TAIL = 1500  # characters of where the reply stopped, repeated in the request (older parts may be trimmed)


def continue_rules(path: Optional[str], tail: str = "") -> str:
    where = f"\n\nYour reply ended with:\n<<<\n{tail}\n>>>" if tail else ""
    return (f"Your reply was cut off in the middle of {path}. Go on with {path} exactly where you stopped: start "
            "with the very next characters, don't repeat anything already written, don't open a new code block "
            "and don't write any intro. Then close the block with ``` and write any files that are still missing "
            "the same way, then the one short line saying what you built." + where)


def continuation_start(held: str):
    """(decided, text to read) for the start of a continuation, held until its first line is complete. A repeated
    fence line that opens the same file again ("```js app.js") is dropped; anything else is read as it is."""
    stripped = held.lstrip()
    if not stripped:
        return False, ""
    if not stripped.startswith("```"):
        return True, held
    if "\n" not in stripped:
        return False, ""
    line, rest = stripped.split("\n", 1)
    if _FENCE_OPEN.match(line) and not _FENCE_CLOSE.match(line):
        return True, rest
    return True, held


def _plain(files: Dict[str, str]) -> Dict[str, str]:
    return {p: c for p, c in files.items() if not p.startswith(_SKIP_DIRS) and p != apps.KIT_NAME}


def fresh_template(files: Dict[str, str]) -> Optional[str]:
    """The starter template the app still is, untouched (ignoring the user's own uploads), or None."""
    plain = _plain(files)
    for tid, tfiles in apps.TEMPLATES.items():
        if plain == {p: c for p, c in tfiles.items() if p != apps.KIT_NAME}:
            return tid
    return None


def wanted(history_docs: list, files: Dict[str, str], model: str) -> bool:
    """True for the first build of an app that is still a starter template, on a model with room for a whole
    app in one reply. Not when the user gave sample files (those are studied with tools first) or code."""
    users = [m for m in history_docs if m["role"] == "user"]
    if len(users) != 1:
        return False
    text = (users[0].get("content") or "").strip()
    if not text or "```" in text or "<html" in text.lower() or "[Pasted code saved" in text:
        return False
    if any(p.startswith(apps.SAMPLE_DIR + "/") for p in files):
        return False
    if agent_llm.lean(model) and agent_llm.token_budget(model) <= 16000:
        return False  # Groq's free tier can't fit a whole app in one reply
    return fresh_template(files) is not None


def pick_template(request: str) -> Optional[str]:
    text = (request or "").lower()
    for tid, pattern in _TEMPLATE_WORDS:
        if tid in apps.TEMPLATES and re.search(pattern, text):
            return tid
    return None


def _event(name: str, call_id: str, label: str, path: str, ok: bool = True, summary: str = "") -> dict:
    if name == "start":
        return {"type": "tool_start", "id": call_id, "name": "write_file", "label": label, "args": {"path": path}}
    return {"type": "tool_end", "id": call_id, "name": "write_file", "ok": ok, "summary": summary, "output": "",
            "media": []}


async def instant_start(app_id: str, request: str, files: Dict[str, str]) -> AsyncIterator[dict]:
    """Put the closest starter template on screen right away when the app is still the blank one."""
    if fresh_template(files) != "blank":
        return
    tid = pick_template(request)
    if not tid:
        return
    call_id = f"start-{uuid.uuid4().hex[:8]}"
    yield {"type": "tool_start", "id": call_id, "name": "start_template", "label": "Setting up a starting point",
           "args": {"template": tid}}
    for path in _plain(files):
        if path not in apps.TEMPLATES[tid]:
            await apps.delete_file(app_id, path)
    for path, content in apps.TEMPLATES[tid].items():
        await apps.write_file(app_id, path, content)
    yield {"type": "tool_end", "id": call_id, "name": "write_file", "ok": True,
           "summary": f"Showing the {tid} starter while I write yours", "output": "", "media": []}


class _Reader:
    """Reads the streamed reply line by line: text outside code blocks, and code blocks that name a file."""

    def __init__(self, force_path: Optional[str] = None):
        self.force = force_path
        self.buf = ""
        self.path: Optional[str] = None
        self.lines: List[str] = []
        self.used: set = set()

    def feed(self, delta: str, final: bool = False) -> List[tuple]:
        self.buf += delta
        out = []
        parts = self.buf.split("\n")
        self.buf = "" if final else parts.pop()
        for line in parts:
            out.extend(self._line(line))
        if final and self.path is not None:
            out.append(("close", self.path, "\n".join(self.lines)))
            self.path = None
        return out

    def _line(self, line: str) -> List[tuple]:
        if self.path is None:
            m = _FENCE_OPEN.match(line)
            if not m:
                return [("text", line + "\n")]
            path = self.force or m.group(2) or _DEFAULT_NAMES.get(m.group(1).lower())
            if path in self.used and not m.group(2) and not self.force:
                path = None
            try:
                path = apps.clean_path(path) if path else f"extra-{len(self.used) + 1}.txt"
            except ValueError:
                path = f"extra-{len(self.used) + 1}.txt"
            self.path, self.lines = path, []
            self.used.add(path)
            return [("open", path)]
        if _FENCE_CLOSE.match(line):
            done = ("close", self.path, "\n".join(self.lines))
            self.path = None
            return [done]
        self.lines.append(line)
        return [("code", self.path, line + "\n")]


async def draft(stream_fn, app_id: str, model: str, llm_messages: list, rules: Optional[str] = DRAFT_RULES,
                force_path: Optional[str] = None) -> AsyncIterator[dict]:
    """Stream the one-reply build. Yields text, code_draft and write_file step events; the last event is
    {"type": "draft_done", "files": [paths written], "plan": [...], "said": "the reply's text"}.
    `rules` None sends `llm_messages` as they are (a fix writes its own request); `force_path` saves every block
    as that file (a fix of js/app.js answered as "```js app.js" must not add a second app.js)."""
    messages = list(llm_messages)
    last = messages[-1] if messages else None
    if rules is None:
        pass
    elif last and last.get("role") == "user" and isinstance(last.get("content"), str):
        messages[-1] = {**last, "content": last["content"] + "\n\n" + rules}
    elif last and last.get("role") == "user" and isinstance(last.get("content"), list):
        messages[-1] = {**last, "content": last["content"] + [{"type": "text", "text": rules}]}
    else:
        messages.append({"role": "user", "content": rules})
    reader = _Reader(force_path)
    written, plan, said, pending, steps = [], [], [], {}, {}
    key = uuid.uuid4().hex[:6]

    async def handle(items):
        for item in items:
            kind = item[0]
            if kind == "text":
                said.append(item[1])
                if not written and not steps:
                    m = _BULLET.match(item[1])
                    if m and len(plan) < MAX_PLAN:
                        plan.append(m.group(1).strip())
                yield {"type": "text", "text": item[1]}
            elif kind == "open":
                path = item[1]
                steps[path] = f"fast-{key}-{len(steps)}"
                pending[path] = ""
                yield _event("start", steps[path], "Writing " + path, path)
            elif kind == "code":
                path = item[1]
                pending[path] += item[2]
                if len(pending[path]) >= 160:
                    yield {"type": "code_draft", "key": steps[path], "path": path, "mode": "write",
                           "text": pending[path], "reset": False}
                    pending[path] = ""
            elif kind == "close":
                path, content = item[1], item[2] + "\n"
                if pending.get(path):
                    yield {"type": "code_draft", "key": steps[path], "path": path, "mode": "write",
                           "text": pending[path], "reset": False}
                    pending[path] = ""
                try:
                    await apps.write_file(app_id, path, content)
                    written.append(path)
                    yield _event("end", steps[path], "", path, True, f"Wrote {path}")
                except ValueError as exc:
                    yield _event("end", steps[path], "", path, False, str(exc)[:200])

    reply: List[str] = []
    for attempt in range(MAX_CONTINUE + 1):
        ask = messages if attempt == 0 else messages + [
            {"role": "assistant", "content": "".join(reply)},
            {"role": "user", "content": continue_rules(reader.path, "".join(reply)[-CONTINUE_TAIL:])}]
        held = "" if attempt > 0 else None
        async for ev in stream_fn(model, ask, []):
            if ev["type"] == "text":
                text = ev["text"]
                if held is not None:
                    # The model sometimes opens the block again ("```js app.js") before going on.
                    decided, text = continuation_start(held + text)
                    held = None if decided else held + ev["text"]
                    if not decided:
                        continue
                reply.append(text)
                async for out in handle(reader.feed(text)):
                    yield out
            elif ev["type"] == "heartbeat":
                yield ev
        if held:  # the continuation was only a fence line: the closing ```
            reply.append(held)
            async for out in handle(reader.feed(held)):
                yield out
        if reader.path is None:
            break  # every file was closed: nothing was cut off
        # The reply ran out of room inside a file. Saving it like this left app.js cut off ("Unexpected end of
        # input"), so the model is asked to go on from where it stopped instead.
    async for out in handle(reader.feed("", final=True)):
        yield out
    yield {"type": "draft_done", "files": written, "plan": plan, "said": "".join(said)}


async def tidy_starter(app_id: str, template: Optional[str], written: List[str]) -> None:
    """Remove starter files the new app neither replaced nor uses (an old app.js next to a new main.js)."""
    if not template or not written:
        return
    files = await apps.snapshot(app_id)
    used = "\n".join(files.get(p, "") for p in written)
    for path in apps.TEMPLATES.get(template, {}):
        if path not in written and path in files and path.rsplit("/", 1)[-1] not in used:
            await apps.delete_file(app_id, path)


# ------------------------------------------------------------------ fixing one broken file without tools
# The free builders often answer a repair request with chat ("Sure! What would you like to build?") instead of
# calling edit_file. A file that doesn't parse (usually cut off) is fixed the way the first build is written:
# one reply holding the whole corrected file, saved when its block closes, and continued if it is cut off again.
_PROBLEM_FILE = re.compile(r"^([\w\-./]+\.(?:m?js|jsx|tsx?|html?|css))\b has\b")
FIX_SYSTEM = ("You are Krish AI, a senior engineer fixing a broken file in the user's web app. You never chat, "
              "greet or ask questions: you answer with the complete corrected file and one short line.")


def broken_file(problem: str, files: Dict[str, str]) -> Optional[str]:
    """The file a syntax-error problem names, when it is in the app, else None."""
    m = _PROBLEM_FILE.match(problem or "")
    if not m or m.group(1) not in files:
        return None
    return m.group(1) if re.search(r"syntax error|doesn't compile|cut off", problem) else None


def fix_room(model: str) -> int:
    """Characters of a file that fit in a fix request, with room left for the whole file to come back."""
    if not agent_llm.lean(model):
        return 60000
    return max(0, int((agent_llm.token_budget(model) - 4000) / 2 * agent_llm._CHARS_PER_TOKEN))


def fix_messages(path: str, code: str, problem: str, request: str) -> List[dict]:
    ext = path.rsplit(".", 1)[-1].lower()
    lang = {"mjs": "js", "htm": "html"}.get(ext, ext)
    ask = f"\n\nWhat the user asked this app to do:\n{request.strip()[:2500]}" if request.strip() else ""
    return [{"role": "system", "content": FIX_SYSTEM}, {"role": "user", "content": (
        f"The automatic test of the app found this problem:\n{problem}{ask}\n\n"
        f"Here is {path} as it is now ({code.count(chr(10)) + 1} lines):\n````{lang}\n{code}\n````\n\n"
        f"Write the complete corrected {path} as one code block whose first line names the file:\n"
        f"```{lang} {path}\n...\n```\n"
        "Keep everything that works, finish anything that was cut off, and make every feature the user asked "
        "for work. Never write \"...\" or leave a part out. After the block, one short line saying what you "
        "fixed. No greeting, no questions, no plan.")}]
