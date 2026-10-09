"""Change code the user gave Krish (attached, pasted, or shown earlier in the chat) without losing any of it.

Free models can't hold a 1,000-line page in their prompt, and none can write one back in a single reply, so
asking them to "make it light theme" used to get a small new page instead of the user's. Here the model never
rewrites the file: it reads it a part at a time and answers with small SEARCH/REPLACE edits, which are applied
to the user's own text. Everything it doesn't touch stays byte for byte as given, and the reply carries the
whole file under its own name, so the chat's preview shows the user's page with only the asked-for change.
"""
import re
from typing import AsyncIterator, Callable, Dict, List, Optional, Tuple

from agent import llm as agent_llm

# A fenced block (``` or longer, so a file that itself holds ``` still parses) and the file name on its info line.
_FENCE_RE = re.compile(r"(?:^|\n)[ \t]*(`{3,})([^\n`]*)\n(.*?)\n[ \t]*\1(?!`)", re.DOTALL)
_FILE_RE = re.compile(r"([\w\-./]*[\w-]\.(?:html?|s?css|m?js|cjs|jsx|tsx?|json|svg|md|txt|xml|py|vue|php))\b",
                      re.IGNORECASE)
_HTML_DOC_RE = re.compile(r"((?:<!doctype html[^>]*>\s*)?<html\b.*?</html>)", re.IGNORECASE | re.DOTALL)
_DEFAULT_NAMES = {"html": "index.html", "htm": "index.html", "css": "style.css", "js": "app.js",
                  "javascript": "app.js", "jsx": "App.jsx"}
_LANGS = {"htm": "html", "mjs": "js", "cjs": "js", "md": "markdown"}

# Messages that ask for a change to the code, not about it. English and the Hinglish people type.
_EDIT_WORDS = re.compile(
    r"\b(make|change|convert|turn|add|remove|delete|replace|fix|update|modify|edit|rename|translate|improve|"
    r"redesign|restyle|style|move|swap|put|set|increase|decrease|reduce|bigger|smaller|larger|light|dark|theme|"
    r"colou?rs?|font|responsive|mobile|cent(?:er|re)|align|hide|insert|switch|bana|banao|badal|badlo|hata|hatao|"
    r"jod|jodo|daal|daalo)\b", re.IGNORECASE)
# ...unless it is a question about the code ("what does this do?", "explain the script").
_ASKS_ABOUT = re.compile(r"^\s*(what|why|explain|describe|summari[sz]e|review|is|are|does|which|who|when|where|"
                         r"tell me (?:about|what)|can you explain)\b", re.IGNORECASE)

# ...or a new thing to build ("make a gym website", "now create another game").
_NEW_BUILD = re.compile(
    r"\b(make|create|build|generate|design|write|code|bana(?:o|do)?)\s+(?:me\s+|us\s+)?(?:a|an|another|new|one|ek)\s+"
    r"(?:\w+\s+){0,4}?(website|site|web\s*site|app|game|tool|landing|portfolio|dashboard|calculator|clone|"
    r"web\s*app|application|program|project)\b"
    r"|\b(?:ek|new|naya|nayi|another)\s+(?:\w+\s+){0,3}?(?:website|site|app|game|tool|portfolio|dashboard)\s+"
    r"(?:bana\w*|create|make|build)\b", re.IGNORECASE)

# Past this, code Krish wrote is changed with edits too: free models only see the first 2,000 characters of an
# earlier reply, so asked to "make it blue" they rewrote the page from memory and lost parts of it.
BIG_CODE = 3000
RECENT_MESSAGES = 8   # how far back a follow-up ("now make the buttons blue") may refer to the code
_MAX_PART = 40000     # characters per request, so one part's edits fit in one reply
_OUTPUT = 8000        # tokens of edits a request may write
_PROMPT_ROOM = 1200   # tokens of instructions around each part

_BLOCK_RE = re.compile(r"<{5,9}[ \t]*SEARCH[^\n]*\n(.*?)\n?={5,9}[ \t]*\n(.*?)\n?>{5,9}[ \t]*REPLACE", re.DOTALL)
_SUMMARY_RE = re.compile(r"^\s*SUMMARY:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

SYSTEM = ("You are Krish AI, an expert code editor. The user gave you their own file and wants it changed. You "
          "change exactly what they ask, in place, and keep everything else (content, text, scripts, features, "
          "layout) as it is. You never replace their file with a new or shorter one.")


def _block_name(info: str, code: str) -> Optional[str]:
    """The file a fenced block holds, from its info line ("html index.html"), or None for a snippet."""
    lang = (info.split() or [""])[0].lower()
    named = _FILE_RE.search(info)
    name = named.group(1).lstrip("./") if named else None
    if not name and (lang in ("html", "htm") or re.match(r"\s*(<!doctype|<html)", code, re.I)):
        name = "index.html"
    elif not name and lang in _DEFAULT_NAMES and code.count("\n") >= 30:
        name = _DEFAULT_NAMES[lang]
    return name if name and code.strip() and ".." not in name.split("/") else None


def code_files(text: str, raw_html: bool = False) -> Dict[str, str]:
    """{name: code} for the fenced code blocks in a message that are files (named, or a whole page).

    `raw_html` also takes an unfenced HTML page pasted straight into the message.
    """
    files: Dict[str, str] = {}
    for m in _FENCE_RE.finditer(text or ""):
        name = _block_name(m.group(2).strip(), m.group(3))
        if name:
            files[name] = m.group(3)
    if not files and raw_html:
        m = _HTML_DOC_RE.search(text or "")
        if m:
            files["index.html"] = m.group(1).strip()
    return files


def fence_for(code: str) -> str:
    """Backticks that fence `code` safely: one more than the longest run inside it."""
    return "`" * max([3] + [len(t) + 1 for t in re.findall(r"`{3,}", code)])


def block(path: str, code: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    fence = fence_for(code)
    return f"{fence}{_LANGS.get(ext, ext)} {path}\n{code.rstrip()}\n{fence}"


def close_fence(text: str) -> Tuple[str, Optional[str]]:
    """(text with a code block that was cut off mid-way closed, the fence that was missing or None).

    A reply that ran out of room stops inside its last file; closing the fence lets that file be read.
    """
    open_ticks = None
    for line in (text or "").split("\n"):
        m = re.match(r"[ \t]*(`{3,})(.*)$", line)
        if not m:
            continue
        if open_ticks is None:
            open_ticks = m.group(1)
        elif m.group(1) == open_ticks and not m.group(2).strip():
            open_ticks = None
    if open_ticks is None:
        return text, None
    return text.rstrip("\n") + "\n" + open_ticks, open_ticks


def replace_blocks(text: str, files: Dict[str, str]) -> str:
    """`text` with each named file's code block swapped for the new code; files it doesn't have are added at the end."""
    done = set()

    def swap(m):
        name = _block_name(m.group(2).strip(), m.group(3))
        if name in files and name not in done:
            done.add(name)
            lead = m.group(0)[:len(m.group(0)) - len(m.group(0).lstrip("\n"))]
            return lead + block(name, files[name])
        return m.group(0)

    out = _FENCE_RE.sub(swap, text or "")
    extra = [block(p, c) for p, c in files.items() if p not in done]
    return out.rstrip() + ("\n\n" + "\n\n".join(extra) if extra else "")


def without_code(text: str) -> str:
    """The words of a message, without its code blocks or a pasted page."""
    text = _FENCE_RE.sub("\n", text or "")
    return _HTML_DOC_RE.sub("\n", text).strip()


def wants_edit(words: str) -> bool:
    """True when the words ask for a change to the code rather than a question about it or something new."""
    words = (words or "").strip()
    return (bool(words) and bool(_EDIT_WORDS.search(words)) and not _ASKS_ABOUT.match(words)
            and not _NEW_BUILD.search(words))


def find_target(history: List[dict]) -> Tuple[Optional[Dict[str, str]], Optional[dict]]:
    """The code a new ask should change: the latest files in the last few messages, with the message they came from.

    History is oldest first and ends with the new user message.
    """
    for msg in reversed(history[-RECENT_MESSAGES:]):
        files = code_files(msg.get("content") or "", raw_html=msg.get("role") == "user")
        if files:
            return files, msg
    return None, None


def should_edit(history: List[dict]) -> Optional[Tuple[Dict[str, str], str]]:
    """(files, the ask) when the latest message asks to change code the user gave, else None.

    Code the user gave (attached, pasted, or a reply that already carries their code) is always edited in place.
    Code Krish wrote itself is too, once it's too big for a model to write back whole.
    """
    if not history or history[-1].get("role") != "user":
        return None
    ask = without_code(history[-1].get("content") or "")
    if not wants_edit(ask):
        return None
    files, origin = find_target(history)
    if not files:
        return None
    theirs = origin.get("role") == "user" or origin.get("userCode")
    if not theirs and sum(len(c) for c in files.values()) < BIG_CODE:
        return None
    return files, ask


def editing_model(model: str) -> str:
    """The model that edits: the chosen one, unless it's on a small free budget and a roomier one is set up."""
    if not agent_llm.lean(model) or agent_llm.provider_for(model) == "cerebras":
        return model
    for roomier in ("cerebras/gpt-oss-120b", "gemini-3.5-flash-lite"):
        if agent_llm.configured(roomier):
            return roomier
    return model


def part_size(model: str) -> int:
    """Characters of code per request for this model."""
    if not agent_llm.lean(model):
        return _MAX_PART
    room = agent_llm.token_budget(model) - min(_OUTPUT, agent_llm.token_budget(model) // 3) - _PROMPT_ROOM
    return max(4000, min(_MAX_PART, int(room * 2.6)))


def split_parts(code: str, size: int) -> List[str]:
    """The code cut at line ends into parts of about `size` characters, which join back to the same text."""
    lines = code.splitlines(keepends=True)
    parts, current = [], ""
    for line in lines:
        if current and len(current) + len(line) > size:
            parts.append(current)
            current = ""
        current += line
    if current or not parts:
        parts.append(current)
    return parts


def parse_edits(reply: str) -> List[Tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _BLOCK_RE.finditer(reply or "")]


def apply_edit(text: str, search: str, replace: str) -> Optional[str]:
    """`text` with the first match of `search` replaced, or None when it isn't there.

    Models often get indentation or trailing spaces wrong, so lines are also matched with spaces trimmed.
    """
    if search and search in text:
        return text.replace(search, replace, 1)
    want = [l.strip() for l in search.strip("\n").split("\n")]
    if not any(want):
        return None
    lines = text.split("\n")
    for i in range(len(lines) - len(want) + 1):
        if all(lines[i + j].strip() == w for j, w in enumerate(want)):
            # Keep the file's own indentation when the model dropped it: each new line takes the indentation of
            # the line it replaces (the last one's for lines it adds).
            old = lines[i:i + len(want)]
            new = replace.split("\n") if replace else []
            if not any(l.startswith((" ", "\t")) for l in new):
                indents = [re.match(r"[ \t]*", l).group(0) for l in old]
                new = [(indents[min(j, len(indents) - 1)] + l) if l.strip() else l for j, l in enumerate(new)]
            return "\n".join(lines[:i] + new + lines[i + len(want):])
    return None


def _prompt(path: str, ask: str, part: str, index: int, total: int, first_line: int, line_count: int) -> str:
    last_line = first_line + part.count("\n")
    where = (f"You see part {index} of {total}: lines {first_line} to {last_line}. The other parts are edited "
             "separately, so change only what is in this part. Add something new (a section, a style block, a "
             "script) only once: in the part that holds the right place for it."
             if total > 1 else "You see the whole file.")
    ext = path.rsplit(".", 1)[-1].lower()
    return (
        f'The user\'s request: "{ask}"\n\n'
        f"File: {path} ({line_count} lines). {where}\n\n"
        "Reply with SEARCH/REPLACE blocks only, like this:\n"
        "<<<<<<< SEARCH\n(a few lines copied exactly from the file)\n=======\n(the same lines, changed)\n"
        ">>>>>>> REPLACE\n\n"
        "Rules:\n"
        "- Copy SEARCH lines exactly as they are in the file, with enough lines to be unique. Keep blocks small.\n"
        "- Make every change the request needs here. For a colour or theme change that means every background, "
        "text, border, shadow and gradient colour, including colours set in inline styles and in JavaScript, "
        "so the whole page matches and text stays easy to read.\n"
        "- Don't touch anything else: keep all content, text, scripts and features.\n"
        "- If nothing here needs changing, reply NONE.\n"
        "- End with one line: SUMMARY: what you changed, in a few plain words.\n\n"
        f"Part {index}:\n````{_LANGS.get(ext, ext)}\n{part}\n````"
    )


Ask = Callable[[str, List[dict], int], AsyncIterator[dict]]


def _default_ask(model: str, messages: List[dict], max_output: int) -> AsyncIterator[dict]:
    return agent_llm.stream_completion(model, messages, [], max_output=max_output)


async def run(model: str, files: Dict[str, str], ask: str, ask_model: Ask = _default_ask) -> AsyncIterator[dict]:
    """Edit `files` as `ask` says. Yields {"type": "heartbeat"}, {"type": "part", "path", "index", "total"} when a
    part starts, {"type": "part_done", "path", "index", "applied", "missed"}, then one
    {"type": "result", "files", "applied", "missed", "summaries"}."""
    size = part_size(model)
    result: Dict[str, str] = {}
    applied = missed = 0
    summaries: List[str] = []
    for path, code in files.items():
        parts = split_parts(code, size)
        line_count = code.count("\n") + 1
        first_line = 1
        out = []
        for i, part in enumerate(parts, 1):
            yield {"type": "part", "path": path, "index": i, "total": len(parts)}
            messages = [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": _prompt(path, ask, part, i, len(parts), first_line, line_count)}]
            reply = []
            async for ev in ask_model(model, messages, _OUTPUT):
                if ev["type"] == "text":
                    reply.append(ev["text"])
                elif ev["type"] == "heartbeat":
                    yield ev
            text = "".join(reply)
            new, got, lost = part, 0, 0
            for search, replace in parse_edits(text):
                changed = apply_edit(new, search, replace)
                if changed is None:
                    lost += 1
                else:
                    new, got = changed, got + 1
            # A part that ended with a newline still ends with one, so the parts join up as before.
            if part.endswith("\n") and not new.endswith("\n"):
                new += "\n"
            m = _SUMMARY_RE.search(text)
            if m and got and m.group(1).strip().rstrip(".") not in summaries:
                summaries.append(m.group(1).strip().rstrip("."))
            applied, missed = applied + got, missed + lost
            yield {"type": "part_done", "path": path, "index": i, "applied": got, "missed": lost}
            out.append(new)
            first_line += part.count("\n")
        result[path] = "".join(out)
    yield {"type": "result", "files": result, "applied": applied, "missed": missed, "summaries": summaries}


def reply_text(original: Dict[str, str], edited: Dict[str, str], applied: int, missed: int,
               summaries: List[str]) -> str:
    """The chat reply: what changed, then every file whole, under its own name, for the preview."""
    names = ", ".join(original)
    if not applied or edited == original:
        why = "my edits didn't match the code" if missed else "I couldn't find what to change"
        return (f"I couldn't make that change to {names}: {why}, so I left your file "
                "exactly as it was rather than give you a different one. Try saying what to change in a little "
                "more detail (for example which part or colour), or pick another model from the menu at the top.")
    what = "; ".join(summaries[:4]) or "made the change you asked for"
    lines = sum(c.count("\n") + 1 for c in edited.values())
    head = (f"Done. I edited your {names} in place ({applied} change{'s' if applied != 1 else ''}: {what[0].lower() + what[1:]}) "
            f"and kept everything else exactly as it was. The full file ({lines} lines) is below and in the preview.")
    return head + "\n\n" + "\n\n".join(block(p, c) for p, c in edited.items())
