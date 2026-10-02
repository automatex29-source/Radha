"""More backend for apps made in the App Builder, on top of appdata's database and accounts.

The page gets these on the same global RADHA object (see appdata.SDK):

  await RADHA.ai(prompt, {system, history, json})   an answer from the free AI model
  await RADHA.notify({subject, message, replyTo})   emails the app's owner (contact forms, orders, bookings)
  await RADHA.files.upload(file)                    stores a picture or document, returns {url, ...}
  await RADHA.fetch(url, {method, headers, body})   calls an outside API from the server (no CORS problems)
  POST /api/appdata/<app>/hook/<collection>?key=…   other tools (Zapier, Make, n8n, forms) push data in

Like appdata, these endpoints are public (visitors of a published app have no Krish AI login), so each is
limited per visitor and per app, only free AI models are used, and fetch refuses private network addresses.

The app's owner sees the data, sign-ups, files and inbox in the App Builder's Data tab (/api/apps/<id>/data).
"""
import asyncio
import hashlib
import hmac
import html
import ipaddress
import json
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import appdata
import mailer
from agent import llm
from auth import _secret, get_user_id_from_request

router = APIRouter(prefix="/api/appdata")
owner_router = APIRouter(prefix="/api/apps")
db = None

OWNER = "__owner__"  # ownerId of documents only the app's owner may see (inbox, private webhook data)
INBOX = "inbox"
FREE_AI_MODELS = ["cerebras/gpt-oss-120b", "openai/gpt-oss-120b"]
AI_TIMEOUT = 60
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES = 100
FILE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "text/plain", "text/csv",
              "application/json", "audio/mpeg", "audio/wav", "audio/webm"}
MAX_FETCH_BYTES = 1024 * 1024
FETCH_TIMEOUT = 15
_TEXT_TYPES = ("json", "text/", "xml", "javascript", "csv")
# (per visitor per hour, per app per day)
LIMITS = {"ai": (30, 500), "notify": (5, 50), "upload": (20, 200), "fetch": (60, 1000), "hook": (120, 2000)}
_hits: Dict[str, List[float]] = {}


def init(database):
    global db
    db = database


async def ensure_indexes():
    await db.appdata_files.create_index([("appId", 1), ("id", 1)], unique=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "?")


def _limit(kind: str, app_id: str, request: Request) -> None:
    per_ip, per_app = LIMITS[kind]
    now = time.time()
    for key, cap, window in ((f"{kind}|{app_id}|{_ip(request)}", per_ip, 3600), (f"{kind}|{app_id}", per_app, 86400)):
        hits = [t for t in _hits.get(key, []) if now - t < window]
        if len(hits) >= cap:
            _hits[key] = hits
            raise HTTPException(status_code=429, detail="Too many requests right now. Please try again later.")
        _hits[key] = hits + [now]
    if len(_hits) > 20000:
        _hits.clear()


async def _app(app_id: str) -> dict:
    app = await db.apps.find_one({"id": app_id}, {"id": 1, "userId": 1, "name": 1})
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


def hook_key(app_id: str) -> str:
    return hmac.new(_secret().encode(), f"apphook:{app_id}".encode(), hashlib.sha256).hexdigest()[:32]


# ------------------------------------------------------------------ AI
class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=8000)


class AiIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    system: str = Field(default="", max_length=3000)
    history: List[Turn] = Field(default_factory=list, max_length=20)
    json_mode: bool = Field(default=False, alias="json")


def ai_model() -> Optional[str]:
    wanted = os.environ.get("APP_AI_MODEL")
    for m in ([wanted] if wanted else []) + FREE_AI_MODELS:
        if m and llm.configured(m) and (m == wanted or not llm.paid(m)):
            return m
    return None


@router.post("/{app_id}/ai")
async def app_ai(app_id: str, body: AiIn, request: Request):
    await _app(app_id)
    model = ai_model()
    if not model:
        raise HTTPException(status_code=503, detail="AI isn't set up on this server yet")
    _limit("ai", app_id, request)
    system = body.system or "You are a helpful assistant inside a web app. Answer clearly and briefly."
    if body.json_mode:
        system += "\nReply with only valid JSON, no other text and no code fences."
    messages = [{"role": "system", "content": system}] + [t.model_dump() for t in body.history[-20:]] \
        + [{"role": "user", "content": body.prompt}]
    out: List[str] = []

    async def run():
        async for ev in llm.stream_completion(model, messages, []):
            if ev["type"] == "text":
                out.append(ev["text"])

    try:
        await asyncio.wait_for(run(), AI_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="The AI took too long. Please try again.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"The AI is busy right now. Please try again. ({str(exc)[:120]})")
    text = "".join(out).strip()
    if body.json_mode:
        clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return {"text": text, "data": json.loads(clean)}
        except ValueError:
            return {"text": text, "data": None}
    return {"text": text}


# ------------------------------------------------------------------ email the owner
class NotifyIn(BaseModel):
    subject: str = Field(default="", max_length=150)
    message: str = Field(min_length=1, max_length=5000)
    replyTo: str = Field(default="", max_length=200)
    fields: Dict[str, Any] = Field(default_factory=dict)


@router.post("/{app_id}/notify")
async def notify(app_id: str, body: NotifyIn, request: Request):
    app = await _app(app_id)
    _limit("notify", app_id, request)
    fields = {str(k)[:60]: str(v)[:500] for k, v in list(body.fields.items())[:20]}
    data = {"subject": body.subject or f"New message from {app.get('name') or 'your app'}", "message": body.message,
            "replyTo": body.replyTo, **({"fields": fields} if fields else {})}
    appdata._check_size(data)
    ts = _now()
    await db.appdata_docs.insert_one({"appId": app_id, "collection": INBOX, "id": str(uuid.uuid4()), "data": data,
                                      "ownerId": OWNER, "private": True, "createdAt": ts, "updatedAt": ts})
    owner = await db.users.find_one({"id": app.get("userId")}, {"email": 1})
    if not (owner and owner.get("email") and mailer.configured()):
        return {"ok": True, "emailed": False}
    rows = "".join(f"<tr><td><b>{html.escape(k)}</b></td><td>{html.escape(v)}</td></tr>" for k, v in fields.items())
    lines = "\n".join(f"{k}: {v}" for k, v in fields.items())
    reply = f"\nReply to: {body.replyTo}" if body.replyTo else ""
    try:
        await mailer.send(
            owner["email"], f"[{app.get('name') or 'Your app'}] {data['subject']}"[:180],
            f"<p>{html.escape(body.message).replace(chr(10), '<br>')}</p>"
            + (f"<table>{rows}</table>" if rows else "")
            + (f"<p>Reply to: {html.escape(body.replyTo)}</p>" if body.replyTo else "")
            + "<p style='color:#888'>Sent from your app built with Krish AI. See all messages in its Data tab.</p>",
            f"{body.message}\n\n{lines}{reply}",
        )
    except Exception:
        return {"ok": True, "emailed": False}
    return {"ok": True, "emailed": True}


# ------------------------------------------------------------------ files
@router.post("/{app_id}/files")
async def upload_file(app_id: str, request: Request, file: UploadFile = File(...)):
    await _app(app_id)
    uid = appdata._viewer(request, app_id)
    kind = (file.content_type or "").split(";")[0].strip().lower()
    if kind not in FILE_TYPES:
        raise HTTPException(status_code=415, detail="Only pictures (PNG, JPG, GIF, WebP), PDF, text, CSV, JSON and audio files")
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_FILE_BYTES // (1024 * 1024)} MB)")
    if await db.appdata_files.count_documents({"appId": app_id}) >= MAX_FILES:
        raise HTTPException(status_code=403, detail="This app's file storage is full")
    _limit("upload", app_id, request)
    doc = {"appId": app_id, "id": uuid.uuid4().hex, "name": (file.filename or "file")[:120], "type": kind,
           "size": len(data), "data": data, "ownerId": uid, "createdAt": _now()}
    await db.appdata_files.insert_one(doc)
    return _public_file(doc, str(request.base_url).rstrip("/"))


def _public_file(d: dict, origin: str = "") -> dict:
    return {"id": d["id"], "name": d["name"], "type": d["type"], "size": d["size"], "ownerId": d.get("ownerId"),
            "createdAt": d["createdAt"], "url": f"{origin}/api/appdata/{d['appId']}/files/{d['id']}"}


@router.get("/{app_id}/files/{file_id}")
async def get_file(app_id: str, file_id: str):
    doc = await db.appdata_files.find_one({"appId": app_id, "id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    headers = {"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
               "Cross-Origin-Resource-Policy": "cross-origin", "Access-Control-Allow-Origin": "*"}
    if not doc["type"].startswith(("image/", "audio/")) and doc["type"] != "application/pdf":
        headers["Content-Disposition"] = "attachment"
    return Response(bytes(doc["data"]), media_type=doc["type"], headers=headers)


@router.delete("/{app_id}/files/{file_id}")
async def delete_file(app_id: str, file_id: str, request: Request):
    uid = appdata._viewer(request, app_id)
    doc = await db.appdata_files.find_one({"appId": app_id, "id": file_id}, {"ownerId": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    if doc.get("ownerId") and doc["ownerId"] != uid:
        raise HTTPException(status_code=403, detail="Only the person who uploaded this can delete it")
    await db.appdata_files.delete_one({"_id": doc["_id"]})
    return {"ok": True}


# ------------------------------------------------------------------ outside APIs
class FetchIn(BaseModel):
    url: str = Field(max_length=2000)
    method: str = Field(default="GET", pattern="^(GET|POST|PUT|PATCH|DELETE)$")
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Any = None


_BLOCKED_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "cookie", "x-forwarded-for"}


def _public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def check_url(url: str) -> str:
    """The URL if it points at the public internet, else HTTPException (no localhost, private networks, metadata)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise HTTPException(status_code=400, detail="Use a full http(s) address")
    if parts.port not in (None, 80, 443, 8080, 8443):
        raise HTTPException(status_code=400, detail="That port isn't allowed")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="That address couldn't be found")
    if not infos or not all(_public_ip(i[4][0]) for i in infos):
        raise HTTPException(status_code=400, detail="That address isn't on the public internet")
    return url


@router.post("/{app_id}/fetch")
async def proxy_fetch(app_id: str, body: FetchIn, request: Request):
    await _app(app_id)
    _limit("fetch", app_id, request)
    headers = {k: v for k, v in list(body.headers.items())[:20] if k.lower() not in _BLOCKED_HEADERS}
    headers.setdefault("User-Agent", "KrishAI-App/1.0")
    kwargs: Dict[str, Any] = {}
    if body.body is not None and body.method != "GET":
        if isinstance(body.body, str):
            kwargs["content"] = body.body[:200_000]
        else:
            kwargs["json"] = body.body
    url = body.url
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=False) as client:
        for _ in range(4):  # follow up to 3 redirects, checking each address
            await check_url(url)
            async with client.stream(body.method, url, headers=headers, **kwargs) as resp:
                peer = resp.extensions.get("network_stream")
                addr = peer.get_extra_info("server_addr") if peer else None
                if addr and not _public_ip(str(addr[0])):
                    raise HTTPException(status_code=400, detail="That address isn't on the public internet")
                if resp.is_redirect and resp.headers.get("location"):
                    url = str(resp.url.join(resp.headers["location"]))
                    continue
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_FETCH_BYTES:
                        raise HTTPException(status_code=413, detail="The response is too large (max 1 MB)")
                    chunks.append(chunk)
                kind = resp.headers.get("content-type", "")
                raw = b"".join(chunks)
                text = raw.decode(resp.encoding or "utf-8", errors="replace") if any(t in kind for t in _TEXT_TYPES) or not kind else ""
                data = None
                if "json" in kind:
                    try:
                        data = json.loads(text)
                    except ValueError:
                        pass
                return {"status": resp.status_code, "ok": resp.is_success, "contentType": kind, "text": text, "data": data}
    raise HTTPException(status_code=400, detail="Too many redirects")


# ------------------------------------------------------------------ webhooks in
@router.post("/{app_id}/hook/{collection}")
async def webhook(app_id: str, collection: str, request: Request, key: str = Query(""), private: bool = Query(False)):
    await _app(app_id)
    if not hmac.compare_digest(key, hook_key(app_id)):
        raise HTTPException(status_code=403, detail="Wrong or missing key")
    collection = appdata._collection(collection)
    _limit("hook", app_id, request)
    raw = await request.body()
    if len(raw) > appdata.MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="Too large")
    kind = request.headers.get("content-type", "")
    if "form" in kind:
        data: Any = dict((await request.form()).items())
        data = {k: str(v)[:2000] for k, v in data.items()}
    else:
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            data = {"text": raw.decode("utf-8", errors="replace")}
    if not isinstance(data, dict):
        data = {"value": data}
    if await db.appdata_docs.count_documents({"appId": app_id}) >= appdata.MAX_DOCS:
        raise HTTPException(status_code=403, detail="This app's database is full")
    ts = _now()
    doc = {"appId": app_id, "collection": collection, "id": str(uuid.uuid4()), "data": data,
           "ownerId": OWNER if private else None, "private": private, "createdAt": ts, "updatedAt": ts}
    await db.appdata_docs.insert_one(doc)
    return {"ok": True, "id": doc["id"]}


# ------------------------------------------------------------------ owner's Data tab
async def _owner_app(app_id: str, request: Request) -> dict:
    user_id = get_user_id_from_request(request)
    app = await db.apps.find_one({"id": app_id, "userId": user_id}, {"id": 1, "name": 1})
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


@owner_router.get("/{app_id}/data")
async def data_overview(app_id: str, request: Request):
    await _owner_app(app_id, request)
    groups = await db.appdata_docs.aggregate([
        {"$match": {"appId": app_id}}, {"$group": {"_id": "$collection", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}},
    ]).to_list(200)
    origin = (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or str(request.base_url)).rstrip("/")
    return {
        "collections": [{"name": g["_id"], "count": g["count"]} for g in groups],
        "users": await db.appdata_users.count_documents({"appId": app_id}),
        "files": await db.appdata_files.count_documents({"appId": app_id}),
        "hookUrl": f"{origin}/api/appdata/{app_id}/hook/COLLECTION?key={hook_key(app_id)}",
        "emailReady": mailer.configured(),
        "aiReady": ai_model() is not None,
    }


@owner_router.get("/{app_id}/data/users")
async def data_users(app_id: str, request: Request):
    await _owner_app(app_id, request)
    users = await db.appdata_users.find({"appId": app_id}).sort("createdAt", -1).to_list(500)
    return [{**appdata._public_user(u), "createdAt": u.get("createdAt")} for u in users]


@owner_router.get("/{app_id}/data/files")
async def data_files(app_id: str, request: Request):
    await _owner_app(app_id, request)
    docs = await db.appdata_files.find({"appId": app_id}, {"data": 0}).sort("createdAt", -1).to_list(500)
    return [_public_file(d) for d in docs]


@owner_router.get("/{app_id}/data/docs/{collection}")
async def data_docs(app_id: str, collection: str, request: Request):
    await _owner_app(app_id, request)
    docs = await db.appdata_docs.find({"appId": app_id, "collection": appdata._collection(collection)}) \
        .sort("createdAt", -1).to_list(500)
    return [appdata._public_doc(d) for d in docs]


@owner_router.delete("/{app_id}/data/docs/{collection}/{doc_id}")
async def data_delete_doc(app_id: str, collection: str, doc_id: str, request: Request):
    await _owner_app(app_id, request)
    await db.appdata_docs.delete_one({"appId": app_id, "collection": appdata._collection(collection), "id": doc_id})
    return {"ok": True}


@owner_router.delete("/{app_id}/data/users/{user_id}")
async def data_delete_user(app_id: str, user_id: str, request: Request):
    await _owner_app(app_id, request)
    await db.appdata_users.delete_one({"appId": app_id, "id": user_id})
    return {"ok": True}


@owner_router.delete("/{app_id}/data/files/{file_id}")
async def data_delete_file(app_id: str, file_id: str, request: Request):
    await _owner_app(app_id, request)
    await db.appdata_files.delete_one({"appId": app_id, "id": file_id})
    return {"ok": True}
