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
                                                          "lastLoginAt": 1, "loginCount": 1,
                                                          "googleId": 1, "language": 1})}

    def who(uid: str) -> dict:
        u = users.get(uid) or {}
        return {"userId": uid, "name": u.get("name") or "Deleted account", "email": u.get("email", ""),
                "plan": limits.plan_from(u) if u else "basic"}

    # Time buckets for the charts: hours for the last 24 hours, India-time days otherwise.
    if hourly:
        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        labels = [(start + timedelta(hours=h)).isoformat() for h in range(24)]

        def bucket(iso: str, back: bool = False):
            t = _parse(iso)
            if not t:
                return None
            i = int((t + timedelta(days=1 if back else 0) - start).total_seconds() // 3600)
            return i if 0 <= i < 24 else None
    else:
        labels = days
        index = {d: i for i, d in enumerate(days)}
        prev_index = {d: i for i, d in enumerate(prev_days)}

        def bucket(iso: str, back: bool = False):
            return (prev_index if back else index).get(_ist_day(iso))
    # Each bucket also carries the same bucket of the period before ("prev..."), for the comparison lines.
    series = [{"t": t, "active": 0, "logins": 0, "signups": 0, "revenue": 0.0, "messages": 0, "cost": 0.0,
               "prevActive": 0, "prevLogins": 0, "prevSignups": 0, "prevRevenue": 0.0, "prevMessages": 0}
              for t in labels]

    def add(iso: str, key: str, n=1) -> None:
        back = iso < since
        i = bucket(iso, back)
        if i is not None:
            k = "prev" + key[0].upper() + key[1:] if back else key
            series[i][k] += n

    # Payments: what sold, for how much, and who paid.
    paid = await db.payments.find({"status": "paid", "paidAt": {"$gte": prev_since}}, {"_id": 0}).to_list(None)
    now_paid = [p for p in paid if p["paidAt"] >= since]
    revenue = sum(p["amount"] for p in now_paid) / 100
    prev_revenue = sum(p["amount"] for p in paid if p["paidAt"] < since) / 100
    for p in paid:
        add(p["paidAt"], "revenue", p["amount"] / 100)
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
    for x in logins:
        add(x["at"], "logins")
    login_rows = [{**who(x["userId"]), "method": x["method"], "at": x["at"]}
                  for x in sorted(now_logins, key=lambda x: x["at"], reverse=True)]
    logged = {x["userId"] for x in now_logins}
    # People who signed in before sign-ins were logged one by one still show, from their account's last sign-in.
    login_rows += [{**who(u["id"]), "method": "", "at": u["lastLoginAt"]} for u in users.values()
                   if u.get("lastLoginAt", "") >= since and u["id"] not in logged]
    login_rows.sort(key=lambda r: r["at"], reverse=True)
    signups = [u for u in users.values() if u.get("createdAt", "") >= since]
    prev_signups = sum(1 for u in users.values() if prev_since <= u.get("createdAt", "") < since)
    for u in users.values():
        if u.get("createdAt", "") >= prev_since:
            add(u["createdAt"], "signups")

    # Active people and use.
    all_events = await db.usage_events.find({"at": {"$gte": prev_since}}, {"_id": 0}).to_list(None)
    events = [e for e in all_events if e["at"] >= since]
    per_user = defaultdict(Counter)
    bucket_people = defaultdict(set)
    heat = [[0] * 24 for _ in range(7)]  # India-time weekday (Monday first) x hour
    for e in all_events:
        kinds = [k for k in e.get("kinds", []) if k in FEATURE_LABELS]
        back = e["at"] < since
        if not back:
            per_user[e["userId"]].update(kinds)
            t = _parse(e["at"])
            if t and kinds:
                local = t.astimezone(limits.IST)
                heat[local.weekday()][local.hour] += 1
        if hourly:
            i = bucket(e["at"], back)
            if i is not None:
                bucket_people[(back, i)].add(e["userId"])
                series[i]["prevMessages" if back else "messages"] += sum(1 for k in kinds if k in MESSAGE_KINDS)
                if not back:
                    series[i]["cost"] += sum(costs[k] for k in kinds)
    if hourly:
        for (back, i), people in bucket_people.items():
            series[i]["prevActive" if back else "active"] = len(people)
    else:
        by_day = Counter()
        async for a in db.activity.find({"day": {"$in": days + prev_days}}, {"day": 1}):
            by_day[a["day"]] += 1
        async for d in db.feature_daily.find({"_id": {"$in": days + prev_days}}):
            msgs = sum(d.get(k, 0) for k in MESSAGE_KINDS)
            if d["_id"] in index:
                series[index[d["_id"]]]["messages"] = msgs
                series[index[d["_id"]]]["cost"] += sum(d.get(k, 0) * costs[k] for k in FEATURE_LABELS)
            elif d["_id"] in prev_index:
                series[prev_index[d["_id"]]]["prevMessages"] = msgs
        for i, d in enumerate(days):
            series[i]["active"] = by_day.get(d, 0)
            series[i]["prevActive"] = by_day.get(prev_days[i], 0)
    # Hosting spread evenly, and the payment fee where the money came in.
    hosting_per_bucket = costs["hostingMonthly"] * days_n / 30 / len(series)
    for row in series:
        row["cost"] = round(row["cost"] + hosting_per_bucket + row["revenue"] * costs["paymentFeePercent"] / 100, 2)
        row["revenue"], row["prevRevenue"] = round(row["revenue"], 2), round(row["prevRevenue"], 2)
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

    # Ratios an analyst would look at first.
    n_active = len(active)
    messages = sum(features.get(k, 0) for k in MESSAGE_KINDS)
    paying_active = sum(1 for uid in active if limits.plan_from(users.get(uid) or {}) != "basic")
    new_active = sum(1 for uid in active if users.get(uid, {}).get("createdAt", "") >= since)
    peak = max(range(len(series)), key=lambda i: series[i]["active"]) if any(r["active"] for r in series) else None
    ratios = {
        "arpu": round(revenue / n_active, 2) if n_active else 0,
        "costPerActive": round((money["aiCost"] + money["hostingCost"]) / n_active, 2) if n_active else 0,
        "messagesPerActive": round(messages / n_active, 1) if n_active else 0,
        "margin": round(money["profit"] / revenue * 100, 1) if revenue else None,
        "checkoutConversion": round(len(now_paid) / started * 100, 1) if started else None,
        "payingShare": round(paying_active / n_active * 100, 1) if n_active else 0,
        "newActive": new_active, "returningActive": n_active - new_active,
        "retained": len(active & prev_active), "retention": round(len(active & prev_active) / len(prev_active) * 100, 1)
        if prev_active else None,
        "peak": series[peak]["t"] if peak is not None else None,
        "peakActive": series[peak]["active"] if peak is not None else 0,
        "avgOrder": round(revenue / len(now_paid), 2) if now_paid else 0,
    }

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
        "money": money, "series": series, "ratios": ratios, "heat": heat,
        "plans": {"sold": sold, "subscribers": {p: subscribers.get(p, 0) for p in limits.ORDER},
                  "checkoutsStarted": started, "checkoutsPaid": len(now_paid), "recentPayments": recent_payments},
        "features": [{"kind": k, "label": v, "count": features.get(k, 0)} for k, v in FEATURE_LABELS.items()],
        "people": people[:100], "logins": login_rows[:100],
        "asks": await _asks(db, since, who),
        "costs": costs,
        **await _more(db, since, prev_since, now, users, who, signups),
    }


CONTENT = [  # what people made: (key, label, collection, extra filter)
    ("conversations", "Chats", "conversations", {}),
    ("projects", "Projects", "projects", {}),
    ("files", "Files uploaded", "files", {"is_deleted": {"$ne": True}}),
    ("apps", "Apps built", "apps", {}),
    ("published", "Apps published", "apps", {"published.slug": {"$type": "string"}}),
    ("decks", "Decks", "decks", {}),
    ("docs", "Docs", "docs", {}),
    ("automations", "Automations", "automations", {}),
    ("pages", "Answers shared", "pages", {}),
]


async def _more(db, since: str, prev_since: str, now: datetime, users: dict, who, signups: list) -> dict:
    """Everything else the owner may want: content made, answer ratings, errors, renewals, growth, engagement."""
    content = []
    for key, label, name, extra in CONTENT:
        col = db[name]
        content.append({"key": key, "label": label, "total": await col.count_documents(extra),
                        "period": await col.count_documents({**extra, "createdAt": {"$gte": since}}),
                        "prev": await col.count_documents({**extra, "createdAt": {"$gte": prev_since, "$lt": since}})})

    # Answer quality: 👍 / 👎.
    fb = await db.message_feedback.find({"createdAt": {"$gte": prev_since}}, {"_id": 0}).to_list(None)
    up = sum(1 for f in fb if f["createdAt"] >= since and f["rating"] == "up")
    down = sum(1 for f in fb if f["createdAt"] >= since and f["rating"] == "down")
    prev_up = sum(1 for f in fb if f["createdAt"] < since and f["rating"] == "up")
    prev_down = sum(1 for f in fb if f["createdAt"] < since and f["rating"] == "down")
    disliked = [{**who(f["userId"]), "question": _snippet(f.get("question", ""), 140),
                 "answer": _snippet(f.get("answer", ""), 180), "model": f.get("model"), "at": f["createdAt"]}
                for f in sorted((f for f in fb if f["createdAt"] >= since and f["rating"] == "down"),
                                key=lambda f: f["createdAt"], reverse=True)[:6]]

    # App health: crashes in the app and errors on the server.
    errors = await db.errors.find({"createdAt": {"$gte": prev_since}}, {"_id": 0, "detail": 0}).to_list(None)
    now_errors = [e for e in errors if e["createdAt"] >= since]
    by_source = Counter(e.get("source", "server") for e in now_errors)
    common = Counter(e.get("message", "")[:120] for e in now_errors).most_common(6)

    # Subscriptions: renewals due, plans that ran out, new vs returning customers.
    week = (now + timedelta(days=7)).isoformat()
    now_iso = now.isoformat()
    renewals_due = sorted(({**who(u["id"]), "expiresAt": u["planExpiresAt"]} for u in users.values()
                           if u.get("plan") in ("pro", "max") and u.get("planExpiresAt")
                           and now_iso <= u["planExpiresAt"] <= week), key=lambda r: r["expiresAt"])
    lapsed = sorted(({**who(u["id"]), "plan": u.get("plan"), "expiresAt": u["planExpiresAt"]} for u in users.values()
                     if u.get("plan") in ("pro", "max") and u.get("planExpiresAt")
                     and since <= u["planExpiresAt"] < now_iso), key=lambda r: r["expiresAt"], reverse=True)
    all_paid = await db.payments.find({"status": "paid"}, {"_id": 0, "userId": 1, "amount": 1, "paidAt": 1}).to_list(None)
    first_paid = {}
    for p in sorted(all_paid, key=lambda p: p["paidAt"]):
        first_paid.setdefault(p["userId"], p["paidAt"])
    period_paid = [p for p in all_paid if p["paidAt"] >= since]
    new_customers = len({p["userId"] for p in period_paid if first_paid[p["userId"]] >= since})
    returning_customers = len({p["userId"] for p in period_paid if first_paid[p["userId"]] < since})
    lifetime = sum(p["amount"] for p in all_paid) / 100

    # Growth: invites, offer codes, how people sign up, languages.
    refs = await db.referrals.find({"createdAt": {"$gte": since}}, {"_id": 0}).to_list(None)
    inviters = Counter(r["inviterId"] for r in refs)
    codes = await db.promo_codes.find({}, {"_id": 0}).sort("uses", -1).to_list(20)
    google_all = sum(1 for u in users.values() if u.get("googleId"))
    google_new = sum(1 for u in signups if u.get("googleId"))
    languages = Counter((u.get("language") or "en") for u in users.values())

    # Engagement: daily, weekly and monthly active people (India-time days).
    days30 = _ist_days(30)
    per_day = defaultdict(set)
    async for a in db.activity.find({"day": {"$in": days30}}, {"day": 1, "userId": 1}):
        per_day[a["day"]].add(a["userId"])
    dau = len(per_day.get(days30[-1], set()))
    wau = len(set().union(*(per_day.get(d, set()) for d in days30[-7:])))
    mau = len(set().union(*(per_day.get(d, set()) for d in days30)))
    avg_dau = round(sum(len(per_day.get(d, set())) for d in days30) / 30, 1)

    return {
        "content": content,
        "quality": {"up": up, "down": down, "prevUp": prev_up, "prevDown": prev_down,
                    "satisfaction": round(up / (up + down) * 100, 1) if up + down else None, "disliked": disliked},
        "health": {"total": len(now_errors), "prev": len(errors) - len(now_errors),
                   "app": by_source.get("app", 0), "server": by_source.get("server", 0),
                   "common": [{"message": m, "count": c} for m, c in common],
                   "latest": sorted(now_errors, key=lambda e: e["createdAt"], reverse=True)[:8]},
        "subscriptions": {"renewalsDue": renewals_due[:20], "renewalsDueCount": len(renewals_due),
                          "renewalsDueValue": sum(limits.PLANS[r["plan"]]["price"] for r in renewals_due),
                          "lapsed": lapsed[:20], "lapsedCount": len(lapsed),
                          "newCustomers": new_customers, "returningCustomers": returning_customers,
                          "customersEver": len(first_paid), "lifetimeRevenue": lifetime,
                          "ltv": round(lifetime / len(first_paid), 2) if first_paid else 0},
        "growth": {"invited": len(refs), "invitedRewarded": sum(1 for r in refs if r.get("rewarded")),
                   "topInviters": [{**who(uid), "count": c} for uid, c in inviters.most_common(5)],
                   "codes": [{"code": c["code"], "percentOff": c["percentOff"], "uses": c.get("uses", 0),
                              "maxUses": c.get("maxUses", 0), "active": c.get("active", True)} for c in codes],
                   "signupMethods": {"google": google_new, "email": len(signups) - google_new},
                   "accountMethods": {"google": google_all, "email": len(users) - google_all},
                   "languages": [{"code": code, "count": c} for code, c in languages.most_common(8)]},
        "engagement": {"dau": dau, "wau": wau, "mau": mau, "avgDau": avg_dau,
                       "stickiness": round(dau / mau * 100, 1) if mau else None,
                       "signinsPerPerson": round(sum(u.get("loginCount", 0) for u in users.values()) / len(users), 1)
                       if users else 0},
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
