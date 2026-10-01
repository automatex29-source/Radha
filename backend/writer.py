"""Docs: a side-by-side writing space, like ChatGPT's Canvas.

The user writes in an editor and asks Krish to change the whole document or just the selected part
("make this shorter", "translate to Hindi", "add a conclusion"). Every AI change can be undone, and a
document downloads as Word or PDF. Content is Markdown.
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from auth import decode_token, get_user_id_from_request

router = APIRouter(prefix="/api")
logger = logging.getLogger("radha.writer")
db = None
DEFAULT_MODEL = ""
HISTORY = 20
MAX_CONTENT = 200_000
# Groq's free tier fits about 8,000 tokens per request (prompt + answer), so whole-document edits are capped.
MAX_AI_CHARS_LEAN = 9_000
MAX_AI_CHARS = 60_000

QUICK_ACTIONS = {
    "shorter": "Make it about 40% shorter. Keep every key point.",
    "longer": "Make it more detailed: add useful explanation and examples, about 50% longer.",
    "grammar": "Fix spelling, grammar and punctuation only. Don't change the meaning or style.",
    "formal": "Rewrite in a polished, professional tone.",
    "simple": "Rewrite in simple, friendly words a 12-year-old would understand.",
    "hindi": "Translate into natural Hindi (Devanagari). Keep names, numbers and formatting.",
    "english": "Translate into natural English. Keep names, numbers and formatting.",
    "bullets": "Turn it into clear headings and bullet points.",
    "emoji": "Add a few fitting emojis, without overdoing it.",
}

SYSTEM = (
    "You are the writing assistant inside Krish AI Docs. You edit the user's document as instructed. "
    "Reply with ONLY the new text in Markdown: no preamble, no explanation, no code fences around it. "
    "Keep the user's language unless asked to translate, and keep formatting that still makes sense."
)

# Typed requests in the Ask Krish box can be anything, not just edits, so the model says which kind it is.
ASK_SYSTEM = SYSTEM + (
    "\n\nThe user may also ask something that is not an edit. Decide which kind of request it is:\n"
    "1. A change to the text (rewrite, add, remove, translate, write it): reply with only the new text, as above.\n"
    "2. A question, feedback or anything you can answer in words without changing the text: start with "
    "\"ANSWER:\" and then answer helpfully and briefly, in the user's language.\n"
    "3. Something that needs more than text, like making a video, picture, slides, audio or music from it, "
    "searching the web, or sending an email: reply with \"MAKE:\" and then one short, friendly sentence saying "
    "what you'll make. Don't make it here."
)
ANSWER_RE = re.compile(r"^\W{0,3}ANSWER\W{0,3}:\W{0,3}", re.I)
MAKE_RE = re.compile(r"^\W{0,3}MAKE\W{0,3}:\W{0,3}", re.I)
# Kept small enough for Groq's free tier along with the chat's own instructions and tools.
HANDOFF_CHARS_LEAN = 6_000
HANDOFF_CHARS = 40_000


def init(database, default_model: str):
    global db, DEFAULT_MODEL
    db = database
    DEFAULT_MODEL = default_model


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def current_user_id(request: Request) -> str:
    return get_user_id_from_request(request)


async def _complete(model: str, system: str, user: str) -> str:
    """One non-streaming answer from the model (tests replace this)."""
    from agent import llm

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out = []
    async for ev in llm.stream_completion(model, messages, []):
        if ev["type"] == "text":
            out.append(ev["text"])
    return "".join(out)


def clean_answer(text: str) -> str:
    text = (text or "").strip()
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*?)\n```", text, flags=re.S)
    return (fenced.group(1) if fenced else text).strip()


class DocIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None, max_length=MAX_CONTENT)
    prompt: Optional[str] = Field(default=None, max_length=4000)  # "write a ..." makes a first draft
    model: Optional[str] = None


class DocPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, max_length=MAX_CONTENT)


class AiEditIn(BaseModel):
    instruction: Optional[str] = Field(default=None, max_length=4000)
    action: Optional[str] = None  # one of QUICK_ACTIONS
    selection: Optional[str] = Field(default=None, max_length=MAX_CONTENT)
    model: Optional[str] = None


def public_doc(doc: dict, full: bool = True) -> dict:
    out = {"id": doc["id"], "title": doc["title"], "createdAt": doc["createdAt"], "updatedAt": doc["updatedAt"],
           "preview": (doc.get("content") or "")[:160], "canUndo": bool(doc.get("history"))}
    if full:
        out["content"] = doc.get("content") or ""
    return out


async def owned_doc(doc_id: str, user_id: str) -> dict:
    doc = await db.docs.find_one({"id": doc_id, "userId": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _title_from(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:80]
    return "Untitled document"


def _limit(model: str) -> int:
    from agent import llm
    return MAX_AI_CHARS_LEAN if llm.lean(model) else MAX_AI_CHARS


@router.get("/docs")
async def list_docs(user_id: str = Depends(current_user_id)):
    docs = await db.docs.find({"userId": user_id}, {"history": 0}).sort("updatedAt", -1).to_list(300)
    return [public_doc(d, full=False) for d in docs]


@router.get("/docs/actions")
async def doc_actions(user_id: str = Depends(current_user_id)):
    return {"actions": list(QUICK_ACTIONS)}


@router.post("/docs")
async def create_doc(body: DocIn, user_id: str = Depends(current_user_id)):
    content = body.content or ""
    if body.prompt and body.prompt.strip():
        model = body.model or DEFAULT_MODEL
        try:
            content = clean_answer(await _complete(model, SYSTEM, (
                f"Write this document: {body.prompt.strip()}\n\nStart with a # title. Make it complete and "
                "well structured, ready to use.")))
        except Exception as exc:
            logger.exception("Draft failed")
            raise HTTPException(status_code=502, detail=f"Krish couldn't write the draft: {str(exc)[:200]}")
    ts = _now()
    doc = {"id": str(uuid.uuid4()), "userId": user_id, "title": (body.title or "").strip() or _title_from(content),
           "content": content, "history": [], "createdAt": ts, "updatedAt": ts}
    await db.docs.insert_one(doc)
    return public_doc(doc)


@router.get("/docs/{doc_id}")
async def get_doc(doc_id: str, user_id: str = Depends(current_user_id)):
    return public_doc(await owned_doc(doc_id, user_id))


@router.patch("/docs/{doc_id}")
async def update_doc(doc_id: str, body: DocPatch, user_id: str = Depends(current_user_id)):
    await owned_doc(doc_id, user_id)
    updates = body.model_dump(exclude_none=True)
    if updates:
        updates["updatedAt"] = _now()
        await db.docs.update_one({"id": doc_id}, {"$set": updates})
    return public_doc(await owned_doc(doc_id, user_id))


@router.delete("/docs/{doc_id}")
async def delete_doc(doc_id: str, user_id: str = Depends(current_user_id)):
    await owned_doc(doc_id, user_id)
    await db.docs.delete_one({"id": doc_id})
    return {"ok": True}


def handoff_prompt(doc: dict, request: str, model: str) -> str:
    """The chat message that carries a doc request over to chat, where Krish's tools (video, images...) run."""
    from agent import llm

    content = doc.get("content") or ""
    cap = HANDOFF_CHARS_LEAN if llm.lean(model) else HANDOFF_CHARS
    if len(content) > cap:
        content = content[:cap] + "\n\n[…the rest of the document is cut off]"
    return f"{request}\n\nThis is my document “{doc['title']}”:\n\n{content}"


@router.post("/docs/{doc_id}/ai")
async def ai_edit(doc_id: str, body: AiEditIn, user_id: str = Depends(current_user_id)):
    doc = await owned_doc(doc_id, user_id)
    typed = not QUICK_ACTIONS.get(body.action or "")
    instruction = QUICK_ACTIONS.get(body.action or "") or (body.instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Say what to change")
    content = doc.get("content") or ""
    selection = (body.selection or "").strip()
    if selection and selection not in content:
        raise HTTPException(status_code=409, detail="The selected text changed. Select it again.")
    model = body.model or DEFAULT_MODEL
    target = selection or content
    if typed and len(target) > _limit(model):
        # Too long to send for an edit, but questions and video/picture requests can still go to chat.
        return {**public_doc(doc), "kind": "handoff", "reply": "This document is long, so let's do that in chat.",
                "handoff": handoff_prompt(doc, instruction, model)}
    if not target.strip():
        prompt = f"The document is empty. {instruction}\nStart with a # title."
    else:
        if len(target) > _limit(model):
            raise HTTPException(status_code=413, detail="That's too long to change in one go. Select a part of the "
                                                        "document and try again.")
        context = ""
        if selection:
            around = content[:6000] if len(content) <= _limit(model) else ""
            context = f"For context, the whole document is:\n<<<\n{around}\n>>>\n\n" if around else ""
            prompt = (f"{context}Change only this part of the document:\n<<<\n{selection}\n>>>\n\n"
                      f"Instruction: {instruction}\n\nReply with only the replacement for that part.")
        else:
            prompt = f"Document:\n<<<\n{content}\n>>>\n\nInstruction: {instruction}\n\nReply with the whole new document."
    try:
        answer = clean_answer(await _complete(model, ASK_SYSTEM if typed else SYSTEM, prompt))
    except Exception as exc:
        logger.exception("Doc edit failed")
        raise HTTPException(status_code=502, detail=f"Krish couldn't make that change: {str(exc)[:200]}")
    if not answer:
        raise HTTPException(status_code=502, detail="Krish returned nothing. Try again.")
    if typed and MAKE_RE.match(answer):
        note = MAKE_RE.sub("", answer, count=1).strip() or "I'll make that in chat."
        return {**public_doc(doc), "kind": "handoff", "reply": note, "handoff": handoff_prompt(doc, instruction, model)}
    if typed and ANSWER_RE.match(answer):
        return {**public_doc(doc), "kind": "reply", "reply": ANSWER_RE.sub("", answer, count=1).strip()}
    new = content.replace(selection, answer, 1) if selection else answer
    history = ([content] + (doc.get("history") or []))[:HISTORY]
    await db.docs.update_one({"id": doc_id}, {"$set": {"content": new, "history": history, "updatedAt": _now()}})
    return {**public_doc(await owned_doc(doc_id, user_id)), "kind": "edit"}


@router.post("/docs/{doc_id}/undo")
async def undo(doc_id: str, user_id: str = Depends(current_user_id)):
    doc = await owned_doc(doc_id, user_id)
    history = doc.get("history") or []
    if not history:
        raise HTTPException(status_code=400, detail="Nothing to undo")
    await db.docs.update_one({"id": doc_id}, {"$set": {"content": history[0], "history": history[1:],
                                                         "updatedAt": _now()}})
    return public_doc(await owned_doc(doc_id, user_id))


@router.get("/docs/{doc_id}/export")
async def export_doc(doc_id: str, request: Request, format: str = Query("docx", pattern="^(docx|pdf|md)$"),
                     auth: Optional[str] = Query(None)):
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    doc = await owned_doc(doc_id, decode_token(token)["sub"])
    from agent import documents

    content = doc.get("content") or ""
    name = re.sub(r"[^\w\-]+", "-", doc["title"]).strip("-")[:80] or "document"
    if format == "md":
        return Response(content.encode("utf-8"), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.md"'})
    builder = documents.build_pdf if format == "pdf" else documents.build_docx
    data = await asyncio.get_running_loop().run_in_executor(None, builder, content, "")
    return Response(data, media_type=documents.CONTENT_TYPES[format],
                    headers={"Content-Disposition": f'attachment; filename="{name}.{format}"'})
