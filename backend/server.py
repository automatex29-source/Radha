from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_user_id_from_request,
)
from ai_runtime import ModelRouter, AnthropicProvider, OpenAIProvider, GeminiProvider, AIRequest, ChatMessage

# ---------------------------------------------------------------- infra setup
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

AI_API_KEY = os.environ["AI_API_KEY"]
AI_MODEL = os.environ.get("AI_MODEL", "claude-sonnet-4-6")

# AI Runtime: RADHA -> Router -> Provider -> LLM
# Every provider runs through the Emergent Universal Key. Adding a provider is a
# single .register() call — the chat system never changes.
model_router = (
    ModelRouter(default_model=AI_MODEL)
    .register(AnthropicProvider(AI_API_KEY))
    .register(OpenAIProvider(AI_API_KEY))
    .register(GeminiProvider(AI_API_KEY))
)

AVAILABLE_MODELS = [
    {"id": "claude-sonnet-4-6", "label": "RADHA Omni", "provider": "anthropic", "description": "Deep reasoning · flagship"},
    {"id": "claude-haiku-4-5-20251001", "label": "RADHA Swift", "provider": "anthropic", "description": "Fast · lightweight"},
    {"id": "gpt-5.4", "label": "RADHA Vision", "provider": "openai", "description": "Versatile · OpenAI"},
    {"id": "gemini-3-flash-preview", "label": "RADHA Flash", "provider": "gemini", "description": "Snappy · Google"},
]

app = FastAPI(title="RADHA API")
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


class ConversationIn(BaseModel):
    title: Optional[str] = None


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageIn(BaseModel):
    content: str = Field(min_length=1)
    model: Optional[str] = None


class RegenerateIn(BaseModel):
    model: Optional[str] = None


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
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }


def public_message(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "conversationId": doc["conversationId"],
        "role": doc["role"],
        "content": doc["content"],
        "model": doc.get("model"),
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
    if not doc or not verify_password(body.password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(doc["id"], email)
    return {"token": token, "user": public_user(doc)}


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
async def list_conversations(user_id: str = Depends(current_user_id)):
    docs = await db.conversations.find({"userId": user_id}).sort("updatedAt", -1).to_list(500)
    return [public_conversation(d) for d in docs]


@api.post("/conversations")
async def create_conversation(body: ConversationIn, user_id: str = Depends(current_user_id)):
    ts = now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "title": (body.title or "New conversation").strip()[:200],
        "model": AI_MODEL,
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
    await db.conversations.delete_one({"id": conv_id})
    return {"ok": True}


# ------------------------------------------------------------------- streaming
SYSTEM_PROMPT = (
    "You are RADHA, the flagship AI assistant built by A.utomateX. "
    "You are precise, thoughtful, and helpful. Use clean markdown with code blocks where useful."
)


def _stream_response(conv_id: str, model: str) -> StreamingResponse:
    """Build the SSE response for the current message history of a conversation.

    Assumes the desired history (ending on a user turn) is already persisted.
    """

    async def event_generator():
        history_docs = await db.messages.find({"conversationId": conv_id}).sort("createdAt", 1).to_list(2000)
        messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history_docs]
        ai_request = AIRequest(messages=messages, model=model, system=SYSTEM_PROMPT, session_id=conv_id)

        full = []
        try:
            async for delta in model_router.stream(ai_request):
                full.append(delta)
                yield f"data: {_sse_json(delta)}\n\n"
        except Exception as exc:  # surface provider errors to the client
            logger.exception("AI stream failed")
            yield f"event: error\ndata: {_sse_json(str(exc))}\n\n"
        finally:
            content = "".join(full)
            if content.strip():
                assistant_msg = {
                    "id": str(uuid.uuid4()),
                    "conversationId": conv_id,
                    "role": "assistant",
                    "content": content,
                    "model": model,
                    "createdAt": now_iso(),
                }
                await db.messages.insert_one(assistant_msg)
                await db.conversations.update_one(
                    {"id": conv_id}, {"$set": {"updatedAt": now_iso(), "model": model}}
                )
                yield f"event: done\ndata: {_sse_json({'messageId': assistant_msg['id']})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@api.post("/conversations/{conv_id}/stream")
async def stream_message(conv_id: str, body: MessageIn, user_id: str = Depends(current_user_id)):
    conv = await _owned_conversation(conv_id, user_id)
    model = body.model or AI_MODEL

    user_msg = {
        "id": str(uuid.uuid4()),
        "conversationId": conv_id,
        "role": "user",
        "content": body.content,
        "model": None,
        "createdAt": now_iso(),
    }
    await db.messages.insert_one(user_msg)

    # Auto-title on first user message.
    existing_count = await db.messages.count_documents({"conversationId": conv_id})
    if existing_count == 1 and (conv["title"] in ("New conversation", "", None)):
        auto_title = body.content.strip().split("\n")[0][:60]
        await db.conversations.update_one({"id": conv_id}, {"$set": {"title": auto_title}})

    return _stream_response(conv_id, model)


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

    return _stream_response(conv_id, model)


import json as _json


def _sse_json(payload) -> str:
    return _json.dumps(payload)


@api.get("/")
async def root():
    return {"service": "RADHA", "company": "A.utomateX", "status": "ok"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.conversations.create_index([("userId", 1), ("updatedAt", -1)])
    await db.messages.create_index([("conversationId", 1), ("createdAt", 1)])
    logger.info("RADHA backend ready")


@app.on_event("shutdown")
async def shutdown():
    client.close()
