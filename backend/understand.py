"""Read the user's latest message for what they mean, before Krish answers it.

Krish's checks for what a turn needs (search the web, keep the tool list, the coding or study prompt, which
model answers, which parts of a file to read) look at the raw words of the latest message. Fast phone typing
("iphne 17 lanch kab h"), Hinglish, voice slips and follow-ups ("aur iska price?", "same for 2nd one",
"haan bana do") slip past them: the search looked up "aur iska price", the file search looked for "it", and a
misspelt "exel shet bana do" lost the tool that makes the file.

So one quick call to a small free model reads the message with the last few turns and writes it out plainly:
the question in full, with what "it" and "that" point to, each part of a multi-part ask, a web search query
when the answer needs fresh facts, and the tool that fits. Krish uses that reading for its checks and gets it
as a hint in the prompt; the answer still comes from the full chat. Any failure or a slow reply returns None
and the turn goes on exactly as before, so this step never blocks or breaks an answer.
"""
import asyncio
import json
import logging
import os
import re
from typing import List, Optional

from agent import llm

logger = logging.getLogger("radha.understand")

TIMEOUT = float(os.environ.get("UNDERSTAND_TIMEOUT_SECONDS", "3"))
# Small, fast, free models first: Groq's gpt-oss-20b has its own per-minute budget, apart from the 120b that answers.
_MODELS = ("openai/gpt-oss-20b", "gemini-3.5-flash-lite", "cerebras/gpt-oss-120b", "openai/gpt-oss-120b")
MAX_CHARS = 1500  # a long paste (an essay, a log, code) says what it is; reading it again adds only delay
HISTORY_TURNS = 6

# The tools a reading may name; anything else is dropped.
TOOLS = ("web_search", "deep_research", "run_python", "create_spreadsheet", "create_document",
         "create_presentation", "create_file", "create_zip", "generate_image", "generate_video", "edit_image",
         "browser", "fetch_url")
KINDS = ("chat", "facts", "code", "maths", "study", "writing", "advice", "make")
LANGS = ("english", "hinglish", "hindi", "other")

SYSTEM = (
    "You read a chat message for an AI assistant before it answers. People type fast on phones: typos, missing "
    "spaces, stretched letters, short forms (u, r, pls, h = hai, kr = kar, bta = bata), voice-typing slips and "
    "Hinglish (Hindi in English letters) are normal. Work out what the user most likely means, using the earlier "
    "messages: a short follow-up (\"aur?\", \"iska price\", \"same for 2nd\", \"haan\", \"yes do it\", \"in "
    "Delhi?\") continues the chat, so name what it points to, and \"yes\"/\"haan\" after an offer means \"do "
    "what you offered\". Never answer the message.\n\n"
    "Reply with only a JSON object:\n"
    "{\"question\": the full request in clear English, typos fixed and every \"it\", \"this\", \"wo\" or "
    "\"iska\" replaced by what it means, keeping every name, number and detail the user gave;\n"
    " \"parts\": a list of the separate things asked, only when there are two or more, else [];\n"
    " \"kind\": one of chat, facts, code, maths, study, writing, advice, make;\n"
    " \"web\": true only when a good answer needs current or checkable facts from the web (news, prices, rates, "
    "scores, weather, recent events, people in a role now, product launches and specs), else false;\n"
    " \"search\": when web is true, a short English web search query (add the place or year if it matters), "
    "else \"\";\n"
    " \"tool\": the one tool the request clearly needs, else \"\": web_search, deep_research (a researched "
    "report), run_python (sums, data, charts), create_spreadsheet (Excel), create_document (Word or PDF), "
    "create_presentation (PowerPoint), create_file, create_zip, generate_image, generate_video, edit_image "
    "(change an attached picture), browser (operate a website), fetch_url (read a link);\n"
    " \"lang\": the language the user wrote in: english, hinglish, hindi or other}"
)

_SPACES = re.compile(r"\s+")
_WORDS = re.compile(r"[a-z0-9]+")
_SMALL_TALK = re.compile(
    r"^\s*(hi+|hello+|hey+|namaste|namaskar|good (morning|afternoon|evening|night)|thanks?|thank you|thx|ty|"
    r"bye|good ?bye)[\s!.,?🙏😊👍]*(krish|bro|dear|ji)?[\s!.,?🙏😊👍]*$", re.I)


def model() -> Optional[str]:
    """UNDERSTAND_MODEL, else the first small free model that is set up (None: the step is skipped)."""
    wanted = os.environ.get("UNDERSTAND_MODEL", "").strip()
    if wanted and llm.configured(wanted):
        return wanted
    return next((m for m in _MODELS if llm.configured(m)), None)


def enabled() -> bool:
    return os.environ.get("UNDERSTAND", "1") != "0" and model() is not None


def worth_reading(history_docs: List[dict]) -> bool:
    """False for a first "hi" or "thanks", a long paste or code, where a reading only adds delay."""
    users = [m for m in history_docs if m.get("role") == "user"]
    if not users:
        return False
    text = (users[-1].get("content") or "").strip()
    if not text or len(text) > MAX_CHARS or "```" in text:
        return False
    return not (_SMALL_TALK.match(text) and len(users) == 1)


def _clip(text: str, keep: int) -> str:
    """The start and end of a long message (a reply's topic comes first, its offer of a next step last)."""
    text = _SPACES.sub(" ", text or "").strip()
    if len(text) <= keep:
        return text
    half = keep // 2
    return f"{text[:half]} … {text[-half:]}"


def prompt_for(history_docs: List[dict]) -> str:
    """The reader's input: the last few turns, shortened, then the message to read."""
    turns = [m for m in history_docs if m.get("role") in ("user", "assistant")]
    at = max(i for i, m in enumerate(turns) if m["role"] == "user")
    lines = []
    for m in turns[max(0, at - HISTORY_TURNS):at]:
        said = _clip(m.get("content") or "", 500 if m["role"] == "assistant" else 300)
        if said:
            lines.append(f"{'User' if m['role'] == 'user' else 'Assistant'}: {said}")
    latest = turns[at]
    extra = f" [attached {len(latest['images'])} picture(s)]" if latest.get("images") else ""
    earlier = "Earlier messages:\n" + "\n".join(lines) + "\n\n" if lines else ""
    return f"{earlier}Message to read:{extra}\n{(latest.get('content') or '').strip()}"


def parse(text: str) -> Optional[dict]:
    """The reading as a clean dict, or None when the reply isn't usable."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    question = _SPACES.sub(" ", str(data.get("question") or "")).strip()[:600]
    if len(question) < 2:
        return None
    parts = data.get("parts") if isinstance(data.get("parts"), list) else []
    parts = [_SPACES.sub(" ", str(p)).strip()[:300] for p in parts if str(p).strip()][:6]
    kind = str(data.get("kind") or "").strip().lower()
    tool = str(data.get("tool") or "").strip().lower()
    lang = str(data.get("lang") or "").strip().lower()
    web = data.get("web") is True or str(data.get("web")).lower() == "true"
    search = _SPACES.sub(" ", str(data.get("search") or "")).strip()[:200] if web else ""
    return {
        "question": question,
        "parts": parts if len(parts) >= 2 else [],
        "kind": kind if kind in KINDS else "chat",
        "web": web,
        "search": search,
        "tool": tool if tool in TOOLS else "",
        "lang": lang if lang in LANGS else "",
    }


async def read(history_docs: List[dict]) -> Optional[dict]:
    """The reading of the latest user message (see parse), or None when it is skipped, slow or fails."""
    if not enabled() or not worth_reading(history_docs):
        return None
    out = []

    async def run():
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt_for(history_docs)}]
        async for ev in llm.stream_completion(model(), messages, [], max_output=400):
            if ev["type"] == "text":
                out.append(ev["text"])

    try:
        await asyncio.wait_for(run(), TIMEOUT)
    except Exception as exc:  # a timeout, a rate limit, a provider error: answer without the reading
        logger.info("reading the question failed, going on without it: %r", exc)
        return None
    return parse("".join(out))


def _same(a: str, b: str) -> bool:
    return _WORDS.findall((a or "").lower()) == _WORDS.findall((b or "").lower())


def prompt_note(reading: Optional[dict], said: str) -> str:
    """The reading as a hint for the answering model, or "" when it adds nothing to the message itself."""
    if not reading:
        return ""
    lines = []
    if not _same(reading["question"], said):
        lines.append(f"What they are asking, read with the chat (typos and short forms worked out): "
                     f"\"{reading['question']}\"")
    if reading["parts"]:
        listed = "\n".join(f"{n}. {p}" for n, p in enumerate(reading["parts"], 1))
        lines.append(f"The message asks {len(reading['parts'])} things. Answer every one, in this order, so none "
                     f"is missed:\n{listed}")
    if reading["tool"]:
        lines.append(f"The tool that fits this request: {reading['tool']} (if you have it).")
    if not lines:
        return ""
    return ("A quick reading of the user's latest message (if the chat shows they meant something else, follow "
            "the chat):\n" + "\n".join(lines) + "\nAnswer in the user's own language and script, not in the "
            "English of this note, and never mention this reading or their spelling.")
