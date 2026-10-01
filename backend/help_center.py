"""Help Center: people report a bug, send feedback or ask a question from inside the app.

Every report is saved in MongoDB (`help_reports`) and, when email is set up (see mailer.py),
emailed to the team: SUPPORT_EMAIL if set, otherwise MAIL_FROM (the sender you verified, which
is usually your own inbox). People see their own past reports on the Help page.
"""
import html
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import mailer
from auth import get_user_id_from_request

logger = logging.getLogger("radha.help")
router = APIRouter(prefix="/api/help")

db = None

MAX_PER_HOUR = 10
KINDS = {"bug": "Bug report", "feedback": "Feedback", "question": "Question"}


def init(database) -> None:
    global db
    db = database


async def _uid(request: Request) -> str:
    return get_user_id_from_request(request)


class ReportIn(BaseModel):
    kind: Literal["bug", "feedback", "question"]
    message: str = Field(min_length=3, max_length=5000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    area: Optional[str] = Field(default=None, max_length=40)
    page: Optional[str] = Field(default=None, max_length=300)
    device: Optional[str] = Field(default=None, max_length=400)


def _support_inbox() -> str:
    return (os.environ.get("SUPPORT_EMAIL") or os.environ.get("MAIL_FROM") or "").strip()


def _public(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("id", "kind", "message", "rating", "area", "status", "createdAt")}


def _email(doc: dict) -> tuple[str, str, str]:
    label = KINDS[doc["kind"]]
    stars = f"{doc['rating']}/5" if doc.get("rating") else ""
    rows = [("From", f"{doc['userName']} <{doc['userEmail']}>"), ("Area", doc.get("area") or ""),
            ("Rating", stars), ("Page", doc.get("page") or ""), ("Device", doc.get("device") or ""),
            ("Report id", doc["id"])]
    rows = [(k, v) for k, v in rows if v]
    first_line = doc["message"].strip().splitlines()[0][:60]
    subject = f"[Krish AI] {label}: {first_line}"
    text = f"{label}\n\n{doc['message']}\n\n" + "\n".join(f"{k}: {v}" for k, v in rows)
    table = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#5b6275">{k}</td><td>{html.escape(str(v))}</td></tr>' for k, v in rows)
    body = f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#151a28">
<h2 style="margin:0 0 12px">{label}</h2>
<div style="white-space:pre-wrap;background:#f4f5f9;border-radius:12px;padding:16px;font-size:15px;line-height:1.5">{html.escape(doc['message'])}</div>
<table style="margin-top:16px;font-size:13px">{table}</table>
<p style="font-size:12px;color:#8a90a2">Reply to this email to answer {html.escape(doc['userName'] or 'them')} directly at {html.escape(doc['userEmail'])}.</p>
</body></html>"""
    return subject, body, text


async def _notify(doc: dict) -> None:
    to = _support_inbox()
    if not (to and mailer.configured()):
        return
    try:
        await mailer.send(to, *_email(doc))
        await db.help_reports.update_one({"id": doc["id"]}, {"$set": {"emailed": True}})
    except Exception as e:  # the report is saved either way
        logger.warning("Could not email help report %s: %s", doc["id"], e)


@router.post("/reports")
async def create_report(body: ReportIn, tasks: BackgroundTasks, uid: str = Depends(_uid)):
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    if await db.help_reports.count_documents({"userId": uid, "createdAt": {"$gte": since}}) >= MAX_PER_HOUR:
        raise HTTPException(status_code=429, detail="Thanks! You've sent a lot in the last hour. Please try again a bit later.")
    user = await db.users.find_one({"id": uid}) or {}
    doc = {
        "id": str(uuid.uuid4()), "userId": uid, "userName": user.get("name", ""), "userEmail": user.get("email", ""),
        **body.model_dump(), "message": body.message.strip(), "status": "received", "emailed": False,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.help_reports.insert_one(doc)
    tasks.add_task(_notify, doc)
    return _public(doc)


@router.get("/reports")
async def my_reports(uid: str = Depends(_uid)):
    docs = await db.help_reports.find({"userId": uid}).sort("createdAt", -1).to_list(50)
    return [_public(d) for d in docs]
