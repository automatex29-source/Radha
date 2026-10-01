"""Automations: agent tasks that run on a schedule, on demand, or from a webhook.

Each run creates its own conversation (hidden from the main chat list), runs a
full agent turn with every tool available, and records the outcome in
`automation_runs`. Runs work as an autonomous agent: they plan first, get a
larger step budget, can see what the previous run found (memory), and can
deliver the result by email or to a Discord/Slack webhook. The scheduler claims due automations atomically in MongoDB,
so several backend processes can run without double-firing.
"""
import asyncio
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import limits
import mailer
from agent import prompt_boost
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
MAX_OUTPUT_CHARS = 12_000
STEPS_NORMAL = 12
STEPS_THOROUGH = 20
MEMORY_CHARS = 1500
MAX_RUN_STEPS_SHOWN = 30

AGENT_INSTRUCTIONS = (
    "You are running as an autonomous agent for a saved automation. Nobody is watching, so never ask questions: "
    "make sensible assumptions and state them briefly. Work like this: 1) Start your answer with a short numbered "
    "plan (2-6 steps). 2) Carry out every step with your tools (search, research, code, files, images...), "
    "checking results as you go; if a tool fails, try another way. 3) End with '## Result': the finished answer, "
    "the files you created, and one line 'Next time:' with anything worth checking on the next run."
)

PLAN_SYSTEM = (
    "You turn a person's plain-language goal into a saved automation for an AI agent that has these tools: web "
    "search, open web pages, deep research (cited PDF report), Python for calculations and charts, image and "
    "video generation, and Excel, PowerPoint, Word/PDF, HTML, text and zip file creation. Reply with JSON only: "
    '{"name": "short title, max 6 words", "task": "clear instructions for the agent: numbered steps naming the '
    'tools to use, what to look for, the output format and which files to create", "schedule": {"type": '
    '"daily|weekly|interval|manual", "time": "HH:MM", "weekday": 0-6 (0 = Monday), "minutes": 15-10080}}. '
    "Pick the schedule the goal implies (daily at 08:00 when it says every day, manual when no timing is given). "
    "Write the task in the same language as the goal, 60-180 words."
)
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
    # Most automations have webhookSecret=None; only index real secrets (a sparse index
    # would still include the nulls and reject the second automation).
    await _replace_index(db.automations, "webhookSecret_1", "webhookSecret",
                         {"webhookSecret": {"$type": "string"}})
    await db.automation_runs.create_index([("automationId", 1), ("startedAt", -1)])


async def _replace_index(collection, name: str, field: str, partial: dict):
    """Create a unique partial index, dropping an older definition with the same name."""
    info = await collection.index_information()
    if name in info and info[name].get("partialFilterExpression") != partial:
        await collection.drop_index(name)
    await collection.create_index(field, name=name, unique=True, partialFilterExpression=partial)


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
    task = asyncio.create_task(_execute(auto, run, conv, await _agent_context(auto)))
    _running.add(task)
    task.add_done_callback(_running.discard)
    return public_run(run)


async def _agent_context(auto: dict) -> str:
    """The agent instructions, plus what the last successful run produced when memory is on."""
    parts = [AGENT_INSTRUCTIONS]
    if auto.get("memory", True):
        last = await db.automation_runs.find_one({"automationId": auto["id"], "status": "succeeded"},
                                                 sort=[("startedAt", -1)])
        if last and last.get("output"):
            parts.append(f"Memory: the previous run of this automation ({last.get('finishedAt') or last['startedAt']}) "
                         f"ended with the result below. Build on it: skip items already reported, point out what "
                         f"changed, and follow its 'Next time' notes.\n---\n{last['output'][-MEMORY_CHARS:]}\n---")
    return "\n\n".join(parts)


def _step_view(step: dict) -> dict:
    return {"label": step.get("label") or step.get("name"), "name": step.get("name"),
            "status": step.get("status"), "summary": (step.get("summary") or "")[:200]}


async def _execute(auto: dict, run: dict, conv: dict, context: str = ""):
    error = None
    steps = STEPS_THOROUGH if auto.get("thorough") else STEPS_NORMAL
    async with _semaphore:
        try:
            async for chunk in run_turn(conv["id"], conv["model"], agent=True, extra_system=context or None,
                                        max_steps=steps):
                if chunk.startswith("event: error"):
                    error = json.loads(chunk.split("data: ", 1)[1])
        except Exception as exc:
            logger.exception("Automation run failed")
            error = str(exc)
    reply = await db.messages.find_one({"conversationId": conv["id"], "role": "assistant"}, sort=[("createdAt", -1)])
    status = "failed" if error or not reply else "succeeded"
    update = {"status": status, "finishedAt": _iso(_now()), "error": error,
              "output": (reply or {}).get("content", "")[:MAX_OUTPUT_CHARS] or None,
              "media": (reply or {}).get("media") or [],
              "steps": [_step_view(s) for s in ((reply or {}).get("steps") or [])[:MAX_RUN_STEPS_SHOWN]]}
    update["delivery"] = await _deliver(auto, {**run, **update})
    await db.automation_runs.update_one({"id": run["id"]}, {"$set": update})
    await db.automations.update_one({"id": auto["id"]}, {"$set": {
        "lastRunAt": update["finishedAt"], "lastStatus": status, "lockedUntil": None}})


# ----------------------------------------------------------------- delivery
def _app_url() -> str:
    return (os.environ.get("APP_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")


def _summary_text(auto: dict, run: dict, limit: int) -> str:
    head = f"{auto['name']}: {'finished' if run['status'] == 'succeeded' else 'failed'}"
    body = run.get("output") or run.get("error") or ""
    files = [m.get("name") for m in run.get("media") or [] if m.get("name")]
    tail = (f"\n\nFiles: {', '.join(files)}" if files else "") + \
        (f"\nOpen in Krish AI: {_app_url()}/automations" if _app_url() else "")
    room = max(0, limit - len(head) - len(tail) - 4)
    if len(body) > room:
        body = body[:max(0, room - 1)] + "…"
    return f"{head}\n\n{body}{tail}"


async def check_notify_url(url: str) -> str:
    """Accept only public https URLs, so a webhook can't be pointed at the server's own network."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("The notification URL must start with https://")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or 443,
                                                            type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("That notification URL's website can't be found")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("The notification URL must be a public internet address")
    return url


async def _notify_webhook(url: str, auto: dict, run: dict):
    await check_notify_url(url)
    text = _summary_text(auto, run, 1900)  # Discord's message limit is 2000
    payload = {"content": text, "text": text, "automation": auto["name"], "status": run["status"],
               "output": run.get("output"), "error": run.get("error"),
               "files": [m.get("name") for m in run.get("media") or [] if m.get("name")],
               "finishedAt": run.get("finishedAt")}
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        r = await client.post(url, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"The webhook answered {r.status_code}")


async def _email(auto: dict, run: dict):
    if not mailer.configured():
        raise RuntimeError("Email isn't set up on the server (add BREVO_API_KEY and MAIL_FROM)")
    user = await db.users.find_one({"id": auto["userId"]})
    if not user or not user.get("email"):
        raise RuntimeError("Your account has no email address")
    text = _summary_text(auto, run, 20_000)
    body = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = (f'<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;'
            f'line-height:1.6;white-space:pre-wrap;color:#151a28">{body}</div>')
    status = "result" if run["status"] == "succeeded" else "failed"
    await mailer.send(user["email"], f"{auto['name']} ({status})", html, text)


async def _deliver(auto: dict, run: dict) -> list:
    """Send the run's result to the channels the automation asks for; never raises."""
    jobs = []
    if auto.get("emailResult"):
        jobs.append(("email", _email(auto, run)))
    if auto.get("notifyUrl"):
        jobs.append(("webhook", _notify_webhook(auto["notifyUrl"], auto, run)))
    out = []
    for channel, job in jobs:
        try:
            await job
            out.append({"channel": channel, "ok": True, "error": None})
        except Exception as exc:
            logger.info("Automation delivery by %s failed: %s", channel, exc)
            out.append({"channel": channel, "ok": False, "error": str(exc)[:200]})
    return out


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
    memory: bool = True  # show the agent what the previous run produced
    thorough: bool = False  # a bigger step budget for long multi-step jobs
    emailResult: bool = False
    notifyUrl: Optional[str] = Field(default=None, max_length=500)  # Discord/Slack/any webhook


class AutomationPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    prompt: Optional[str] = Field(default=None, min_length=1, max_length=8000)
    schedule: Optional[Schedule] = None
    model: Optional[str] = None
    enabled: Optional[bool] = None
    memory: Optional[bool] = None
    thorough: Optional[bool] = None
    emailResult: Optional[bool] = None
    notifyUrl: Optional[str] = Field(default=None, max_length=500)  # "" removes it


class PlanIn(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)


def public_automation(doc: dict) -> dict:
    return {
        "id": doc["id"], "name": doc["name"], "prompt": doc["prompt"], "schedule": doc["schedule"],
        "scheduleText": describe_schedule(doc["schedule"]), "model": doc.get("model"), "enabled": doc["enabled"],
        "nextRunAt": doc.get("nextRunAt") if doc["enabled"] else None, "lastRunAt": doc.get("lastRunAt"),
        "lastStatus": doc.get("lastStatus"),
        "memory": doc.get("memory", True), "thorough": bool(doc.get("thorough")),
        "emailResult": bool(doc.get("emailResult")), "notifyUrl": doc.get("notifyUrl"),
        "webhookUrl": f"/api/hooks/{doc['webhookSecret']}" if doc.get("webhookSecret") else None,
        "createdAt": doc["createdAt"],
    }


def public_run(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("id", "automationId", "trigger", "status", "conversationId", "startedAt",
                                    "finishedAt", "output", "error", "media", "steps",
                                    "delivery")}


async def _owned(aid: str, user_id: str) -> dict:
    doc = await db.automations.find_one({"id": aid, "userId": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Automation not found")
    return doc


@router.get("/automations")
async def list_automations(user_id: str = Depends(current_user_id)):
    docs = await db.automations.find({"userId": user_id}).sort("createdAt", -1).to_list(200)
    return [public_automation(d) for d in docs]


async def _clean_notify_url(url: Optional[str]) -> Optional[str]:
    url = (url or "").strip()
    if not url:
        return None
    try:
        return await check_notify_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/automations/options")
async def automation_options(user_id: str = Depends(current_user_id)):
    return {"email": mailer.configured(), "planner": prompt_boost.available()}


@router.post("/automations/plan")
async def plan_automation(body: PlanIn, user_id: str = Depends(current_user_id)):
    """Draft a name, detailed agent task and schedule from a plain-language goal."""
    await limits.require(db, user_id, "automation")
    if not prompt_boost.available():
        raise HTTPException(status_code=503, detail="No AI model is set up to write the plan")
    try:
        text = await prompt_boost.ask(PLAN_SYSTEM, f"Goal: {body.goal.strip()}")
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0) if match else text)
    except Exception as exc:
        logger.info("Automation plan failed: %s", exc)
        raise HTTPException(status_code=502, detail="Couldn't write the plan right now. Please try again.")
    return parse_plan(data, body.goal)


def parse_plan(data: dict, goal: str) -> dict:
    """Keep only valid values from the model's plan, with safe defaults."""
    name = str(data.get("name") or "").strip()[:100] or goal.strip()[:60]
    task = str(data.get("task") or "").strip()[:8000] or goal.strip()
    raw = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
    kind = raw.get("type") if raw.get("type") in ("manual", "interval", "daily", "weekly") else "manual"
    schedule = {"type": kind}
    time = str(raw.get("time") or "08:00")
    schedule["time"] = time if _TIME_RE.match(time) else "08:00"
    try:
        schedule["weekday"] = min(6, max(0, int(raw.get("weekday", 0))))
    except (TypeError, ValueError):
        schedule["weekday"] = 0
    try:
        schedule["minutes"] = min(60 * 24 * 7, max(MIN_INTERVAL_MINUTES, int(raw.get("minutes", 60))))
    except (TypeError, ValueError):
        schedule["minutes"] = 60
    return {"name": name, "prompt": task, "schedule": schedule}


@router.post("/automations")
async def create_automation(body: AutomationIn, user_id: str = Depends(current_user_id)):
    await limits.require(db, user_id, "automation")
    schedule = validate_schedule(body.schedule).model_dump()
    now = _now()
    doc = {"id": str(uuid.uuid4()), "userId": user_id, "name": body.name.strip(), "prompt": body.prompt.strip(),
           "schedule": schedule, "model": body.model, "enabled": body.enabled,
           "memory": body.memory, "thorough": body.thorough, "emailResult": body.emailResult,
           "notifyUrl": await _clean_notify_url(body.notifyUrl),
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
    if body.notifyUrl is not None:
        updates["notifyUrl"] = await _clean_notify_url(body.notifyUrl)
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
