"""Plan first, then check the plan: how the free models build a whole app instead of half of one.

The App Builder prompt already asks for a short plan, but the free models often skip it and stop at a skeleton.
So for a new app or a big change, Krish first makes one quick call for a checklist of what the app needs (screens,
features, files), and the builder follows it. When the build passes the automatic checks, one more call compares
the files with that checklist; anything missing or faked goes back to the builder as a problem to fix, just like
a broken script would.
"""
import json
import logging
import re
from typing import Dict, List, Optional

from agent import llm as agent_llm

logger = logging.getLogger("radha.build_plan")

# A request this long (in words) is a big change even in an app that already has files.
BIG_ASK_WORDS = 25
# Room for the reasoning that comes before the answer, too (both calls reason like a build does).
PLAN_OUTPUT = 2500
CHECK_OUTPUT = 2000
MAX_ITEMS = 10
# Words that start a fix or a small tweak: those turns go straight to the builder.
_SMALL_ASK = re.compile(r"^\s*(fix|change|make (it|the|this)|move|rename|remove|delete|undo|why|what|can you fix|"
                        r"thik|theek|sahi)\b", re.IGNORECASE)

# Asks that only change what's there ("remove the dropdown", "index se footer hatao"), even as the first message
# in an app opened from code: planning those would rebuild the app.
_EDIT_ONLY = re.compile(r"\b(remove|delete|get rid of|take out|hata|hatao|nikal\w*|rename|replace|change|badal\w*|"
                        r"fix|edit|update|modify)\b", re.IGNORECASE)

PLAN_PROMPT = (
    "You plan web apps for Krish AI's app builder. The builder writes a static web app (HTML, CSS and JavaScript "
    "modules, libraries from CDNs, no build step). Read the user's request and the app's current files, and write "
    "the checklist the finished app must meet: 5 to {n} lines, each starting with \"- \", each one concrete thing a "
    "user can see or do (a screen, a section, a working button or form, saved data, the sample content), and a last "
    "line naming the files to write. When the app already has its own pages and the request changes part of them, "
    "list only that change and add \"Keep everything else exactly as it is\". Pick sensible details yourself for anything the user left open. Write only the "
    "checklist, in English, with no intro and no code."
)

CHECK_PROMPT = (
    "You review a web app Krish AI's app builder just wrote. Compare the files with the checklist the app had to "
    "meet. For each checklist item that is missing, only a placeholder, or wired to code that does nothing (a "
    "button with no handler, a form that doesn't save, \"coming soon\" text, an empty list with no sample data), "
    "name it and the file to fix in one short sentence. Ignore styling taste and the line that names the files. "
    "Reply with JSON only: {\"missing\": [\"...\"]}, an empty list when everything is there."
)


def wants_plan(history_docs: list, model: str) -> bool:
    """True when this App Builder turn should start with a plan: the first request in the app's chat, or a long
    one. Not for paid models (they plan on their own) or a small fix."""
    if agent_llm.paid(model):
        return False
    users = [m for m in history_docs if m["role"] == "user"]
    if not users:
        return False
    text = (users[-1].get("content") or "").strip()
    if not text or "```" in text or "<html" in text.lower() or _SMALL_ASK.match(text):
        return False
    if _EDIT_ONLY.search(text):
        return False
    return len(users) == 1 or len(text.split()) >= BIG_ASK_WORDS


async def _ask(model: str, system: str, user: str, max_output: int) -> str:
    said = []
    async for ev in agent_llm.stream_completion(model, [{"role": "system", "content": system},
                                                        {"role": "user", "content": user}], [],
                                                think=agent_llm.DEEPER, max_output=max_output):
        if ev["type"] == "text":
            said.append(ev["text"])
    return "".join(said).strip()


def _items(text: str) -> List[str]:
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip() for line in text.splitlines()]
    return [line for line in lines if line][:MAX_ITEMS + 1]


async def make_plan(model: str, request: str, files: Dict[str, str]) -> List[str]:
    """The checklist for this build, or [] when the model can't make one (the build then goes ahead without it)."""
    listing = "\n".join(f"- {p} ({len(c)} chars)" for p, c in sorted(files.items())) or "(no files yet)"
    try:
        text = await _ask(model, PLAN_PROMPT.format(n=MAX_ITEMS),
                          f"The user's request:\n{request}\n\nThe app's files now:\n{listing}", PLAN_OUTPUT)
    except Exception as exc:
        logger.warning("planning the app failed: %s", str(exc)[:300])
        return []
    items = _items(text)
    return items if len(items) >= 3 else []


def plan_message(items: List[str]) -> str:
    return ("Build plan for this request (follow it: every item must really work when you finish, not as a "
            "placeholder):\n- " + "\n- ".join(items))


def _files_text(files: Dict[str, str], room: int) -> Optional[str]:
    """The app's text files for the review, or None when they don't fit in `room` characters."""
    parts = [f"=== {p} ===\n{c}" for p, c in sorted(files.items())
             if not p.startswith(("assets/", "samples/")) and p.endswith((".html", ".htm", ".css", ".js", ".mjs", ".json"))]
    text = "\n\n".join(parts)
    return text if text and len(text) <= room else None


async def missing_features(model: str, items: List[str], files: Dict[str, str]) -> List[str]:
    """What the plan asked for that the files don't do, as problems for the builder to fix ([] when all is there,
    or when the files are too big to review on this model's budget)."""
    if not items:
        return []
    budget = agent_llm.token_budget(model) if agent_llm.lean(model) else 60000
    room = int((budget - CHECK_OUTPUT - 1500) * agent_llm._CHARS_PER_TOKEN)
    code = _files_text(files, room)
    if code is None:
        return []
    try:
        text = await _ask(model, CHECK_PROMPT, "Checklist:\n- " + "\n- ".join(items) + "\n\nFiles:\n" + code,
                          CHECK_OUTPUT)
        found = re.search(r"\{.*\}", text, re.DOTALL)
        missing = json.loads(found.group(0)).get("missing") if found else []
    except Exception as exc:
        logger.warning("checking the app against its plan failed: %s", str(exc)[:300])
        return []
    if not isinstance(missing, list):
        return []
    return [f"Not done yet: {m.strip()}" for m in missing if isinstance(m, str) and m.strip()][:6]
