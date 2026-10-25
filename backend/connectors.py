"""Connectors: outside apps a user links to Krish, so Krish can use them in chats and automations.

Google Drive, Google Calendar and Gmail sign in on Google's page; GitHub and Notion on theirs when their sign-in
apps are set up (GITHUB_CLIENT_ID/SECRET, NOTION_CLIENT_ID/SECRET), otherwise the user pastes a token. Slack and
Discord take a channel's webhook link. Telegram and WhatsApp link by a short code the user sends to Krish's bot;
after that the user can chat with Krish there and get automation results there.

Each link is one document in `connections` (per user and connector), with its tokens encrypted. connector_tools.py
holds the agent tools that use them; `send()` here delivers a message to the user's own Telegram, WhatsApp, Slack
or Discord.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlencode, quote

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

import google_signin
import limits
from auth import get_user_id_from_request

logger = logging.getLogger("radha.connectors")

db = None
run_turn: Optional[Callable] = None  # server.run_turn, injected by init()
default_model = ""
_tasks: set = set()

GOOGLE = "https://www.googleapis.com/auth/"
NOTION_VERSION = "2022-06-28"
STATE_MINUTES = 30

# plan: the lowest plan that can use it. how: "google" | "oauth" (GitHub/Notion) | "webhook" | "link".
CONNECTORS = {
    "google_drive": {
        "name": "Google Drive", "category": "files", "plan": "basic", "how": "google",
        "scopes": [GOOGLE + "drive.readonly"],
        "blurb": "Ask about your Docs, Sheets, Slides and PDFs",
        "does": ["Find files by name or by words inside them", "Read Docs, Sheets, Slides and PDFs to answer you",
                 "Krish only reads. It never changes or deletes your files"],
    },
    "google_calendar": {
        "name": "Google Calendar", "category": "work", "plan": "pro", "how": "google",
        "scopes": [GOOGLE + "calendar.events"],
        "blurb": "See your day and add events and reminders",
        "does": ["Tell you what's on today or this week", "Add events and reminders when you ask",
                 "Help plan around your free time"],
    },
    "gmail": {
        "name": "Gmail", "category": "work", "plan": "pro", "how": "google",
        "scopes": [GOOGLE + "gmail.readonly", GOOGLE + "gmail.compose"],
        "blurb": "Summarise your inbox and draft replies",
        "does": ["Find and summarise emails", "Write replies as drafts in your Gmail",
                 "Krish never sends an email for you. You send drafts yourself"],
    },
    "github": {
        "name": "GitHub", "category": "work", "plan": "basic", "how": "oauth",
        "blurb": "Save apps to GitHub, read code and open issues",
        "does": ["Push apps you build to your repositories", "Read files in your repositories",
                 "Open issues when you ask"],
    },
    "notion": {
        "name": "Notion", "category": "work", "plan": "pro", "how": "oauth",
        "blurb": "Search, read and add to your Notion pages",
        "does": ["Search the pages you share with Krish", "Read a page to answer you",
                 "Add new pages with notes, plans and summaries"],
    },
    "telegram": {
        "name": "Telegram", "category": "messaging", "plan": "basic", "how": "link",
        "blurb": "Chat with Krish on Telegram and get automation results",
        "does": ["Message Krish from Telegram, like a friend", "Get automation results as Telegram messages",
                 "Your Telegram chats also show in Krish"],
    },
    "whatsapp": {
        "name": "WhatsApp", "category": "messaging", "plan": "max", "how": "link",
        "blurb": "Talk to Krish on WhatsApp",
        "does": ["Message Krish from WhatsApp", "Get automation results on WhatsApp",
                 "Your WhatsApp chats also show in Krish"],
    },
    "slack": {
        "name": "Slack", "category": "messaging", "plan": "basic", "how": "webhook",
        "blurb": "Send results and reports to a Slack channel",
        "does": ["Post automation results to a channel", "Send a message to the channel when you ask"],
        "help": {"url": "https://api.slack.com/messaging/webhooks",
                 "steps": ["Open Slack's Incoming Webhooks page and create an app for your workspace",
                           "Turn on Incoming Webhooks and add one for your channel",
                           "Copy the link that starts with https://hooks.slack.com and paste it here"]},
    },
    "discord": {
        "name": "Discord", "category": "messaging", "plan": "basic", "how": "webhook",
        "blurb": "Send results and reports to a Discord channel",
        "does": ["Post automation results to a channel", "Send a message to the channel when you ask"],
        "help": {"url": "https://support.discord.com/hc/en-us/articles/228383668",
                 "steps": ["In Discord, open the channel's settings, then Integrations",
                           "Choose Webhooks, then New Webhook",
                           "Copy the webhook URL and paste it here"]},
    },
}
TOKEN_HELP = {
    "github": {"url": "https://github.com/settings/tokens/new?scopes=repo&description=Krish%20AI",
               "steps": ["Open GitHub's new token page (the button below)",
                         "Keep the \"repo\" box ticked and press Generate token",
                         "Copy the token (it starts with ghp_) and paste it here"]},
    "notion": {"url": "https://www.notion.so/profile/integrations",
               "steps": ["Open Notion's integrations page and create a new integration",
                         "Copy its Internal Integration Secret and paste it here",
                         "In Notion, open each page Krish may use, then ••• > Connections > add your integration"]},
}
MESSAGING = ("telegram", "whatsapp", "slack", "discord")
SLACK_RE = re.compile(r"^https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+$")
DISCORD_RE = re.compile(r"^https://(?:discord|discordapp)\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$")


class ConnectError(Exception):
    """A problem the user should see, in plain words."""


def init(database, turn_runner: Callable, model: str):
    global db, run_turn, default_model
    db, run_turn, default_model = database, turn_runner, model


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


# ------------------------------------------------------------------ secrets
def _fernet() -> Fernet:
    key = hashlib.sha256(("krish-connectors:" + _env("AUTH_SECRET")).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def unseal(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError):
        return {}


# ------------------------------------------------------------- what's ready
def oauth_ready(cid: str) -> bool:
    """True when the app's own sign-in for this connector is set up on the server."""
    how = CONNECTORS[cid]["how"]
    if how == "google":
        return bool(google_signin.client_id() and _env("GOOGLE_CLIENT_SECRET"))
    if how == "oauth":
        key = cid.upper()
        return bool(_env(f"{key}_CLIENT_ID") and _env(f"{key}_CLIENT_SECRET"))
    return False


def ready(cid: str) -> bool:
    """True when users can connect it now."""
    how = CONNECTORS[cid]["how"]
    if how == "google":
        return oauth_ready(cid)
    if cid == "telegram":
        return bool(_env("TELEGRAM_BOT_TOKEN"))
    if cid == "whatsapp":
        return bool(_env("WHATSAPP_TOKEN") and _env("WHATSAPP_PHONE_ID") and _env("WHATSAPP_NUMBER"))
    return True  # GitHub and Notion fall back to a pasted token; Slack and Discord take a webhook link


def method(cid: str) -> str:
    """How the user connects it: google, oauth, token, webhook or link."""
    how = CONNECTORS[cid]["how"]
    if how == "oauth" and not oauth_ready(cid):
        return "token"
    return how


def _plan_ok(plan: str, needed: str) -> bool:
    return limits.ORDER.index(plan) >= limits.ORDER.index(needed)


def public_url(request: Optional[Request] = None) -> str:
    url = _env("PUBLIC_URL") or _env("APP_URL") or _env("RENDER_EXTERNAL_URL")
    if not url and request is not None:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        url = f"{proto}://{host}"
    return url.rstrip("/")


# ---------------------------------------------------------------- listing
async def listing(user_id: str) -> list:
    user = await db.users.find_one({"id": user_id}, {"plan": 1, "planExpiresAt": 1}) or {}
    plan = limits.plan_from(user)
    links = {c["connector"]: c async for c in db.connections.find({"userId": user_id})}
    out = []
    for cid, c in CONNECTORS.items():
        link = links.get(cid)
        how = method(cid)
        out.append({
            "id": cid, "name": c["name"], "category": c["category"], "plan": c["plan"], "blurb": c["blurb"],
            "does": c["does"], "how": how, "ready": ready(cid), "locked": not _plan_ok(plan, c["plan"]),
            "connected": bool(link), "account": (link or {}).get("account"), "connectedAt": (link or {}).get("createdAt"),
            "help": TOKEN_HELP.get(cid) if how == "token" else c.get("help"),
        })
    return out


async def active(user_id: str) -> set:
    """The connectors this user has linked and their plan allows."""
    if db is None or not user_id:
        return set()
    user = await db.users.find_one({"id": user_id}, {"plan": 1, "planExpiresAt": 1}) or {}
    plan = limits.plan_from(user)
    return {c["connector"] async for c in db.connections.find({"userId": user_id}, {"connector": 1})
            if c["connector"] in CONNECTORS and _plan_ok(plan, CONNECTORS[c["connector"]]["plan"])}


def prompt_line(connected: set) -> str:
    if not connected:
        return ""
    names = ", ".join(CONNECTORS[c]["name"] for c in CONNECTORS if c in connected)
    return (f"Connected apps: the user linked {names} to Krish. When they ask about their files, calendar, email, "
            "code, notes or want something sent to them, use those apps' tools instead of saying you can't reach "
            "them. Never claim you sent an email: Gmail replies are saved as drafts for the user to send.")


async def _save(user_id: str, cid: str, secret: dict, account: str, address: str = ""):
    await db.connections.update_one(
        {"userId": user_id, "connector": cid},
        {"$set": {"secret": seal(secret), "account": account[:120], "address": address, "updatedAt": _now()},
         "$setOnInsert": {"id": uuid.uuid4().hex[:12], "createdAt": _now()}},
        upsert=True)


async def _check_plan(user_id: str, cid: str):
    if cid not in CONNECTORS:
        raise HTTPException(status_code=404, detail="That app isn't available.")
    user = await db.users.find_one({"id": user_id}, {"plan": 1, "planExpiresAt": 1})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    needed = CONNECTORS[cid]["plan"]
    if not _plan_ok(limits.plan_from(user), needed):
        raise HTTPException(status_code=402, detail=f"{CONNECTORS[cid]['name']} is part of the "
                                                    f"{limits.PLANS[needed]['name']} plan. Upgrade to connect it.")
    if not ready(cid):
        raise HTTPException(status_code=400, detail=f"{CONNECTORS[cid]['name']} is coming soon.")


# ------------------------------------------------------------------- tokens
async def secret_for(user_id: str, cid: str) -> dict:
    """The connector's stored secret, with a fresh Google access token. Raises ConnectError when not linked."""
    doc = await db.connections.find_one({"userId": user_id, "connector": cid})
    if not doc:
        raise ConnectError(f"{CONNECTORS[cid]['name']} isn't connected. Connect it in Settings > Connectors.")
    data = unseal(doc["secret"])
    if CONNECTORS[cid]["how"] == "google" and data.get("expires", 0) < time.time() + 60:
        if not data.get("refresh"):
            raise ConnectError(f"Krish lost access to {CONNECTORS[cid]['name']}. Connect it again in Settings.")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id": google_signin.client_id(), "client_secret": _env("GOOGLE_CLIENT_SECRET"),
                "refresh_token": data["refresh"], "grant_type": "refresh_token"})
        if r.status_code >= 400:
            raise ConnectError(f"Google stopped Krish's access to {CONNECTORS[cid]['name']}. Connect it again in "
                               "Settings > Connectors.")
        body = r.json()
        data.update(access=body["access_token"], expires=time.time() + int(body.get("expires_in", 3600)))
        await db.connections.update_one({"_id": doc["_id"]}, {"$set": {"secret": seal(data), "updatedAt": _now()}})
    return data


# -------------------------------------------------------------- connecting
async def _github_account(token: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.github.com/user", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    if r.status_code in (401, 403):
        raise ConnectError("GitHub didn't accept that token. Make a new one with the \"repo\" box ticked.")
    if r.status_code >= 400:
        raise ConnectError(f"GitHub answered {r.status_code}. Try again in a minute.")
    return "@" + r.json().get("login", "")


async def _notion_account(token: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.notion.com/v1/users/me", headers={
            "Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION})
    if r.status_code in (401, 403):
        raise ConnectError("Notion didn't accept that secret. Copy the Internal Integration Secret again.")
    if r.status_code >= 400:
        raise ConnectError(f"Notion answered {r.status_code}. Try again in a minute.")
    body = r.json()
    return (body.get("bot") or {}).get("workspace_name") or body.get("name") or "Notion"


async def _post_webhook(url: str, text: str):
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        r = await client.post(url, json={"text": text, "content": text})
    if r.status_code >= 400:
        raise ConnectError(f"The channel's link answered {r.status_code}. Copy the webhook link again.")


async def connect_with(user_id: str, cid: str, value: str):
    """Link a connector with a pasted token (GitHub, Notion) or webhook link (Slack, Discord)."""
    value = value.strip()
    how = method(cid)
    if how == "token" and cid == "github":
        await _save(user_id, cid, {"access": value}, await _github_account(value))
    elif how == "token" and cid == "notion":
        await _save(user_id, cid, {"access": value}, await _notion_account(value))
    elif how == "webhook":
        pattern = SLACK_RE if cid == "slack" else DISCORD_RE
        if not pattern.match(value):
            raise ConnectError("That isn't a Slack webhook link (https://hooks.slack.com/services/...)." if cid == "slack"
                               else "That isn't a Discord webhook link (https://discord.com/api/webhooks/...).")
        await _post_webhook(value, "Krish AI is connected to this channel. Results you ask for will arrive here.")
        await _save(user_id, cid, {"url": value}, f"{CONNECTORS[cid]['name']} channel")
    else:
        raise ConnectError(f"{CONNECTORS[cid]['name']} connects with the Connect button.")


async def _new_state(user_id: str, cid: str, **extra) -> str:
    state = secrets.token_urlsafe(24)
    await db.connector_states.insert_one({"state": state, "userId": user_id, "connector": cid,
                                          "createdAt": time.time(), **extra})
    return state


async def _take_state(state: str) -> Optional[dict]:
    doc = await db.connector_states.find_one_and_delete({"state": state})
    if not doc or doc["createdAt"] < time.time() - STATE_MINUTES * 60:
        return None
    return doc


def _auth_url(cid: str, state: str, redirect: str) -> str:
    how = CONNECTORS[cid]["how"]
    if how == "google":
        scopes = CONNECTORS[cid]["scopes"] + ["openid", "email"]
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": google_signin.client_id(), "redirect_uri": redirect, "response_type": "code",
            "scope": " ".join(scopes), "access_type": "offline", "prompt": "consent",
            "include_granted_scopes": "true", "state": state})
    if cid == "github":
        return "https://github.com/login/oauth/authorize?" + urlencode({
            "client_id": _env("GITHUB_CLIENT_ID"), "redirect_uri": redirect, "scope": "repo", "state": state})
    return "https://api.notion.com/v1/oauth/authorize?" + urlencode({
        "client_id": _env("NOTION_CLIENT_ID"), "redirect_uri": redirect, "response_type": "code",
        "owner": "user", "state": state})


async def _finish_oauth(user_id: str, cid: str, code: str, redirect: str):
    how = CONNECTORS[cid]["how"]
    async with httpx.AsyncClient(timeout=20) as client:
        if how == "google":
            r = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": google_signin.client_id(), "client_secret": _env("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": redirect, "grant_type": "authorization_code"})
            if r.status_code >= 400:
                raise ConnectError("Google didn't finish the sign-in. Please try again.")
            body = r.json()
            granted = set((body.get("scope") or "").split())
            if not set(CONNECTORS[cid]["scopes"]) <= granted:
                raise ConnectError("Please tick every box on Google's page, so Krish can do what you asked.")
            who = await client.get("https://openidconnect.googleapis.com/v1/userinfo",
                                   headers={"Authorization": f"Bearer {body['access_token']}"})
            email = who.json().get("email", "") if who.status_code == 200 else ""
            await _save(user_id, cid, {"access": body["access_token"], "refresh": body.get("refresh_token"),
                                       "expires": time.time() + int(body.get("expires_in", 3600))}, email)
        elif cid == "github":
            r = await client.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"},
                                  data={"client_id": _env("GITHUB_CLIENT_ID"), "client_secret": _env("GITHUB_CLIENT_SECRET"),
                                        "code": code, "redirect_uri": redirect})
            token = (r.json() if r.status_code < 400 else {}).get("access_token")
            if not token:
                raise ConnectError("GitHub didn't finish the sign-in. Please try again.")
            await _save(user_id, cid, {"access": token}, await _github_account(token))
        else:
            r = await client.post("https://api.notion.com/v1/oauth/token",
                                  auth=(_env("NOTION_CLIENT_ID"), _env("NOTION_CLIENT_SECRET")),
                                  json={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect})
            body = r.json() if r.status_code < 400 else {}
            if not body.get("access_token"):
                raise ConnectError("Notion didn't finish the sign-in. Please try again.")
            await _save(user_id, cid, {"access": body["access_token"]}, body.get("workspace_name") or "Notion")


async def disconnect(user_id: str, cid: str):
    doc = await db.connections.find_one_and_delete({"userId": user_id, "connector": cid})
    if doc and CONNECTORS.get(cid, {}).get("how") == "google":
        data = unseal(doc["secret"])
        token = data.get("refresh") or data.get("access")
        if token:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post("https://oauth2.googleapis.com/revoke", params={"token": token})
            except httpx.HTTPError:
                pass


async def delete_user(user_id: str):
    for doc in await db.connections.find({"userId": user_id}, {"connector": 1}).to_list(None):
        await disconnect(user_id, doc["connector"])
    await db.connector_states.delete_many({"userId": user_id})


# ---------------------------------------------------------------- messaging
def plain(text: str) -> str:
    """Markdown to plain chat text: no #, **, or [n] citation marks."""
    text = re.sub(r"```[a-zA-Z0-9]*\n?", "", text or "")
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\[(\d+)\]", "", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)
    return text.strip()


def _parts(text: str, size: int) -> list:
    out = []
    while text:
        cut = text.rfind("\n", 0, size) if len(text) > size else len(text)
        cut = cut if cut > size // 2 else min(size, len(text))
        out.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return out or [""]


async def _telegram(method_name: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"https://api.telegram.org/bot{_env('TELEGRAM_BOT_TOKEN')}/{method_name}", json=payload)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not body.get("ok"):
        raise ConnectError(f"Telegram said: {body.get('description') or r.status_code}")
    return body.get("result") or {}


async def _telegram_send(chat_id, text: str):
    for part in _parts(plain(text), 4000):
        await _telegram("sendMessage", {"chat_id": chat_id, "text": part, "disable_web_page_preview": True})


async def _whatsapp_send(phone: str, text: str):
    url = f"https://graph.facebook.com/v21.0/{_env('WHATSAPP_PHONE_ID')}/messages"
    async with httpx.AsyncClient(timeout=20) as client:
        for part in _parts(plain(text), 4000):
            r = await client.post(url, headers={"Authorization": f"Bearer {_env('WHATSAPP_TOKEN')}"}, json={
                "messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": part}})
            if r.status_code >= 400:
                raise ConnectError("WhatsApp only lets Krish write to you within 24 hours of your last message "
                                   "to Krish. Send Krish any message on WhatsApp, then try again.")


async def send(user_id: str, cid: str, text: str):
    """Send a message to the user's own Telegram, WhatsApp, Slack or Discord. Raises ConnectError."""
    if cid not in MESSAGING:
        raise ConnectError("Krish can send messages to Telegram, WhatsApp, Slack or Discord.")
    data = await secret_for(user_id, cid)
    if cid == "telegram":
        await _telegram_send(data["chat"], text)
    elif cid == "whatsapp":
        await _whatsapp_send(data["phone"], text)
    else:
        for part in _parts(plain(text), 1900):  # Discord's limit is 2000
            await _post_webhook(data["url"], part)


_bot_name: dict = {}


async def _telegram_link(code: str, request: Request) -> str:
    token = _env("TELEGRAM_BOT_TOKEN")
    if _bot_name.get("token") != token:
        me = await _telegram("getMe", {})
        hook = f"{public_url(request)}/api/connectors/telegram/webhook"
        await _telegram("setWebhook", {"url": hook, "secret_token": _telegram_secret(),
                                       "allowed_updates": ["message"]})
        _bot_name.update(token=token, name=me.get("username", ""))
    return f"https://t.me/{_bot_name['name']}?start={code}"


def _telegram_secret() -> str:
    return hashlib.sha256(("krish-telegram:" + _env("TELEGRAM_BOT_TOKEN")).encode()).hexdigest()[:48]


async def _link_code(user_id: str, cid: str) -> str:
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    await db.connector_states.delete_many({"userId": user_id, "connector": cid})
    await db.connector_states.insert_one({"state": f"link:{cid}:{code}", "userId": user_id, "connector": cid,
                                          "createdAt": time.time()})
    return code


async def _bind(cid: str, code: str, address: str, account: str, secret: dict) -> Optional[str]:
    state = await _take_state(f"link:{cid}:{code.upper()}")
    if not state:
        return None
    # One Krish account per chat: linking again moves the chat to the new account.
    await db.connections.delete_many({"connector": cid, "address": address})
    await _save(state["userId"], cid, secret, account, address)
    return state["userId"]


async def _chat(user_id: str, cid: str, text: str) -> str:
    """Run one Krish turn for a message sent from Telegram or WhatsApp; returns the reply text."""
    conv = await db.conversations.find_one({"userId": user_id, "channel": cid}, sort=[("updatedAt", -1)])
    ts = _now()
    if not conv:
        conv = {"id": str(uuid.uuid4()), "userId": user_id, "channel": cid,
                "title": f"{CONNECTORS[cid]['name']} chat", "model": default_model, "projectId": None,
                "createdAt": ts, "updatedAt": ts}
        await db.conversations.insert_one(conv)
    await db.messages.insert_one({"id": str(uuid.uuid4()), "conversationId": conv["id"], "role": "user",
                                  "content": text[:8000], "model": None, "createdAt": ts})
    await db.conversations.update_one({"id": conv["id"]}, {"$set": {"updatedAt": ts}})
    error = None
    async for chunk in run_turn(conv["id"], conv.get("model") or default_model, agent=True):
        if chunk.startswith("event: error"):
            error = json.loads(chunk.split("data: ", 1)[1])
        elif chunk.startswith("event: plan_limit"):
            error = "You've used this session's allowance. It refills soon, or upgrade in Krish for more."
    reply = await db.messages.find_one({"conversationId": conv["id"], "role": "assistant"}, sort=[("createdAt", -1)])
    if error or not reply or reply.get("createdAt", "") < ts:
        return f"Sorry, Krish couldn't answer that: {error or 'please try again.'}"
    files = [m.get("name") for m in reply.get("media") or [] if m.get("name")]
    link = public_url()
    tail = f"\n\nFiles: {', '.join(files)}" + (f"\nOpen them in Krish: {link}" if link else "") if files else ""
    return (reply.get("content") or "") + tail


def _background(coro):
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _answer(cid: str, address: str, user_id: str, text: str):
    sender = _telegram_send if cid == "telegram" else _whatsapp_send
    try:
        if cid == "telegram":
            await _telegram("sendChatAction", {"chat_id": address, "action": "typing"})
        reply = await _chat(user_id, cid, text)
    except Exception as exc:
        logger.exception("%s chat failed", cid)
        reply = f"Sorry, something went wrong: {exc}"
    try:
        await sender(address, reply)
    except Exception:
        logger.exception("%s reply failed", cid)


NOT_LINKED = ("Hi! I'm Krish AI. To chat with me here, open Krish, go to Settings > Connectors > {name} and "
              "press Connect.")


async def on_message(cid: str, address: str, account: str, text: str):
    """A message reached Krish's Telegram or WhatsApp number."""
    sender = _telegram_send if cid == "telegram" else _whatsapp_send
    m = re.match(r"^\s*(?:/start|connect)\s+([A-Za-z0-9]{6})\s*$", text or "", re.I)
    if m:
        secret = {"chat": address} if cid == "telegram" else {"phone": address}
        if await _bind(cid, m.group(1), address, account, secret):
            await sender(address, f"Connected! You can chat with Krish here now, and get automation results here. "
                                  f"Ask me anything.")
        else:
            await sender(address, "That code has expired. Press Connect in Krish again for a new one.")
        return
    link = await db.connections.find_one({"connector": cid, "address": address})
    if not link:
        await sender(address, NOT_LINKED.format(name=CONNECTORS[cid]["name"]))
        return
    if (text or "").strip():
        _background(_answer(cid, address, link["userId"], text.strip()))


# ------------------------------------------------------------------- routes
async def current_user_id(request: Request) -> str:
    return get_user_id_from_request(request)


class ConnectIn(BaseModel):
    value: str = Field(min_length=8, max_length=500)


class SendIn(BaseModel):
    text: str = Field(default="", max_length=500)


router = APIRouter(prefix="/api/connectors")


@router.get("")
async def list_connectors(user_id: str = Depends(current_user_id)):
    return {"connectors": await listing(user_id)}


@router.post("/{cid}/connect")
async def connect_route(cid: str, body: ConnectIn, user_id: str = Depends(current_user_id)):
    await _check_plan(user_id, cid)
    try:
        await connect_with(user_id, cid, body.value)
    except ConnectError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Couldn't reach the app. Check your internet and try again.")
    return {"connectors": await listing(user_id)}


@router.post("/{cid}/start")
async def start_route(cid: str, request: Request, user_id: str = Depends(current_user_id)):
    """The page to open to connect: the app's sign-in page, or Krish's bot with a one-time code."""
    await _check_plan(user_id, cid)
    how = method(cid)
    if how in ("google", "oauth"):
        redirect = f"{public_url(request)}/api/connectors/oauth/callback"
        state = await _new_state(user_id, cid, redirect=redirect)
        return {"url": _auth_url(cid, state, redirect)}
    if how == "link":
        code = await _link_code(user_id, cid)
        try:
            if cid == "telegram":
                url = await _telegram_link(code, request)
            else:
                url = f"https://wa.me/{re.sub(r'[^0-9]', '', _env('WHATSAPP_NUMBER'))}?text={quote('Connect ' + code)}"
        except (ConnectError, httpx.HTTPError) as exc:
            raise HTTPException(status_code=502, detail=f"Couldn't reach {CONNECTORS[cid]['name']}: {exc}")
        return {"url": url, "code": code}
    raise HTTPException(status_code=400, detail="Paste the link or token to connect this app.")


@router.get("/oauth/callback")
async def oauth_callback(state: str = "", code: str = "", error: str = ""):
    doc = await _take_state(state) if state else None
    base = public_url()
    back = (doc or {}).get("redirect", "").rsplit("/api/", 1)[0] or base
    if not doc:
        return RedirectResponse(f"{back}/?settings=connectors&connectError=" + quote("That sign-in expired. Try again."))
    cid = doc["connector"]
    if error or not code:
        return RedirectResponse(f"{back}/?settings=connectors&connectError=" + quote("You cancelled the sign-in."))
    try:
        await _finish_oauth(doc["userId"], cid, code, doc["redirect"])
    except ConnectError as exc:
        return RedirectResponse(f"{back}/?settings=connectors&connectError=" + quote(str(exc)))
    except (httpx.HTTPError, KeyError, ValueError):
        logger.exception("OAuth for %s failed", cid)
        return RedirectResponse(f"{back}/?settings=connectors&connectError=" + quote("Sign-in failed. Please try again."))
    return RedirectResponse(f"{back}/?settings=connectors&connected={cid}")


@router.post("/{cid}/test")
async def test_route(cid: str, body: SendIn, user_id: str = Depends(current_user_id)):
    """Send a test message to a linked Telegram, WhatsApp, Slack or Discord."""
    try:
        await send(user_id, cid, body.text or "Hello from Krish AI! Messages you ask for will arrive here.")
    except ConnectError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Couldn't reach the app. Try again in a minute.")
    return {"ok": True}


@router.delete("/{cid}")
async def disconnect_route(cid: str, user_id: str = Depends(current_user_id)):
    if cid not in CONNECTORS:
        raise HTTPException(status_code=404, detail="That app isn't available.")
    await disconnect(user_id, cid)
    return {"connectors": await listing(user_id)}


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    if not _env("TELEGRAM_BOT_TOKEN") or not hmac.compare_digest(x_telegram_bot_api_secret_token, _telegram_secret()):
        raise HTTPException(status_code=403, detail="Forbidden")
    update = await request.json()
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") == "private" and chat.get("id"):
        sender = msg.get("from") or {}
        account = "@" + sender["username"] if sender.get("username") else sender.get("first_name") or "Telegram"
        try:
            await on_message("telegram", str(chat["id"]), account, msg.get("text") or "")
        except Exception:
            logger.exception("Telegram message failed")
    return {"ok": True}


@router.get("/whatsapp/webhook")
async def whatsapp_verify(request: Request):
    q = request.query_params
    token = _env("WHATSAPP_VERIFY_TOKEN")
    if token and q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), token):
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, x_hub_signature_256: str = Header(default="")):
    raw = await request.body()
    secret = _env("WHATSAPP_APP_SECRET")
    if not _env("WHATSAPP_TOKEN"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if secret:
        want = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="Bad signature")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad body")
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
            for msg in value.get("messages") or []:
                if msg.get("type") != "text" or not msg.get("from"):
                    continue
                phone = msg["from"]
                try:
                    await on_message("whatsapp", phone, names.get(phone) or f"+{phone}", (msg.get("text") or {}).get("body", ""))
                except Exception:
                    logger.exception("WhatsApp message failed")
    return {"ok": True}
