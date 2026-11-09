"""Automations: agent tasks that run on a schedule, on demand, or from a webhook.

Each run creates its own conversation (hidden from the main chat list), runs a
full agent turn with every tool available, and records the outcome in
`automation_runs`. Runs work as an autonomous agent: they plan first, get a
larger step budget, can see what the previous run found (memory), and can
deliver the result by email or to a Discord/Slack webhook. The scheduler claims due automations atomically in MongoDB,
so several backend processes can run without double-firing.

Each plan decides what its automations may do (limits.automation_rules): how often they repeat, Thorough mode and
the premium models. A run is checked against the plan when it starts, so a downgrade takes effect on the next run,
and automations beyond the plan's count are paused. Runs send a heartbeat while they work; one whose heartbeat stops
(the server restarted) is marked failed, a run can be stopped, and only the newest KEEP_RUNS runs are kept.
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
from typing import Callable, List, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import connectors
import limits
import mailer
import media
from agent import prompt_boost
from auth import get_user_id_from_request

logger = logging.getLogger("radha.automations")
router = APIRouter(prefix="/api")

db = None
run_turn: Optional[Callable] = None  # server.run_turn, injected by init()
pick_model: Optional[Callable] = None  # server._pick_model: the plan's model and its credits, injected by init()
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
RUN_TIMEOUT_MINUTES = 15  # a run that takes longer is stopped (the scheduler's lock lasts LOCK_MINUTES)
HEARTBEAT_SECONDS = 30
STALE_MINUTES = 5  # a running run with no heartbeat for this long was lost (the server restarted)
KEEP_RUNS = 50  # older runs, and their conversations, are deleted
DAY_MINUTES = 60 * 24

AGENT_INSTRUCTIONS = (
    "You are running as an autonomous agent for a saved automation. Nobody is watching, so never ask questions: "
    "make sensible assumptions and state them briefly. Work like this: 1) Start your answer with a short numbered "
    "plan (2-6 steps). 2) Carry out every step with your tools (search, research, code, files, images...), "
    "checking results as you go; if a tool fails, try another way. 3) End with '## Result': the finished answer, "
    "the files you created, and one line 'Next time:' with anything worth checking on the next run."
)

PLAN_SYSTEM = (
    "You turn a person's plain-language goal into a saved automation for an AI agent that has these tools: web "
    "search, open web pages, deep research (cited PDF report), Python for calculations and charts, "
    + ("image and video generation" if media.video_enabled() else "image generation")
    + ", and Excel, PowerPoint, Word/PDF, HTML, text and zip file creation. Reply with JSON only: "
    '{"name": "short title, max 6 words", "task": "clear instructions for the agent: numbered steps naming the '
    'tools to use, what to look for, the output format and which files to create", "schedule": {"type": '
    '"daily|weekly|interval|once|manual", "time": "HH:MM", "weekday": 0-6 (0 = Monday), "minutes": 15-10080, '
    '"date": "YYYY-MM-DD (only for once)"}, "deliver": ["email", "telegram", "whatsapp", "slack", "discord"]}. '
    "Pick the schedule the goal implies (daily at 08:00 when it says every day, once with a date for a single "
    "future time such as 'tomorrow at 5 pm', manual when no timing is given). Put in deliver only the places the "
    "goal asks for the result to go ('mail me', 'on WhatsApp'); leave it empty otherwise. "
    "Write the task in the same language as the goal, 60-180 words."
)
APPS_HINT = {
    "gmail": "Gmail (search and read emails, write drafts and send emails)",
    "google_calendar": "Google Calendar (read events, add events)",
    "google_drive": "Google Drive (search and read files)",
    "notion": "Notion (search, read and add pages)",
    "github": "GitHub (read repositories, open issues)",
}
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
_scheduler_task: Optional[asyncio.Task] = None
_running: set = set()
_tasks: dict = {}  # run id -> its task in this process, so Stop can cancel it


def init(database, turn_runner: Callable, model: str, model_picker: Optional[Callable] = None):
    global db, run_turn, default_model, pick_model
    db, run_turn, default_model, pick_model = database, turn_runner, model, model_picker


async def ensure_indexes():
    await db.automations.create_index([("userId", 1), ("createdAt", -1)])
    await db.automations.create_index([("enabled", 1), ("nextRunAt", 1)])
    # Most automations have webhookSecret=None; only index real secrets (a sparse index
    # would still include the nulls and reject the second automation).
    await _replace_index(db.automations, "webhookSecret_1", "webhookSecret",
                         {"webhookSecret": {"$type": "string"}})
    await db.automation_runs.create_index([("automationId", 1), ("startedAt", -1)])
    await db.automation_runs.create_index([("status", 1), ("heartbeatAt", 1)])


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
    type: str = Field(pattern="^(manual|once|interval|daily|weekly)$")
    minutes: Optional[int] = Field(default=None, ge=MIN_INTERVAL_MINUTES, le=60 * 24 * 7)
    time: Optional[str] = None  # "HH:MM" for daily/weekly
    weekday: Optional[int] = Field(default=None, ge=0, le=6)  # 0 = Monday
    date: Optional[str] = None  # "YYYY-MM-DD" for a one-time job (with time, in timezone)
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
    if s.type == "once":
        if not (s.time and _TIME_RE.match(s.time)) or not _once_at(s.model_dump()):
            raise HTTPException(status_code=400, detail="A one-time job needs a date and time")
    return s


def _once_at(schedule: dict) -> Optional[datetime]:
    """When a one-time job runs (UTC), or None if its date or time is missing or invalid."""
    try:
        day = datetime.strptime(schedule.get("date") or "", "%Y-%m-%d")
        hour, minute = map(int, (schedule.get("time") or "").split(":"))
        tz = ZoneInfo(schedule.get("timezone") or "UTC")
    except (ValueError, ZoneInfoNotFoundError):
        return None
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz).astimezone(timezone.utc)


def next_run(schedule: dict, after: datetime, min_interval: Optional[int] = MIN_INTERVAL_MINUTES) -> Optional[datetime]:
    """Next fire time strictly after `after` (UTC), or None for manual automations. An interval shorter than the
    plan allows (`min_interval`; None means daily at most) waits that long instead."""
    kind = schedule.get("type")
    if kind == "interval":
        return after + timedelta(minutes=max(schedule["minutes"], min_interval or DAY_MINUTES))
    if kind == "once":
        at = _once_at(schedule)
        return at if at and at > after else None
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
    if kind == "once":
        at = _once_at(s)
        when = at.astimezone(ZoneInfo(s.get("timezone") or "UTC")).strftime("%a %-d %b %Y") if at else s.get("date")
        return f"Once, on {when} at {s.get('time')} ({s.get('timezone', 'UTC')})"
    return "Manual only"


# -------------------------------------------------------------- plan rules
def _every(minutes: int) -> str:
    return "hour" if minutes == 60 else f"{minutes // 60} hours" if minutes % 60 == 0 else f"{minutes} minutes"


async def _rules(user_id: str) -> tuple:
    plan = await limits.plan_of(db, user_id)
    return plan, limits.automation_rules(plan)


def _upgrade(plan: str) -> str:
    nxt = limits.ORDER[limits.ORDER.index(plan) + 1] if plan != limits.ORDER[-1] else None
    return f" Upgrade to {limits.PLANS[nxt]['name']} for more." if nxt else ""


async def check_plan_rules(user_id: str, schedule: dict, model: Optional[str], thorough: bool):
    """Refuse (402, so the app offers the plans page) what the user's plan doesn't include."""
    plan, rules = await _rules(user_id)
    name = limits.PLANS[plan]["name"]
    problem = None
    if schedule.get("type") == "interval":
        least = rules["minInterval"]
        if least is None:
            problem = f"On the {name} plan an automation runs once a day or once a week."
        elif (schedule.get("minutes") or 0) < least:
            problem = f"On the {name} plan an automation can repeat every {_every(least)} at most."
    if thorough and not rules["thorough"]:
        problem = problem or "Thorough mode is part of the Max plan."
    if model and _premium(model) and not rules["premiumModels"]:
        problem = problem or "The premium AI models are part of the Pro and Max plans."
    if problem:
        raise HTTPException(status_code=402, detail=problem + _upgrade(plan))


def _premium(model: str) -> bool:
    from agent import llm as agent_llm
    return model == agent_llm.PRO or agent_llm.paid(model)


async def _allowed_ids(user_id: str, plan: str) -> set:
    """The automations the plan keeps running: the oldest ones, up to its count (the rest are paused)."""
    n = limits.PLANS[plan]["total"]["automation"] if limits.enabled() else 10 ** 6
    docs = await db.automations.find({"userId": user_id}, {"id": 1}).sort("createdAt", 1).limit(n).to_list(None)
    return {d["id"] for d in docs}


async def _over_count(auto: dict) -> Optional[str]:
    """Why the plan can't run this automation (it has more than the plan keeps), or None."""
    plan = await limits.plan_of(db, auto["userId"])
    if auto["id"] in await _allowed_ids(auto["userId"], plan):
        return None
    n = limits.PLANS[plan]["total"]["automation"]
    return (f"Paused: the {limits.PLANS[plan]['name']} plan keeps {n} automation{'s' if n != 1 else ''} running. "
            f"Delete one, or upgrade, to turn this back on.")


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
           "output": None, "error": None, "media": [], "heartbeatAt": _iso(ts)}
    await db.conversations.insert_one(conv)
    await db.messages.insert_one({"id": str(uuid.uuid4()), "conversationId": conv["id"], "role": "user",
                                  "content": prompt, "model": None, "createdAt": _iso(ts)})
    await db.automation_runs.insert_one(run)
    task = asyncio.create_task(_execute(auto, run, conv, await _agent_context(auto)))
    _running.add(task)
    _tasks[run["id"]] = task
    task.add_done_callback(_running.discard)
    task.add_done_callback(lambda _t, rid=run["id"]: _tasks.pop(rid, None))
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


class _StopRequested(Exception):
    pass


async def _plan_check(auto: dict, conv: dict) -> tuple:
    """(steps, model, why the run can't happen) for this run, by the user's plan right now."""
    plan, rules = await _rules(auto["userId"])
    steps = STEPS_THOROUGH if auto.get("thorough") and rules["thorough"] else STEPS_NORMAL
    try:
        await limits.check_fair_use(db, auto["userId"])
    except limits.LimitReached as exc:
        return steps, conv["model"], str(exc)
    model = conv["model"]
    if model and _premium(model) and not rules["premiumModels"]:
        model = default_model
    if pick_model:
        try:
            model = await pick_model(auto["userId"], conv, model, new_chars=len(auto.get("prompt") or ""),
                                     text=auto.get("prompt") or "")
        except Exception:
            logger.exception("Picking the automation's model failed")
    return steps, model, None


async def _execute(auto: dict, run: dict, conv: dict, context: str = ""):
    error, status = None, None
    async with _semaphore:
        steps, model, blocked = await _plan_check(auto, conv)
        if blocked:
            error, status = blocked, "skipped"
        else:
            turn = run_turn(conv["id"], model, agent=True, extra_system=context or None, max_steps=steps)

            async def consume():
                nonlocal error
                beat = asyncio.get_running_loop().time()
                async for chunk in turn:
                    if chunk.startswith("event: error"):
                        error = json.loads(chunk.split("data: ", 1)[1])
                    if asyncio.get_running_loop().time() - beat >= HEARTBEAT_SECONDS:
                        beat = asyncio.get_running_loop().time()
                        doc = await db.automation_runs.find_one_and_update(
                            {"id": run["id"]}, {"$set": {"heartbeatAt": _iso(_now())}})
                        if doc and doc.get("stopRequested"):  # Stop pressed on another server process
                            raise _StopRequested()

            try:
                await asyncio.wait_for(consume(), RUN_TIMEOUT_MINUTES * 60)
            except (asyncio.CancelledError, _StopRequested):
                status, error = "stopped", "Stopped"
            except asyncio.TimeoutError:
                error = f"This run took longer than {RUN_TIMEOUT_MINUTES} minutes, so it was stopped."
            except Exception as exc:
                logger.exception("Automation run failed")
                error = str(exc)
            finally:
                try:  # a stopped turn saves what it wrote so far
                    await asyncio.shield(turn.aclose())
                except Exception:
                    pass
    reply = await db.messages.find_one({"conversationId": conv["id"], "role": "assistant"}, sort=[("createdAt", -1)])
    status = status or ("failed" if error or not reply else "succeeded")
    update = {"status": status, "finishedAt": _iso(_now()), "error": error,
              "output": (reply or {}).get("content", "")[:MAX_OUTPUT_CHARS] or None,
              "media": (reply or {}).get("media") or [],
              "steps": [_step_view(s) for s in ((reply or {}).get("steps") or [])[:MAX_RUN_STEPS_SHOWN]]}
    if status != "stopped":
        update["delivery"] = await _deliver(auto, {**run, **update})
    await db.automation_runs.update_one({"id": run["id"]}, {"$set": update})
    await db.automations.update_one({"id": auto["id"]}, {"$set": {
        "lastRunAt": update["finishedAt"], "lastStatus": status, "lockedUntil": None}})
    try:
        await _prune(auto["id"])
    except Exception:
        logger.exception("Pruning old automation runs failed")


async def _prune(aid: str):
    """Delete runs past the newest KEEP_RUNS, with their conversations."""
    old = await db.automation_runs.find({"automationId": aid, "status": {"$ne": "running"}},
                                        {"id": 1, "conversationId": 1}).sort("startedAt", -1).skip(KEEP_RUNS).to_list(None)
    if not old:
        return
    conv_ids = [r["conversationId"] for r in old if r.get("conversationId")]
    await db.messages.delete_many({"conversationId": {"$in": conv_ids}})
    await db.conversations.delete_many({"id": {"$in": conv_ids}})
    await db.automation_runs.delete_many({"id": {"$in": [r["id"] for r in old]}})


async def recover_lost_runs():
    """Mark runs whose heartbeat stopped (the server restarted mid-run) as failed, so they don't spin forever."""
    cutoff = _iso(_now() - timedelta(minutes=STALE_MINUTES))
    lost = await db.automation_runs.find(
        {"status": "running", "$or": [{"heartbeatAt": {"$lt": cutoff}},
                                      {"heartbeatAt": None, "startedAt": {"$lt": cutoff}}]},
        {"id": 1, "automationId": 1}).to_list(200)
    for r in lost:
        if r["id"] in _tasks:  # still working in this process (a long tool step)
            continue
        await db.automation_runs.update_one({"id": r["id"], "status": "running"}, {"$set": {
            "status": "failed", "finishedAt": _iso(_now()),
            "error": "The server restarted while this was running. Press Run now to try again."}})
        await db.automations.update_one({"id": r["automationId"]}, {"$set": {"lastStatus": "failed", "lockedUntil": None}})


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
    for app in auto.get("sendTo") or []:
        jobs.append((app, connectors.send(auto["userId"], app, _summary_text(auto, run, 20_000))))
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
        paused = await _over_count(auto)
        if paused:  # the plan keeps fewer automations now (a downgrade)
            await db.automations.update_one({"id": auto["id"]}, {"$set": {
                "enabled": False, "nextRunAt": None, "lockedUntil": None, "pausedReason": paused}})
            continue
        _, rules = await _rules(auto["userId"])
        nxt = next_run(auto["schedule"], now, rules["minInterval"])
        done = {"enabled": False} if auto["schedule"].get("type") == "once" else {}  # a one-time job is finished
        await db.automations.update_one({"id": auto["id"]}, {"$set": {"nextRunAt": _iso(nxt), **done}})
        await start_run(auto, "schedule")


async def _loop():
    while True:
        try:
            await recover_lost_runs()
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
def _clean_send_to(apps: Optional[List[str]]) -> List[str]:
    return [a for a in connectors.MESSAGING if a in (apps or [])]


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
    sendTo: List[str] = Field(default_factory=list, max_length=4)  # connected apps: telegram, whatsapp, slack, discord


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
    sendTo: Optional[List[str]] = Field(default=None, max_length=4)


class PlanIn(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)
    timezone: str = "UTC"


def public_automation(doc: dict) -> dict:
    return {
        "id": doc["id"], "name": doc["name"], "prompt": doc["prompt"], "schedule": doc["schedule"],
        "scheduleText": describe_schedule(doc["schedule"]), "model": doc.get("model"), "enabled": doc["enabled"],
        "nextRunAt": doc.get("nextRunAt") if doc["enabled"] else None, "lastRunAt": doc.get("lastRunAt"),
        "lastStatus": doc.get("lastStatus"), "pausedReason": None if doc["enabled"] else doc.get("pausedReason"),
        "memory": doc.get("memory", True), "thorough": bool(doc.get("thorough")),
        "emailResult": bool(doc.get("emailResult")), "notifyUrl": doc.get("notifyUrl"),
        "sendTo": doc.get("sendTo") or [],
        "webhookUrl": f"/api/hooks/{doc['webhookSecret']}" if doc.get("webhookSecret") else None,
        "createdAt": doc["createdAt"],
    }


def public_run(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("id", "automationId", "trigger", "status", "conversationId", "startedAt",
                                    "finishedAt", "output", "error", "media", "steps",
                                    "delivery", "heartbeatAt")}


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
    plan, rules = await _rules(user_id)
    return {"email": mailer.configured(), "planner": prompt_boost.available(), "plan": plan,
            "planName": limits.PLANS[plan]["name"], "rules": rules,
            "limit": limits.PLANS[plan]["total"]["automation"] if limits.enabled() else None}


@router.post("/automations/plan")
async def plan_automation(body: PlanIn, user_id: str = Depends(current_user_id)):
    """Draft a name, detailed agent task and schedule from a plain-language goal."""
    await limits.require(db, user_id, "automation")
    if not prompt_boost.available():
        raise HTTPException(status_code=503, detail="No AI model is set up to write the plan")
    try:
        try:
            tz = ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            tz = ZoneInfo("UTC")
        linked = [APPS_HINT[c] for c in APPS_HINT if c in await connectors.active(user_id)]
        context = (f"Now: {datetime.now(tz).strftime('%A %Y-%m-%d %H:%M')} ({body.timezone}). "
                   + (f"The user connected these apps, which the agent can use: {'; '.join(linked)}. " if linked
                      else "The user has not connected Gmail, Calendar, Drive or Notion yet. "))
        text = await prompt_boost.ask(PLAN_SYSTEM, f"{context}\nGoal: {body.goal.strip()}")
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
    kind = raw.get("type") if raw.get("type") in ("manual", "once", "interval", "daily", "weekly") else "manual"
    schedule = {"type": kind}
    if kind == "once":
        date = str(raw.get("date") or "")
        try:
            datetime.strptime(date, "%Y-%m-%d")
            schedule["date"] = date
        except ValueError:
            schedule["type"] = "manual"
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
    deliver = data.get("deliver") if isinstance(data.get("deliver"), list) else []
    return {"name": name, "prompt": task, "schedule": schedule, "emailResult": "email" in deliver,
            "sendTo": [a for a in connectors.MESSAGING if a in deliver]}


@router.post("/automations")
async def create_automation(body: AutomationIn, user_id: str = Depends(current_user_id)):
    await limits.require(db, user_id, "automation")
    schedule = validate_schedule(body.schedule).model_dump()
    await check_plan_rules(user_id, schedule, body.model, body.thorough)
    now = _now()
    doc = {"id": str(uuid.uuid4()), "userId": user_id, "name": body.name.strip(), "prompt": body.prompt.strip(),
           "schedule": schedule, "model": body.model, "enabled": body.enabled,
           "memory": body.memory, "thorough": body.thorough, "emailResult": body.emailResult,
           "notifyUrl": await _clean_notify_url(body.notifyUrl), "sendTo": _clean_send_to(body.sendTo),
           "nextRunAt": _iso(next_run(schedule, now, (await _rules(user_id))[1]["minInterval"])) if body.enabled else None,
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
    if body.sendTo is not None:
        updates["sendTo"] = _clean_send_to(body.sendTo)
    if body.schedule:
        updates["schedule"] = validate_schedule(body.schedule).model_dump()
    merged = {**doc, **updates}
    if {"schedule", "model", "thorough"} & updates.keys():
        await check_plan_rules(user_id, merged["schedule"], merged.get("model"), bool(merged.get("thorough")))
    if updates.get("enabled") and not doc["enabled"]:
        paused = await _over_count(doc)
        if paused:
            raise HTTPException(status_code=402, detail=paused.replace("Paused: the", "The"))
        updates["pausedReason"] = None
    if "schedule" in updates or "enabled" in updates:
        rules = (await _rules(user_id))[1]
        updates["nextRunAt"] = _iso(next_run(merged["schedule"], _now(), rules["minInterval"])) if merged["enabled"] else None
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
    auto = await _owned(aid, user_id)
    if await db.automation_runs.count_documents({"automationId": aid, "status": "running"}):
        raise HTTPException(status_code=409, detail="This automation is already running. Wait for it, or stop it.")
    paused = await _over_count(auto)
    if paused:
        raise HTTPException(status_code=402, detail=paused.replace("Paused: the", "The"))
    try:
        await limits.check_fair_use(db, user_id)
    except limits.LimitReached as exc:
        raise limits.http_error(exc)
    return await start_run(auto, "manual")


@router.post("/automations/{aid}/runs/{rid}/stop")
async def stop_run(aid: str, rid: str, user_id: str = Depends(current_user_id)):
    """Stop a running run: right away in this process, or at its next heartbeat in another one."""
    await _owned(aid, user_id)
    doc = await db.automation_runs.find_one_and_update({"id": rid, "automationId": aid, "status": "running"},
                                                       {"$set": {"stopRequested": True}})
    if not doc:
        raise HTTPException(status_code=409, detail="This run has already finished")
    task = _tasks.get(rid)
    if task:
        task.cancel()
    return {"ok": True}


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
