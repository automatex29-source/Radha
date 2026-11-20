"""What people ask Krish, for the owner's Questions page: topics, trending words, questions per day and the
questions themselves.

Each question shows who asked it (name, email and plan), as the owner chose; the privacy policy says the team
can read questions with the account they came from. Emails and phone numbers inside a question are still hidden. Counsellor chats are private and never read here. Automation tasks
are left out too (they are instructions, repeated on a schedule, not questions).
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

import limits
from owner_dashboard import STOPWORDS, _WORD, _hide_private, _ist_day, _ist_days, topic_of

RANGES = (1, 7, 30, 90)
PAGE = 50
MAX_SCAN = 5000
SHOW = 500  # characters of each question shown


def _clip(text: str, n: int = SHOW) -> str:
    text = " ".join(_hide_private(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


async def overview(db, days: int = 7, topic: str = "", q: str = "", page: int = 0, user: str = "") -> dict:
    days = days if days in RANGES else 7
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    day_list = _ist_days(days)
    index = {d: i for i, d in enumerate(day_list)}
    find = {"role": "user", "createdAt": {"$gte": since}}
    if user:  # one person's questions: only their conversations
        find["conversationId"] = {"$in": [c["id"] async for c in db.conversations.find({"userId": user}, {"id": 1})]}
    msgs = await db.messages.find(find,
                                  {"_id": 0, "conversationId": 1, "content": 1, "createdAt": 1}
                                  ).sort("createdAt", -1).to_list(MAX_SCAN)
    conv_ids = list({m["conversationId"] for m in msgs})
    convs = {c["id"]: c async for c in db.conversations.find(
        {"id": {"$in": conv_ids}}, {"_id": 0, "id": 1, "userId": 1, "mode": 1, "appId": 1, "automationId": 1})}
    people = {u["id"]: u async for u in db.users.find(
        {"id": {"$in": list({c["userId"] for c in convs.values()})}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "plan": 1,
                                                                        "planExpiresAt": 1})}
    topics, words, where = Counter(), Counter(), Counter()
    per_day = [0] * len(day_list)
    rows = []
    term = (q or "").strip().lower()
    for m in msgs:
        conv = convs.get(m["conversationId"])
        text = m.get("content")
        if not conv or conv.get("mode") == "counsellor" or conv.get("automationId") or not isinstance(text, str):
            continue
        if not text.strip():
            continue
        place = "App Builder" if conv.get("appId") else "Chat"
        t = "Coding & apps" if conv.get("appId") else topic_of(text)
        topics[t] += 1
        where[place] += 1
        i = index.get(_ist_day(m["createdAt"]))
        if i is not None:
            per_day[i] += 1
        words.update(w for w in (x.lower() for x in _WORD.findall(_hide_private(text)[:2000])) if w not in STOPWORDS)
        u = people.get(conv["userId"]) or {}
        if (not topic or t == topic) and (not term or term in text.lower()
                                          or term in f"{u.get('name', '')} {u.get('email', '')}".lower()):
            rows.append({"text": _clip(text), "topic": t, "where": place, "at": m["createdAt"],
                         "userId": conv["userId"], "name": u.get("name") or "Deleted account", "email": u.get("email", ""),
                         "plan": limits.plan_from(u) if u else "basic",
                         "long": len(text) > SHOW})
    total = sum(topics.values())
    page = max(0, int(page or 0))
    person = people.get(user) if user else None
    return {
        "user": {"id": user, "name": person.get("name", ""), "email": person.get("email", "")} if person else None,
        "days": days, "since": since, "total": total, "matching": len(rows), "capped": len(msgs) >= MAX_SCAN,
        "topics": [{"name": n, "count": c, "share": round(c / total * 100, 1) if total else 0}
                   for n, c in topics.most_common()],
        "words": [{"word": w, "count": c} for w, c in words.most_common(30) if c > 1],
        "where": [{"name": n, "count": c} for n, c in where.most_common()],
        "daily": [{"day": d, "count": per_day[i]} for i, d in enumerate(day_list)],
        "questions": rows[page * PAGE:(page + 1) * PAGE], "page": page, "pages": max(1, -(-len(rows) // PAGE)),
    }
