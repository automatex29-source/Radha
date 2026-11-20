"""What each person does in Krish, for the owner: which features they use, how often and when, the AI tokens
their replies took, their plan and payments, and the things they made.

Privacy: this never reads what people write. No chat text, prompts, questions or answers are loaded or returned,
and chat titles are left out too (they are made from the first message). Counsellor use is private and is not
shown per person at all. What is shown is the kind of thing that happened and when, plus the names of things
people made (apps, decks, docs, automations, files), which they named themselves.

Everything comes from what the app already saves: the timed use rows (`usage_events`, monitor.py), sign-ins
(`logins`), payments, the made things' own collections, and, from this update on, AI tokens per person per day
(`token_daily`, monitor.tokens).
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import limits

RANGES = (7, 30, 90, 365)

# What the owner sees per person, in this order. "events" come from the use rows; the rest from what was made.
FEATURES = [
    ("chat", "Chat", "events"),
    ("web", "Web search", "events"),
    ("think", "Think", "events"),
    ("voice", "Voice", "events"),
    ("picture", "Pictures", "events"),
    ("video", "Videos", "events"),
    ("deck", "Decks", "events"),
    ("doc", "Docs", "made"),
    ("build", "App Builder", "events"),
    ("app", "Apps made", "made"),
    ("automation", "Automation runs", "made"),
    ("upload", "Files uploaded", "made"),
]
LABELS = {k: label for k, label, _ in FEATURES}
EVENT_KINDS = {k for k, _, src in FEATURES if src == "events"}

FILE_KINDS = {  # content type -> a short label for files Krish made
    "image/": "Picture", "video/": "Video", "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.spreadsheetml": "Excel",
    "application/vnd.openxmlformats-officedocument.presentationml": "PowerPoint",
    "application/vnd.openxmlformats-officedocument.wordprocessingml": "Word", "text/html": "Web page",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: str):
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _ist_day(iso: str) -> str:
    t = _parse(iso)
    return t.astimezone(limits.IST).date().isoformat() if t else ""


def _ist_days(n: int) -> list:
    today = datetime.now(limits.IST).date()
    return [(today - timedelta(days=back)).isoformat() for back in range(n - 1, -1, -1)]


def _file_kind(content_type: str) -> str:
    for prefix, label in FILE_KINDS.items():
        if (content_type or "").startswith(prefix):
            return label
    return "File"


def clamp_days(days: int) -> int:
    return days if days in RANGES else 30


async def _counsellor_convs(db, user_ids=None) -> set:
    q = {"mode": "counsellor", **({"userId": {"$in": list(user_ids)}} if user_ids else {})}
    return {c["id"] async for c in db.conversations.find(q, {"id": 1})}


async def _made(db, user_id: str, since: str = "") -> list:
    """Things this person made, newest first: names and dates only, never what is inside."""
    when = {"createdAt": {"$gte": since}} if since else {}
    rows = []
    async for d in db.apps.find({"userId": user_id, **when}, {"_id": 0, "id": 1, "name": 1, "published": 1, "createdAt": 1}):
        rows.append({"type": "app", "label": "App", "name": d.get("name") or "Untitled app", "at": d.get("createdAt"),
                     "note": "Published" if (d.get("published") or {}).get("slug") else ""})
    async for d in db.decks.find({"userId": user_id, **when}, {"_id": 0, "title": 1, "status": 1, "slides": 1, "createdAt": 1}):
        n = len(d.get("slides") or [])
        rows.append({"type": "deck", "label": "Deck", "name": d.get("title") or "Untitled deck", "at": d.get("createdAt"),
                     "note": f"{n} slide{'s' if n != 1 else ''}" if n else (d.get("status") or "")})
    async for d in db.docs.find({"userId": user_id, **when}, {"_id": 0, "title": 1, "createdAt": 1}):
        rows.append({"type": "doc", "label": "Doc", "name": d.get("title") or "Untitled doc", "at": d.get("createdAt"), "note": ""})
    async for d in db.automations.find({"userId": user_id, **when}, {"_id": 0, "name": 1, "schedule": 1, "enabled": 1, "createdAt": 1}):
        rows.append({"type": "automation", "label": "Automation", "name": d.get("name") or "Untitled automation",
                     "at": d.get("createdAt"),
                     "note": f"{(d.get('schedule') or {}).get('type', '')}{'' if d.get('enabled') else ' · paused'}".strip(" ·")})
    async for d in db.files.find({"userId": user_id, "is_deleted": {"$ne": True}, **when},
                                 {"_id": 0, "original_filename": 1, "size": 1, "createdAt": 1}):
        rows.append({"type": "upload", "label": "Uploaded", "name": d.get("original_filename") or "File",
                     "at": d.get("createdAt"), "size": d.get("size")})
    private = await _counsellor_convs(db, [user_id])
    async for d in db.media.find({"userId": user_id, "kind": {"$in": ["generated", "code_output"]}, **when},
                                 {"_id": 0, "name": 1, "contentType": 1, "size": 1, "conversationId": 1, "createdAt": 1}):
        if d.get("conversationId") in private:
            continue
        kind = _file_kind(d.get("contentType"))
        rows.append({"type": "file", "label": kind, "name": d.get("name") or kind, "at": d.get("createdAt"),
                     "size": d.get("size")})
    rows.sort(key=lambda r: r.get("at") or "", reverse=True)
    return rows


async def person(db, user_id: str, days: int = 30):
    """One person's activity over the last `days` days. None when there is no such account."""
    days = clamp_days(days)
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        return None
    now = _now()
    since = (now - timedelta(days=days)).isoformat()
    day_list = _ist_days(days)
    day_index = {d: i for i, d in enumerate(day_list)}

    counts, first, last = Counter(), {}, {}
    daily = [{"day": d, "actions": 0, "visits": 0, "tokens": 0} for d in day_list]
    hours = [0] * 24
    timeline = []

    def note(kind: str, at: str, n: int = 1) -> None:
        counts[kind] += n
        first[kind] = min(first.get(kind) or at, at)
        last[kind] = max(last.get(kind) or at, at)
        i = day_index.get(_ist_day(at))
        if i is not None:
            daily[i]["actions"] += n
        t = _parse(at)
        if t:
            hours[t.astimezone(limits.IST).hour] += n

    async for e in db.usage_events.find({"userId": user_id, "at": {"$gte": since}}, {"_id": 0}).sort("at", -1):
        kinds = [k for k in e.get("kinds", []) if k in EVENT_KINDS]
        if not kinds:
            if "visit" in e.get("kinds", []):
                i = day_index.get(_ist_day(e["at"]))
                if i is not None:
                    daily[i]["visits"] += 1
            continue  # counsellor and plain visits are not listed one by one
        for k in kinds:
            note(k, e["at"])
        if len(timeline) < 80:
            timeline.append({"at": e["at"], "kinds": kinds, "labels": [LABELS[k] for k in kinds]})

    made_all = await _made(db, user_id)
    made = [m for m in made_all if (m.get("at") or "") >= since]
    for m in made:
        kind = {"app": "app", "doc": "doc", "upload": "upload"}.get(m["type"])
        if kind:
            note(kind, m["at"])
    async for r in db.automation_runs.find({"userId": user_id, "startedAt": {"$gte": since}},
                                           {"_id": 0, "startedAt": 1, "status": 1}):
        note("automation", r["startedAt"])

    tokens_total, tokens_by = 0, Counter()
    async for t in db.token_daily.find({"userId": user_id, "day": {"$in": day_list}}, {"_id": 0}):
        tokens_total += t.get("tokens", 0)
        tokens_by.update(t.get("byKind") or {})
        if t["day"] in day_index:
            daily[day_index[t["day"]]]["tokens"] = t.get("tokens", 0)
    meter = await db.usage.find_one({"_id": f"{user_id}:meter"}, {"_id": 0}) or {}
    fair = await db.usage.find_one({"_id": f"{user_id}:fair"}, {"_id": 0}) or {}
    plan = limits.plan_from(u)
    limit = limits.PLANS[plan]["meter"]

    logins = await db.logins.find({"userId": user_id}, {"_id": 0, "method": 1, "at": 1}).sort("at", -1).to_list(20)
    payments = await db.payments.find({"userId": user_id, "status": "paid"},
                                      {"_id": 0, "plan": 1, "amount": 1, "paidAt": 1, "promoCode": 1}
                                      ).sort("paidAt", -1).to_list(20)
    conversations = await db.conversations.count_documents(
        {"userId": user_id, "mode": {"$ne": "counsellor"}, "appId": None, "automationId": None})

    for m in made[:40]:
        timeline.append({"at": m["at"], "kinds": [m["type"]], "labels": ["Uploaded a file" if m["type"] == "upload" else f"Made {'an' if m['label'][0] in 'AEIOU' else 'a'} {m['label'] if m['type'] == 'file' else m['label'].lower()}"], "name": m["name"]})
    for x in logins:
        if (x.get("at") or "") >= since:
            timeline.append({"at": x["at"], "kinds": ["login"], "labels": ["Signed in"], "method": x.get("method")})
    timeline.sort(key=lambda r: r["at"] or "", reverse=True)

    active_days = sum(1 for d in daily if d["actions"] or d["visits"])
    return {
        "days": days, "since": since, "generatedAt": now.isoformat(),
        "user": {"id": u["id"], "name": u.get("name") or "", "email": u.get("email", ""), "plan": plan,
                 "planName": limits.PLANS[plan]["name"], "planExpiresAt": u.get("planExpiresAt"),
                 "createdAt": u.get("createdAt"), "lastSeenAt": u.get("lastSeenAt") or u.get("lastLoginAt"),
                 "lastLoginAt": u.get("lastLoginAt"), "loginCount": u.get("loginCount", 0),
                 "signIn": "Google" if u.get("googleId") else "Email", "language": u.get("language") or "en"},
        "summary": {"actions": sum(counts.values()), "activeDays": active_days,
                    "featuresUsed": sum(1 for k in LABELS if counts.get(k)), "made": len(made),
                    "madeEver": len(made_all), "chats": conversations, "tokens": tokens_total},
        "features": [{"kind": k, "label": label, "count": counts.get(k, 0), "first": first.get(k), "last": last.get(k)}
                     for k, label, _ in FEATURES],
        "daily": daily, "hours": hours,
        "usage": {"tokens": tokens_total, "tokensByKind": dict(tokens_by), "tokensToday": fair.get("tokens", 0)
                  if fair.get("day") == limits.today() else 0, "fairUseLimit": limits.fair_use_limit(plan),
                  "sessionUsed": round(meter.get("sessionUsed", 0), 1), "sessionLimit": limit["session"],
                  "weekUsed": round(meter.get("weekUsed", 0), 1), "weekLimit": limit["week"]},
        "payments": [{**p, "amount": p["amount"] / 100} for p in payments],
        "logins": logins[:10],
        "made": made_all[:60],
        "timeline": timeline[:100],
    }


async def overview(db, days: int = 30) -> dict:
    """Across everyone: the most used features, how many people use each, active people per day and the most
    active people. Counts only, never content."""
    days = clamp_days(days)
    since = (_now() - timedelta(days=days)).isoformat()
    day_list = _ist_days(days)
    day_index = {d: i for i, d in enumerate(day_list)}
    users = {u["id"]: u async for u in db.users.find({}, {"_id": 0, "id": 1, "name": 1, "email": 1, "plan": 1,
                                                          "planExpiresAt": 1, "createdAt": 1, "lastSeenAt": 1})}
    counts, people = Counter(), defaultdict(set)
    per_user = defaultdict(Counter)
    per_day = [set() for _ in day_list]
    actions_day = [0] * len(day_list)

    def note(uid: str, kind: str, at: str) -> None:
        counts[kind] += 1
        people[kind].add(uid)
        per_user[uid][kind] += 1
        i = day_index.get(_ist_day(at))
        if i is not None:
            actions_day[i] += 1

    async for e in db.usage_events.find({"at": {"$gte": since}}, {"_id": 0, "userId": 1, "kinds": 1, "at": 1}):
        i = day_index.get(_ist_day(e["at"]))
        if i is not None:
            per_day[i].add(e["userId"])
        for k in e.get("kinds", []):
            if k in EVENT_KINDS:
                note(e["userId"], k, e["at"])
    for name, kind in (("apps", "app"), ("docs", "doc")):
        async for d in db[name].find({"createdAt": {"$gte": since}}, {"_id": 0, "userId": 1, "createdAt": 1}):
            note(d["userId"], kind, d["createdAt"])
    async for d in db.files.find({"createdAt": {"$gte": since}, "is_deleted": {"$ne": True}}, {"_id": 0, "userId": 1, "createdAt": 1}):
        note(d["userId"], "upload", d["createdAt"])
    async for r in db.automation_runs.find({"startedAt": {"$gte": since}}, {"_id": 0, "userId": 1, "startedAt": 1}):
        note(r["userId"], "automation", r["startedAt"])
    # Days before the timed rows began still show from the daily activity marks.
    async for a in db.activity.find({"day": {"$in": day_list}}, {"_id": 0, "day": 1, "userId": 1}):
        per_day[day_index[a["day"]]].add(a["userId"])

    tokens = Counter()
    async for t in db.token_daily.find({"day": {"$in": day_list}}, {"_id": 0, "userId": 1, "tokens": 1}):
        tokens[t["userId"]] += t.get("tokens", 0)

    active = set().union(*per_day) if per_day else set()
    top = sorted(per_user.items(), key=lambda kv: sum(kv[1].values()), reverse=True)
    top_people = []
    for uid, c in top[:15]:
        u = users.get(uid)
        if not u:
            continue
        fav = c.most_common(1)[0][0] if c else None
        top_people.append({"userId": uid, "name": u.get("name") or "", "email": u.get("email", ""),
                           "plan": limits.plan_from(u), "actions": sum(c.values()), "tokens": tokens.get(uid, 0),
                           "favourite": LABELS.get(fav), "featuresUsed": len(c), "lastSeenAt": u.get("lastSeenAt")})
    n_active = len(active)
    return {
        "days": days, "since": since,
        "summary": {"activePeople": n_active, "totalPeople": len(users), "actions": sum(counts.values()),
                    "tokens": sum(tokens.values()),
                    "avgDaily": round(sum(len(s) for s in per_day) / len(per_day), 1) if per_day else 0,
                    "newPeople": sum(1 for u in users.values() if (u.get("createdAt") or "") >= since),
                    "quiet": sum(1 for u in users.values() if u["id"] not in active)},
        "features": sorted(({"kind": k, "label": label, "count": counts.get(k, 0), "people": len(people.get(k, ())),
                             "share": round(len(people.get(k, ())) / n_active * 100, 1) if n_active else 0}
                            for k, label, _ in FEATURES), key=lambda f: f["count"], reverse=True),
        "daily": [{"day": d, "active": len(per_day[i]), "actions": actions_day[i]} for i, d in enumerate(day_list)],
        "topPeople": top_people,
    }
