from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import asyncio
import anyio
import functools
import hashlib
import json
import os
import re
import secrets
import time
import uuid
import logging
import mimetypes
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
from ai_runtime import (ModelRouter, AnthropicProvider, OpenAIProvider, GeminiProvider, GroqProvider, OpenRouterProvider,
                        AIRequest, ChatMessage)
from ai_runtime._backend import uses_emergent
import storage
import embeddings
import extract as extractor
import memory
import vision
import media
import preview as previewer
import apps
import site_images
import appcloud
import decks
import appdata
import automations
import live_search
import related
import mailer
import counsellor
import discover
import help_center
import writer
import code_edit
import code_check
import limits
import billing
import languages
import abuse
import daily_verse
import google_signin
import monitor
import promos
import referrals
import growth_mail
import invite_card
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
# A free model made for code (OpenRouter's free tier, OPENROUTER_API_KEY). Coding questions asked of a free model go
# to it when it's set up; CODER_MODEL picks another one if this one is retired.
CODER_MODEL = os.environ.get("CODER_MODEL", "").strip() or "openrouter/qwen/qwen3-coder:free"
# What people see in the model menu: Krish names and plain words, never the provider or its tier.
# "pro" marks models only paid plans get (the frontend shows a Pro badge on them). The free models (Gemini, Groq,
# Cerebras and Krish Coder) are one model, Krish AI, which picks the right one for each question (see _auto_model);
# their ids still work for older chats and for AI_MODEL / BUILDER_MODEL.
AUTO_MODEL = agent_llm.AUTO
AVAILABLE_MODELS = [
    {"id": AUTO_MODEL, "label": "Krish Basic", "description": "Free, and picks the best engine for each question", "pro": False},
    {"id": "claude-sonnet-5-5", "label": "Krish Ultra", "description": "Our smartest, for deep thinking", "pro": True},
    {"id": "claude-haiku-4-5-20251001", "label": "Krish Swift", "description": "Quick and sharp for daily work", "pro": True},
    {"id": "gpt-5.4", "label": "Krish Vision", "description": "A strong all-rounder for any task", "pro": True},
]
# The App Builder's models: BUILDER_MODEL (any model above, the owner's choice for every user) wins;
# otherwise free-tier builds (Groq or Gemini) move to Krish Coder when it's set up (it writes better code, and hands
# over to Cerebras when its free allowance runs out), else to Cerebras, since it fits about 4x more per request.
FREE_BUILDER = "cerebras/gpt-oss-120b"
BUILDER_STEPS = 14  # tool steps per builder turn for models with room for them (Groq's free tier keeps the default)

# Default model: AI_MODEL if set, otherwise the first configured model, free ones first, so adding a
# paid key doesn't make every chat paid.
AI_MODEL = (os.environ.get("AI_MODEL")
            or (AUTO_MODEL if agent_llm.configured(AUTO_MODEL) else None)
            or next((m["id"] for m in sorted(AVAILABLE_MODELS, key=lambda m: agent_llm.paid(m["id"]))
                     if agent_llm.configured(m["id"])), "claude-sonnet-5-5"))

# AI Runtime: RADHA -> Router -> Provider -> LLM
# Providers use the Emergent Universal Key on Emergent, or LiteLLM with your own
# keys elsewhere. Adding a provider is a single .register() call.
model_router = (
    ModelRouter(default_model=AI_MODEL)
    .register(AnthropicProvider(AI_API_KEY))
    .register(OpenAIProvider(AI_API_KEY))
    .register(GeminiProvider(AI_API_KEY))
    .register(GroqProvider())
    .register(OpenRouterProvider())
)


tool_registry = default_registry()
storage.init(db)
apps.init(db)
appdata.init(db)
site_images.init(db)
appcloud.init(db)
apps.register_tools(tool_registry)

# The web app owns /docs and the API owns /api/docs (both the Docs writing space), so FastAPI's own
# API reference pages are turned off: at /api/docs they hid the Docs list and broke the Docs page.
app = FastAPI(title="Krish AI API", docs_url=None, redoc_url=None, openapi_url=None)
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
    ref: Optional[str] = Field(default=None, max_length=20)  # a friend's invite code


class GoogleSignInIn(BaseModel):
    credential: str = Field(min_length=20, max_length=5000)  # the signed token from Google's button
    ref: Optional[str] = Field(default=None, max_length=20)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=6, max_length=128)


class DeleteAccountIn(BaseModel):
    password: str = Field(default="", max_length=128)
    confirmEmail: str = Field(default="", max_length=320)  # accounts made with Google have no password


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
    think: bool = False  # the Think button: reason longer and check the answer
    study: bool = False  # Study mode: teach step by step and quiz instead of just answering
    web: bool = False  # the Search button: always search the web and cite sources
    focus: Literal["web", "academic", "social", "video"] = "web"  # where Search looks
    pro: bool = False  # Pro search: plan several searches and read the best pages
    voice: bool = False  # sent from voice mode: the reply is spoken aloud
    voiceLang: Optional[str] = Field(default=None, max_length=8)


class RegenerateIn(BaseModel):
    model: Optional[str] = None
    agent: bool = False
    think: bool = False
    study: bool = False
    web: bool = False
    focus: Literal["web", "academic", "social", "video"] = "web"
    pro: bool = False


class EditIn(RegenerateIn):
    content: str = Field(min_length=1)


class SpeechIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    voice: Optional[str] = None
    lang: Optional[str] = Field(default=None, max_length=8)


def public_user(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "email": doc["email"],
        "name": doc["name"],
        "language": languages.normalize(doc.get("language")),
        "plan": limits.plan_from(doc),
        "planExpiresAt": doc.get("planExpiresAt") if limits.plan_from(doc) != "basic" else None,
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
        "isOwner": is_owner_email(doc["email"]),
        "hasPassword": bool(doc.get("password_hash")),
        "google": bool(doc.get("googleId")),
    }


def owner_emails() -> set:
    """The app owner's email(s), from OWNER_EMAIL (comma-separated). Only they can see the users list."""
    return {e.strip().lower() for e in os.environ.get("OWNER_EMAIL", "").split(",") if e.strip()}


def is_owner_email(email: str) -> bool:
    return (email or "").lower() in owner_emails()


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
        "assistantCode": doc.get("assistantCode"),
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
        "related": doc.get("related") or [],
        "webHint": bool(doc.get("webHint")),
        "images": doc.get("images") or [],
        "steps": doc.get("steps") or [],
        "media": doc.get("media") or [],
        "stopped": bool(doc.get("stopped")),
        "rating": doc.get("rating"),
        "createdAt": doc["createdAt"],
    }


# ----------------------------------------------------------------------- auth
async def _check_new_account(email: str, request: Request) -> None:
    """Spam protection for sign-ups: no throwaway emails, and only a few new accounts an hour per connection."""
    await abuse.check_signup_email(email)
    abuse.require("signup", abuse.client_ip(request))


@api.get("/auth/config")
async def auth_config():
    """What the login page offers: the Google button appears only when GOOGLE_CLIENT_ID is set."""
    return {"googleClientId": google_signin.client_id() or None, "inviteDays": referrals.REWARD_DAYS}


@api.post("/auth/register")
async def register(body: RegisterIn, request: Request):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    await _check_new_account(email, request)
    ts = now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": body.name.strip(),
        "password_hash": hash_password(body.password),
        "createdAt": ts,
        "updatedAt": ts,
        "lastLoginAt": ts,
        "lastSeenAt": ts,
        "loginCount": 1,
    }
    await db.users.insert_one(doc)
    referral = await referrals.apply(db, doc, body.ref)
    if referral:
        doc = await db.users.find_one({"id": doc["id"]})
    _welcome_emails(doc, referral)
    token = create_access_token(doc["id"], email)
    return {"token": token, "user": public_user(doc), "invited": bool(referral)}


def _welcome_emails(user: dict, referral: Optional[dict]) -> None:
    """A personal welcome (with a picture) for the new person, and a thank-you to whoever invited them."""
    base = growth_mail.app_url()
    if not base:
        return
    inviter = (referral or {}).get("inviter") or {}
    _background(growth_mail.send(user["email"], growth_mail.welcome(
        base, user.get("name", ""), inviter.get("name", "") if referral else "", referrals.REWARD_DAYS)))
    if referral:
        _background(growth_mail.send(inviter.get("email"), growth_mail.friend_joined(
            base, inviter.get("name", ""), user.get("name", ""), referrals.REWARD_DAYS, referral["rewarded"],
            referral["joined"])))


@api.post("/auth/google")
async def google_sign_in(body: GoogleSignInIn, request: Request):
    """Sign in (or sign up) with the token from Google's button. A matching email account is the same account."""
    try:
        info = await google_signin.verify(body.credential)
    except google_signin.GoogleSignInError as exc:
        logger.warning(f"Google sign-in refused: {exc}")
        raise HTTPException(status_code=401, detail="Google sign-in didn't work. Please try again.")
    ts = now_iso()
    doc = await db.users.find_one({"googleId": info["sub"]}) or await db.users.find_one({"email": info["email"]})
    referral = None
    if doc:
        await db.users.update_one({"id": doc["id"]}, {"$set": {"googleId": info["sub"], "lastLoginAt": ts, "lastSeenAt": ts},
                                                      "$inc": {"loginCount": 1}})
    else:
        abuse.require("signup", abuse.client_ip(request))  # Google confirmed the email, so no email check
        doc = {
            "id": str(uuid.uuid4()), "email": info["email"], "name": info["name"].strip() or "Friend",
            "password_hash": "", "googleId": info["sub"],
            "createdAt": ts, "updatedAt": ts, "lastLoginAt": ts, "lastSeenAt": ts, "loginCount": 1,
        }
        try:
            await db.users.insert_one(doc)
        except Exception:  # the same person signing in twice at once
            doc = await db.users.find_one({"email": info["email"]})
            if not doc:
                raise
        else:
            referral = await referrals.apply(db, doc, body.ref)
            _welcome_emails(doc, referral)
    doc = await db.users.find_one({"id": doc["id"]})
    return {"token": create_access_token(doc["id"], doc["email"]), "user": public_user(doc), "invited": bool(referral)}


LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 15 * 60
_login_failures: dict = {}  # email -> monotonic times of recent wrong passwords


def _recent_failures(email: str) -> list:
    cutoff = time.monotonic() - LOGIN_WINDOW_SECONDS
    recent = [t for t in _login_failures.get(email, []) if t > cutoff]
    if recent:
        _login_failures[email] = recent
    else:
        _login_failures.pop(email, None)
    return recent


@api.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.lower()
    # Stop password guessing: after 10 wrong passwords in 15 minutes the account waits (reset still works).
    if len(_recent_failures(email)) >= LOGIN_MAX_FAILURES:
        raise HTTPException(status_code=429, detail="Too many wrong passwords. Wait 15 minutes, or use "
                                                    "\"Forgot password\" to set a new one.")
    doc = await db.users.find_one({"email": email})
    if not doc or not verify_password(body.password, doc.get("password_hash", "")):
        _login_failures.setdefault(email, []).append(time.monotonic())
        if len(_login_failures) > 50000:  # keep memory bounded under a flood of made-up emails
            _login_failures.clear()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _login_failures.pop(email, None)
    ts = now_iso()
    await db.users.update_one({"id": doc["id"]}, {"$set": {"lastLoginAt": ts, "lastSeenAt": ts},
                                                  "$inc": {"loginCount": 1}})
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
    _login_failures.pop(user["email"], None)
    return {"token": create_access_token(user["id"], user["email"]), "user": public_user(user)}


@api.post("/auth/logout")
async def logout():
    return {"ok": True}


@api.post("/auth/delete-account")
async def delete_account(body: DeleteAccountIn, user_id: str = Depends(current_user_id)):
    """Delete the account and everything in it (chats, files, projects, apps, decks, docs, automations, memory).
    Asks for the password again so a borrowed, signed-in phone can't do it by accident."""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.get("password_hash"):
        if not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=403, detail="That password isn't right.")
    elif body.confirmEmail.strip().lower() != user["email"]:
        raise HTTPException(status_code=403, detail="Type your account email exactly to confirm.")
    for app in await db.apps.find({"userId": user_id}, {"id": 1}).to_list(None):
        await apps.delete_app(app["id"], user_id)
    for auto in await db.automations.find({"userId": user_id}, {"id": 1}).to_list(None):
        await automations.delete_automation(auto["id"], user_id)
    async for f in db.files.find({"userId": user_id}, {"storage_path": 1}):
        if f.get("storage_path"):
            await storage.delete_object(f["storage_path"])
    conv_ids = [c["id"] async for c in db.conversations.find({"userId": user_id}, {"id": 1})]
    await db.messages.delete_many({"conversationId": {"$in": conv_ids}})
    await media.delete_media(db, {"userId": user_id})
    for name in ("conversations", "files", "chunks", "memories", "projects", "decks", "docs", "pages",
                 "help_reports", "password_resets", "push_subscriptions", "message_feedback", "activity"):
        await db[name].delete_many({"userId": user_id})
    await db.referrals.delete_many({"$or": [{"inviterId": user_id}, {"friendId": user_id}]})
    await db.usage.delete_many({"_id": {"$regex": f"^{re.escape(user_id)}:"}})
    await db.users.delete_one({"id": user_id})
    _login_failures.pop(user["email"], None)
    return {"ok": True}


@api.get("/auth/me")
async def me(user_id: str = Depends(current_user_id)):
    doc = await db.users.find_one({"id": user_id})
    if not doc:
        raise HTTPException(status_code=401, detail="User not found")
    # Opening the app with a saved sign-in counts as a visit, so the owner sees who is still using Krish.
    await db.users.update_one({"id": user_id}, {"$set": {"lastSeenAt": now_iso()}})
    await monitor.count(db, user_id)
    return public_user(doc)


@api.get("/admin/users")
async def admin_users(user_id: str = Depends(current_user_id)):
    """Owner only: everyone who has an account, most recently active first. Others get a plain 404."""
    me_doc = await db.users.find_one({"id": user_id}, {"email": 1})
    if not me_doc or not is_owner_email(me_doc["email"]):
        raise HTTPException(status_code=404, detail="Not found")
    fields = {"_id": 0, "id": 1, "name": 1, "email": 1, "plan": 1, "planExpiresAt": 1, "createdAt": 1,
              "lastLoginAt": 1, "lastSeenAt": 1, "loginCount": 1}
    docs = await db.users.find({}, fields).to_list(10000)
    users = [{
        "id": d["id"], "name": d.get("name", ""), "email": d["email"],
        "plan": limits.plan_from(d),
        "createdAt": d.get("createdAt"), "lastLoginAt": d.get("lastLoginAt"),
        "lastSeenAt": d.get("lastSeenAt") or d.get("lastLoginAt"), "loginCount": d.get("loginCount", 0),
    } for d in docs]
    users.sort(key=lambda u: u["lastSeenAt"] or u["createdAt"] or "", reverse=True)
    return {"total": len(users), "users": users}


async def _require_owner(user_id: str) -> None:
    me_doc = await db.users.find_one({"id": user_id}, {"email": 1})
    if not me_doc or not is_owner_email(me_doc["email"]):
        raise HTTPException(status_code=404, detail="Not found")


@api.get("/admin/stats")
async def admin_stats(days: int = Query(14, ge=1, le=60), user_id: str = Depends(current_user_id)):
    """Owner only: people and features used each day, 👍 / 👎 on answers, and the latest problems."""
    await _require_owner(user_id)
    return await monitor.stats(db, days)


class PromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=24)
    percentOff: int = Field(ge=1, le=promos.MAX_PERCENT)
    maxUses: int = Field(default=0, ge=0, le=1000000)
    expiresOn: Optional[str] = Field(default=None, max_length=10)  # last day, YYYY-MM-DD


class PromoActiveIn(BaseModel):
    active: bool


@api.get("/admin/promos")
async def admin_promos(user_id: str = Depends(current_user_id)):
    await _require_owner(user_id)
    return {"codes": await promos.list_all(db)}


@api.post("/admin/promos")
async def admin_create_promo(body: PromoIn, user_id: str = Depends(current_user_id)):
    await _require_owner(user_id)
    try:
        return await promos.create(db, body.code, body.percentOff, body.maxUses, body.expiresOn)
    except promos.PromoError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@api.put("/admin/promos/{code}")
async def admin_toggle_promo(code: str, body: PromoActiveIn, user_id: str = Depends(current_user_id)):
    await _require_owner(user_id)
    doc = await promos.set_active(db, code, body.active)
    if not doc:
        raise HTTPException(status_code=404, detail="No such code")
    return doc


@api.get("/invite/{code}")
async def invite_info(code: str):
    """The invite page (open to anyone with the link): who invited them and how many free Pro days they get."""
    info = await referrals.public_invite(db, code)
    if not info:
        raise HTTPException(status_code=404, detail="This invite link isn't valid any more.")
    return info


@api.get("/cards/invite/{code}.png", include_in_schema=False)
async def invite_card_png(code: str):
    """The invite picture for link previews and sharing: "<Name> invited you to Krish AI"."""
    info = await referrals.public_invite(db, code)
    png = invite_card.render(info["name"] if info else "", referrals.REWARD_DAYS)
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@api.get("/cards/welcome.png", include_in_schema=False)
async def welcome_card_png(n: str = Query("", max_length=40), p: str = Query("", max_length=8)):
    """The picture at the top of welcome and thank-you emails."""
    png = invite_card.welcome(invite_card.first_name(n), p if p in ("pro", "max") else "")
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})


@api.get("/referrals")
async def my_referrals(user_id: str = Depends(current_user_id)):
    """The Invite page: this person's invite code and what it has earned."""
    return await referrals.summary(db, user_id)


class ClientErrorIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    stack: str = Field(default="", max_length=8000)
    path: str = Field(default="", max_length=500)


@api.post("/client-errors")
async def client_error(body: ClientErrorIn, request: Request):
    """A crash in the app on someone's device, sent so the owner hears about it. Works signed in or out."""
    abuse.require("report", abuse.client_ip(request))
    try:
        user_id = get_user_id_from_request(request)
    except HTTPException:
        user_id = ""
    await monitor.record("app", body.message, body.stack, body.path, user_id)
    return {"ok": True}


class LanguageIn(BaseModel):
    language: str


@api.put("/auth/language")
async def set_language(body: LanguageIn, user_id: str = Depends(current_user_id)):
    if body.language not in languages.LANGUAGES:
        raise HTTPException(status_code=400, detail="That language isn't available.")
    await db.users.update_one({"id": user_id}, {"$set": {"language": body.language, "updatedAt": now_iso()}})
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


@api.get("/conversations/search")
async def search_conversations(q: str = Query(min_length=2, max_length=100), user_id: str = Depends(current_user_id)):
    """Find chats whose title or messages contain the words, with a short snippet around the first match."""
    convs = await db.conversations.find(
        {"userId": user_id, "appId": None, "automationId": None, "mode": None},
        {"id": 1, "title": 1, "updatedAt": 1}).sort("updatedAt", -1).to_list(500)
    by_id = {c["id"]: c for c in convs}
    pattern = {"$regex": re.escape(q.strip()), "$options": "i"}
    hits = {}
    for c in convs:
        if re.search(re.escape(q.strip()), c.get("title") or "", re.IGNORECASE):
            hits[c["id"]] = None
    msgs = await db.messages.find({"conversationId": {"$in": list(by_id)}, "content": pattern},
                                  {"conversationId": 1, "content": 1}).sort("createdAt", -1).to_list(400)
    for m in msgs:
        if hits.get(m["conversationId"]) is None:
            hits[m["conversationId"]] = _snippet(m["content"], q.strip())
    ordered = [c for c in convs if c["id"] in hits][:30]
    return [{"id": c["id"], "title": c["title"], "updatedAt": c["updatedAt"], "snippet": hits[c["id"]]} for c in ordered]


def _snippet(text: str, q: str, width: int = 70) -> str:
    m = re.search(re.escape(q), text, re.IGNORECASE)
    if not m:
        return text[:width * 2]
    start, end = max(0, m.start() - width), min(len(text), m.end() + width)
    out = re.sub(r"\s+", " ", text[start:end]).strip()
    return ("…" if start else "") + out + ("…" if end < len(text) else "")


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
# Who makes Krish AI. Without this, models guessed, or copied the founders of other companies named EmpireX
# from web results.
ABOUT_EMPIREX = (
    "About you and your company: you are Krish AI, made and owned by EmpireX, an Indian technology company based in "
    "India. EmpireX was earlier called Automatex; it is the same company under a new name. When asked who made, "
    "built, trained or owns you, or who your company is, say EmpireX, an Indian company based in India. "
    "EmpireX was founded by Lakshay Sharma, who leads the company. When asked who the founder, owner, CEO or head "
    "of EmpireX or Krish AI is, say Lakshay Sharma. Name no one else, and never take facts about Krish AI or "
    "EmpireX from web results: other, unrelated companies also use the name EmpireX. Don't bring this up unless "
    "the user asks.\n\n"
)

# How to read what people actually type. Many users write fast on a phone: typos, missing spaces, stretched letters
# ("plzzz"), SMS short forms, slang, voice-typing slips and Roman Hindi mixed with English. Krish read some of
# these literally, answered the wrong thing, or replied in a different language than the user wrote.
UNDERSTAND_USER = (
    "Understanding the user: many people type fast on a phone, so read every message for what they mean, not "
    "the exact spelling. Typos, missing spaces or punctuation, stretched letters (\"plzzz\", \"hiiii\"), short "
    "forms (u, r, pls, msg, tmrw, bcz, kya, kr, hai), slang, voice-typing slips and Hindi written in English "
    "letters mixed with English (Hinglish) are normal: work out the likeliest meaning and answer it. Never "
    "correct, mention or joke about their spelling or grammar. A short or vague message (\"aur?\", \"iska "
    "price\", \"same for 2nd one\", \"not working\", \"ok then?\") continues the chat: read it with the earlier "
    "messages and pictures, work out what \"it\", \"this\" or \"wo\" points to, and answer that. If one meaning "
    "is clearly likelier, answer it, and say in a few words which one you took only when it really could be "
    "read another way. Ask one short clarifying question, offering the two or three likely options, only when "
    "you truly can't tell what they want and a wrong guess would waste their time. Reply in the language and "
    "script they write in: Hinglish in English letters gets Hinglish in English letters, Hindi in Devanagari "
    "gets Devanagari, English gets English, and a mix gets the same mix, written correctly and simply.\n\n"
)

# The App Builder's base prompt. It replaces SYSTEM_PROMPT there: the chat prompt's "put code in fenced blocks"
# would fight the file tools, and its design guide is already in apps.app_prompt (Groq's free budget is tight).
BUILDER_PROMPT = ("You are Krish AI, the AI app builder made by EmpireX. You build by calling your file tools; never "
                  "paste code into the chat. Reply in the user's language, in a line or two. Read typos, short forms "
                  "and Hinglish for what the user means, and build that. " + ABOUT_EMPIREX)

SYSTEM_PROMPT = (
    "You are Krish AI, the flagship AI assistant built by EmpireX. " + ABOUT_EMPIREX + UNDERSTAND_USER +
    "Answer first: put the direct answer in the first sentence, then add only what the user needs. "
    "Keep replies short and easy to scan. No filler, no restating the question, no long lists of alternatives, "
    "no tables or code unless the user asks or they clearly help. Match the user's language.\n\n"
    "Write ordinary answers like a friendly expert chatting, not a report: usually 2-4 short paragraphs of one "
    "to three sentences each, with a blank line between them. Put the key facts and phrases in **bold**: the "
    "direct answer, names, numbers, prices, dates and the one thing the user should do (for example \"That "
    "looks like a **boAt Airdopes charging case**\" or \"around **\u20b9799**\"). Bold a few words per "
    "paragraph, never whole sentences or every line. Use bullets only for real lists of three or more items. "
    "Never send one long block of text: when an answer runs past about four sentences, split it into short "
    "paragraphs or bullets so it reads easily on a phone. "
    "Sound warm and direct, and when you can't be sure, say so plainly and why. End with one short, specific "
    "offer that keeps the chat going, naming what the user could send or ask next (\"If you **send a photo of "
    "the back of the case**, I can tell you the exact model.\"); skip it for greetings, thanks and one-word "
    "answers.\n\n"
    "Write well. Use clear, natural, correct English (or the user's language) with proper grammar, capitals and "
    "punctuation, even when the user writes casually or in Hinglish. Prefer short, plain words and active "
    "sentences, and vary how sentences start. Every sentence should add something: no throat-clearing (\"Great "
    "question!\", \"Sure!\", \"Certainly!\"), no stock phrases (\"It's important to note\", \"In today's "
    "world\", \"delve\", \"In conclusion\"), no repeating the same point in other words, and at most one emoji, "
    "only when the mood is light. For longer answers (explanations, comparisons, plans, how-tos), give the shape "
    "at a glance: a one-line answer on top, then two to four short sections that each start with a short bold "
    "label or a ### heading, numbered steps for anything done in order, and a one-line takeaway at the end. "
    "Keep the same style through the whole answer.\n\n"
    "For meaningful or personal questions (life, faith, Krishna and the Gita, relationships, purpose, a hard "
    "choice), slow down and answer with warmth and depth, like a wise friend: the plain answer first in its own "
    "short paragraph, then the two or three key ideas, each in a short paragraph or bullet with its core point in "
    "**bold**, a quote on its own line (> ...) when you share a verse or saying, and a caring closing line. Keep "
    "slang and jokes out of these answers.\n\n"
    "Get it right before you write it. Answer the question the user actually asked, and every part of it when "
    "they ask several things. Be specific: real names, numbers, prices in \u20b9 for Indian users, steps and "
    "examples that fit their situation, not generic advice anyone could give. Work out maths, logic, dates and "
    "unit conversions step by step before you write the answer, check the result (plug it back in, estimate, or "
    "count again), and show the short working when it helps the user follow. For code, write it so it runs: "
    "correct imports, real APIs for the version they use, edge cases handled, and say in one line how to run it. "
    "If the question rests on a wrong fact, say so kindly and answer the real question. If it could mean two "
    "different things, answer the likeliest one and say in a few words which one you took. Never invent facts, "
    "quotes, studies, laws, links or numbers; when you aren't sure, say what you do know and what to check. "
    "For advice on health, money or law, give the useful specifics first, then one line on when to see a "
    "professional. Keep the friendly, short style above: careful thinking, not longer answers.\n\n"
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
    "For a site, game or tool, prefer one complete index.html with its CSS in <style> and its JavaScript in "
    "<script>, unless the user asks for separate files or it is large. Write working code, not placeholders: every "
    "button and form does what it says, every id the script uses exists in the HTML, every function it calls is "
    "defined, it works on phones as well as computers, and data the user adds is kept in localStorage when it "
    "should survive a reload. Say in one line what you built before "
    "the files. Krish AI shows the user a live preview, a Download ZIP button and an Open in App Builder button for "
    "those files automatically. Never output base64, never pretend to attach or encode a ZIP or any other archive, "
    "and never tell the user to decode anything. When the user gives you their own code or file and asks for a "
    "change, keep everything else exactly as they wrote it (structure, styles, colors, wording) and change only "
    "what they asked; return each changed file in full. The design guide below is only for things you design "
    "yourself.\n\n" + apps.DESIGN_GUIDE
)


_CITATION = re.compile(r"\[\d{1,2}\]")

NO_RESULTS_NOTE = (
    "The automatic web search found nothing for this question. Call web_search now with a short, clear query "
    "before answering. Don't answer current facts (who holds a job, prices, news) from memory: they may have "
    "changed. If your search also finds nothing, say you couldn't check it live and that your answer may be out of date."
)
NO_RESULTS_NOTE_PLAIN = (
    "The web search found nothing for this question just now. Answer from what you know, but say plainly that you "
    "couldn't check it live, so facts that change (who holds a job, prices, news) may be out of date."
)
STREAM_FAILED_NOTE = ("Sorry, the AI model stopped before writing the answer (it may be busy or out of free "
                      "requests for now). Tap Regenerate, or pick another model from the menu at the top.")
WEB_OFF_NOTE = (
    "Web search is off for this answer (the user turns it on with the Web button). Answer from what you know and "
    "never say you searched. If the answer depends on facts that change (news, prices, who holds a job), add one "
    "short line that it may be out of date. Live exchange rates, weather or stock data given below are current."
)

AGENT_PROMPT = (
    "You have tools; use them on your own whenever they make the answer better, without asking. "
    "Anything current or checkable (news, prices, rates, scores, people, recent events, facts you are unsure of): "
    "call web_search first, open the best result with fetch_url when snippets are thin, and answer from what you "
    "found, citing results with their [n] numbers. For research, reports, market analysis or detailed comparisons of tools, prices or options, "
    "call deep_research (it writes a cited PDF report). For step-by-step guides, web_search the service's current "
    "docs first so button names are right. Live exchange rates, when given, are the source of truth for currency questions. "
    "Use run_python for any calculation, data work or chart; browser to operate websites; edit_image to change a "
    "picture the user attached or you made (AI changes or quick fixes like crop, rotate, black and white); generate_image and "
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


THINK_PROMPT = (
    "Think mode is on: the user wants your most careful answer. Before you write, work out what they really need, "
    "solve it step by step, and look for the traps: a wrong assumption, a missed case, a unit or date mistake, an "
    "outdated fact. Check your answer a second way (redo the sum differently, test the code in your head on a "
    "tricky input, ask what an expert would object to) and fix anything that doesn't hold. Check facts with "
    "web_search when they matter and you can. Then lead with the answer, give the key reasoning in a few short "
    "steps, and say plainly what you are unsure of. Think mode may be longer than a usual reply, but never padded."
)

# Pro and Max answers are crafted, not just quick (limits.work_of: any plan whose model isn't "free").
PREMIUM_ANSWER_PROMPT = (
    "This user is on a paid plan: give them noticeably better answers than a quick reply. Understand what they "
    "are really trying to do and answer that. Make it complete and polished: a clear structure (short headings or "
    "bullets when it helps, a table for any comparison), one concrete example or worked case, the details an "
    "expert would add, and end with a useful next step or tip. Make it personal when you know about them. Stay "
    "warm and easy to read; never pad, and keep short questions short."
)

# Questions where a free reasoning model answers better when it thinks harder (see agent_llm.DEEPER): maths and
# numbers, code, "why"/"how"/"compare" questions, plans and puzzles. Long asks count too.
_HARD_ASK = re.compile(
    r"\d\s*[-+*/x\u00d7\u00f7^%]\s*\d|\b\d{1,2}:\d{2}\b|\bhow (?:many|much|long|far)\b|"
    r"\b(solve|calculate|calculation|compute|prove|derive|equation|formula|integral|derivative|probability|"
    r"speed|distance|percent|percentage|interest|emi|loan|profit|loss|ratio|average|tax|gst|why|how does|"
    r"how do|how is|how are|how can|explain|compare|comparison|difference between|vs|versus|pros and cons|"
    r"should i|which is better|best way|plan|strategy|analy[sz]e|analysis|debug|error|bug|code|function|"
    r"algorithm|sql|regex|riddle|puzzle|logic|kyu|kyon|kaise)\b", re.IGNORECASE)
HARD_ASK_CHARS = 280


def _hard_ask(text: str) -> bool:
    """True when the user's message looks like it needs real reasoning (see _HARD_ASK)."""
    return len(text or "") >= HARD_ASK_CHARS or bool(_HARD_ASK.search(text or ""))


# Coding questions (writing, fixing or explaining code) get CODE_PROMPT on top of the chat prompt.
_CODE_ASK = re.compile(
    r"```|\btraceback\b|(?-i:\b[A-Z][A-Za-z]*(?:Error|Exception)\b)|\bfunctions? (?:to|that|which|in)\b|"
    r"(?<!pin )(?<!promo )(?<!coupon )(?<!zip )(?<!dress )(?<!qr )(?<!otp )(?<!referral )\bcode\b|"
    r"\b(coding|programming|script|bug|debug|exception|stack ?trace|compile|compiler|syntax error|refactor|"
    r"algorithm|leetcode|dsa|api|endpoint|regex|sql|python|javascript|typescript|kotlin|golang|c\+\+|php|"
    r"react|next\.?js|node\.?js|django|flask|fastapi|flutter|html|css|tailwind|bash|"
    r"github|docker|npm|pip install|unit tests?|pytest|jest)\b", re.IGNORECASE)

CODE_PROMPT = (
    "This is a coding question. Answer like a senior engineer pairing with the user. Working code matters more than "
    "the short-reply style above: never shorten, skip or summarise code to keep a reply short.\n"
    "- Start with one line on what the code does or what was wrong, then the code, then a short note.\n"
    "- For a bug or error, read the error and the code first, name the root cause in one sentence, then give the "
    "fix. Change what is broken; don't rewrite working code or switch libraries unless that is the real fix. If the "
    "error or the code needed to find it is missing, give the likeliest cause and fix, then ask for the exact error "
    "or file in one line.\n"
    "- For a follow-up (\"still not working\", \"add a login\", \"now in Java\"), work from the latest version of "
    "the code in this chat and keep everything that already works.\n"
    "- Before writing new code, settle the approach in a sentence or two (data structures, edge cases, and time "
    "complexity when it matters), then write it.\n"
    "- Give complete, runnable code: every import, no \"...\" or placeholder comments, nothing left for the user "
    "to fill in. For a small change to a long file, show the changed part with a few lines around it and say where "
    "it goes. Never stop mid-file or mid-function; if the whole answer would be very long, give the complete core "
    "first and offer the rest.\n"
    "- Put code in fenced blocks tagged with its real language (```python, ```javascript, ```sql, ```bash), never "
    "a bare ```. With several files, add the file name after the language (```python app.py) and give each file "
    "in full. Shell commands go in their own ```bash block without a $ prompt. Never put markdown such as ** "
    "inside code.\n"
    "- Use the language, framework and version the user uses; if they didn't say, use the one their earlier code "
    "uses, otherwise Python (JavaScript for anything in a browser). Only call functions, options and packages that "
    "really exist, prefer the standard library and well-known packages, use current, non-deprecated APIs, and give "
    "the exact install command for anything extra. If an API differs between versions, say which you wrote for.\n"
    "- Write code a reviewer would approve: clear names, small functions, no dead code or unused imports, comments "
    "only where the reason isn't obvious, and errors handled where they can happen instead of swallowed.\n"
    "- Handle the edge cases (empty input, missing values, bad user input, network failures) and keep it safe: "
    "no secrets in code, parameterised SQL, validated input.\n"
    "- Before you send it, review the code once: trace it on a normal input and an edge case, and look for "
    "off-by-one errors, wrong types, None or undefined values, missing awaits, unclosed files or connections, and "
    "names used before they are defined. Fix what you find without mentioning the check.\n"
    "- After the code, say in one line how to run it and show one example input and its output, or a short test.\n"
    "- If you have the run_python tool and the code is Python (or its logic can be checked in Python), run it on "
    "a small test before you answer and fix anything that fails. Don't paste the test run unless it helps.\n"
    "- Explain what isn't obvious in a few short lines, in the user's language (Hinglish if they write it), with "
    "code, names and comments in English; explain line by line only if the user is learning or asks."
)

# A short follow-up in a chat about code ("still not working", "add a dark mode", "now in java") is a coding
# question too, even with no code words in it. Thanks and new topics (ideas, the news) aren't.
_THANKS = re.compile(r"^\W*(?:thanks?|thank you|thx|ty|ok(?:ay)?|cool|great|nice|perfect|awesome|got it|done|"
                     r"shukriya|dhanyavaad|dhanyavad)\W*$", re.IGNORECASE)
FOLLOW_UP_CHARS = 400


def _coding_turn(history_docs: list) -> bool:
    """True when the latest user message is a coding question, or a short follow-up in a chat about code."""
    turns = [m for m in history_docs if m["role"] in ("user", "assistant")]
    at = next((i for i in range(len(turns) - 1, -1, -1) if turns[i]["role"] == "user"), None)
    if at is None:
        return False
    text = turns[at]["content"] or ""
    if _code_ask(text):
        return True
    if len(text) > FOLLOW_UP_CHARS or _THANKS.match(text) or _ideas_ask(text) or live_search.suggests_web(text):
        return False
    before = turns[:at]
    reply = next((m["content"] or "" for m in reversed(before) if m["role"] == "assistant"), "")
    asked = next((m["content"] or "" for m in reversed(before) if m["role"] == "user"), "")
    return "```" in reply or _code_ask(asked)


# Requests for ideas (brainstorming, names, business or content ideas) get IDEAS_PROMPT.
_IDEAS_ASK = re.compile(
    r"(?<!any )\b(ideas?|brainstorm\w*|names? for|name ideas|startup|side hustle|captions?|taglines?|slogans?|"
    r"ways to (?:earn|make money|grow|promote|market)|how (?:can|could|do) i (?:grow|earn|make money|get more)|"
    r"sujhav)\b", re.IGNORECASE)

IDEAS_PROMPT = (
    "The user wants ideas. Give 5-8 ideas that are really different from each other, not variations of one. Mix "
    "safe and bold ones, and include at least one non-obvious idea most people wouldn't think of. Make each one "
    "specific to the user's situation (India, budget in \u20b9, their audience and skills when known): a bold name "
    "or one-line summary, then a line on why it works and the first concrete step. Then pick your top idea and say "
    "why in two sentences. If key facts are missing (budget, audience, skills, goal), assume sensible ones, say "
    "what you assumed in a few words, and offer to tailor the list."
)


def _code_ask(text: str) -> bool:
    return bool(_CODE_ASK.search(text or ""))


def _ideas_ask(text: str) -> bool:
    return bool(_IDEAS_ASK.search(text or "")) and not _code_ask(text)


def _to_coder(model: str, conv: Optional[dict], coding: bool, history_docs: list, special: bool) -> bool:
    """True when a free model was asked a coding question and the free coding model should answer instead."""
    if special or (conv or {}).get("appId") or model == CODER_MODEL or agent_llm.paid(model):
        return False
    if not agent_llm.configured(CODER_MODEL) or agent_llm.gateway() or not coding:
        return False
    recent = [m for m in history_docs if m["role"] == "user"][-1:]
    return not any(m.get("images") for m in recent)  # pictures need a model that can see them


# Past this many tokens of chat, Krish AI answers with Cerebras, whose free tier fits about 4x more than Groq's.
LONG_CHAT_TOKENS = 6000


def _auto_model(history_docs: list, text: Optional[str], coding: bool = False) -> str:
    """The free model that answers a Krish AI question. Pictures go to Gemini (it can see them), long chats to
    Cerebras (most room), hard questions to gpt-oss-120b (it reasons), everything else to Gemini (quick). Coding
    questions then move to Krish Coder in _to_coder. Gemini hands over to Groq, then Cerebras, when it runs out."""
    recent = [m for m in history_docs if m["role"] == "user"][-1:]
    if any(m.get("images") for m in recent):
        wanted = ["gemini-3.5-flash-lite"]
    elif agent_llm.estimate_tokens([m.get("content") or "" for m in history_docs]) > LONG_CHAT_TOKENS:
        wanted = ["cerebras/gpt-oss-120b", "openai/gpt-oss-120b"]
    elif coding or _hard_ask(text or "") or _code_ask(text or ""):
        wanted = ["cerebras/gpt-oss-120b", "openai/gpt-oss-120b"]
    else:
        wanted = ["gemini-3.5-flash-lite"]
    return next((m for m in wanted if agent_llm.configured(m)), agent_llm.concrete(AUTO_MODEL))


VOICE_LANG_NAMES = {"hi": "Hindi", "en": "English", "bn": "Bengali", "mr": "Marathi", "gu": "Gujarati",
                    "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "ur": "Urdu",
                    "es": "Spanish", "fr": "French", "de": "German", "ar": "Arabic", "pa": "Punjabi"}


def voice_prompt(lang: Optional[str], fallback: Optional[str] = None) -> str:
    """`lang` is the language the user just spoke (or picked); `fallback` is their Settings language."""
    language = VOICE_LANG_NAMES.get(lang or "")
    usual = VOICE_LANG_NAMES.get(fallback or "")
    reply_in = (f"The user just spoke {language}: reply in {language}, written in its own script, even if their "
                "Settings language or earlier messages are different. If they mix Hindi and English, mix the same way."
                if language else
                "Reply in the language the user just spoke, in its own script (Hindi in Devanagari); if they mix "
                "Hindi and English, mix the same way." + (f" If you can't tell, use {usual}." if usual else ""))
    return (
        "Voice mode is on: the user is talking to you out loud and your reply will be read aloud by a voice. "
        "Answer like a warm, natural person on a phone call: usually one to three short sentences, the most useful "
        "part first. Offer to say more instead of giving long lists. Never use markdown, bullet points, tables, "
        "emoji, links, URLs or code; write numbers and symbols the way they are spoken. The words come from "
        "speech-to-text and can be misheard: answer what the user most likely said. " + reply_in
    )


STUDY_PROMPT = (
    "Study mode is on: act as a patient, encouraging tutor for a student in India. Don't just hand over the final "
    "answer. First ask what level they are at if it isn't clear (class, exam such as CBSE, JEE, NEET, UPSC, or "
    "college). Explain one idea at a time in simple words with a small everyday example, then ask one short "
    "question to check they understood before moving on. For homework, give hints and let them try each step; "
    "show the full solution only after they try or ask for it. When a topic is done, offer a quick quiz or "
    "flashcards (use create_flashcards) for revision."
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


# Words that mean a chat turn may need tools. Without any, Groq's free models answer without the tool list,
# which is about 4,000 tokens: the reply starts sooner and the next message isn't held up by the
# per-minute token limit. Current facts (news, rates, prices) are still looked up by live_search.
_NEEDS_TOOLS = re.compile(
    _TOOL_ASK.pattern + r"|\b(file|files|pdf|excel|xlsx|csv|word|docx|ppt|pptx|powerpoint|presentation|slides?|deck|"
    r"spreadsheet|sheet|zip|image|images|picture|pic|photo|logo|poster|video|animate|edit|crop|resize|research|"
    r"report|code|run|script|app|website|site|game|page|browser|open|visit|fetch|url|link|flashcards?|quiz|"
    r"remind|schedule|email|send|save|translate|time|date|price|rate|weather|news|today|current|latest)\b|https?://|www\.",
    re.IGNORECASE)


def _quick_chat(history_docs: list) -> bool:
    """True when the latest message is plain conversation that needs no tools (see _NEEDS_TOOLS)."""
    last_user = [m for m in history_docs if m["role"] == "user"][-2:]
    if not last_user or any(m.get("images") for m in last_user):
        return False
    if any(m.get("steps") for m in history_docs[-4:] if m["role"] == "assistant"):
        return False  # a follow-up to a turn that used tools ("now make it blue") keeps them
    return not any(_NEEDS_TOOLS.search(m["content"] or "") for m in last_user)


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
                                                          else "attached, but no readable text in it (an empty, encrypted, audio or program file). Tell the user what you can and cannot do with it")
            if f.get("appPath"):
                note += (f"; the whole file is in the app as {f['appPath']}" + (": read it with search_files and "
                         "read_file before you build anything that reads such files" if f["appPath"].startswith(
                             apps.SAMPLE_DIR) else ": show it with <img>"))
            status.append(f"- {f['original_filename']}: {note}")
        parts.append("Files the user attached to this chat:\n" + "\n".join(status))
    if chosen:
        parts.append(
            "Content of the user's files (answer from it, and name the file in [brackets] when you use it; "
            "if the answer isn't there, say so):\n\n"
            + "\n\n".join(f"[{c['fileName']}] {c['text']}" for c in chosen)
        )
    return "\n\n".join(parts), sources


_FILE_TOOLS = ("write_file", "append_file", "edit_file", "delete_file")
REPAIR_STEPS = 5
SMOKE_TIMEOUT = 60  # seconds for the browser test of an app
REPAIR_ROUNDS = 2  # rounds of automatic fixes after a builder turn leaves the app broken


async def _app_problems(app_id: str):
    """Static problems (apps.check_app), then, when there are none, what a real browser hits when it opens the
    app and presses its buttons (apps.smoke_test). Yields test-step events; the last event is {"type": "problems"}."""
    files = await apps.snapshot(app_id)
    problems = await apps.check_app(files)
    # Apps on Krish's backend (RADHA.db, .ai, .notify...) aren't pressed: a click could email the owner or change
    # real data, and the browser test has no signed-in user. Their static checks still run.
    if problems or not agent_browser.available() or any("RADHA." in c for c in files.values()):
        yield {"type": "problems", "problems": problems}
        return
    step_id = f"smoke-{uuid.uuid4().hex[:8]}"
    yield {"type": "tool_start", "id": step_id, "name": "check_preview", "label": "Testing the app",
           "args": {"path": "index.html"}}
    try:
        problems = await asyncio.wait_for(apps.smoke_test(files, app_id=app_id), SMOKE_TIMEOUT)
    except Exception as exc:  # no browser on this server: the static checks stand
        logger.warning("app smoke test failed: %s", str(exc)[:300])
        yield {"type": "tool_end", "id": step_id, "name": "check_preview", "ok": True, "summary": "Skipped (no browser)", "output": "", "media": []}
        yield {"type": "problems", "problems": []}
        return
    n = len(problems)
    yield {"type": "tool_end", "id": step_id, "name": "check_preview", "ok": not problems, "output": "\n".join(problems), "media": [],
           "summary": f"{n} error{'s' if n != 1 else ''} found" if problems else "Opened it and pressed every button: no errors"}
    yield {"type": "problems", "problems": problems}


async def _agent_events(stream_fn, ctx: ToolContext, model: str, llm_messages: list, use_tools: bool, max_steps: int):
    """The agent's events. In the App Builder, when the turn changed files, the app is checked (missing files and
    elements, scripts that don't parse) and opened in a real browser that presses its buttons. Anything that
    breaks gets up to two rounds of fixes, and anything still wrong is told to the user instead of ending silently."""
    said, changed = [], False
    async for ev in run_agent(stream_fn, tool_registry, ctx, model, llm_messages, use_tools=use_tools,
                              max_steps=max_steps):
        if ev["type"] == "text":
            said.append(ev["text"])
        elif ev["type"] == "tool_end" and ev["name"] in _FILE_TOOLS and ev["ok"]:
            changed = True
        yield ev
    if not (ctx.app_id and use_tools and changed):
        return
    problems = []
    rounds = ctx.repair_rounds if ctx.repair_rounds is not None else REPAIR_ROUNDS
    for repair_round in range(rounds + 1):
        async for ev in _app_problems(ctx.app_id):
            if ev["type"] == "problems":
                problems = ev["problems"]
            else:
                yield ev
        if not problems or repair_round == rounds:
            break
        if repair_round == 0:
            yield {"type": "text", "text": "\n\nChecking the app… I found a problem and I'm fixing it.\n\n"}
        llm_messages.append({"role": "assistant", "content": "".join(said).strip() or "I wrote the files."})
        llm_messages.append({"role": "user", "content": (
            "Automatic test of the app found these problems:\n- " + "\n- ".join(problems)
            + "\nFix every one now (read the files, then edit_file or write_file the missing parts so the whole app "
            "works), then say in one short line what you fixed.")})
        said = []
        async for ev in run_agent(stream_fn, tool_registry, ctx, model, llm_messages, use_tools=True,
                                  max_steps=REPAIR_STEPS):
            if ev["type"] == "text":
                said.append(ev["text"])
            yield ev
    if problems:
        yield {"type": "text", "text": "\n\nHeads up, the app still has a problem: " + problems[0].split(" The file looks cut off")[0]
               + " Tap “Fix errors with AI” under the preview, or reply “fix it”."}


def _builder_summary(steps: list) -> str:
    """A plain account of an App Builder turn the model ended without a reply."""
    changed = sorted({(s.get("args") or {}).get("path", "") for s in steps
                      if s.get("name") in _FILE_TOOLS and s.get("status") == "done"} - {""})
    failed = [s for s in steps if s.get("status") == "error"]
    if changed:
        text = f"I changed {', '.join(changed)}. Check the preview, and tell me what else to adjust."
        if failed:
            text += f" ({len(failed)} of my edits didn't apply, so some of what you asked may be missing.)"
        return text
    if failed:
        return ("I couldn't make that change: my edits didn't match the file, so nothing was changed. "
                "Try asking for one specific change, like \"make the Search button green\".")
    return "I looked at the files but didn't change anything. Tell me exactly what you'd like changed."


async def run_turn(conv_id: str, model: str, agent: bool = False, extra_system: Optional[str] = None,
                   max_steps: Optional[int] = None, think: bool = False, study: bool = False,
                   voice: bool = False, voice_lang: Optional[str] = None, web: bool = False,
                   focus: str = "web", pro: bool = False):
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
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history_docs if m["content"]]

    chosen = model  # the model the user picked, kept for the chat even when the coding model answers
    last_user = next((m["content"] for m in reversed(history_docs) if m["role"] == "user"), None)
    coding = _coding_turn(history_docs)
    if model == AUTO_MODEL:
        model = _auto_model(history_docs, last_user, coding)
    if _to_coder(model, conv, coding, history_docs, counselling or voice or bool(extra_system)):
        model = CODER_MODEL
    base = counsellor.PROMPT if counselling else BUILDER_PROMPT if (conv or {}).get("appId") else SYSTEM_PROMPT
    system_parts = [base, f"Today is {datetime.now(timezone.utc).strftime('%A, %d %B %Y')} (UTC)."]
    sources = []
    quiet_cards = []  # automatic search results, shown only if the answer cites them
    pro_step = None

    # Memory (user-global + project) — real, user-controlled facts.
    settings_lang = None
    if user_id:
        remembered = await memory.prompt_section(db, user_id, project_id)
        if remembered:
            system_parts.append(remembered)
        owner = await db.users.find_one({"id": user_id}, {"language": 1})
        settings_lang = (owner or {}).get("language")
        lang_line = languages.prompt_line(settings_lang)
        if lang_line and not voice:  # voice replies follow the language spoken (see voice_prompt)
            system_parts.append(lang_line)

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
    if agent and not app_id and not extra_system and not think and not study and agent_llm.lean(model) \
            and _quick_chat(history_docs) and not await db.files.count_documents(
                {"conversationId": conv_id, "is_deleted": False}):
        agent = False
    if app_id:
        agent = True  # the app builder always works with its tools
        system_parts.append(await apps.app_prompt(db, app_id))
    use_runtime = agent or any(m.get("images") for m in history_docs)
    # Web search runs only when the user turns it on (or asks for a search in words); automations and the app
    # builder keep it. Otherwise a question that needs fresh facts gets a "Search the web" suggestion.
    asked = live_search.asks_for_search(last_user or "")
    searching = web or pro or focus != "web" or bool(extra_system) or bool(app_id) or asked
    web = web or asked
    web_hint = not searching and not counselling and not voice and live_search.suggests_web(last_user or "")
    if not searching and not counselling:
        system_parts.append(WEB_OFF_NOTE)
    # Look up live info (news, rates, prices) up front, so the answer never depends on the model choosing to search.
    if not app_id and not counselling:
        user_texts = [m["content"] for m in history_docs if m["role"] == "user"]
        if pro:
            pro_step = {"id": "pro-search", "name": "pro_search", "label": "Pro search",
                        "args": {"query": (last_user or "")[:200]}, "status": "running"}
            yield f"event: tool\ndata: {_sse_json(pro_step)}\n\n"
        found = await live_search.gather(user_texts, search=searching, force=web, focus=focus, pro=pro, model=model)
        if found["context"]:
            system_parts.append(found["context"])
            web_hint = web_hint and searching  # a live rates, weather or stock card already answered it
        if (web or pro) and not any(c.get("type") in ("web", "video") for c in found["sources"]):
            system_parts.append(NO_RESULTS_NOTE if agent else NO_RESULTS_NOTE_PLAIN)
        sources = sources + found["sources"]
        if not (web or pro or focus != "web"):
            # Automations search on their own; those source cards only show when the answer cites them.
            quiet_cards = [c for c in found["sources"] if c.get("type") in ("web", "video")]
        if pro:
            pages = sum(1 for s in found["sources"] if s.get("type") in ("web", "video", "weather", "stock"))
            pro_step.update(status="done" if pages else "error", args={"queries": found["queries"]},
                            summary=(f"Searched {len(found['queries'])} way{'s' if len(found['queries']) != 1 else ''}, "
                                     f"found {pages} source{'s' if pages != 1 else ''}") if pages
                            else "Search engines didn't answer, so Krish answered from what it knows",
                            output="\n".join(f"Searched: {q}" for q in found["queries"]), media=[])
            yield f"event: tool_result\ndata: {_sse_json(pro_step)}\n\n"
    # Perplexity-style follow-up questions under ordinary chat answers.
    ask_related = not app_id and not counselling and not voice and not extra_system
    if ask_related:
        system_parts.append(related.PROMPT)
    # Free models (Groq) get only the app tools inside an app, to stay within their token budget.
    focused = bool(app_id) and agent_llm.lean(model)
    work = limits.work_of(await limits.plan_of(db, user_id)) if user_id else limits.work_of("basic")
    if app_id and not max_steps and (not agent_llm.lean(model) or agent_llm.token_budget(model) > 16000):
        max_steps = max(BUILDER_STEPS, work["builderSteps"]) if not agent_llm.lean(model) else BUILDER_STEPS
    if agent and not focused:
        system_parts.append(AGENT_PROMPT)
    if study and not app_id and not counselling:
        system_parts.append(STUDY_PROMPT)
    # How to answer this kind of question well: code, or ideas (not in the app builder, voice or counselling).
    if not (app_id or counselling or voice or extra_system):
        if coding:
            system_parts.append(CODE_PROMPT)
        elif _ideas_ask(last_user or ""):
            system_parts.append(IDEAS_PROMPT)
    if think and not counselling:
        system_parts.append(THINK_PROMPT)
    premium_answers = work["model"] != "free" and not (app_id or counselling or voice or extra_system)
    if premium_answers:
        system_parts.append(PREMIUM_ANSWER_PROMPT)
    # Without Think, a hard question still gets more reasoning from the free models (never in voice, the app
    # builder or a counselling chat, where a quick reply matters more).
    reasoning = think or (agent_llm.DEEPER if not (voice or app_id or counselling or extra_system)
                          and (_hard_ask(last_user or "") or coding) else False)
    if app_id and not think:
        # A build is a hard task: the free builder (gpt-oss) otherwise plans a whole app at its lightest setting.
        reasoning = agent_llm.DEEPER
    if extra_system:
        system_parts.append(extra_system)
    if voice and not app_id:
        system_parts.append(voice_prompt(voice_lang, settings_lang))
    if counselling and not voice:
        system_parts.append(counsellor.BRIEF)
    system_prompt = "\n\n".join(system_parts)

    shown = [s for s in sources if s not in quiet_cards]
    if shown:
        yield f"event: sources\ndata: {_sse_json(shown)}\n\n"
    shown_sources = len(sources)

    full, steps, produced = [], [pro_step] if pro_step else [], []
    stopped = False  # the user pressed Stop (the browser closed the stream) before the reply finished
    try:
        if use_runtime:
            if not agent_llm.configured(model):
                raise RuntimeError(agent_llm.missing_key_message(model))
            llm_messages = await _llm_messages(history_docs, system_prompt, user_id,
                                               see_images=agent_llm.supports_images(model))
            # Searched already (Search button, Pro or a fact question): one more web search at most, so the
            # answer doesn't wait on a chain of searches. The model's own results join the source cards.
            searched = any(s.get("type") in ("web", "video") for s in sources)
            ctx = ToolContext(db=db, user_id=user_id, conversation_id=conv_id, app_id=app_id, focused=focused,
                              model=model, sources=None if app_id else sources,
                              searches_left=None if app_id else (1 if searched else work["searches"]), web=searching,
                              search_results=work["results"], research_depth=work["research"],
                              repair_rounds=work["repairRounds"])
            stream_fn = functools.partial(agent_llm.stream_completion, think=reasoning)
            async for ev in _agent_events(stream_fn, ctx, model, llm_messages, agent, max_steps or MAX_AGENT_STEPS):
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
                    if ctx.limit_hit:
                        yield f"event: plan_limit\ndata: {_sse_json(ctx.limit_hit)}\n\n"
                        ctx.limit_hit = None
                    if len(sources) != shown_sources:
                        shown_sources = len(sources)
                        quiet_cards = []  # Krish searched on its own: show everything it read
                        yield f"event: sources\ndata: {_sse_json(sources)}\n\n"
        else:
            if not uses_emergent(AI_API_KEY) and not agent_llm.configured(model):
                raise RuntimeError(agent_llm.missing_key_message(model))
            ai_request = AIRequest(messages=messages, model=model, system=system_prompt, session_id=conv_id,
                                   think=reasoning, long_answer=coding or premium_answers)
            async for delta in model_router.stream(ai_request):
                full.append(delta)
                yield f"data: {_sse_json(delta)}\n\n"
    except (asyncio.CancelledError, GeneratorExit):
        stopped = True  # also cancels the model call and any running tool
        raise
    except Exception as exc:  # surface provider errors to the client
        logger.exception("AI stream failed")
        if not related.split("".join(full))[0].strip():
            # Keep a visible reason (with Regenerate) instead of leaving the question unanswered.
            full.append(STREAM_FAILED_NOTE)
            yield f"data: {_sse_json(STREAM_FAILED_NOTE)}\n\n"
        yield f"event: error\ndata: {_sse_json(str(exc))}\n\n"
    else:
        if app_id and steps and not "".join(full).strip():
            # Free models sometimes stop after their tools without a word: always say what happened.
            summary = _builder_summary(steps)
            full.append(summary)
            yield f"data: {_sse_json(summary)}\n\n"
        elif steps and not related.split("".join(full))[0].strip():
            note = "Sorry, I searched but couldn't finish writing the answer. Tap Regenerate to try again."
            full.insert(0, note + "\n\n")
            yield f"data: {_sse_json(note)}\n\n"
        # Crisis replies always carry the helplines, even if the model left them out.
        note = counsellor.helpline_note("".join(full)) if counselling and counsellor.is_crisis(last_user or "") else ""
        if note:
            note = "\n\n" + note
            full.append(note)
            yield f"data: {_sse_json(note)}\n\n"
        if not app_id and not counselling:
            async for event in _check_code_reply(model, full, steps):
                yield event
    finally:
        content = "".join(full).strip()
        follow_ups = []
        if ask_related:
            content, follow_ups = related.split(content)
            if follow_ups and not stopped:
                yield f"event: related\ndata: {_sse_json(follow_ups)}\n\n"
        if web_hint and not stopped:
            yield "event: web_hint\ndata: true\n\n"
        if quiet_cards:
            if _CITATION.search(content):
                if not stopped:
                    yield f"event: sources\ndata: {_sse_json(sources)}\n\n"
            else:
                sources = [s for s in sources if s not in quiet_cards]
        if content or steps:
            if stopped:
                for step in steps:
                    if step["status"] == "running":
                        step.update(status="stopped", summary="Stopped")
            assistant_msg = {
                "id": str(uuid.uuid4()),
                "conversationId": conv_id,
                "role": "assistant",
                "content": content,
                "model": model,
                "sources": sources or None,
                "related": follow_ups or None,
                "webHint": web_hint or None,
                "steps": steps or None,
                "media": produced or None,
                "stopped": stopped or None,
                "createdAt": now_iso(),
            }
            # Shielded, so the part written before Stop is kept even though the turn is being cancelled.
            with anyio.CancelScope(shield=True):
                await db.messages.insert_one(assistant_msg)
                await db.conversations.update_one(
                    {"id": conv_id}, {"$set": {"updatedAt": now_iso(), "model": chosen}}
                )
            if not stopped:
                yield f"event: done\ndata: {_sse_json({'messageId': assistant_msg['id']})}\n\n"


async def _check_code_reply(model: str, full: list, steps: list):
    """Check the app or site a chat reply just wrote and fix what would break it (see code_check.py).

    The fixed files replace the broken ones in `full`, so the saved reply, which the chat reloads when the
    stream ends, previews the working version.
    """
    text = "".join(full)
    files, cut = code_check.web_files(text)
    if not files:
        return
    try:
        found = await code_check.problems(files, cut)
    except Exception as exc:  # a check that can't run never costs the user their answer
        logger.warning("code check failed: %s", str(exc)[:300])
        return
    if not found:
        return
    step = {"id": str(uuid.uuid4()), "name": "check_preview", "label": "Checking and fixing your app",
            "args": {"path": next(p for p in files if p.endswith((".html", ".htm")))}, "status": "running"}
    steps.append(step)
    yield f"event: tool\ndata: {_sse_json(step)}\n\n"
    result = None
    try:
        async for ev in code_check.repair(code_edit.editing_model(model), files, found):
            if ev["type"] == "heartbeat":
                yield ": keepalive\n\n"
            elif ev["type"] == "result":
                result = ev
    except Exception as exc:
        logger.warning("code repair failed: %s", str(exc)[:300])
    fixed = (result or {}).get("fixed") or []
    if fixed:
        content = code_edit.replace_blocks(code_edit.close_fence(text)[0], result["files"])
        n = len(fixed)
        note = (f"\n\nI tested the preview and fixed {n} problem{'s' if n != 1 else ''} before handing it over "
                f"({'; '.join(f.split(' (')[0].rstrip('.') for f in fixed[:3])}).")
        tail = related._LINE.search(content)  # the note goes before the Related questions line, which is cut off
        full[:] = [content[:tail.start()].rstrip() + note + "\n\n" + content[tail.start():] if tail else content + note]
        yield f"data: {_sse_json(note)}\n\n"
        step.update(status="done", summary=f"Fixed {n} problem{'s' if n != 1 else ''}", output="\n".join(fixed), media=[])
    else:
        step.update(status="done", summary="Checked; some problems are still there", output="\n".join(found), media=[])
    yield f"event: tool_result\ndata: {_sse_json(step)}\n\n"


class _TurnResponse(StreamingResponse):
    """A reply stream that is always closed, so a stopped turn saves what it wrote.

    When the browser stops reading, Starlette cancels the response; if that lands while the reply is
    waiting to be sent, the generator is left open and its cleanup would only run whenever it is
    garbage-collected. Closing it here runs it right away.
    """

    async def stream_response(self, send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()



def _stream_response(conv_id: str, model: str, agent: bool = False, think: bool = False, study: bool = False,
                     voice: bool = False, voice_lang: Optional[str] = None, web: bool = False, focus: str = "web",
                     pro: bool = False) -> StreamingResponse:
    return _TurnResponse(
        run_turn(conv_id, model, agent, think=think, study=study, voice=voice, voice_lang=voice_lang, web=web,
                 focus=focus, pro=pro),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@api.post("/conversations/{conv_id}/stream")
async def stream_message(conv_id: str, body: MessageIn, user_id: str = Depends(current_user_id)):
    abuse.require("chat", user_id)
    conv = await _owned_conversation(conv_id, user_id)
    model = await _pick_model(user_id, conv, body.model or AI_MODEL, body.think, body.content)

    image_ids = []
    for mid in body.images:
        doc = await db.media.find_one({"id": mid, "userId": user_id}, {"data": 0})
        if not doc or not (doc.get("contentType") or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Unknown image attachment")
        image_ids.append(mid)
    if conv.get("appId"):  # chat is unlimited; an App Builder message uses credits by how much it asks for
        await limits.require(db, user_id, "build", size=len(body.content))

    content, ready_reply = body.content, None
    if conv.get("appId"):
        # Code pasted into the App Builder is saved verbatim, so the AI edits it instead of rebuilding it.
        try:
            pasted = await apps.absorb_pasted_code(conv["appId"], body.content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if pasted:
            content, ready_reply = pasted
    elif conv.get("mode") != counsellor.MODE and not body.images:
        # Code pasted or attached in the chat is shown exactly as given: no AI rewrite when the user only
        # wants to see it. With instructions ("make the button red"), the AI works on it as usual.
        ready_reply = show_as_is(body.content)

    user_msg = {
        "id": str(uuid.uuid4()),
        "conversationId": conv_id,
        "role": "user",
        "content": content,
        "images": image_ids or None,
        "model": None,
        "createdAt": now_iso(),
    }
    await db.messages.insert_one(user_msg)
    used = ["build" if conv.get("appId") else "counsellor" if conv.get("mode") == counsellor.MODE else "chat"]
    used += [f for f, on in (("web", body.web), ("voice", body.voice), ("think", body.think)) if on]
    await monitor.count(db, user_id, *used)

    # Auto-title on first user message.
    existing_count = await db.messages.count_documents({"conversationId": conv_id})
    if existing_count == 1 and (conv["title"] in ("New conversation", "", None)):
        auto_title = body.content.strip().split("\n")[0][:60]
        if auto_title.startswith(("<", "```")):  # pasted code: the page's own title, else a plain name
            found = re.search(r"<title>([^<]{1,60})</title>", body.content, re.IGNORECASE)
            auto_title = found.group(1).strip() if found and found.group(1).strip() else "My code"
        await db.conversations.update_one({"id": conv_id}, {"$set": {"title": auto_title}})

    # Learn lasting facts about the user in the background (see memory.py).
    # Counselling chats are private: nothing said there is saved to memory.
    if not conv.get("appId") and not conv.get("automationId") and conv.get("mode") != counsellor.MODE:
        _background(memory.learn(db, user_id, body.content, model))

    if ready_reply:
        return StreamingResponse(_canned_turn(conv_id, ready_reply, user_code=not conv.get("appId")),
                                 media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    if not conv.get("appId") and conv.get("mode") != counsellor.MODE and not body.images:
        edit = await _code_edit_ask(conv_id)
        if edit:
            return _code_edit_response(conv_id, model, *edit)
    return _stream_response(conv_id, model, agent=body.agent, think=body.think, study=body.study,
                            voice=body.voice, voice_lang=body.voiceLang, web=body.web,
                            focus=body.focus, pro=body.pro)


THINK_MODELS = ("claude-sonnet-5-5", "gpt-5.4")  # Think on Pro and Max: the first one set up answers


async def _chat_chars(conv: dict) -> int:
    """How much text a premium model is sent for this chat (the recent history), for the usage meter."""
    if not conv.get("id"):
        return 0
    docs = await db.messages.find({"conversationId": conv["id"]}, {"content": 1}).sort("createdAt", -1).to_list(40)
    return sum(len(d.get("content") or "") for d in docs)


async def _pick_model(user_id: str, conv: dict, requested: str, think: bool = False, text: str = "") -> str:
    """The model that answers: the App Builder's stronger model inside an app, and no paid
    model (Claude, GPT) for free-plan users unless the owner sets PAID_MODELS=all.

    Paid plans move a free-model question to the strongest premium model that is set up: Think on Pro and
    Max, hard questions and app builds on Pro, every answer on Max (limits.work_of). A premium message uses
    credits from the plan's meter by how much is sent (the chat so far and the new message); once the meter
    is empty the chat answers with Krish Basic."""
    model = requested
    plan = await limits.plan_of(db, user_id)
    pro = limits.PLANS[plan]["premium"]
    upgrade = limits.work_of(plan)["model"]
    builder_override = conv.get("appId") and os.environ.get("BUILDER_MODEL", "").strip()
    if pro and not agent_llm.paid(model) and not builder_override and (
            upgrade == "all" or (think and not conv.get("appId"))
            or (upgrade == "hard" and (conv.get("appId") or _hard_ask(text) or _code_ask(text)))):
        model = next((m for m in THINK_MODELS if agent_llm.configured(m)), model)
    if pro and agent_llm.paid(model) and not await limits.use_premium(db, user_id,
                                                                       len(text) + await _chat_chars(conv)):
        return AI_MODEL
    if model == AUTO_MODEL and conv.get("appId"):
        model = agent_llm.concrete(model)
    if conv.get("appId"):
        override = os.environ.get("BUILDER_MODEL", "").strip()
        if override and agent_llm.configured(override):
            return override
        # Gemini's free daily allowance is kept for chat; a build takes many steps.
        if agent_llm.lean(model) or agent_llm.provider_for(model) == "gemini":
            builders = (FREE_BUILDER,) if agent_llm.gateway() else (CODER_MODEL, FREE_BUILDER)
            model = next((m for m in builders if agent_llm.configured(m)), model)
    if agent_llm.paid(model) and not agent_llm.paid(AI_MODEL) and os.environ.get("PAID_MODELS") != "all" \
            and not pro:
        model = AI_MODEL
    return model


_SHOW_WORDS = set("""show preview run display open render view see test check this it my our the a an of in
code html css js page file files website site app please pls plz just simply only same exactly as is it's its here
me give output result how looks look like kindly can you do what i want to with without changes change any no
and snd n
""".split())
_LANGS = {"htm": "html", "mjs": "js", "cjs": "js", "jsx": "jsx", "tsx": "tsx", "md": "markdown"}


def show_as_is(content: str) -> Optional[str]:
    """A ready reply that shows the user's own code unchanged, or None when the AI should answer.

    Used when the message is pasted code (a whole HTML page, an HTML snippet, or fenced blocks that name
    their files) with no instructions beyond "show this". The reply repeats the files verbatim as named
    code blocks, under the names they came with, so the chat's side panel previews them exactly as given.
    """
    files = code_edit.code_files(content, raw_html=True)
    rest = code_edit.without_code(content)
    if not files:
        files, rest = apps.split_pasted_code(content)
    text = (content or "").strip()
    if not files and text.startswith("<") and re.search(r"</[A-Za-z][\w-]*>\s*$", text):
        files, rest = {"index.html": text}, ""
    if not files or any(w not in _SHOW_WORDS for w in re.findall(r"[a-z']+", (rest or "").lower())):
        return None
    blocks = []
    for path, code in files.items():
        ext = path.rsplit(".", 1)[-1].lower()
        fence = "````" if "```" in code else "```"
        blocks.append(f"{fence}{_LANGS.get(ext, ext)} {path}\n{code.rstrip()}\n{fence}")
    names = ", ".join(files)
    return (f"Here is your {names}, shown exactly as you gave it, with nothing changed. "
            "Tell me if you want any changes.\n\n" + "\n\n".join(blocks))


async def _canned_turn(conv_id: str, text: str, user_code: bool = False):
    """A fixed assistant reply, streamed and saved like a model's (no AI call needed).

    `user_code` marks a reply that carries the user's own code, so a later "make it blue" edits that code.
    """
    msg = {"id": str(uuid.uuid4()), "conversationId": conv_id, "role": "assistant", "content": text,
           "model": None, "createdAt": now_iso(), **({"userCode": True} if user_code else {})}
    yield f"data: {_sse_json(text)}\n\n"
    await db.messages.insert_one(msg)
    await db.conversations.update_one({"id": conv_id}, {"$set": {"updatedAt": now_iso()}})
    yield f"event: done\ndata: {_sse_json({'messageId': msg['id']})}\n\n"


async def _code_edit_ask(conv_id: str):
    """(files, the ask) when the latest message asks to change code the user gave in this chat, else None."""
    recent = await db.messages.find({"conversationId": conv_id}).sort("createdAt", -1).to_list(code_edit.RECENT_MESSAGES)
    return code_edit.should_edit(recent[::-1])


def _code_edit_response(conv_id: str, model: str, files: dict, ask: str):
    return _TurnResponse(_code_edit_turn(conv_id, model, files, ask), media_type="text/event-stream",
                         headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


async def _code_edit_turn(conv_id: str, model: str, files: dict, ask: str):
    """Change the user's own code in place with small edits (see code_edit.py) and reply with the whole file."""
    model = code_edit.editing_model(model)
    steps, text, failed = [], "", False
    try:
        async for ev in code_edit.run(model, files, ask):
            if ev["type"] == "heartbeat":
                yield ": keepalive\n\n"
            elif ev["type"] == "part":
                where = f" (part {ev['index']} of {ev['total']})" if ev["total"] > 1 else ""
                steps.append({"id": str(uuid.uuid4()), "name": "edit_file", "label": "Editing your file",
                              "args": {"path": ev["path"] + where}, "status": "running"})
                yield f"event: tool\ndata: {_sse_json(steps[-1])}\n\n"
            elif ev["type"] == "part_done":
                n = ev["applied"]
                steps[-1].update(status="done", summary=f"{n} change{'s' if n != 1 else ''}" if n else "Nothing to change here",
                                 output="", media=[])
                yield f"event: tool_result\ndata: {_sse_json(steps[-1])}\n\n"
            elif ev["type"] == "result":
                text = code_edit.reply_text(files, ev["files"], ev["applied"], ev["missed"], ev["summaries"])
    except (asyncio.CancelledError, GeneratorExit):
        raise
    except Exception as exc:
        logger.warning("code edit failed: %s", str(exc)[:300])
        failed = True
        text = ("Sorry, the AI model stopped before it could finish editing your file (it may be busy or out of "
                "free requests for now), so I didn't change it. Tap Regenerate, or pick another model from the menu at the top.")
    for step in steps:
        if step["status"] == "running":
            step.update(status="error", summary="Stopped", output="", media=[])
    yield f"data: {_sse_json(text)}\n\n"
    msg = {"id": str(uuid.uuid4()), "conversationId": conv_id, "role": "assistant", "content": text, "model": model,
           "steps": steps or None, "userCode": not failed or None, "createdAt": now_iso()}
    with anyio.CancelScope(shield=True):
        await db.messages.insert_one(msg)
        await db.conversations.update_one({"id": conv_id}, {"$set": {"updatedAt": now_iso(), "model": model}})
    yield f"event: done\ndata: {_sse_json({'messageId': msg['id']})}\n\n"


_BACKGROUND_TASKS = set()


def _background(coro):
    """Run a coroutine after the response without it being garbage-collected mid-way."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


@api.post("/conversations/{conv_id}/regenerate")
async def regenerate_message(conv_id: str, body: RegenerateIn, user_id: str = Depends(current_user_id)):
    abuse.require("chat", user_id)
    conv = await _owned_conversation(conv_id, user_id)
    last = await db.messages.find_one({"conversationId": conv_id, "role": "user"}, sort=[("createdAt", -1)])
    asked = (last or {}).get("content") or ""
    model = await _pick_model(user_id, conv, body.model or conv.get("model") or AI_MODEL, body.think, asked)
    if conv.get("appId"):  # chat is unlimited; an App Builder message uses credits by how much it asks for
        await limits.require(db, user_id, "build", size=len(asked))

    history_docs = await db.messages.find({"conversationId": conv_id}).sort("createdAt", 1).to_list(2000)
    if not history_docs:
        raise HTTPException(status_code=400, detail="Nothing to regenerate")

    # Drop the trailing assistant turn so we re-answer the last user message.
    if history_docs[-1]["role"] == "assistant":
        await db.messages.delete_one({"id": history_docs[-1]["id"]})

    remaining = await db.messages.count_documents({"conversationId": conv_id})
    if remaining == 0:
        raise HTTPException(status_code=400, detail="Nothing to regenerate")
    if not conv.get("appId") and conv.get("mode") != counsellor.MODE:
        edit = await _code_edit_ask(conv_id)
        if edit:
            return _code_edit_response(conv_id, model, *edit)

    return _stream_response(conv_id, model, agent=body.agent, think=body.think, study=body.study, web=body.web,
                            focus=body.focus, pro=body.pro)


@api.post("/conversations/{conv_id}/messages/{message_id}/edit")
async def edit_message(conv_id: str, message_id: str, body: EditIn, user_id: str = Depends(current_user_id)):
    """Edit one of the user's earlier questions (like ChatGPT): everything after it is dropped and Krish answers
    the new wording."""
    abuse.require("chat", user_id)
    conv = await _owned_conversation(conv_id, user_id)
    model = await _pick_model(user_id, conv, body.model or conv.get("model") or AI_MODEL, body.think, body.content)
    if conv.get("appId"):
        await limits.require(db, user_id, "build", size=len(body.content))
    history_docs = await db.messages.find({"conversationId": conv_id}).sort("createdAt", 1).to_list(2000)
    index = next((i for i, m in enumerate(history_docs) if m["id"] == message_id), None)
    if index is None or history_docs[index]["role"] != "user":
        raise HTTPException(status_code=404, detail="That question isn't in this chat any more")
    later = [m["id"] for m in history_docs[index + 1:]]
    if later:
        await db.messages.delete_many({"id": {"$in": later}})
    await db.messages.update_one({"id": message_id}, {"$set": {"content": body.content, "editedAt": now_iso()}})
    return _stream_response(conv_id, model, agent=body.agent, think=body.think, study=body.study, web=body.web,
                            focus=body.focus, pro=body.pro)


class FeedbackIn(BaseModel):
    rating: Optional[Literal["up", "down"]] = None  # None takes the rating back


@api.post("/conversations/{conv_id}/messages/{message_id}/feedback")
async def rate_message(conv_id: str, message_id: str, body: FeedbackIn, user_id: str = Depends(current_user_id)):
    """👍 / 👎 on one of Krish's answers. A 👎 keeps the question and the start of the answer, so the owner
    can see which answers are weak."""
    await _owned_conversation(conv_id, user_id)
    msg = await db.messages.find_one({"id": message_id, "conversationId": conv_id, "role": "assistant"})
    if not msg:
        raise HTTPException(status_code=404, detail="That answer isn't in this chat any more")
    await db.messages.update_one({"id": message_id}, {"$set": {"rating": body.rating}})
    await db.message_feedback.delete_one({"messageId": message_id})
    if body.rating:
        question = await db.messages.find_one({"conversationId": conv_id, "role": "user",
                                               "createdAt": {"$lte": msg["createdAt"]}}, sort=[("createdAt", -1)])
        await db.message_feedback.insert_one({
            "messageId": message_id, "conversationId": conv_id, "userId": user_id, "rating": body.rating,
            "model": msg.get("model"), "createdAt": now_iso(),
            **({"question": (question or {}).get("content", "")[:400], "answer": (msg.get("content") or "")[:600]}
               if body.rating == "down" else {}),
        })
    return {"rating": body.rating}


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


# ----------------------------------------------------------------- assistants
# A project's name, description and instructions can be shared as an "assistant" link (like a custom GPT).
# Anyone signed in who opens it can add their own copy. Files, chats and memory are never shared.
@api.post("/projects/{pid}/assistant-link")
async def share_assistant(pid: str, user_id: str = Depends(current_user_id)):
    proj = await _owned_project(pid, user_id)
    code = proj.get("assistantCode") or secrets.token_urlsafe(9)
    await db.projects.update_one({"id": pid}, {"$set": {"assistantCode": code}})
    return {"code": code}


@api.delete("/projects/{pid}/assistant-link")
async def unshare_assistant(pid: str, user_id: str = Depends(current_user_id)):
    await _owned_project(pid, user_id)
    await db.projects.update_one({"id": pid}, {"$set": {"assistantCode": None}})
    return {"ok": True}


async def _shared_assistant(code: str) -> dict:
    proj = await db.projects.find_one({"assistantCode": code}) if code else None
    if not proj:
        raise HTTPException(status_code=404, detail="This assistant link was turned off or doesn't exist")
    return proj


@api.get("/assistants/{code}")
async def get_shared_assistant(code: str, user_id: str = Depends(current_user_id)):
    proj = await _shared_assistant(code)
    owner = await db.users.find_one({"id": proj["userId"]}, {"name": 1})
    return {"name": proj["name"], "description": proj.get("description"), "instructions": proj.get("instructions"),
            "by": (owner or {}).get("name"), "mine": proj["userId"] == user_id}


@api.post("/assistants/{code}/copy")
async def copy_shared_assistant(code: str, user_id: str = Depends(current_user_id)):
    proj = await _shared_assistant(code)
    return await create_project(ProjectIn(name=proj["name"], description=proj.get("description"),
                                          instructions=proj.get("instructions")), user_id)


# ---------------------------------------------------------------------- files
async def _process_file(file_id: str, user_id: str, project_id, data: bytes, ext: str, filename: str, content_type: str, conversation_id=None):
    """Extract text, chunk, embed, and store chunks. Updates file status."""
    try:
        # Parsing, OCR and embedding are CPU-bound: keep them off the event loop.
        text = await asyncio.to_thread(extractor.extract_text, data, ext, content_type)
        chunks = extractor.chunk_text(text)
        if chunks:
            try:
                if not embeddings.ENABLED:  # small server: keyword search only
                    vectors = [None] * len(chunks)
                else:
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


async def _check_upload_size(user_id: str, data: bytes, what: str) -> None:
    """Uploads can be as big as the plan allows (20MB on Basic, more on Pro and Max)."""
    limit = await limits.upload_bytes(db, user_id)
    if len(data) > limit:
        more = " Pro and Max take bigger files." if limit < limits.quality_of("max")["uploadMb"] * 1024 * 1024 else ""
        raise HTTPException(status_code=413, detail=f"{what} too large (max {limit // (1024 * 1024)}MB).{more}")


@api.post("/projects/{pid}/files")
async def upload_file(pid: str, file: UploadFile = File(...), user_id: str = Depends(current_user_id)):
    await _owned_project(pid, user_id)
    data = await file.read()
    await _check_upload_size(user_id, data, "File")
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


async def _keep_in_app(app_id: str, file_id: str, filename: str, data: bytes):
    """A file attached in the App Builder also goes into the app (samples/ or assets/), whole, so the builder can
    read every line of it with its file tools (see apps.keep_upload)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        text = ""
        if ext not in apps.IMAGE_EXTS and extractor.is_binary(data):  # a PDF, Word or Excel file: its text
            text = await asyncio.to_thread(extractor.extract_text, data, ext, "")
        path = await apps.keep_upload(app_id, filename, data, text)
    except Exception:
        logger.exception("Could not copy the attached file into the app")
        return
    if path:
        await db.files.update_one({"id": file_id}, {"$set": {"appPath": path}})


@api.get("/conversations/{conv_id}/files")
async def list_conversation_files(conv_id: str, user_id: str = Depends(current_user_id)):
    await _owned_conversation(conv_id, user_id)
    docs = await db.files.find({"conversationId": conv_id, "is_deleted": False}).sort("createdAt", -1).to_list(200)
    return [public_file(f) for f in docs]


@api.post("/conversations/{conv_id}/files")
async def upload_conversation_file(conv_id: str, file: UploadFile = File(...), user_id: str = Depends(current_user_id)):
    conv = await _owned_conversation(conv_id, user_id)
    data = await file.read()
    await _check_upload_size(user_id, data, "File")
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
    if conv.get("appId"):
        await _keep_in_app(conv["appId"], file_id, file.filename, data)
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


@api.get("/usage")
async def usage(user_id: str = Depends(current_user_id)):
    user = await db.users.find_one({"id": user_id}, {"plan": 1, "planExpiresAt": 1}) or {}
    expires = user.get("planExpiresAt") if limits.plan_from(user) != "basic" else None
    return {**await limits.summary(db, user_id), "paymentsOn": billing.enabled(), "planExpiresAt": expires}


# ------------------------------------------------------------------- billing
class CheckoutIn(BaseModel):
    plan: Literal["pro", "max"]
    code: str = Field(default="", max_length=24)  # an offer code like LAUNCH50


@api.post("/billing/check-code")
async def billing_check_code(body: CheckoutIn, user_id: str = Depends(current_user_id)):
    """Try an offer code on the Plans page before paying: says what it takes off."""
    plan = limits.PLANS[body.plan]
    try:
        promo = await promos.check(db, body.code, user_id, body.plan)
    except promos.PromoError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"code": promo["code"], "percentOff": promo["percentOff"],
            "price": promos.discounted(plan["price"] * 100, promo["percentOff"]) // 100}


class PaymentDoneIn(BaseModel):
    orderId: str = Field(min_length=1, max_length=64)
    paymentId: str = Field(min_length=1, max_length=64)
    signature: str = Field(min_length=1, max_length=256)


@api.post("/billing/order")
async def billing_order(body: CheckoutIn, user_id: str = Depends(current_user_id)):
    """Start paying for a month of Pro or Max: returns the Razorpay order the checkout opens."""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    try:
        return await billing.create_order(db, user, body.plan, body.code)
    except billing.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@api.post("/billing/verify")
async def billing_verify(body: PaymentDoneIn, user_id: str = Depends(current_user_id)):
    """The checkout finished: confirm the payment and switch the plan on. Returns the updated account."""
    try:
        await billing.verify(db, user_id, body.orderId, body.paymentId, body.signature)
    except billing.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return public_user(await db.users.find_one({"id": user_id}))


@api.post("/billing/webhook")
async def billing_webhook(request: Request, x_razorpay_signature: str = Header(default="")):
    """Razorpay tells us an order was paid, even if the user closed the app before it came back."""
    body = await request.body()
    try:
        event = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad body")
    if not await billing.webhook(db, body, x_razorpay_signature, event):
        raise HTTPException(status_code=400, detail="Bad signature")
    return {"ok": True}


# ------------------------------------------------------------------ discover
@api.get("/discover")
async def discover_news(topic: str = "top", limit: int = 24, user_id: str = Depends(current_user_id)):
    """Today's top stories for the Discover page (free Google News feeds), in the user's language."""
    owner = await db.users.find_one({"id": user_id}, {"language": 1})
    try:
        items = await discover.stories(topic, (owner or {}).get("language") or "en", max(1, min(limit, 40)))
    except Exception as exc:
        logger.warning("Discover feed failed: %s", exc)
        raise HTTPException(status_code=503, detail="News is not available right now. Try again in a minute.")
    return {"topic": topic if topic in discover.TOPICS else "top", "topics": list(discover.TOPICS), "stories": items}


# --------------------------------------------------------------------- pages
# A Page turns one answer into a clean public article (like Perplexity Pages), with its own link.
PAGE_SOURCE_TYPES = {"web", "video", "image", "weather", "stock"}


class PageIn(BaseModel):
    messageId: str = Field(min_length=1, max_length=64)


def public_page(doc: dict) -> dict:
    return {"id": doc["id"], "title": doc["title"], "question": doc["question"], "content": doc["content"],
            "sources": doc.get("sources") or [], "related": doc.get("related") or [], "createdAt": doc["createdAt"],
            "path": f"/page/{doc['id']}"}


@api.post("/pages")
async def create_page(body: PageIn, user_id: str = Depends(current_user_id)):
    msg = await db.messages.find_one({"id": body.messageId, "role": "assistant"})
    if not msg:
        raise HTTPException(status_code=404, detail="Answer not found")
    await _owned_conversation(msg["conversationId"], user_id)
    existing = await db.pages.find_one({"messageId": msg["id"], "userId": user_id})
    if existing:
        return public_page(existing)
    question = await db.messages.find_one({"conversationId": msg["conversationId"], "role": "user",
                                           "createdAt": {"$lte": msg["createdAt"]}}, sort=[("createdAt", -1)])
    asked = " ".join(((question or {}).get("content") or "").split())
    title = asked[:110].rstrip(" ?.!") if asked else "Krish AI answer"
    doc = {"id": secrets.token_urlsafe(10), "userId": user_id, "conversationId": msg["conversationId"],
           "messageId": msg["id"], "title": title[:1].upper() + title[1:], "question": asked[:2000],
           "content": msg.get("content") or "", "related": msg.get("related") or [],
           "sources": [x for x in msg.get("sources") or [] if x.get("type") in PAGE_SOURCE_TYPES],
           "createdAt": now_iso()}
    await db.pages.insert_one(doc)
    return public_page(doc)


@api.get("/pages/{page_id}")
async def get_page(page_id: str):
    """Public: anyone with the link can read a Page. Shows no account details."""
    doc = await db.pages.find_one({"id": page_id})
    if not doc:
        raise HTTPException(status_code=404, detail="This page was removed or doesn't exist")
    return public_page(doc)


@api.delete("/pages/{page_id}")
async def delete_page(page_id: str, user_id: str = Depends(current_user_id)):
    result = await db.pages.delete_one({"id": page_id, "userId": user_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Page not found")
    return {"ok": True}


@api.get("/capabilities")
async def capabilities(user_id: str = Depends(current_user_id)):
    return {
        "agent": {m["id"]: agent_llm.configured(m["id"]) for m in AVAILABLE_MODELS},
        "tools": tool_registry.describe(),
        "voice": media.transcription_available(),
        "serverSpeech": media.speech_available(),
        "video": any(t["name"] == "generate_video" and t["available"] for t in tool_registry.describe()),
        "imageGeneration": media.image_available(),
        "voices": media.TTS_VOICES,
    }


@api.post("/media")
async def upload_media(file: UploadFile = File(...), conversationId: Optional[str] = Form(None),
                       user_id: str = Depends(current_user_id)):
    abuse.require("media", user_id)
    content_type = (file.content_type or "").lower()
    if content_type not in IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Only PNG, JPEG, WebP and GIF images are supported")
    if conversationId:
        await _owned_conversation(conversationId, user_id)
    data = await file.read()
    await _check_upload_size(user_id, data, "Image")
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
    abuse.require("media", user_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio too large (max 25MB)")
    try:
        lang = language if language in media.VOICE_LANGUAGES else None
        text, heard = await media.transcribe_detect(data, file.filename or "audio.webm", lang)
        text = media.clean_transcript(text)
        if heard in ("hi", "ur") and not lang:
            # Spoken Hindi and Urdu sound alike; lean on the language they chose in Settings.
            owner = await db.users.find_one({"id": user_id}, {"language": 1})
            if (owner or {}).get("language") in ("hi", "ur") and not media.script_language(text):
                heard = owner["language"]
    except media.MediaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}")
    return {"text": text.strip(), "language": heard if text else None}


@api.post("/audio/speech")
async def text_to_speech(body: SpeechIn, user_id: str = Depends(current_user_id)):
    try:
        audio = await media.speak(body.text, body.voice or "nova", body.lang)
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
app.include_router(site_images.router)
app.include_router(appcloud.router)
app.include_router(appcloud.owner_router)
decks.init(db, AI_MODEL)
app.include_router(decks.router)
writer.init(db, AI_MODEL)
app.include_router(writer.router)
automations.init(db, run_turn, AI_MODEL)
app.include_router(automations.router)
help_center.init(db)
app.include_router(help_center.router)
daily_verse.init(db)
app.include_router(daily_verse.routes(current_user_id))

# Serve the built frontend (frontend/build) from the same origin, so a single
# process runs all of RADHA. In development the Vite dev server is used instead.
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST") or ROOT_DIR.parent / "frontend" / "build").resolve()
if (FRONTEND_DIST / "index.html").is_file():
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend(full_path: str, request: Request):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            cache = "public, max-age=31536000, immutable" if full_path.startswith("assets/") else "no-cache"
            headers = {"Cache-Control": cache, "Vary": "Accept-Encoding"}
            # The Docker build gzips the scripts and styles; a gzipped bundle is about a third of the size.
            packed = candidate.with_name(candidate.name + ".gz")
            if "gzip" in (request.headers.get("accept-encoding") or "") and packed.is_file():
                media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                return FileResponse(packed, media_type=media_type, headers={**headers, "Content-Encoding": "gzip"})
            return FileResponse(candidate, headers=headers)
        # Link previews (WhatsApp, X, LinkedIn) need the share picture as a full address.
        page = (FRONTEND_DIST / "index.html").read_text(encoding="utf-8")
        invite = re.fullmatch(r"i/([A-Za-z0-9]{4,20})/?", full_path)
        info = await referrals.public_invite(db, invite.group(1)) if invite else None
        if info:
            page = _invite_preview(page, info, _app_url(request))
        page = page.replace('content="/og-image.png"', f'content="{_app_url(request)}/og-image.png"')
        return Response(page, media_type="text/html", headers={"Cache-Control": "no-cache"})

def _invite_preview(page: str, info: dict, base: str) -> str:
    """Swap the link preview (WhatsApp, X, email) for the inviter's personal one."""
    import html as _html
    who = _html.escape(info["name"]) or "A friend"
    title = f"{who} invited you to Krish AI 🎁"
    desc = (f"Join with this link and you both get {info['days']} days of Krish AI Pro, free. "
            "Chat, study, build apps and get calm advice from the Bhagavad Gita.")
    picture = f"{base}/api/cards/invite/{info['code']}.png"
    values = {"og:title": title, "twitter:title": title, "og:description": desc, "twitter:description": desc,
              "description": desc, "og:image": picture, "twitter:image": picture}
    for prop, value in values.items():
        page = re.sub(rf'(<meta (?:property|name)="{re.escape(prop)}" content=")[^"]*"',
                      lambda m, v=value: f'{m.group(1)}{v}"', page)
    return page.replace("<title>Krish AI</title>", f"<title>{title}</title>")


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeaders:
    """Browsers must not guess file types (an uploaded file can't run as a script), and links to other
    sites don't carry the page address (share links stay private). Plain ASGI, so streamed replies and
    Stop are untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        https = scope.get("scheme") == "https"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                names = {k.lower() for k, _ in headers}
                extra = [(b"x-content-type-options", b"nosniff"),
                         (b"referrer-policy", b"strict-origin-when-cross-origin")]
                if https:
                    extra.append((b"strict-transport-security", b"max-age=31536000"))
                headers += [(k, v) for k, v in extra if k not in names]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(SecurityHeaders)


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
    await db.pages.create_index("id", unique=True)
    await db.pages.create_index([("messageId", 1), ("userId", 1)])
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
    await site_images.ensure_indexes()
    await appcloud.ensure_indexes()
    await automations.ensure_indexes()
    await db.settings.create_index("id", unique=True)
    await db.users.create_index("referralCode", sparse=True)
    await db.users.create_index("googleId", sparse=True)
    await db.promo_codes.create_index("code", unique=True)
    await db.push_subscriptions.create_index("endpoint", unique=True)
    await db.push_subscriptions.create_index("userId")
    await db.message_feedback.create_index("createdAt")
    await db.errors.create_index("createdAt")
    await db.activity.create_index("day")
    monitor.start(db)
    await monitor.clean_old(db)
    if os.environ.get("AUTOMATIONS_SCHEDULER", "1") != "0":
        automations.start_scheduler()
        daily_verse.start_scheduler()
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
    if not embeddings.ENABLED:
        logger.info("Small server: files are searched by keyword (set EMBEDDINGS=1 to load the embedding model)")
    logger.info("Krish AI backend ready")


@app.on_event("shutdown")
async def shutdown():
    await automations.stop_scheduler()
    await daily_verse.stop_scheduler()
    monitor.stop()
    await agent_browser.manager.shutdown()
    client.close()
