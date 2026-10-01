"""RADHA's memory of the user: facts it keeps across chats.

Facts are added by hand (the Memory panel, project pages) or learned automatically
from what the user says ("my shop is in Pune", "call me Raj", "remember that...").
Learning runs in the background after a message is sent, with a small free model,
and only when the message looks like it tells RADHA something about the user.
The user can see, add and delete every fact, and turn learning off.
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from agent import llm as agent_llm

logger = logging.getLogger("radha.memory")

MAX_FACTS = 60
_MAX_FACT_CHARS = 300

# Words that suggest the user is saying something about themselves or asking RADHA to (un)remember.
_HINT = re.compile(
    r"\b(my|mine|i am|i'm|im|i work|i run|i own|i have|i live|i prefer|i like|i love|i hate|i don'?t like|"
    r"we are|we're|our|call me|name is|remember|forget|don'?t forget|note that|from now on|always|never|"
    r"mera|meri|mere|mujhe|main|hum|hamara|hamari|yaad)\b",
    re.IGNORECASE,
)

_PROMPT = """You maintain a short list of lasting facts about a user of an AI assistant.
Read the user's new message and decide what to change in the list.

Save only durable, personal facts useful in future chats: their name or what to call them, their business or job,
company, products, customers, city or country, language, goals, and how they like answers (tone, length, format).
Do NOT save one-off requests, questions, temporary tasks, things about other people, or anything already in the list.
Never save passwords, card numbers, bank details, OTPs or other secrets.
If the user asks to forget something, remove the matching fact. If a new fact replaces an old one, remove the old one.
Write each new fact as one short sentence in third person, e.g. "Runs a bakery called Sweet Crumbs in Pune."

Current facts:
{facts}

User's new message:
\"\"\"{message}\"\"\"

Reply with JSON only: {{"add": ["..."], "remove": ["exact text of a current fact"]}}. Use empty lists when nothing changes."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def worth_checking(text: str) -> bool:
    return bool(text) and len(text) <= 2000 and bool(_HINT.search(text))


def learning_model(chat_model: str) -> Optional[str]:
    """A small model for fact extraction: MEMORY_MODEL, Groq's free gpt-oss-20b, or the chat model."""
    if os.environ.get("MEMORY_MODEL"):
        return os.environ["MEMORY_MODEL"]
    if os.environ.get("GROQ_API_KEY") and not agent_llm.gateway():
        return "openai/gpt-oss-20b"
    return chat_model if agent_llm.configured(chat_model) else None


async def auto_enabled(db, user_id: str) -> bool:
    doc = await db.users.find_one({"id": user_id}, {"memoryAuto": 1})
    return (doc or {}).get("memoryAuto", True) is not False


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def _ask(model: str, prompt: str) -> str:
    import litellm
    kwargs = {"model": agent_llm.litellm_model(model),
              "messages": [{"role": "user", "content": prompt}], "max_tokens": 700, "timeout": 45}
    gw = agent_llm.gateway()
    if gw:
        kwargs.update(model=f"openai/{model}", **gw)
    if model.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = "low"
    resp = await litellm.acompletion(**kwargs)
    return resp.choices[0].message.content or ""


async def learn(db, user_id: str, message: str, chat_model: str, ask=None) -> dict:
    """Update the user's global facts from one message. Returns {"added": [...], "removed": [...]}.

    Never raises: memory is a nice-to-have and must not break chat.
    """
    result = {"added": [], "removed": []}
    try:
        if not worth_checking(message) or not await auto_enabled(db, user_id):
            return result
        model = learning_model(chat_model)
        if not model:
            return result
        facts = await db.memories.find({"userId": user_id, "projectId": None}).sort("createdAt", 1).to_list(MAX_FACTS)
        listing = "\n".join(f"- {f['content']}" for f in facts) or "(none yet)"
        reply = await (ask or _ask)(model, _PROMPT.format(facts=listing, message=message[:2000]))
        data = _parse(reply)

        by_text = {f["content"].strip().lower(): f for f in facts}
        for text in data.get("remove") or []:
            doc = by_text.get(str(text).strip().lower().lstrip("- ").strip())
            if doc:
                await db.memories.delete_one({"id": doc["id"]})
                by_text.pop(doc["content"].strip().lower(), None)
                result["removed"].append(doc["content"])

        for text in data.get("add") or []:
            text = str(text).strip().lstrip("- ").strip()[:_MAX_FACT_CHARS]
            if len(text) < 3 or text.lower() in by_text:
                continue
            if len(by_text) >= MAX_FACTS:
                break
            doc = {"id": str(uuid.uuid4()), "userId": user_id, "projectId": None, "content": text,
                   "source": "auto", "createdAt": now_iso()}
            await db.memories.insert_one(doc)
            by_text[text.lower()] = doc
            result["added"].append(text)
    except Exception:
        logger.exception("Memory learning failed")
    return result


async def prompt_section(db, user_id: str, project_id: Optional[str]) -> str:
    """System-prompt text with what RADHA knows about the user, or "" when nothing."""
    user = await db.users.find_one({"id": user_id}, {"name": 1})
    query = {"userId": user_id, "$or": [{"projectId": None}, {"projectId": project_id}]}
    facts = await db.memories.find(query).sort("createdAt", -1).to_list(MAX_FACTS)
    lines = []
    if user and user.get("name"):
        lines.append(f"- Account name: {user['name']}")
    lines += [f"- {m['content']}" for m in facts]
    if not lines:
        return ""
    return (
        "What you remember about the user (from past chats and their Memory settings). Use it naturally to "
        "personalise answers; don't recite it unless asked. If they ask what you remember, list it and say "
        "they can edit it under Memory in the menu.\n" + "\n".join(lines)
    )
