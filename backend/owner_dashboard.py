"""The owner dashboard: sign-ins, active people, plans sold, revenue and profit, use per person and what people ask.

Everything is worked out from what the app already saves: accounts, payments (Razorpay), the daily activity and
feature counts (monitor.py), and from this update on a timed row per sign-in (`logins`) and per request
(`usage_events`), so the last 24 hours can be shown hour by hour.

Profit is an estimate: revenue minus the payment fee, the hosting bill and a cost for each AI request. The
owner sets those costs on the dashboard (kept in `settings`, id "owner_costs").

What people ask: the questions are grouped into topics, and the latest ones are shown cut short, with emails and
phone numbers hidden. Counsellor chats are private and never shown or counted here.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import limits

RANGES = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}
ONLINE_MINUTES = 10

FEATURE_LABELS = {
    "chat": "Chat", "counsellor": "Counsellor", "web": "Web search", "voice": "Voice", "think": "Think",
    "build": "App builds", "picture": "Pictures", "deck": "Decks", "video": "Videos",
}
MESSAGE_KINDS = ("chat", "counsellor", "build")

# Rough costs in rupees, until the owner types in their own.
DEFAULT_COSTS = {
    "hostingMonthly": 600.0,   # Render web service + database, per month
    "paymentFeePercent": 2.36,  # Razorpay's 2% + 18% GST
    "chat": 0.05, "counsellor": 0.05, "web": 0.20, "voice": 0.30, "think": 0.20,
    "build": 1.50, "picture": 2.00, "deck": 1.00, "video": 6.00,
}

TOPICS = [
    ("Coding & apps", r"code|coding|python|javascript|java\b|html|css|react|\bapi\b|bug|error|website|\bapp\b|app\s|"
                      r"function|program|sql|database|build"),
    ("Study & exams", r"exam|study|homework|explain|math|physics|chemistry|biology|history|geography|notes|upsc|neet|"
                      r"\bjee\b|class \d|chapter|syllabus|formula|solve|definition"),
    ("Business & money", r"business|marketing|sales|startup|money|invest|stock|share market|price|profit|\bgst\b|tax|"
                         r"loan|customer|brand"),
    ("Writing & content", r"write|essay|letter|email|caption|story|poem|blog|resume|\bcv\b|script|article|translate"),
    ("Pictures & media", r"image|picture|photo|logo|video|draw|design|poster|thumbnail|slide|deck|presentation"),
    ("Spiritual", r"krishna|krishn|gita|geeta|god\b|bhagwan|mantra|puja|pooja|radha|spiritual|karma|dharma|shiv|ram\b"),
    ("Health & fitness", r"health|diet|exercise|doctor|medicine|pain|weight|sleep|yoga|fever|gym|skin|hair"),
    ("Career & jobs", r"\bjob|career|interview|salary|internship|hiring|linkedin"),
    ("News & facts", r"news|today|latest|weather|score|match|election|who is|who was"),
]
_TOPIC_RES = [(name, re.compile(pattern, re.I)) for name, pattern in TOPICS]

STOPWORDS = set("""
the and for are but not you your yours with this that these those have has had was were will would could should can
from into about what when where which while who whom whose why how than then them they their there here also just only
very much more most some such each other any all both few many like make made give tell show please want need know
does did doing done been being its it's i'm im me my mine our ours we us he she his her him hers itself use using used
write explain help kya hai hain kaise mujhe mera meri mere aur bhi koi kuch karo karna batao bata liye wala wali
krish hello thanks thank okay read cannot undefined properties something thing things yes no ok hi hey one two get got let let's out over under again same new
""".split())

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_NUMBER = re.compile(r"\+?\d[\d\s-]{6,}\d")
_WORD = re.compile(r"[a-zA-Zऀ-ॿ]{4,}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: str):
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _ist_days(days: int) -> list:
    """The last `days` India-time days, oldest first (today last)."""
    today = datetime.now(limits.IST).date()
    return [(today - timedelta(days=back)).isoformat() for back in range(days - 1, -1, -1)]


def _ist_day(iso: str) -> str:
    t = _parse(iso)
    return t.astimezone(limits.IST).date().isoformat() if t else ""


def _hide_private(text: str) -> str:
    return _LONG_NUMBER.sub("[number]", _EMAIL.sub("[email]", text))


def _snippet(text: str, n: int = 160) -> str:
    text = " ".join(_hide_private(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def topic_of(text: str) -> str:
    for name, pattern in _TOPIC_RES:
        if pattern.search(text or ""):
            return name
    return "Other"


def _change(value: float, prev: float) -> dict:
    return {"value": round(value, 2), "prev": round(prev, 2)}


async def get_costs(db) -> dict:
    doc = await db.settings.find_one({"id": "owner_costs"}) or {}
    return {k: float(doc.get(k, v)) for k, v in DEFAULT_COSTS.items()}


async def set_costs(db, values: dict) -> dict:
    clean = {k: max(0.0, min(float(v), 10_000_000.0)) for k, v in values.items() if k in DEFAULT_COSTS}
    await db.settings.update_one({"id": "owner_costs"}, {"$set": clean}, upsert=True)
    return await get_costs(db)


async def _feature_counts(db, days: list, since: str, until: str, hourly: bool) -> Counter:
    counts = Counter()
    if hourly:
        async for e in db.usage_events.find({"at": {"$gte": since, "$lt": until}}, {"kinds": 1}):
            counts.update(k for k in e.get("kinds", []) if k in FEATURE_LABELS)
    else:
        async for d in db.feature_daily.find({"_id": {"$in": days}}):
            counts.update({k: d.get(k, 0) for k in FEATURE_LABELS})
    return counts


async def _active_ids(db, days: list, since: str, until: str, hourly: bool) -> set:
    if hourly:
        ids = {e["userId"] async for e in db.usage_events.find({"at": {"$gte": since, "$lt": until}}, {"userId": 1})}
        ids |= {u["id"] async for u in db.users.find({"lastSeenAt": {"$gte": since, "$lt": until}}, {"id": 1})}
        return ids
    return {a["userId"] async for a in db.activity.find({"day": {"$in": days}}, {"userId": 1})}


def _money(features: Counter, revenue: float, costs: dict, span_days: float) -> dict:
    ai = [{"kind": k, "label": FEATURE_LABELS[k], "count": features.get(k, 0),
           "cost": round(features.get(k, 0) * costs[k], 2)} for k in FEATURE_LABELS]
    ai_cost = sum(r["cost"] for r in ai)
    hosting = costs["hostingMonthly"] * span_days / 30
    fees = revenue * costs["paymentFeePercent"] / 100
    return {"revenue": round(revenue, 2), "aiCost": round(ai_cost, 2), "hostingCost": round(hosting, 2),
            "paymentFees": round(fees, 2), "profit": round(revenue - ai_cost - hosting - fees, 2), "aiBreakdown": ai}


async def overview(db, range_key: str = "24h") -> dict:
    days_n = RANGES.get(range_key, 1)
    hourly = days_n == 1
    now = _now()
    since_t = now - timedelta(days=days_n)
    since, until, prev_since = since_t.isoformat(), now.isoformat(), (since_t - timedelta(days=days_n)).isoformat()
    days = _ist_days(days_n)
    prev_days = _ist_days(days_n * 2)[:days_n]
    costs = await get_costs(db)

    users = {u["id"]: u async for u in db.users.find({}, {"_id": 0, "id": 1, "name": 1, "email": 1, "plan": 1,
                                                          "planExpiresAt": 1, "createdAt": 1, "lastSeenAt": 1,
                                                          "lastLoginAt": 1, "loginCount": 1})}

    def who(uid: str) -> dict:
        u = users.get(uid) or {}
        return {"userId": uid, "name": u.get("name") or "Deleted account", "email": u.get("email", ""),
                "plan": limits.plan_from(u) if u else "basic"}

    # Time buckets for the charts: hours for the last 24 hours, India-time days otherwise.
    if hourly:
        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        labels = [(start + timedelta(hours=h)).isoformat() for h in range(24)]

        def bucket(iso: str):
            t = _parse(iso)
            if not t:
                return None
            i = int((t - start).total_seconds() // 3600)
            return i if 0 <= i < 24 else None
    else:
        labels = days
        index = {d: i for i, d in enumerate(days)}

        def bucket(iso: str):
            return index.get(_ist_day(iso))
    series = [{"t": t, "active": 0, "logins": 0, "signups": 0, "revenue": 0.0, "messages": 0} for t in labels]

    # Payments: what sold, for how much, and who paid.
    paid = await db.payments.find({"status": "paid", "paidAt": {"$gte": prev_since}}, {"_id": 0}).to_list(None)
    now_paid = [p for p in paid if p["paidAt"] >= since]
    revenue = sum(p["amount"] for p in now_paid) / 100
    prev_revenue = sum(p["amount"] for p in paid if p["paidAt"] < since) / 100
    for p in now_paid:
        i = bucket(p["paidAt"])
        if i is not None:
            series[i]["revenue"] += p["amount"] / 100
    started = await db.payments.count_documents({"createdAt": {"$gte": since}})
    sold = []
    for plan in limits.ORDER[1:]:
        rows = [p for p in now_paid if p["plan"] == plan]
        sold.append({"plan": plan, "name": limits.PLANS[plan]["name"], "price": limits.PLANS[plan]["price"],
                     "count": len(rows), "revenue": sum(p["amount"] for p in rows) / 100})
    subscribers = Counter(limits.plan_from(u) for u in users.values())
    mrr = sum(subscribers.get(p, 0) * limits.PLANS[p]["price"] for p in limits.ORDER[1:])
    paid_by_user = defaultdict(float)
    for p in now_paid:
        paid_by_user[p["userId"]] += p["amount"] / 100
    recent_payments = [{**who(p["userId"]), "plan": p["plan"], "amount": p["amount"] / 100,
                        "promoCode": p.get("promoCode"), "at": p["paidAt"]}
                       for p in sorted(now_paid, key=lambda p: p["paidAt"], reverse=True)[:20]]

    # Sign-ins and sign-ups.
    logins = await db.logins.find({"at": {"$gte": prev_since}}, {"_id": 0}).to_list(None)
    now_logins = [x for x in logins if x["at"] >= since]
    for x in now_logins:
        i = bucket(x["at"])
        if i is not None:
            series[i]["logins"] += 1
    login_rows = [{**who(x["userId"]), "method": x["method"], "at": x["at"]}
                  for x in sorted(now_logins, key=lambda x: x["at"], reverse=True)]
    logged = {x["userId"] for x in now_logins}
    # People who signed in before sign-ins were logged one by one still show, from their account's last sign-in.
    login_rows += [{**who(u["id"]), "method": "", "at": u["lastLoginAt"]} for u in users.values()
                   if u.get("lastLoginAt", "") >= since and u["id"] not in logged]
    login_rows.sort(key=lambda r: r["at"], reverse=True)
    signups = [u for u in users.values() if u.get("createdAt", "") >= since]
    prev_signups = sum(1 for u in users.values() if prev_since <= u.get("createdAt", "") < since)
    for u in signups:
        i = bucket(u["createdAt"])
        if i is not None:
            series[i]["signups"] += 1

    # Active people and use.
    events = await db.usage_events.find({"at": {"$gte": since}}, {"_id": 0}).to_list(None)
    per_user = defaultdict(Counter)
    hour_people = defaultdict(set)
    for e in events:
        kinds = [k for k in e.get("kinds", []) if k in FEATURE_LABELS]
        per_user[e["userId"]].update(kinds)
        per_user[e["userId"]]["_requests"] += 1 if kinds else 0
        i = bucket(e["at"])
        if i is not None:
            hour_people[i].add(e["userId"])
            if hourly:
                series[i]["messages"] += sum(1 for k in kinds if k in MESSAGE_KINDS)
    if hourly:
        for i, people in hour_people.items():
            series[i]["active"] = len(people)
    else:
        by_day = Counter()
        async for a in db.activity.find({"day": {"$in": days}}, {"day": 1}):
            by_day[a["day"]] += 1
        async for d in db.feature_daily.find({"_id": {"$in": days}}):
            series[index[d["_id"]]]["messages"] = sum(d.get(k, 0) for k in MESSAGE_KINDS)
        for i, d in enumerate(days):
            series[i]["active"] = by_day.get(d, 0)
    active = await _active_ids(db, days, since, until, hourly)
    prev_active = await _active_ids(db, prev_days, prev_since, since, hourly)
    online_cut = (now - timedelta(minutes=ONLINE_MINUTES)).isoformat()
    online = {u["id"] for u in users.values() if u.get("lastSeenAt", "") >= online_cut}
    online |= {e["userId"] for e in events if e["at"] >= online_cut}

    features = await _feature_counts(db, days, since, until, hourly)
    prev_features = await _feature_counts(db, prev_days, prev_since, since, hourly)
    money = _money(features, revenue, costs, days_n)
    prev_money = _money(prev_features, prev_revenue, costs, days_n)

    people = []
    for uid in set(per_user) | active | set(paid_by_user):
        if uid not in users:
            continue
        c = per_user.get(uid, Counter())
        people.append({
            **who(uid), "lastSeenAt": users[uid].get("lastSeenAt"), "online": uid in online,
            "messages": sum(c.get(k, 0) for k in MESSAGE_KINDS),
            "made": c.get("picture", 0) + c.get("deck", 0) + c.get("video", 0),
            "builds": c.get("build", 0), "web": c.get("web", 0) + c.get("think", 0) + c.get("voice", 0),
            "cost": round(sum(c.get(k, 0) * costs[k] for k in FEATURE_LABELS), 2),
            "paid": round(paid_by_user.get(uid, 0.0), 2),
        })
    people.sort(key=lambda p: (p["messages"] + p["made"] + p["builds"], p["paid"], p["lastSeenAt"] or ""),
                reverse=True)

    return {
        "range": range_key, "since": since, "generatedAt": until, "bucket": "hour" if hourly else "day",
        "kpis": {
            "revenue": _change(revenue, prev_revenue),
            "profit": _change(money["profit"], prev_money["profit"]),
            "activeUsers": _change(len(active), len(prev_active)),
            "signups": _change(len(signups), prev_signups),
            "logins": _change(len(now_logins), sum(1 for x in logins if x["at"] < since)),
            "messages": _change(sum(features.get(k, 0) for k in MESSAGE_KINDS),
                                sum(prev_features.get(k, 0) for k in MESSAGE_KINDS)),
            "onlineNow": len(online), "totalUsers": len(users),
            "paidUsers": subscribers.get("pro", 0) + subscribers.get("max", 0), "mrr": mrr,
        },
        "money": money, "series": series,
        "plans": {"sold": sold, "subscribers": {p: subscribers.get(p, 0) for p in limits.ORDER},
                  "checkoutsStarted": started, "checkoutsPaid": len(now_paid), "recentPayments": recent_payments},
        "features": [{"kind": k, "label": v, "count": features.get(k, 0)} for k, v in FEATURE_LABELS.items()],
        "people": people[:100], "logins": login_rows[:100],
        "asks": await _asks(db, since, who),
        "costs": costs,
    }


async def _asks(db, since: str, who) -> dict:
    """What people asked: topics, common words and the latest questions (never counsellor chats)."""
    msgs = await db.messages.find({"role": "user", "createdAt": {"$gte": since}},
                                  {"_id": 0, "conversationId": 1, "content": 1, "createdAt": 1}
                                  ).sort("createdAt", -1).to_list(3000)
    conv_ids = list({m["conversationId"] for m in msgs})
    convs = {c["id"]: c async for c in db.conversations.find({"id": {"$in": conv_ids}},
                                                             {"_id": 0, "id": 1, "userId": 1, "mode": 1, "appId": 1})}
    topics, words, recent, total = Counter(), Counter(), [], 0
    for m in msgs:
        conv = convs.get(m["conversationId"])
        if not conv or conv.get("mode") == "counsellor" or not isinstance(m.get("content"), str):
            continue
        text = m["content"]
        total += 1
        topic = "Coding & apps" if conv.get("appId") else topic_of(text)
        topics[topic] += 1
        words.update(w for w in (x.lower() for x in _WORD.findall(_hide_private(text)[:2000])) if w not in STOPWORDS)
        if len(recent) < 40:
            recent.append({**who(conv["userId"]), "text": _snippet(text), "topic": topic, "at": m["createdAt"],
                           "where": "App Builder" if conv.get("appId") else "Chat"})
    return {"total": total, "topics": [{"name": n, "count": c} for n, c in topics.most_common()],
            "words": [{"word": w, "count": c} for w, c in words.most_common(18) if c > 1],
            "recent": recent}
