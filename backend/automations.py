"""Automations: agent tasks that run on a schedule, on demand, or from a webhook.

Each run creates its own conversation (hidden from the main chat list), runs a
full agent turn with every tool available, and records the outcome in
`automation_runs`. The scheduler claims due automations atomically in MongoDB,
so several backend processes can run without double-firing.
"""
import asyncio
import json
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_user_id_from_request

logger = logging.getLogger("radha.automations")
router = APIRouter(prefix="/api")

db = None
run_turn: Optional[Callable] = None  # server.run_turn, injected by init()
default_model: str = ""

TICK_SECONDS = 20
LOCK_MINUTES = 20
MIN_INTERVAL_MINUTES = 15
MAX_CONCURRENT_RUNS = 3
MAX_PAYLOAD_CHARS = 20_000
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
_scheduler_task: Optional[asyncio.Task] = None
_running: set = set()


def init(database, turn_runner: Callable, model: str):
    global db, run_turn, default_model
    db, run_turn, default_model = database, turn_runner, model


async def ensure_indexes():
    await db.automations.create_index([("userId", 1), ("createdAt", -1)])
    await db.automations.create_index([("enabled", 1), ("nextRunAt", 1)])
    await db.automations.create_index("webhookSecret", unique=True, sparse=True)
    await db.automation_runs.create_index([("automationId", 1), ("startedAt", -1)])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


async def current_user_id(request: Request) -> str:
    return get_user_id_from_request(request)


# ---------------------------------------------------------------- schedules
class Schedule(BaseModel):
    type: str = Field(pattern="^(manual|interval|daily|weekly)$")
    minutes: Optional[int] = Field(default=None, ge=MIN_INTERVAL_MINUTES, le=60 * 24 * 7)
    time: Optional[str] = None  # "HH:MM" for daily/weekly
    weekday: Optional[int] = Field(default=None, ge=0, le=6)  # 0 = Monday
    timezone: str = "UTC"


def validate_schedule(s: Schedule) -> Schedule:
    try:
        ZoneInfo(s.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=400, detail=f"Unknown timezone '{s.timezone}'")
    if s.type == "interval" and not s.minutes:
        raise HTTPException(status_code=400, detail=f"Interval schedules need minutes (at least {MIN_INTERVAL_MINUTES})")
    if s.type in ("daily", "weekly") and not (s.time and _TIME_RE.match(s.time)):
        raise HTTPException(status_code=400, detail="Daily and weekly schedules need a time as HH:MM")
    if s.type == "weekly" and s.weekday is None:
        raise HTTPException(status_code=400, detail="Weekly schedules need a weekday")
    return s


def next_run(schedule: dict, after: datetime) -> Optional[datetime]:
    """Next fire time strictly after `after` (UTC), or None for manual automations."""
    kind = schedule.get("type")
    if kind == "interval":
        return after + timedelta(minutes=schedule["minutes"])
    if kind not in ("daily", "weekly"):
        return None
    tz = ZoneInfo(schedule.get("timezone") or "UTC")
    hour, minute = map(int, schedule["time"].split(":"))
    local = after.astimezone(tz)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for _ in range(9):
        if candidate > local and (kind == "daily" or candidate.weekday() == schedule["weekday"]):
            # Rebuild from the wall-clock date so DST changes keep the local time.
            return datetime(candidate.year, candidate.month, candidate.day, hour, minute, tzinfo=tz).astimezone(timezone.utc)
        candidate = (candidate + timedelta(days=1)).replace(hour=hour, minute=minute)
    return None


def describe_schedule(s: dict) -> str:
    kind = s.get("type")
    if kind == "interval":
        m = s["minutes"]
        return f"Every {m // 60} hours" if m % 60 == 0 and m >= 120 else "Every hour" if m == 60 else f"Every {m} minutes"
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if kind == "daily":
        return f"Every day at {s['time']} ({s.get('timezone', 'UTC')})"
    if kind == "weekly":
        return f"Every {days[s['weekday']]} at {s['time']} ({s.get('timezone', 'UTC')})"
    return "Manual only"


# ------------------------------------------------------------------ running
async def start_run(auto: dict, trigger: str, payload: Optional[str] = None) -> dict:
    """Create a run record and execute it in the background."""
    ts = _now()
    conv = {"id": str(uuid.uuid4()), "userId": auto["userId"], "automationId": auto["id"],
            "title": f"{auto['name']} — {ts.strftime('%b %d, %H:%M UTC')}", "model": auto.get("model") or default_model,
            "projectId": None, "createdAt": _iso(ts), "updatedAt": _iso(ts)}
    prompt = auto["prompt"]
    if payload:
        prompt += f"\n\nThis run was triggered by a webhook with this payload:\n```\n{payload[:MAX_PAYLOAD_CHARS]}\n```"
    run = {"id": uuid.uuid4().hex[:12], "automationId": auto["id"], "userId": auto["userId"], "trigger": trigger,
           "status": "running", "conversationId": conv["id"], "startedAt": _iso(ts), "finishedAt": None,
           "output": None, "error": None, "media": []}
    await db.conversations.insert_one(conv)
    await db.messages.insert_one({"id": str(uuid.uuid4()), "conversationId": conv["id"], "role": "user",
                                  "content": prompt, "model": None, "createdAt": _iso(ts)})
    await db.automation_runs.insert_one(run)
    task = asyncio.create_task(_execute(auto, run, conv))
    _running.add(task)
    task.add_done_callback(_running.discard)
    return public_run(run)


async def _execute(auto: dict, run: dict, conv: dict):
    error = None
    async with _semaphore:
        try:
            async for chunk in run_turn(conv["id"], conv["model"], agent=True):
                if chunk.startswith("event: error"):
                    error = json.loads(chunk.split("data: ", 1)[1])
        except Exception as exc:
            logger.exception("Automation run failed")
            error = str(exc)
    reply = await db.messages.find_one({"conversationId": conv["id"], "role": "assistant"}, sort=[("createdAt", -1)])
    status = "failed" if error or not reply else "succeeded"
    update = {"status": status, "finishedAt": _iso(_now()), "error": error,
              "output": (reply or {}).get("content", "")[:4000] or None,
              "media": (reply or {}).get("media") or [], "steps": len((reply or {}).get("steps") or [])}
    await db.automation_runs.update_one({"id": run["id"]}, {"$set": update})
    await db.automations.update_one({"id": auto["id"]}, {"$set": {
        "lastRunAt": update["finishedAt"], "lastStatus": status, "lockedUntil": None}})


async def tick():
    """Claim and start every automation that is due."""
    while True:
        now = _now()
        auto = await db.automations.find_one_and_update(
            {"enabled": True, "nextRunAt": {"$ne": None, "$lte": _iso(now)},
             "$or": [{"lockedUntil": None}, {"lockedUntil": {"$lt": _iso(now)}}]},
            {"$set": {"lockedUntil": _iso(now + timedelta(minutes=LOCK_MINUTES))}},
        )
        if not auto:
            return
        nxt = next_run(auto["schedule"], now)
        await db.automations.update_one({"id": auto["id"]}, {"$set": {"nextRunAt": _iso(nxt)}})
        await start_run(auto, "schedule")


async def _loop():
    while True:
        try:
            await tick()
        except Exception:
            logger.exception("Automation scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)


def start_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_loop())


async def stop_scheduler():
    global _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None


# ---------------------------------------------------------------- HTTP API
class AutomationIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=8000)
    schedule: Schedule
    model: Optional[str] = None
    enabled: bool = True


class AutomationPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    prompt: Optional[str] = Field(default=None, min_length=1, max_length=8000)
    schedule: Optional[Schedule] = None
    model: Optional[str] = None
    enabled: Optional[bool] = None


def public_automation(doc: dict) -> dict:
    return {
        "id": doc["id"], "name": doc["name"], "prompt": doc["prompt"], "schedule": doc["schedule"],
        "scheduleText": describe_schedule(doc["schedule"]), "model": doc.get("model"), "enabled": doc["enabled"],
        "nextRunAt": doc.get("nextRunAt") if doc["enabled"] else None, "lastRunAt": doc.get("lastRunAt"),
        "lastStatus": doc.get("lastStatus"),
        "webhookUrl": f"/api/hooks/{doc['webhookSecret']}" if doc.get("webhookSecret") else None,
        "createdAt": doc["createdAt"],
    }


def public_run(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("id", "automationId", "trigger", "status", "conversationId", "startedAt",
                                    "finishedAt", "output", "error", "media", "steps")}


async def _owned(aid: str, user_id: str) -> dict:
    doc = await db.automations.find_one({"id": aid, "userId": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Automation not found")
    return doc


@router.get("/automations")
async def list_automations(user_id: str = Depends(current_user_id)):
    docs = await db.automations.find({"userId": user_id}).sort("createdAt", -1).to_list(200)
    return [public_automation(d) for d in docs]


@router.post("/automations")
async def create_automation(body: AutomationIn, user_id: str = Depends(current_user_id)):
    schedule = validate_schedule(body.schedule).model_dump()
    now = _now()
    doc = {"id": str(uuid.uuid4()), "userId": user_id, "name": body.name.strip(), "prompt": body.prompt.strip(),
           "schedule": schedule, "model": body.model, "enabled": body.enabled,
           "nextRunAt": _iso(next_run(schedule, now)) if body.enabled else None,
           "lastRunAt": None, "lastStatus": None, "lockedUntil": None, "webhookSecret": None, "createdAt": _iso(now)}
    await db.automations.insert_one(doc)
    return public_automation(doc)


@router.get("/automations/{aid}")
async def get_automation(aid: str, user_id: str = Depends(current_user_id)):
    return public_automation(await _owned(aid, user_id))


@router.patch("/automations/{aid}")
async def update_automation(aid: str, body: AutomationPatch, user_id: str = Depends(current_user_id)):
    doc = await _owned(aid, user_id)
    updates = body.model_dump(exclude_none=True)
    if body.schedule:
        updates["schedule"] = validate_schedule(body.schedule).model_dump()
    merged = {**doc, **updates}
    if "schedule" in updates or "enabled" in updates:
        updates["nextRunAt"] = _iso(next_run(merged["schedule"], _now())) if merged["enabled"] else None
    for key in ("name", "prompt"):
        if key in updates:
            updates[key] = updates[key].strip()
    if updates:
        await db.automations.update_one({"id": aid}, {"$set": updates})
    return public_automation(await _owned(aid, user_id))


@router.delete("/automations/{aid}")
async def delete_automation(aid: str, user_id: str = Depends(current_user_id)):
    await _owned(aid, user_id)
    conv_ids = [r["conversationId"] async for r in db.automation_runs.find({"automationId": aid}, {"conversationId": 1})]
    await db.messages.delete_many({"conversationId": {"$in": conv_ids}})
    await db.conversations.delete_many({"id": {"$in": conv_ids}})
    await db.automation_runs.delete_many({"automationId": aid})
    await db.automations.delete_one({"id": aid})
    return {"ok": True}


@router.post("/automations/{aid}/run")
async def run_now(aid: str, user_id: str = Depends(current_user_id)):
    return await start_run(await _owned(aid, user_id), "manual")


@router.get("/automations/{aid}/runs")
async def list_runs(aid: str, user_id: str = Depends(current_user_id)):
    await _owned(aid, user_id)
    docs = await db.automation_runs.find({"automationId": aid}).sort("startedAt", -1).to_list(100)
    return [public_run(d) for d in docs]


@router.post("/automations/{aid}/webhook")
async def rotate_webhook(aid: str, user_id: str = Depends(current_user_id)):
    """Create (or replace) the secret webhook URL that triggers this automation."""
    await _owned(aid, user_id)
    await db.automations.update_one({"id": aid}, {"$set": {"webhookSecret": secrets.token_urlsafe(24)}})
    return public_automation(await _owned(aid, user_id))


@router.delete("/automations/{aid}/webhook")
async def remove_webhook(aid: str, user_id: str = Depends(current_user_id)):
    await _owned(aid, user_id)
    await db.automations.update_one({"id": aid}, {"$set": {"webhookSecret": None}})
    return public_automation(await _owned(aid, user_id))


@router.post("/hooks/{secret}")
async def webhook(secret: str, request: Request):
    auto = await db.automations.find_one({"webhookSecret": secret, "enabled": True})
    if not auto or len(secret) < 20:
        raise HTTPException(status_code=404, detail="Unknown webhook")
    busy = await db.automation_runs.count_documents({"automationId": auto["id"], "status": "running"})
    if busy >= 2:
        raise HTTPException(status_code=429, detail="This automation is already running; try again shortly")
    body = (await request.body())[:MAX_PAYLOAD_CHARS * 2].decode("utf-8", "replace")
    try:
        body = json.dumps(json.loads(body), indent=2)
    except ValueError:
        pass
    run = await start_run(auto, "webhook", body or "(empty body)")
    return {"ok": True, "runId": run["id"]}
