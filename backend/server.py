from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional

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
from ai_runtime import ModelRouter, AnthropicProvider, OpenAIProvider, GeminiProvider, AIRequest, ChatMessage
import storage
import embeddings
import extract as extractor

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
    projectId: Optional[str] = None


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
        "projectId": doc.get("projectId"),
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

    If the conversation belongs to a project, relevant document chunks (RAG) and
    project/user memory are retrieved and injected as grounding context.
    """

    async def event_generator():
        conv = await db.conversations.find_one({"id": conv_id})
        user_id = conv["userId"] if conv else None
        project_id = conv.get("projectId") if conv else None

        history_docs = await db.messages.find({"conversationId": conv_id}).sort("createdAt", 1).to_list(2000)
        messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history_docs]

        system_parts = [SYSTEM_PROMPT]
        sources = []
        last_user = next((m["content"] for m in reversed(history_docs) if m["role"] == "user"), None)

        # Memory (user-global + project) — real, user-controlled facts.
        mem_query = {"userId": user_id, "$or": [{"projectId": None}, {"projectId": project_id}]} if user_id else None
        if mem_query:
            mems = await db.memories.find(mem_query).sort("createdAt", -1).to_list(50)
            if mems:
                system_parts.append(
                    "Known facts the user asked you to remember:\n"
                    + "\n".join(f"- {m['content']}" for m in mems)
                )

        # Project instructions.
        if project_id:
            proj = await db.projects.find_one({"id": project_id})
            if proj and proj.get("instructions"):
                system_parts.append(f"Project instructions:\n{proj['instructions']}")

        # RAG retrieval over project documents AND files attached to this chat.
        if user_id and last_user:
            or_conds = [{"conversationId": conv_id}]
            if project_id:
                or_conds.append({"projectId": project_id})
            chunk_docs = await db.chunks.find({"userId": user_id, "$or": or_conds}).to_list(5000)
            if chunk_docs:
                try:
                    qvec = embeddings.embed_query(last_user)
                    top = embeddings.cosine_rank(qvec, chunk_docs, top_k=5, threshold=0.3)
                    if top:
                        ctx = "\n\n".join(f"[{c['fileName']}] {c['text']}" for c in top)
                        system_parts.append(
                            "Use the following context from the user's uploaded documents to answer. "
                            "Cite the source file names in [brackets]. If the answer is not in the context, say so.\n\n"
                            + ctx
                        )
                        seen = set()
                        for c in top:
                            if c["fileName"] not in seen:
                                seen.add(c["fileName"])
                                sources.append({"fileName": c["fileName"], "score": c["score"]})
                except Exception:
                    logger.exception("RAG retrieval failed")

        system_prompt = "\n\n".join(system_parts)
        ai_request = AIRequest(messages=messages, model=model, system=system_prompt, session_id=conv_id)

        if sources:
            yield f"event: sources\ndata: {_sse_json(sources)}\n\n"

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
                    "sources": sources or None,
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
        text = extractor.extract_text(data, ext, content_type)
        chunks = extractor.chunk_text(text)
        if chunks:
            vectors = embeddings.embed_texts(chunks)
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
        result = storage.put_object(path, data, content_type)
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
        result = storage.put_object(path, data, content_type)
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
    data, content_type = storage.get_object(doc["storage_path"])
    return Response(content=data, media_type=doc.get("content_type", content_type))


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
    await db.projects.create_index([("userId", 1), ("updatedAt", -1)])
    await db.files.create_index([("projectId", 1), ("is_deleted", 1)])
    await db.chunks.create_index([("userId", 1), ("projectId", 1)])
    await db.memories.create_index([("userId", 1), ("projectId", 1)])
    try:
        storage.init_storage()
        logger.info("Object storage initialized")
    except Exception as exc:
        logger.error(f"Storage init failed: {exc}")
    logger.info("RADHA backend ready")


@app.on_event("shutdown")
async def shutdown():
    client.close()
