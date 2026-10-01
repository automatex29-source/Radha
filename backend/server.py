from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import asyncio
import hashlib
import os
import re
import secrets
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Literal, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, Header, Query
from fastapi.responses import StreamingResponse, Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_user_id_from_request,
    decode_token,
)
from ai_runtime import ModelRouter, AnthropicProvider, OpenAIProvider, GeminiProvider, GroqProvider, AIRequest, ChatMessage
from ai_runtime._backend import uses_emergent
import storage
import embeddings
import extract as extractor
import memory
import vision
import media
import preview as previewer
import apps
import decks
import appdata
import automations
import live_search
import mailer
import counsellor
import help_center
from agent import default_registry, run_agent, ToolContext
from agent import browser as agent_browser
from agent import llm as agent_llm
from agent.runtime import MAX_STEPS as MAX_AGENT_STEPS

# ---------------------------------------------------------------- infra setup
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get("DB_NAME") or "radha"]

# Emergent Universal Key (only used on Emergent). Elsewhere, set provider keys instead.
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AVAILABLE_MODELS = [
    {"id": "claude-sonnet-4-6", "label": "Krish Omni", "provider": "anthropic", "description": "Deep reasoning · flagship"},
    {"id": "claude-haiku-4-5-20251001", "label": "Krish Swift", "provider": "anthropic", "description": "Fast · lightweight"},
    {"id": "gpt-5.4", "label": "Krish Vision", "provider": "openai", "description": "Versatile · OpenAI"},
    {"id": "gemini-2.5-flash", "label": "Krish Flash", "provider": "gemini", "description": "Snappy · Google · free tier"},
    {"id": "openai/gpt-oss-120b", "label": "Krish Open", "provider": "groq", "description": "Fast · Groq · free tier"},
]

# Default model: AI_MODEL if set, otherwise the first model whose provider key is configured.
AI_MODEL = (os.environ.get("AI_MODEL")
            or next((m["id"] for m in AVAILABLE_MODELS if agent_llm.configured(m["id"])), "claude-sonnet-4-6"))

# AI Runtime: RADHA -> Router -> Provider -> LLM
# Providers use the Emergent Universal Key on Emergent, or LiteLLM with your own
# keys elsewhere. Adding a provider is a single .register() call.
model_router = (
    ModelRouter(default_model=AI_MODEL)
    .register(AnthropicProvider(AI_API_KEY))
    .register(OpenAIProvider(AI_API_KEY))
    .register(GeminiProvider(AI_API_KEY))
    .register(GroqProvider())
)


tool_registry = default_registry()
storage.init(db)
apps.init(db)
appdata.init(db)
apps.register_tools(tool_registry)

app = FastAPI(title="Krish AI API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("radha")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def current_user_id(request: Request) -> str:
    return get_user_id_from_request(request)


# --------------------------------------------------------------------- models
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=6, max_length=128)


class ConversationIn(BaseModel):
    title: Optional[str] = None
    projectId: Optional[str] = None
    mode: Optional[Literal["counsellor"]] = None


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    instructions: Optional[str] = Field(default=None, max_length=8000)


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    instructions: Optional[str] = Field(default=None, max_length=8000)


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    projectId: Optional[str] = None


class MessageIn(BaseModel):
    content: str = Field(min_length=1)
    model: Optional[str] = None
    images: List[str] = Field(default_factory=list, max_length=8)
    agent: bool = False


class RegenerateIn(BaseModel):
    model: Optional[str] = None
    agent: bool = False


class SpeechIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    voice: Optional[str] = None


def public_user(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "email": doc["email"],
        "name": doc["name"],
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }


def public_conversation(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "title": doc["title"],
        "model": doc.get("model"),
        "projectId": doc.get("projectId"),
        "mode": doc.get("mode"),
        "shareId": doc.get("shareId"),
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }


def public_project(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "name": doc["name"],
        "description": doc.get("description"),
        "instructions": doc.get("instructions"),
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }


def public_file(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "projectId": doc.get("projectId"),
        "conversationId": doc.get("conversationId"),
        "filename": doc["original_filename"],
        "contentType": doc.get("content_type"),
        "size": doc.get("size"),
        "status": doc.get("status"),
        "error": doc.get("error"),
        "chunkCount": doc.get("chunk_count", 0),
        "createdAt": doc["createdAt"],
    }


def public_memory(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "content": doc["content"],
        "projectId": doc.get("projectId"),
        "source": doc.get("source", "manual"),
        "createdAt": doc["createdAt"],
    }


def public_message(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "conversationId": doc["conversationId"],
        "role": doc["role"],
        "content": doc["content"],
        "model": doc.get("model"),
        "sources": doc.get("sources"),
        "images": doc.get("images") or [],
        "steps": doc.get("steps") or [],
        "media": doc.get("media") or [],
        "createdAt": doc["createdAt"],
    }


# ----------------------------------------------------------------------- auth
@api.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    ts = now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": body.name.strip(),
        "password_hash": hash_password(body.password),
        "createdAt": ts,
        "updatedAt": ts,
    }
    await db.users.insert_one(doc)
    token = create_access_token(doc["id"], email)
    return {"token": token, "user": public_user(doc)}


@api.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.lower()
    doc = await db.users.find_one({"email": email})
    if not doc or not verify_password(body.password, doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(doc["id"], email)
    return {"token": token, "user": public_user(doc)}


RESET_MINUTES = 30
RESET_RESEND_SECONDS = 60


def _reset_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _app_url(request: Request) -> str:
    # Prefer a configured address over the request's Host header, so a forged
    # Host can't put someone else's site into the emailed link.
    url = os.environ.get("APP_URL") or os.environ.get("RENDER_EXTERNAL_URL") or str(request.base_url)
    return url.rstrip("/")


async def _valid_reset(token: str) -> Optional[dict]:
    doc = await db.password_resets.find_one({"tokenHash": _reset_hash(token), "usedAt": None})
    if not doc or doc["expiresAt"] < now_iso():
        return None
    return doc


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordIn, request: Request):
    """Email a one-time reset link. Answers the same whether or not the email has an
    account, so this can't be used to find out who is signed up."""
    configured = mailer.configured()
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if user and configured:
        now = datetime.now(timezone.utc)
        recent = await db.password_resets.find_one({
            "userId": user["id"], "usedAt": None,
            "createdAt": {"$gt": (now - timedelta(seconds=RESET_RESEND_SECONDS)).isoformat()},
        })
        if not recent:
            token = secrets.token_urlsafe(32)
            await db.password_resets.insert_one({
                "id": str(uuid.uuid4()), "userId": user["id"], "tokenHash": _reset_hash(token),
                "createdAt": now.isoformat(), "expiresAt": (now + timedelta(minutes=RESET_MINUTES)).isoformat(),
                "usedAt": None,
            })
            link = f"{_app_url(request)}/reset-password?token={token}"
            subject, html, text = mailer.reset_email(user.get("name", ""), link, RESET_MINUTES)
            try:
                await mailer.send(email, subject, html, text)
            except Exception as exc:
                logger.error(f"Password reset email failed: {exc}")
                raise HTTPException(status_code=502, detail="We couldn't send the email right now. Please try again in a minute.")
    return {"ok": True, "emailConfigured": configured}


@api.get("/auth/reset-password/check")
async def check_reset_link(token: str = Query(..., max_length=200)):
    return {"valid": bool(await _valid_reset(token))}


@api.post("/auth/reset-password")
async def reset_password(body: ResetPasswordIn):
    doc = await _valid_reset(body.token)
    if not doc:
        raise HTTPException(status_code=400, detail="This reset link has expired or was already used. Ask for a new one.")
    # Claim the link atomically so it can only be used once.
    claimed = await db.password_resets.update_one({"id": doc["id"], "usedAt": None}, {"$set": {"usedAt": now_iso()}})
    if not claimed.modified_count:
        raise HTTPException(status_code=400, detail="This reset link has expired or was already used. Ask for a new one.")
    user = await db.users.find_one({"id": doc["userId"]})
    if not user:
        raise HTTPException(status_code=400, detail="This account no longer exists.")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(body.password), "updatedAt": now_iso()}})
    # Any other links sent earlier stop working too.
    await db.password_resets.update_many({"userId": user["id"], "usedAt": None}, {"$set": {"usedAt": now_iso()}})
    return {"token": create_access_token(user["id"], user["email"]), "user": public_user(user)}


@api.post("/auth/logout")
async def logout():
    return {"ok": True}


@api.get("/auth/me")
async def me(user_id: str = Depends(current_user_id)):
    doc = await db.users.find_one({"id": user_id})
    if not doc:
        raise HTTPException(status_code=401, detail="User not found")
    return public_user(doc)


@api.get("/models")
async def models(user_id: str = Depends(current_user_id)):
    return {"models": AVAILABLE_MODELS, "default": AI_MODEL}


# --------------------------------------------------------------- conversations
@api.get("/conversations")
async def list_conversations(mode: Optional[Literal["counsellor"]] = None, user_id: str = Depends(current_user_id)):
    # App-builder, automation and Counsellor chats live on their own pages.
    docs = await db.conversations.find({"userId": user_id, "appId": None, "automationId": None, "mode": mode}).sort("updatedAt", -1).to_list(500)
    return [public_conversation(d) for d in docs]


@api.post("/conversations")
async def create_conversation(body: ConversationIn, user_id: str = Depends(current_user_id)):
    project_id = None
    if body.projectId:
        proj = await db.projects.find_one({"id": body.projectId, "userId": user_id})
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        project_id = body.projectId
    ts = now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "title": (body.title or "New conversation").strip()[:200],
        "model": AI_MODEL,
        "projectId": project_id,
        "mode": body.mode,
        "createdAt": ts,
        "updatedAt": ts,
    }
    await db.conversations.insert_one(doc)
    return public_conversation(doc)


async def _owned_conversation(conv_id: str, user_id: str) -> dict:
    doc = await db.conversations.find_one({"id": conv_id, "userId": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return doc


@api.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, user_id: str = Depends(current_user_id)):
    conv = await _owned_conversation(conv_id, user_id)
    msgs = await db.messages.find({"conversationId": conv_id}).sort("createdAt", 1).to_list(2000)
    return {"conversation": public_conversation(conv), "messages": [public_message(m) for m in msgs]}


@api.patch("/conversations/{conv_id}")
async def rename_conversation(conv_id: str, body: ConversationPatch, user_id: str = Depends(current_user_id)):
    await _owned_conversation(conv_id, user_id)
    await db.conversations.update_one(
        {"id": conv_id}, {"$set": {"title": body.title.strip()[:200], "updatedAt": now_iso()}}
    )
    doc = await db.conversations.find_one({"id": conv_id})
    return public_conversation(doc)


@api.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user_id: str = Depends(current_user_id)):
    await _owned_conversation(conv_id, user_id)
    await db.messages.delete_many({"conversationId": conv_id})
    await media.delete_media(db, {"conversationId": conv_id, "userId": user_id})
    await agent_browser.manager.close(f"{user_id}:{conv_id}")
    await db.conversations.delete_one({"id": conv_id})
    return {"ok": True}


# ------------------------------------------------------------------- streaming
SYSTEM_PROMPT = (
    "You are Krish AI, the flagship AI assistant built by EmpireX. "
    "Answer first: put the direct answer in the first sentence, then add only what the user needs. "
    "Keep replies short and plain. No filler, no restating the question, no long lists of alternatives, "
    "no tables or code unless the user asks or they clearly help. Match the user's language. "
    "Krish AI can search the web: when live web results or rates are included below, answer from them, "
    "give the number or fact directly, and name the source briefly. Never say you cannot browse or "
    "access live data. If a word looks like a misspelled currency, place or name, assume the closest match, "
    "say so in a few words (\"Assuming you meant INR\"), and answer. Never stop at \"I couldn't find it\" "
    "when the results or your own knowledge give a useful answer.\n\n"
    "When the user asks how to set up, fix or do something on a website, app or service (Render, MongoDB Atlas, "
    "GitHub, Google, Vercel, domains, payments, phone settings...), guide them like a patient teacher: give only the "
    "next 1-3 small numbered steps, name the exact buttons and menus in quotes, say what they should see after each "
    "step, then ask them to reply \"done\" or send a screenshot before you give the next steps. If they send a "
    "screenshot or error, read it, say what it shows and give the fix. Never ask for passwords or secret keys; tell "
    "them where to paste those themselves.\n\n"
    "When the user asks you to build an app, website, game, tool or page, build the complete, working thing right "
    "away. Put each file in its own fenced code block whose info string is the language followed by the file name, "
    "for example ```html index.html and ```javascript app.js, and link them from index.html by those names. "
    "Say in one line what you built before "
    "the files. Krish AI shows the user a live preview, a Download ZIP button and an Open in App Builder button for "
    "those files automatically. Never output base64, never pretend to attach or encode a ZIP or any other archive, "
    "and never tell the user to decode anything.\n\n" + apps.DESIGN_GUIDE
)


AGENT_PROMPT = (
    "You have tools; use them on your own whenever they make the answer better, without asking. "
    "Anything current or checkable (news, prices, rates, scores, people, recent events, facts you are unsure of): "
    "call web_search first, open the best result with fetch_url when snippets are thin, and answer from what you "
    "found with 1-2 source links. For research, reports, market analysis or detailed comparisons of tools, prices or options, "
    "call deep_research (it writes a cited PDF report). For step-by-step guides, web_search the service's current "
    "docs first so button names are right. Live exchange rates, when given, are the source of truth for currency questions. "
    "Use run_python for any calculation, data work or chart; browser to operate websites; generate_image and "
    "generate_video whenever the user asks to make, draw, design or animate a picture, logo, poster or video (you "
    "can create them; never say you can't). Pick the style that fits (ad, movie, trailer, 3d_animation, anime, "
    "cartoon, music_video, social_reel...), write 3-6 vivid scenes, and add short captions for ads and reels. When the user asks for a file, create a real one that "
    "gets a download button: create_spreadsheet (Excel), create_presentation (PowerPoint), create_document (Word "
    "or PDF), create_file (any single text or code file: txt, csv, json, py, js, css, sql...), create_zip "
    "(multi-file projects such as a Node or Python app). Never paste base64 or made-up download links. For apps, websites and games, follow the app "
    "instructions above (files in fenced code blocks). Make files complete and polished, not outlines. "
    "Do not narrate tool calls; after them give the answer or a short summary, not the file's contents. "
    "Never invent tool results; if a tool fails, try another way before saying you could not. Images labelled as "
    "video frames come from a video the user attached; treat them as that video."
)


MAX_CONTEXT_IMAGES = 6


async def _llm_messages(history_docs: list, system_prompt: str, user_id: str, see_images: bool = True) -> list:
    """OpenAI-style messages for LiteLLM, with user images inlined as data URLs.

    For text-only models (see_images=False) each image is replaced by a written
    description and its text (see vision.py).
    """
    # Only the most recent images are sent, to bound request size.
    image_budget = MAX_CONTEXT_IMAGES
    allowed = set()
    for m in reversed(history_docs):
        for mid in reversed(m.get("images") or []):
            if image_budget > 0:
                allowed.add(mid)
                image_budget -= 1
    out = [{"role": "system", "content": system_prompt}]
    for m in history_docs:
        if m["role"] == "user" and m.get("images") and not see_images:
            notes = []
            for n, mid in enumerate(m["images"], 1):
                doc = await media.load_media(db, user_id, mid) if mid in allowed else None
                if not doc:
                    continue
                text = await vision.describe_media(db, doc)
                name = doc.get("name") or f"image {n}"
                notes.append(f"[Attached image \"{name}\": {text}]" if text
                             else f"[Attached image \"{name}\": it could not be read. Say so and ask the user to type what it shows.]")
            out.append({"role": "user", "content": "\n\n".join([m["content"], *notes])})
        elif m["role"] == "user" and m.get("images"):
            parts = [{"type": "text", "text": m["content"]}]
            for mid in m["images"]:
                if mid in allowed:
                    doc = await media.load_media(db, user_id, mid)
                    if doc:
                        parts.append({"type": "image_url", "image_url": {"url": await media.data_url(db, doc)}})
            out.append({"role": "user", "content": parts})
        elif m["content"]:
            out.append({"role": m["role"], "content": m["content"]})
    return out


# How many words of attached files go into one prompt: whole files when they fit, else the best parts.
FILE_WORDS = 6000
FILE_WORDS_LEAN = 1400  # Groq's free tier: about 8,000 tokens per request in total
FILE_WORDS_LEAN_TOOLS = 450  # ...of which the tool list alone takes about 3,000
# Asks that need tools (web search, making files or pictures, code) even when a document is attached.
_TOOL_ASK = re.compile(
    r"\b(search|google|web|online|internet|latest|news|weather|draw|chart|graph|plot|make|create|generate|"
    r"export|convert|download|build|design|python|calculate)\b", re.IGNORECASE)


async def _file_context(conv_id: str, user_id: str, project_id, question: str, limit: int):
    """(system-prompt text, sources) for the files attached to this chat and the project's documents.

    Small attached files are included whole, so "summarise this" works; bigger ones and
    project documents are searched for the parts closest to the question.
    """
    files = await db.files.find({"conversationId": conv_id, "userId": user_id, "is_deleted": False}).to_list(50)
    or_conds = [{"conversationId": conv_id}] + ([{"projectId": project_id}] if project_id else [])
    chunk_docs = await db.chunks.find({"userId": user_id, "$or": or_conds}).to_list(5000)
    if not files and not chunk_docs:
        return "", []

    chat_file_ids = {f["id"] for f in files}
    chat_chunks = sorted((c for c in chunk_docs if c.get("fileId") in chat_file_ids),
                         key=lambda c: (c["fileName"], c["index"]))
    step = 180  # chunk_text() windows are 220 words overlapping by 40
    whole = bool(chat_chunks) and len(chat_chunks) * step <= limit
    chosen = list(chat_chunks) if whole else []  # small files go in whole, so "summarise this" works
    sources = [{"fileName": n, "score": 1.0} for n in dict.fromkeys(c["fileName"] for c in chosen)]
    taken = {c["id"] for c in chosen}
    others = [c for c in chunk_docs if c["id"] not in taken]
    room = (limit - len(chosen) * step) // 220
    if others and room > 0:
        ranked = await embeddings.rank(question, others, top_k=room)
        if not whole:
            # A vague question ("what is this?") still gets the start of each attached file.
            for fid in list(chat_file_ids)[:3]:
                first = next((c for c in chat_chunks if c["fileId"] == fid), None)
                if first and first["id"] not in {r["id"] for r in ranked}:
                    if len(ranked) >= room:
                        ranked.pop()
                    ranked.insert(0, {**{k: v for k, v in first.items() if k != "embedding"}, "score": 0.0})
        chosen += ranked
        for c in ranked:
            if c["fileName"] not in {s["fileName"] for s in sources}:
                sources.append({"fileName": c["fileName"], "score": c["score"]})

    parts = []
    if files:
        status = []
        for f in files:
            note = "read" if f.get("chunk_count") else ("could not be read" if f.get("status") == "failed"
                                                          else "no readable text found (it may be a blank or photo-only file)")
            status.append(f"- {f['original_filename']}: {note}")
        parts.append("Files the user attached to this chat:\n" + "\n".join(status))
    if chosen:
        parts.append(
            "Content of the user's files (answer from it, and name the file in [brackets] when you use it; "
            "if the answer isn't there, say so):\n\n"
            + "\n\n".join(f"[{c['fileName']}] {c['text']}" for c in chosen)
        )
    return "\n\n".join(parts), sources


async def run_turn(conv_id: str, model: str, agent: bool = False, extra_system: Optional[str] = None,
                   max_steps: Optional[int] = None):
    """Generate the assistant's reply to a conversation, as SSE-formatted chunks.

    If the conversation belongs to a project, relevant document chunks (RAG) and
    project/user memory are retrieved and injected as grounding context.

    Automations pass `extra_system` (their agent instructions and memory) and a larger `max_steps`.

    Plain chat streams through the model router. Agent turns (tool use), any
    conversation containing images, and app-builder conversations stream through
    the agent runtime instead. The reply is saved when the turn ends.
    """
    conv = await db.conversations.find_one({"id": conv_id})
    user_id = conv["userId"] if conv else None
    project_id = conv.get("projectId") if conv else None
    counselling = (conv or {}).get("mode") == counsellor.MODE

    history_docs = await db.messages.find({"conversationId": conv_id}).sort("createdAt", 1).to_list(2000)
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history_docs]

    system_parts = [counsellor.PROMPT if counselling else SYSTEM_PROMPT, f"Today is {datetime.now(timezone.utc).strftime('%A, %d %B %Y')} (UTC)."]
    sources = []
    last_user = next((m["content"] for m in reversed(history_docs) if m["role"] == "user"), None)

    # Memory (user-global + project) — real, user-controlled facts.
    if user_id:
        remembered = await memory.prompt_section(db, user_id, project_id)
        if remembered:
            system_parts.append(remembered)

    # Project instructions.
    if project_id:
        proj = await db.projects.find_one({"id": project_id})
        if proj and proj.get("instructions"):
            system_parts.append(f"Project instructions:\n{proj['instructions']}")

    if counselling:
        agent = False  # a listening conversation: no tools, no web search
        if counsellor.is_crisis(last_user or ""):
            system_parts.append("The person's latest message may describe a crisis or danger. Follow the Safety "
                                "instructions now: respond with care and give the helplines.")

    # Files attached to this chat, plus project documents (RAG).
    if user_id and last_user and not counselling:
        lean = agent_llm.lean(model)
        if lean and agent and not (conv or {}).get("appId") and not _TOOL_ASK.search(last_user) and \
                await db.files.count_documents({"conversationId": conv_id, "is_deleted": False}):
            # Groq's free tier can't fit the tools AND a document in one request; a question about
            # the document needs the document more.
            agent = False
        budget = FILE_WORDS if not lean else FILE_WORDS_LEAN if not agent else FILE_WORDS_LEAN_TOOLS
        try:
            file_ctx, sources = await _file_context(conv_id, user_id, project_id, last_user, budget)
            if file_ctx:
                system_parts.append(file_ctx)
        except Exception:
            logger.exception("RAG retrieval failed")

    app_id = conv.get("appId") if conv else None
    if app_id:
        agent = True  # the app builder always works with its tools
        system_parts.append(await apps.app_prompt(db, app_id))
    use_runtime = agent or any(m.get("images") for m in history_docs)
    # Look up live info (news, rates, prices) up front, so the answer never depends on the model choosing to search.
    if not app_id and not counselling:
        live = await live_search.lookup([m["content"] for m in history_docs if m["role"] == "user"])
        if live:
            system_parts.append(live)
    # Free models (Groq) get only the app tools inside an app, to stay within their token budget.
    focused = bool(app_id) and agent_llm.lean(model)
    if agent and not focused:
        system_parts.append(AGENT_PROMPT)
    if extra_system:
        system_parts.append(extra_system)
    system_prompt = "\n\n".join(system_parts)

    if sources:
        yield f"event: sources\ndata: {_sse_json(sources)}\n\n"

    full, steps, produced = [], [], []
    try:
        if use_runtime:
            if not agent_llm.configured(model):
                raise RuntimeError(agent_llm.missing_key_message(model))
            llm_messages = await _llm_messages(history_docs, system_prompt, user_id,
                                               see_images=agent_llm.supports_images(model))
            ctx = ToolContext(db=db, user_id=user_id, conversation_id=conv_id, app_id=app_id, focused=focused,
                              model=model)
            async for ev in run_agent(agent_llm.stream_completion, tool_registry, ctx, model, llm_messages, use_tools=agent,
                                      max_steps=max_steps or MAX_AGENT_STEPS):
                if ev["type"] == "text":
                    full.append(ev["text"])
                    yield f"data: {_sse_json(ev['text'])}\n\n"
                elif ev["type"] == "tool_start":
                    steps.append({"id": ev["id"], "name": ev["name"], "label": ev["label"], "args": ev["args"], "status": "running"})
                    yield f"event: tool\ndata: {_sse_json(steps[-1])}\n\n"
                elif ev["type"] == "heartbeat":
                    yield ": keepalive\n\n"
                elif ev["type"] == "tool_end":
                    step = next((s for s in steps if s["id"] == ev["id"]), None)
                    if step is not None:
                        step.update(status="done" if ev["ok"] else "error", summary=ev["summary"],
                                    output=ev["output"], media=ev["media"])
                        produced.extend(ev["media"])
                        yield f"event: tool_result\ndata: {_sse_json(step)}\n\n"
        else:
            if not uses_emergent(AI_API_KEY) and not agent_llm.configured(model):
                raise RuntimeError(agent_llm.missing_key_message(model))
            ai_request = AIRequest(messages=messages, model=model, system=system_prompt, session_id=conv_id)
            async for delta in model_router.stream(ai_request):
                full.append(delta)
                yield f"data: {_sse_json(delta)}\n\n"
    except Exception as exc:  # surface provider errors to the client
        logger.exception("AI stream failed")
        yield f"event: error\ndata: {_sse_json(str(exc))}\n\n"
    else:
        # Crisis replies always carry the helplines, even if the model left them out.
        note = counsellor.helpline_note("".join(full)) if counselling and counsellor.is_crisis(last_user or "") else ""
        if note:
            note = "\n\n" + note
            full.append(note)
            yield f"data: {_sse_json(note)}\n\n"
    finally:
        content = "".join(full).strip()
        if content or steps:
            assistant_msg = {
                "id": str(uuid.uuid4()),
                "conversationId": conv_id,
                "role": "assistant",
                "content": content,
                "model": model,
                "sources": sources or None,
                "steps": steps or None,
                "media": produced or None,
                "createdAt": now_iso(),
            }
            await db.messages.insert_one(assistant_msg)
            await db.conversations.update_one(
                {"id": conv_id}, {"$set": {"updatedAt": now_iso(), "model": model}}
            )
            yield f"event: done\ndata: {_sse_json({'messageId': assistant_msg['id']})}\n\n"



def _stream_response(conv_id: str, model: str, agent: bool = False) -> StreamingResponse:
    return StreamingResponse(
        run_turn(conv_id, model, agent),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@api.post("/conversations/{conv_id}/stream")
async def stream_message(conv_id: str, body: MessageIn, user_id: str = Depends(current_user_id)):
    conv = await _owned_conversation(conv_id, user_id)
    model = body.model or AI_MODEL

    image_ids = []
    for mid in body.images:
        doc = await db.media.find_one({"id": mid, "userId": user_id}, {"data": 0})
        if not doc or not (doc.get("contentType") or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Unknown image attachment")
        image_ids.append(mid)

    user_msg = {
        "id": str(uuid.uuid4()),
        "conversationId": conv_id,
        "role": "user",
        "content": body.content,
        "images": image_ids or None,
        "model": None,
        "createdAt": now_iso(),
    }
    await db.messages.insert_one(user_msg)

    # Auto-title on first user message.
    existing_count = await db.messages.count_documents({"conversationId": conv_id})
    if existing_count == 1 and (conv["title"] in ("New conversation", "", None)):
        auto_title = body.content.strip().split("\n")[0][:60]
        await db.conversations.update_one({"id": conv_id}, {"$set": {"title": auto_title}})

    # Learn lasting facts about the user in the background (see memory.py).
    # Counselling chats are private: nothing said there is saved to memory.
    if not conv.get("appId") and not conv.get("automationId") and conv.get("mode") != counsellor.MODE:
        _background(memory.learn(db, user_id, body.content, model))

    return _stream_response(conv_id, model, agent=body.agent)


_BACKGROUND_TASKS = set()


def _background(coro):
    """Run a coroutine after the response without it being garbage-collected mid-way."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


@api.post("/conversations/{conv_id}/regenerate")
async def regenerate_message(conv_id: str, body: RegenerateIn, user_id: str = Depends(current_user_id)):
    conv = await _owned_conversation(conv_id, user_id)
    model = body.model or conv.get("model") or AI_MODEL

    history_docs = await db.messages.find({"conversationId": conv_id}).sort("createdAt", 1).to_list(2000)
    if not history_docs:
        raise HTTPException(status_code=400, detail="Nothing to regenerate")

    # Drop the trailing assistant turn so we re-answer the last user message.
    if history_docs[-1]["role"] == "assistant":
        await db.messages.delete_one({"id": history_docs[-1]["id"]})

    remaining = await db.messages.count_documents({"conversationId": conv_id})
    if remaining == 0:
        raise HTTPException(status_code=400, detail="Nothing to regenerate")

    return _stream_response(conv_id, model, agent=body.agent)


# -------------------------------------------------------------------- sharing
# A shared chat gets a random, unguessable link that anyone can open read-only.
# It shows the chat as it is now (later messages too) until the owner stops sharing.
@api.post("/conversations/{conv_id}/share")
async def share_conversation(conv_id: str, user_id: str = Depends(current_user_id)):
    conv = await _owned_conversation(conv_id, user_id)
    share_id = conv.get("shareId")
    if not share_id:
        share_id = secrets.token_urlsafe(16)
        await db.conversations.update_one({"id": conv_id}, {"$set": {"shareId": share_id, "sharedAt": now_iso()}})
    return {"shareId": share_id, "path": f"/share/{share_id}"}


@api.delete("/conversations/{conv_id}/share")
async def unshare_conversation(conv_id: str, user_id: str = Depends(current_user_id)):
    await _owned_conversation(conv_id, user_id)
    await db.conversations.update_one({"id": conv_id}, {"$unset": {"shareId": "", "sharedAt": ""}})
    return {"ok": True}


async def _shared_conversation(share_id: str) -> dict:
    conv = await db.conversations.find_one({"shareId": share_id}) if share_id else None
    if not conv:
        raise HTTPException(status_code=404, detail="This link was turned off or doesn't exist")
    return conv


def _message_media_ids(msg: dict) -> set:
    ids = set(msg.get("images") or [])
    ids.update(m["id"] for m in msg.get("media") or [] if m.get("id"))
    return ids


@api.get("/share/{share_id}")
async def get_shared_conversation(share_id: str):
    """Public, read-only view of a shared chat. No sign-in; shows no account details."""
    conv = await _shared_conversation(share_id)
    msgs = await db.messages.find({"conversationId": conv["id"]}).sort("createdAt", 1).to_list(2000)
    base = f"/api/share/{share_id}/media"
    out = []
    for m in msgs:
        if not m.get("content") and not m.get("media"):
            continue
        out.append({
            "id": m["id"],
            "role": m["role"],
            "content": m.get("content") or "",
            "images": [f"{base}/{mid}" for mid in m.get("images") or []],
            "media": [{**x, "url": f"{base}/{x['id']}"} for x in m.get("media") or [] if x.get("id")],
            "sources": m.get("sources"),
            "createdAt": m["createdAt"],
        })
    return {"title": conv["title"], "createdAt": conv["createdAt"], "updatedAt": conv["updatedAt"], "messages": out}


@api.get("/share/{share_id}/media/{mid}")
async def get_shared_media(share_id: str, mid: str,
                           range_header: Optional[str] = Header(None, alias="Range")):
    conv = await _shared_conversation(share_id)
    # Only pictures and files that appear in this chat can be opened through its link.
    async for m in db.messages.find({"conversationId": conv["id"]}, {"images": 1, "media": 1}):
        if mid in _message_media_ids(m):
            break
    else:
        raise HTTPException(status_code=404, detail="Media not found")
    doc = await media.load_media(db, conv["userId"], mid)
    if not doc:
        raise HTTPException(status_code=404, detail="Media not found")
    return await _serve_media(doc, range_header)


# ------------------------------------------------------------------- projects
async def _owned_project(pid: str, user_id: str) -> dict:
    doc = await db.projects.find_one({"id": pid, "userId": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    return doc


@api.get("/projects")
async def list_projects(user_id: str = Depends(current_user_id)):
    docs = await db.projects.find({"userId": user_id}).sort("updatedAt", -1).to_list(500)
    out = []
    for d in docs:
        item = public_project(d)
        item["fileCount"] = await db.files.count_documents({"projectId": d["id"], "is_deleted": False})
        item["conversationCount"] = await db.conversations.count_documents({"projectId": d["id"]})
        out.append(item)
    return out


@api.post("/projects")
async def create_project(body: ProjectIn, user_id: str = Depends(current_user_id)):
    ts = now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "name": body.name.strip(),
        "description": (body.description or "").strip() or None,
        "instructions": (body.instructions or "").strip() or None,
        "createdAt": ts,
        "updatedAt": ts,
    }
    await db.projects.insert_one(doc)
    return public_project(doc)


@api.get("/projects/{pid}")
async def get_project(pid: str, user_id: str = Depends(current_user_id)):
    proj = await _owned_project(pid, user_id)
    files = await db.files.find({"projectId": pid, "is_deleted": False}).sort("createdAt", -1).to_list(500)
    convs = await db.conversations.find({"projectId": pid, "userId": user_id}).sort("updatedAt", -1).to_list(500)
    mems = await db.memories.find({"userId": user_id, "projectId": pid}).sort("createdAt", -1).to_list(200)
    return {
        "project": public_project(proj),
        "files": [public_file(f) for f in files],
        "conversations": [public_conversation(c) for c in convs],
        "memories": [public_memory(m) for m in mems],
    }


@api.patch("/projects/{pid}")
async def update_project(pid: str, body: ProjectPatch, user_id: str = Depends(current_user_id)):
    await _owned_project(pid, user_id)
    updates = {k: (v.strip() or None) for k, v in body.model_dump(exclude_none=True).items()}
    if updates:
        updates["updatedAt"] = now_iso()
        await db.projects.update_one({"id": pid}, {"$set": updates})
    doc = await db.projects.find_one({"id": pid})
    return public_project(doc)


@api.delete("/projects/{pid}")
async def delete_project(pid: str, user_id: str = Depends(current_user_id)):
    await _owned_project(pid, user_id)
    await db.chunks.delete_many({"projectId": pid})
    await db.files.delete_many({"projectId": pid})
    await db.memories.delete_many({"projectId": pid, "userId": user_id})
    # Detach conversations rather than delete them.
    await db.conversations.update_many({"projectId": pid}, {"$set": {"projectId": None}})
    await db.projects.delete_one({"id": pid})
    return {"ok": True}


# ---------------------------------------------------------------------- files
async def _process_file(file_id: str, user_id: str, project_id, data: bytes, ext: str, filename: str, content_type: str, conversation_id=None):
    """Extract text, chunk, embed, and store chunks. Updates file status."""
    try:
        # Parsing, OCR and embedding are CPU-bound: keep them off the event loop.
        text = await asyncio.to_thread(extractor.extract_text, data, ext, content_type)
        chunks = extractor.chunk_text(text)
        if chunks:
            try:
                vectors = await asyncio.to_thread(embeddings.embed_texts, chunks)
            except Exception:
                # The embedding model couldn't load (download blocked, low memory): keep the text,
                # which is still found by keyword search.
                logger.exception("Embedding failed; storing chunks for keyword search")
                vectors = [None] * len(chunks)
            docs = [
                {
                    "id": str(uuid.uuid4()),
                    "userId": user_id,
                    "projectId": project_id,
                    "conversationId": conversation_id,
                    "fileId": file_id,
                    "fileName": filename,
                    "index": i,
                    "text": chunk,
                    "embedding": vec,
                    "createdAt": now_iso(),
                }
                for i, (chunk, vec) in enumerate(zip(chunks, vectors))
            ]
            await db.chunks.insert_many(docs)
        await db.files.update_one(
            {"id": file_id},
            {"$set": {"status": "ready", "chunk_count": len(chunks), "error": None}},
        )
    except Exception as exc:
        logger.exception("File processing failed")
        await db.files.update_one({"id": file_id}, {"$set": {"status": "failed", "error": str(exc)[:300]}})


@api.post("/projects/{pid}/files")
async def upload_file(pid: str, file: UploadFile = File(...), user_id: str = Depends(current_user_id)):
    await _owned_project(pid, user_id)
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    file_id = str(uuid.uuid4())
    path = storage.object_path(user_id, file_id, ext)
    content_type = file.content_type or "application/octet-stream"

    try:
        result = await storage.put_object(path, data, content_type)
    except Exception as exc:
        logger.exception("Storage upload failed")
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {exc}")

    doc = {
        "id": file_id,
        "userId": user_id,
        "projectId": pid,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "status": "processing",
        "chunk_count": 0,
        "error": None,
        "is_deleted": False,
        "createdAt": now_iso(),
    }
    await db.files.insert_one(doc)
    await _process_file(file_id, user_id, pid, data, ext, file.filename, content_type)
    updated = await db.files.find_one({"id": file_id})
    return public_file(updated)


@api.get("/conversations/{conv_id}/files")
async def list_conversation_files(conv_id: str, user_id: str = Depends(current_user_id)):
    await _owned_conversation(conv_id, user_id)
    docs = await db.files.find({"conversationId": conv_id, "is_deleted": False}).sort("createdAt", -1).to_list(200)
    return [public_file(f) for f in docs]


@api.post("/conversations/{conv_id}/files")
async def upload_conversation_file(conv_id: str, file: UploadFile = File(...), user_id: str = Depends(current_user_id)):
    conv = await _owned_conversation(conv_id, user_id)
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    file_id = str(uuid.uuid4())
    path = storage.object_path(user_id, file_id, ext)
    content_type = file.content_type or "application/octet-stream"
    try:
        result = await storage.put_object(path, data, content_type)
    except Exception as exc:
        logger.exception("Storage upload failed")
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {exc}")

    doc = {
        "id": file_id,
        "userId": user_id,
        "projectId": conv.get("projectId"),
        "conversationId": conv_id,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "status": "processing",
        "chunk_count": 0,
        "error": None,
        "is_deleted": False,
        "createdAt": now_iso(),
    }
    await db.files.insert_one(doc)
    await _process_file(file_id, user_id, conv.get("projectId"), data, ext, file.filename, content_type, conversation_id=conv_id)
    updated = await db.files.find_one({"id": file_id})
    return public_file(updated)


@api.delete("/files/{fid}")
async def delete_file(fid: str, user_id: str = Depends(current_user_id)):
    doc = await db.files.find_one({"id": fid, "userId": user_id, "is_deleted": False})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    await db.chunks.delete_many({"fileId": fid})
    await db.files.update_one({"id": fid}, {"$set": {"is_deleted": True}})
    return {"ok": True}


@api.get("/files/{fid}/download")
async def download_file(fid: str, authorization: str = Header(None), auth: str = Query(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_token(token)["sub"]
    doc = await db.files.find_one({"id": fid, "userId": user_id, "is_deleted": False})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, content_type = await storage.get_object(doc["storage_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File data missing")
    return Response(content=data, media_type=doc.get("content_type", content_type))


# ---------------------------------------------------------------------- media
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def _user_from_header_or_query(authorization: Optional[str], auth: Optional[str]) -> str:
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_token(token)["sub"]


@api.get("/capabilities")
async def capabilities(user_id: str = Depends(current_user_id)):
    return {
        "agent": {m["id"]: agent_llm.configured(m["id"]) for m in AVAILABLE_MODELS},
        "tools": tool_registry.describe(),
        "voice": media.transcription_available(),
        "serverSpeech": media.openai_configured(),
        "video": any(t["name"] == "generate_video" and t["available"] for t in tool_registry.describe()),
        "imageGeneration": media.image_available(),
        "voices": media.TTS_VOICES,
    }


@api.post("/media")
async def upload_media(file: UploadFile = File(...), conversationId: Optional[str] = Form(None),
                       user_id: str = Depends(current_user_id)):
    content_type = (file.content_type or "").lower()
    if content_type not in IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Only PNG, JPEG, WebP and GIF images are supported")
    if conversationId:
        await _owned_conversation(conversationId, user_id)
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 20MB)")
    try:
        return await media.save_media(db, user_id, data, content_type, "upload",
                                      name=file.filename, conversation_id=conversationId)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))


@api.get("/media/{mid}")
async def get_media(mid: str, authorization: str = Header(None), auth: str = Query(None),
                    range_header: Optional[str] = Header(None, alias="Range")):
    user_id = _user_from_header_or_query(authorization, auth)
    doc = await media.load_media(db, user_id, mid)
    if not doc:
        raise HTTPException(status_code=404, detail="Media not found")
    return await _serve_media(doc, range_header)


async def _serve_media(doc: dict, range_header: Optional[str]):
    mid = doc["id"]
    size = doc.get("size") or 0
    headers = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff", "Accept-Ranges": "bytes"}
    if doc["contentType"] in ("text/html", "image/svg+xml"):
        # Code-produced HTML/SVG could carry script: force download, never render inline.
        headers["Content-Disposition"] = f'attachment; filename="{doc.get("name") or mid}"'
    # Byte ranges let the video player seek and start quickly on large files.
    if range_header and range_header.startswith("bytes=") and size:
        spec = range_header[6:].split(",")[0].strip()
        start_s, _, end_s = spec.partition("-")
        try:
            if start_s:
                start, end = int(start_s), int(end_s) if end_s else size - 1
            else:
                start, end = max(size - int(end_s), 0), size - 1
        except ValueError:
            start, end = 0, size - 1
        if start >= size or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        end = min(end, size - 1, start + 8 * 1024 * 1024 - 1)
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(content=await media.read_bytes(db, doc, start, end), status_code=206,
                        media_type=doc["contentType"], headers=headers)
    if doc.get("chunks"):
        async def body():
            for offset in range(0, size, media.CHUNK_BYTES):
                yield await media.read_bytes(db, doc, offset, offset + media.CHUNK_BYTES - 1)
        headers["Content-Length"] = str(size)
        return StreamingResponse(body(), media_type=doc["contentType"], headers=headers)
    return Response(content=await media.read_bytes(db, doc), media_type=doc["contentType"], headers=headers)


@api.get("/media/{mid}/preview")
async def preview_media(mid: str, user_id: str = Depends(current_user_id)):
    doc = await media.load_media(db, user_id, mid)
    if not doc:
        raise HTTPException(status_code=404, detail="Media not found")
    try:
        if doc.get("size", 0) > 30 * 1024 * 1024 and not doc["contentType"].startswith(("video/", "image/")):
            raise ValueError("File too large to preview — download it instead")
        preview = previewer.build_preview(doc["contentType"], await media.read_bytes(db, doc), doc.get("name") or "")
    except Exception as exc:
        logger.exception("Preview failed")
        preview = {"type": "unsupported", "error": str(exc)[:200]}
    return {"media": media.public_media(doc), "preview": preview}


# ---------------------------------------------------------------------- voice
@api.post("/audio/transcribe")
async def transcribe_audio(file: UploadFile = File(...), language: Optional[str] = Form(None),
                           user_id: str = Depends(current_user_id)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio too large (max 25MB)")
    try:
        lang = language if language in ("en", "hi") else None
        text = await media.transcribe(data, file.filename or "audio.webm", lang)
    except media.MediaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}")
    return {"text": text.strip()}


@api.post("/audio/speech")
async def text_to_speech(body: SpeechIn, user_id: str = Depends(current_user_id)):
    try:
        audio = await media.speak(body.text, body.voice or "nova")
    except media.MediaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Speech synthesis failed")
        raise HTTPException(status_code=502, detail=f"Speech synthesis failed: {exc}")
    return Response(content=audio, media_type="audio/mpeg")


# --------------------------------------------------------------------- memory
@api.get("/memory")
async def list_memory(projectId: Optional[str] = Query(None), user_id: str = Depends(current_user_id)):
    query = {"userId": user_id}
    if projectId:
        query["$or"] = [{"projectId": None}, {"projectId": projectId}]
    else:
        query["projectId"] = None
    docs = await db.memories.find(query).sort("createdAt", -1).to_list(200)
    return [public_memory(m) for m in docs]


@api.post("/memory")
async def create_memory(body: MemoryIn, user_id: str = Depends(current_user_id)):
    if body.projectId:
        await _owned_project(body.projectId, user_id)
    doc = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "projectId": body.projectId,
        "content": body.content.strip(),
        "source": "manual",
        "createdAt": now_iso(),
    }
    await db.memories.insert_one(doc)
    return public_memory(doc)


@api.delete("/memory/{mid}")
async def delete_memory(mid: str, user_id: str = Depends(current_user_id)):
    res = await db.memories.delete_one({"id": mid, "userId": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@api.delete("/memory")
async def clear_memory(user_id: str = Depends(current_user_id)):
    """Forget everything RADHA remembers about the user (project memory is kept)."""
    res = await db.memories.delete_many({"userId": user_id, "projectId": None})
    return {"ok": True, "deleted": res.deleted_count}


class MemorySettingsIn(BaseModel):
    auto: bool


@api.get("/memory/settings")
async def memory_settings(user_id: str = Depends(current_user_id)):
    return {"auto": await memory.auto_enabled(db, user_id)}


@api.put("/memory/settings")
async def update_memory_settings(body: MemorySettingsIn, user_id: str = Depends(current_user_id)):
    await db.users.update_one({"id": user_id}, {"$set": {"memoryAuto": body.auto}})
    return {"auto": body.auto}


import json as _json


def _sse_json(payload) -> str:
    return _json.dumps(payload)


@api.get("/")
async def root():
    return {"service": "Krish AI", "company": "EmpireX", "status": "ok"}


app.include_router(api)
app.include_router(apps.router)
app.include_router(appdata.router)
decks.init(db, AI_MODEL)
app.include_router(decks.router)
automations.init(db, run_turn, AI_MODEL)
app.include_router(automations.router)
help_center.init(db)
app.include_router(help_center.router)

# Serve the built frontend (frontend/build) from the same origin, so a single
# process runs all of RADHA. In development the Vite dev server is used instead.
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST") or ROOT_DIR.parent / "frontend" / "build").resolve()
if (FRONTEND_DIST / "index.html").is_file():
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            cache = "public, max-age=31536000, immutable" if full_path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _ensure_auth_secret():
    """Use AUTH_SECRET if set; otherwise create one once and keep it in the database,
    so logins survive restarts without any setup."""
    if os.environ.get("AUTH_SECRET"):
        return
    await db.settings.create_index("id", unique=True)
    doc = await db.settings.find_one({"id": "auth_secret"})
    if not doc:
        doc = {"id": "auth_secret", "value": secrets.token_urlsafe(48)}
        try:
            await db.settings.insert_one(doc)
        except Exception:  # another process created it first
            doc = await db.settings.find_one({"id": "auth_secret"})
    os.environ["AUTH_SECRET"] = doc["value"]


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.password_resets.create_index("tokenHash")
    await db.conversations.create_index([("userId", 1), ("updatedAt", -1)])
    await db.conversations.create_index("shareId", sparse=True)
    await db.messages.create_index([("conversationId", 1), ("createdAt", 1)])
    await db.projects.create_index([("userId", 1), ("updatedAt", -1)])
    await db.files.create_index([("projectId", 1), ("is_deleted", 1)])
    await db.chunks.create_index([("userId", 1), ("projectId", 1)])
    await db.memories.create_index([("userId", 1), ("projectId", 1)])
    await db.media.create_index("id", unique=True)
    await db.media.create_index([("userId", 1), ("conversationId", 1)])
    await db.media_chunks.create_index([("mediaId", 1), ("n", 1)], unique=True)
    await apps.ensure_indexes()
    await decks.ensure_indexes()
    await appdata.ensure_indexes()
    await automations.ensure_indexes()
    if os.environ.get("AUTOMATIONS_SCHEDULER", "1") != "0":
        automations.start_scheduler()
    await _ensure_auth_secret()
    await storage.ensure_indexes()
    if storage.USE_EMERGENT:
        try:
            storage.init_storage()
            logger.info("Object storage initialized")
        except Exception as exc:
            logger.error(f"Storage init failed: {exc}")
    else:
        logger.info("Storing uploaded files in MongoDB")
    logger.info("Krish AI backend ready")


@app.on_event("shutdown")
async def shutdown():
    await automations.stop_scheduler()
    await agent_browser.manager.shutdown()
    client.close()
