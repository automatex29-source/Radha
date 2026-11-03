"""Show a file while the model is still typing it.

A write_file call arrives as JSON in small pieces ({"path": "index.html", "content": "<!doctype ...). The App
Builder shows that file growing in the chat, so a build feels as fast as it really is instead of sitting on
"Writing index.html" for half a minute. These helpers read the path and the content written so far out of
unfinished JSON, and turn each new piece into a {"type": "code_draft"} event.
"""
import json
import re
from typing import Dict, Optional

DRAFT_TOOLS = {"write_file", "append_file"}
MIN_CHARS = 160  # send the code in pieces of at least this much, so a long file is a few dozen events, not thousands
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def partial_string(raw: str, field: str) -> Optional[str]:
    """The decoded value of the JSON string `field` in `raw`, which may stop part-way (even inside an escape).
    None when the field hasn't started."""
    m = re.search(r'"' + re.escape(field) + r'"\s*:\s*"', raw)
    if not m:
        return None
    out, i, n = [], m.end(), len(raw)
    while i < n:
        ch = raw[i]
        if ch == '"':
            break
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            break  # the escape isn't complete yet
        esc = raw[i + 1]
        if esc == "u":
            if i + 6 > n:
                break
            try:
                code = int(raw[i + 2:i + 6], 16)
            except ValueError:
                break
            if 0xD800 <= code < 0xDC00:  # a surrogate pair: wait for both halves
                if i + 12 > n:
                    break
                try:
                    out.append(json.loads('"' + raw[i:i + 12] + '"'))
                except ValueError:
                    out.append("�")
                i += 12
                continue
            out.append(chr(code))
            i += 6
            continue
        out.append(_ESCAPES.get(esc, esc))
        i += 2
    return "".join(out)


class DraftTracker:
    """Turns tool_draft events (the call's arguments so far) into code_draft events (new code to show).

    Each event carries `key` (one per call), `path`, `mode` ("write" or "append") and `text`. `reset` is True when
    the model was asked again and the call started over, so the shown code is replaced instead of extended.
    """

    def __init__(self, step: str):
        self.step = step
        self.shown: Dict[int, str] = {}

    def update(self, ev: dict, force: bool = False) -> Optional[dict]:
        if ev.get("name") not in DRAFT_TOOLS:
            return None
        raw = ev.get("arguments") or ""
        path = partial_string(raw, "path")
        content = partial_string(raw, "content")
        if not path or content is None or not re.search(r'"path"\s*:\s*"[^"]*"', raw):
            return None  # wait until the file name is complete
        idx = ev.get("index", 0)
        before = self.shown.get(idx, "")
        reset = not content.startswith(before)
        if reset:
            before = ""
        if len(content) - len(before) < (1 if force else MIN_CHARS) and not reset:
            return None
        self.shown[idx] = content
        return {"type": "code_draft", "key": f"{self.step}-{idx}", "path": path,
                "mode": "append" if ev["name"] == "append_file" else "write",
                "text": content[len(before):], "reset": reset}
