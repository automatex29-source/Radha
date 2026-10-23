"""How Krish works differently on each plan (limits.work_of): which questions get a premium model, how much web
search and Deep Research read, App Builder steps, picture resolution and how often automations may repeat.
MongoDB is mongomock."""
import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    env = dict(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0", AI_MODEL="openai/gpt-oss-120b")
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        yield c
    for k, v in saved.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _user(client, email, plan="basic"):
    import server
    r = client.post("/api/auth/register", json={"name": "Asha", "email": email, "password": "secret1"})
    assert r.status_code == 200, r.text
    uid = r.json()["user"]["id"]

    async def set_plan():
        await server.db.users.update_one({"id": uid}, {"$set": {"plan": plan}})
    client.portal.call(set_plan)
    return uid, {"Authorization": f"Bearer {r.json()['token']}"}


def test_each_plan_works_better_than_the_one_below():
    import limits
    basic, pro, top = (limits.work_of(p) for p in limits.ORDER)
    for key in ("searches", "results", "builderSteps", "repairRounds", "automationMinutes"):
        if key == "automationMinutes":
            assert basic[key] > pro[key] > top[key]
        else:
            assert basic[key] < pro[key] < top[key]
    assert (basic["model"], pro["model"], top["model"]) == ("free", "hard", "all")
    assert top["research"] > pro["research"] and top["pictureSize"] == "4K" and top["priority"]


def test_premium_model_by_plan(client, monkeypatch):
    import server
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("BUILDER_MODEL", raising=False)
    basic, _ = _user(client, "work-basic@test.com")
    pro, _ = _user(client, "work-pro@test.com", "pro")
    top, _ = _user(client, "work-max@test.com", "max")
    hard = "Explain step by step why quicksort is O(n log n) on average and prove it"
    pick = lambda uid, text, conv=None: client.portal.call(server._pick_model, uid, conv or {}, server.AUTO_MODEL,
                                                           False, text)
    assert pick(basic, hard) == server.AUTO_MODEL  # Basic stays on Krish Basic
    assert pick(pro, "hi there") == server.AUTO_MODEL  # Pro: a quick hello stays free
    assert pick(pro, hard) == "claude-sonnet-5-5"  # Pro: a hard question gets the premium model
    assert pick(pro, "make it blue", {"appId": "a1"}) == "claude-sonnet-5-5"  # Pro: app builds on premium
    assert pick(top, "hi there") == "claude-sonnet-5-5"  # Max: every answer


def test_web_search_reads_more_on_bigger_plans(monkeypatch):
    from agent import tools, web
    asked = []

    async def search(query, n):
        asked.append(n)
        return [{"title": "t", "url": "https://x.test", "snippet": "s"}]
    monkeypatch.setattr(web, "search", search)
    for results in (6, 10):
        ctx = tools.ToolContext(db=None, user_id="u", sources=[], searches_left=3, search_results=results)
        asyncio.run(tools._web_search(ctx, {"query": "news"}))
    assert asked == [6, 10]


def test_deep_research_goes_twice_as_deep_on_max():
    from agent import research
    normal, deep = research.limits("claude-sonnet-5-5"), research.limits("claude-sonnet-5-5", 2)
    assert deep["queries"] == normal["queries"] * 2 and deep["sources"] == normal["sources"] * 2
    assert deep["report_tokens"] > normal["report_tokens"]
    many = '["a one", "b two", "c three", "d four", "e five", "f six", "g seven", "h eight"]'
    assert len(research.parse_queries(many, "q", deep["queries"])) == 8
    assert len(research.parse_queries(many, "q")) == research.MAX_QUERIES


def test_max_pictures_are_4k_and_cost_more(client, monkeypatch):
    import limits
    import media
    import server
    from agent import prompt_boost, tools
    top, _ = _user(client, "pic-max@test.com", "max")
    pro, _ = _user(client, "pic-pro@test.com", "pro")
    seen = []

    async def make(prompt, size, quality=None):
        seen.append(media.PICTURE_SIZE.get())
        return b"\x89PNG\r\n\x1a\n" + b"0" * 100

    async def same(prompt, style):
        return prompt
    monkeypatch.setattr(media, "generate_image", make)
    monkeypatch.setattr(prompt_boost, "image_prompt", same)
    for uid in (pro, top):
        client.portal.call(tools._generate_image, tools.ToolContext(db=server.db, user_id=uid), {"prompt": "a fox"})
    assert seen == ["2K", "4K"] and media.PICTURE_SIZE.get() == ""
    assert limits.cost("picture", 1, "max") == 2 * limits.cost("picture", 1, "pro")


def test_automations_repeat_as_often_as_the_plan_allows(client):
    _, basic = _user(client, "auto-basic@test.com")
    _, top = _user(client, "auto-max@test.com", "max")
    body = {"name": "Prices", "prompt": "Check prices", "schedule": {"type": "interval", "minutes": 15}}
    r = client.post("/api/automations", headers=basic, json=body)
    assert r.status_code == 402 and "once every day" in r.json()["detail"] and "15 minutes" in r.json()["detail"]
    assert client.post("/api/automations", headers=basic,
                       json={**body, "schedule": {"type": "interval", "minutes": 1440}}).status_code == 200
    assert client.post("/api/automations", headers=top, json=body).status_code == 200


def test_paid_plans_get_crafted_answers(monkeypatch):
    from tests.test_builder_models import _server
    server = _server()
    seen = {}

    async def fake_gather(*a, **k):
        return {"context": None, "sources": [], "queries": []}

    async def fake_stream(req):
        seen["system"], seen["long"] = req.system, req.long_answer
        yield "An answer."
    monkeypatch.setattr(server.live_search, "gather", fake_gather)
    monkeypatch.setattr(server.model_router, "stream", fake_stream)

    def answer(plan):
        db = mongomock_motor.AsyncMongoMockClient()["t"]
        monkeypatch.setattr(server, "db", db)

        async def go():
            await db.users.insert_one({"id": "u1", "plan": plan})
            await db.conversations.insert_one({"id": "c1", "userId": "u1"})
            await db.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                          "content": "how do I start a small bakery", "createdAt": "1"})
            [c async for c in server.run_turn("c1", "openai/gpt-oss-120b")]
        asyncio.run(go())
        return server.PREMIUM_ANSWER_PROMPT in seen["system"], seen["long"]
    assert answer("basic") == (False, False)
    assert answer("pro") == (True, True)
