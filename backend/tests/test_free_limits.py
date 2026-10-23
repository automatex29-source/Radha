"""Offline tests for the plan limits (MongoDB is mongomock)."""
import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")

mongomock_motor = pytest.importorskip("mongomock_motor")

from fastapi import HTTPException  # noqa: E402

import limits  # noqa: E402
from agent import tools  # noqa: E402


@pytest.fixture
def db(monkeypatch):
    monkeypatch.delenv("FREE_LIMITS", raising=False)
    return mongomock_motor.AsyncMongoMockClient()["t"]


def run(coro):
    return asyncio.run(coro)


def _used(db, uid):
    async def get():
        return (await limits.summary(db, uid))["meter"]
    return get()


def test_requests_use_credits_by_their_size_and_chat_is_never_counted(db):
    async def scenario():
        assert limits.cost("build", 100) < limits.cost("build", 5000)  # a bigger ask uses more
        assert limits.cost("build", 10**6) == 20  # but never more than this
        assert limits.cost("video", 8, "basic") < limits.cost("video", 8, "pro")  # the premium engine costs more
        await limits.use(db, "u", "build", 1000)
        await limits.use(db, "u", "picture")
        meter = await _used(db, "u")
        assert meter["session"]["used"] == limits.cost("build", 1000) + limits.cost("picture") == meter["week"]["used"]
        assert meter["session"]["limit"] == 40 and meter["session"]["resetsAt"] > time.time()
        await limits.use(db, "someone-else", "build")  # each user has their own meter
        assert (await _used(db, "u"))["session"]["used"] == 6
        summary = await limits.summary(db, "u")
        assert "chat" not in summary["usage"] and summary["costs"]["picture"] == 2

    run(scenario())


def test_an_empty_meter_says_when_it_refills_and_refills_after_the_session(db, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(limits.time, "time", lambda: now[0])

    async def scenario():
        for _ in range(20):
            await limits.use(db, "u", "picture")  # 20 x 2 = Basic's 40 for a session
        with pytest.raises(HTTPException) as err:
            await limits.require(db, "u", "picture")
        assert err.value.status_code == 402 and "this session's usage" in err.value.detail
        assert "(in 5h 0m)" in err.value.detail and "Upgrade to Pro" in err.value.detail
        now[0] += limits.SESSION_HOURS * 3600
        await limits.use(db, "u", "picture")  # a new session
        meter = await _used(db, "u")
        assert meter["session"]["used"] == 2 and meter["week"]["used"] == 42

    run(scenario())


def test_the_week_meter_caps_many_sessions(db, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(limits.time, "time", lambda: now[0])
    monkeypatch.setitem(limits.PLANS["basic"], "meter", {"session": 40, "week": 60})

    async def scenario():
        for _ in range(20):
            await limits.use(db, "u", "picture")
        now[0] += limits.SESSION_HOURS * 3600
        for _ in range(10):
            await limits.use(db, "u", "picture")
        with pytest.raises(limits.LimitReached, match="this week's usage"):
            await limits.use(db, "u", "picture")
        now[0] += limits.WEEK_DAYS * 86400
        await limits.use(db, "u", "picture")

    run(scenario())


def test_a_big_request_says_a_smaller_one_still_fits(db):
    async def scenario():
        await limits.use(db, "u", "build", 10**6)  # 20
        await limits.use(db, "u", "build", 5000)  # 12
        with pytest.raises(limits.LimitReached, match="needs 20 credits and you have 8 left"):
            await limits.use(db, "u", "build", 10**6)
        await limits.use(db, "u", "build", 0)  # a small one still fits

    run(scenario())


def test_refund_gives_credits_back(db):
    async def scenario():
        await limits.use(db, "u", "video", 8)
        await limits.refund(db, "u", "video", 8)
        meter = await _used(db, "u")
        assert meter["session"]["used"] == 0 and meter["week"]["used"] == 0

    run(scenario())


def test_decks_peek_and_automations_are_a_total(db):
    async def scenario():
        for _ in range(8):
            await limits.require(db, "u", "deck", peek=True)  # writing an outline doesn't use anything
            await limits.use(db, "u", "deck")
        with pytest.raises(HTTPException) as err:
            await limits.require(db, "u", "deck", peek=True)
        assert "usage" in err.value.detail
        assert (await _used(db, "u"))["session"]["used"] == 40

        await limits.check_total(db, "u", "automation")
        await db.automations.insert_one({"id": "a1", "userId": "u"})
        with pytest.raises(limits.LimitReached):
            await limits.check_total(db, "u", "automation")
        await db.automations.delete_one({"id": "a1"})
        await limits.check_total(db, "u", "automation")  # deleting one frees a slot

    run(scenario())


def test_three_plans_and_prices():
    assert [(p["id"], p["price"]) for p in limits.public_plans()] == [("basic", 0), ("pro", 299), ("max", 699)]
    for part in ("session", "week"):
        basic, pro, top = (limits.PLANS[p]["meter"][part] for p in limits.ORDER)
        assert basic < pro < top


def test_paid_plans_get_more_and_switch_off_has_no_limits(db, monkeypatch):
    async def scenario():
        await db.users.insert_many([{"id": "pro", "plan": "pro"}, {"id": "max", "plan": "max"}])
        for _ in range(20):
            await limits.use(db, "pro", "build", 10**6)  # 20 x 20 = Pro's 400
        with pytest.raises(limits.LimitReached, match="Upgrade to Max"):
            await limits.use(db, "pro", "build")
        for _ in range(21):
            await limits.use(db, "max", "build", 10**6)
        assert await limits.is_pro(db, "max") and not await limits.is_pro(db, "u")
        assert await limits.use_premium(db, "max", 5000)
        assert not await limits.use_premium(db, "pro", 0)  # an empty meter: the chat falls back to Krish Basic

        monkeypatch.setenv("FREE_LIMITS", "off")
        await db.automations.insert_many([{"id": "a1", "userId": "u"}, {"id": "a2", "userId": "u"}])
        await limits.check_total(db, "u", "automation")
        assert await limits.can_publish(db, "u")
        await limits.use(db, "pro", "build")

    run(scenario())


def test_only_paid_plans_can_publish(db):
    async def scenario():
        await db.users.insert_many([{"id": "b"}, {"id": "p", "plan": "pro"}])
        with pytest.raises(HTTPException) as err:
            await limits.require_publish(db, "b")
        assert err.value.status_code == 402 and "Pro and Max" in err.value.detail
        await limits.require_publish(db, "p")
        assert (await limits.summary(db, "b"))["canPublish"] is False

    run(scenario())


def test_picture_tool_refunds_on_failure_and_explains_the_limit(db, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("image service down")

    async def same(prompt, style):
        return prompt

    monkeypatch.setattr(tools.media, "generate_image", boom)
    monkeypatch.setattr(tools.prompt_boost, "image_prompt", same)
    ctx = tools.ToolContext(db=db, user_id="u")

    async def scenario():
        with pytest.raises(RuntimeError):
            await tools._generate_image(ctx, {"prompt": "a cat"})
        assert (await limits.summary(db, "u"))["meter"]["session"]["used"] == 0
        for _ in range(20):
            await limits.use(db, "u", "picture")
        with pytest.raises(ValueError, match="usage"):
            await tools._generate_image(ctx, {"prompt": "a cat"})
        assert "refills" in ctx.limit_hit  # streamed to the app, which pops up the upgrade message

    run(scenario())
