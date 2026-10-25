"""Crash and usage tracking for the owner.

Problems: every error the server logs, and every crash the app hits on someone's phone or laptop, is saved
(kept 30 days). When problems happen, the owner (OWNER_EMAIL) gets one email at most every hour listing them,
if email is set up. The owner's Users page shows the latest problems.

Usage: each day counts how many people used Krish and how often each feature was used (chat, counsellor,
web search, voice, app builds, pictures, decks, videos), plus sign-ups and 👍 / 👎 on answers. Days are
India time, like the plan limits.
"""
import asyncio
import contextvars
import html
import logging
import os
import traceback
from datetime import datetime, timedelta, timezone

import limits
import mailer

logger = logging.getLogger("radha.monitor")

KEEP_DAYS = 30
EVENT_KEEP_DAYS = 400  # sign-ins and use, for the owner dashboard's longer views
ALERT_EVERY_SECONDS = 3600
FEATURES = ("chat", "counsellor", "web", "voice", "think", "build", "picture", "deck", "video")

_db = None
_inside = contextvars.ContextVar("monitor_inside", default=False)
_pending: list = []  # problems waiting for the next alert email
_last_alert = 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _owner_emails() -> list:
    return [e.strip() for e in os.environ.get("OWNER_EMAIL", "").split(",") if e.strip()]


async def record(source: str, message: str, detail: str = "", path: str = "", user_id: str = "") -> None:
    """Save one problem and queue it for the owner's alert email."""
    if _db is None:
        return
    token = _inside.set(True)  # anything logged while saving must not be saved again
    try:
        doc = {"source": source, "message": message[:500], "detail": detail[:4000], "path": path[:300],
               "userId": user_id or None, "createdAt": _now().isoformat()}
        await _db.errors.insert_one(dict(doc))
        _pending.append(doc)
        del _pending[:-50]
        await _maybe_alert()
    except Exception:
        pass
    finally:
        _inside.reset(token)


async def _maybe_alert() -> None:
    global _last_alert
    loop_time = asyncio.get_running_loop().time()
    owners = _owner_emails()
    if not owners or not mailer.configured() or not _pending:
        return
    if _last_alert and loop_time - _last_alert < ALERT_EVERY_SECONDS:
        return
    _last_alert = loop_time
    items, _pending[:] = list(_pending), []
    rows = "".join(f"<li><b>{html.escape(i['source'])}</b> · {html.escape(i['message'])}"
                   f"{' · ' + html.escape(i['path']) if i['path'] else ''}</li>" for i in items[-20:])
    text = "\n".join(f"- {i['source']}: {i['message']} {i['path']}" for i in items[-20:])
    subject = f"Krish AI: {len(items)} problem{'s' if len(items) != 1 else ''} in the last hour"
    body = (f"<p>Krish AI ran into {len(items)} problem{'s' if len(items) != 1 else ''}. The latest:</p><ul>{rows}</ul>"
            "<p>See them all on the Users page in the app.</p>")
    for owner in owners:
        try:
            await mailer.send(owner, subject, body, text)
        except Exception as exc:
            logger.warning("Alert email failed: %s", exc)


class _ErrorHandler(logging.Handler):
    """Saves every ERROR log line (and the crash behind it) as a server problem."""

    def emit(self, rec: logging.LogRecord) -> None:
        if _inside.get() or rec.name.startswith(("radha.monitor", "pymongo", "motor")):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        detail = "".join(traceback.format_exception(*rec.exc_info)) if rec.exc_info else ""
        try:
            message = rec.getMessage()
        except Exception:
            message = str(rec.msg)
        loop.create_task(record("server", message, detail, rec.name))


_handler = _ErrorHandler(level=logging.ERROR)


def start(db) -> None:
    """Begin saving problems into `db` (called when the server starts)."""
    global _db
    _db = db
    for name in ("", "uvicorn", "uvicorn.error"):
        log = logging.getLogger(name)
        if _handler not in log.handlers:
            log.addHandler(_handler)


def stop() -> None:
    global _db
    _db = None


async def count(db, user_id: str, *features: str) -> None:
    """Note that this user was active today and used these features once each."""
    day = limits.today()
    try:
        await db.activity.update_one({"_id": f"{day}:{user_id}"}, {"$setOnInsert": {"day": day, "userId": user_id}},
                                     upsert=True)
        inc = {f: 1 for f in features if f in FEATURES}
        if inc:
            await db.feature_daily.update_one({"_id": day}, {"$inc": inc}, upsert=True)
        # One timed row per visit or request, so the owner dashboard can show the last 24 hours and each person.
        await db.usage_events.insert_one({"userId": user_id, "kinds": list(inc) or ["visit"], "at": _now().isoformat()})
    except Exception as exc:  # counting must never break a chat
        logger.warning("Usage count failed: %s", exc)


async def login(db, user_id: str, method: str) -> None:
    """Note one sign-in ("password", "google", "signup" or "reset") for the owner dashboard."""
    try:
        await db.logins.insert_one({"userId": user_id, "method": method, "at": _now().isoformat()})
    except Exception as exc:
        logger.warning("Login note failed: %s", exc)


def _ist_day_range(day: str) -> tuple:
    ist = timezone(timedelta(hours=5, minutes=30))
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=ist)
    return start.astimezone(timezone.utc).isoformat(), (start + timedelta(days=1)).astimezone(timezone.utc).isoformat()


async def stats(db, days: int = 14) -> dict:
    """The owner's numbers for the last `days` days (newest first), the totals and the latest problems."""
    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).date()
    rows = []
    for back in range(days):
        day = (today - timedelta(days=back)).isoformat()
        start, end = _ist_day_range(day)
        features = await db.feature_daily.find_one({"_id": day}) or {}
        rows.append({
            "day": day,
            "activeUsers": await db.activity.count_documents({"day": day}),
            "signups": await db.users.count_documents({"createdAt": {"$gte": start, "$lt": end}}),
            "features": {f: features.get(f, 0) for f in FEATURES},
            "thumbsUp": await db.message_feedback.count_documents({"rating": "up", "createdAt": {"$gte": start, "$lt": end}}),
            "thumbsDown": await db.message_feedback.count_documents({"rating": "down", "createdAt": {"$gte": start, "$lt": end}}),
            "problems": await db.errors.count_documents({"createdAt": {"$gte": start, "$lt": end}}),
        })
    errors = await db.errors.find({}, {"_id": 0, "detail": 0}).sort("createdAt", -1).to_list(30)
    disliked = await db.message_feedback.find({"rating": "down"}, {"_id": 0}).sort("createdAt", -1).to_list(20)
    return {"days": rows, "totalUsers": await db.users.count_documents({}), "problems": errors,
            "disliked": disliked}


async def clean_old(db) -> None:
    """Forget problems older than KEEP_DAYS (run once a day)."""
    cutoff = (_now() - timedelta(days=KEEP_DAYS)).isoformat()
    await db.errors.delete_many({"createdAt": {"$lt": cutoff}})
    events_cutoff = (_now() - timedelta(days=EVENT_KEEP_DAYS)).isoformat()
    await db.usage_events.delete_many({"at": {"$lt": events_cutoff}})
    await db.logins.delete_many({"at": {"$lt": events_cutoff}})
