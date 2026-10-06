"""Offline tests for the plan limits (MongoDB is mongomock)."""
import asyncio
import os
import sys
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


def test_app_builds_stop_but_chat_is_never_counted(db):
    async def scenario():
        for _ in range(5):
            await limits.use(db, "u", "build")
        with pytest.raises(limits.LimitReached):
            await limits.use(db, "u", "build")
        await limits.use(db, "someone-else", "build")  # each user has their own allowance
        summary = await limits.summary(db, "u")
        assert summary["plan"] == "basic"
        assert summary["usage"]["build"] == {"used": 5, "limit": 5}
        assert "chat" not in summary["usage"] and "chat" not in limits.PLANS["basic"]["daily"]
        with pytest.raises(HTTPException) as err:
            await limits.require(db, "u", "build")
        assert err.value.status_code == 402 and "5 app builds" in err.value.detail and "Upgrade to Pro" in err.value.detail

    run(scenario())


def test_three_plans_and_prices():
    assert [(p["id"], p["price"]) for p in limits.public_plans()] == [("basic", 0), ("pro", 299), ("max", 699)]
    for kind in limits.DAILY_KINDS:
        basic, pro, top = (limits.PLANS[p]["daily"][kind] for p in limits.ORDER)
        assert basic < pro < top


def test_new_day_refills(db, monkeypatch):
    async def scenario():
        for _ in range(3):
            await limits.use(db, "u", "picture")
        with pytest.raises(limits.LimitReached):
            await limits.use(db, "u", "picture")
        monkeypatch.setattr(limits, "today", lambda: "2099-01-01")
        await limits.use(db, "u", "picture")

    run(scenario())


def test_refund_gives_a_picture_back(db):
    async def scenario():
        for _ in range(3):
            await limits.use(db, "u", "picture")
        await limits.refund(db, "u", "picture")
        await limits.use(db, "u", "picture")
        with pytest.raises(limits.LimitReached):
            await limits.use(db, "u", "picture")

    run(scenario())


def test_decks_are_four_a_day_and_automations_a_total(db):
    async def scenario():
        for _ in range(4):
            await limits.require(db, "u", "deck", peek=True)  # writing an outline doesn't use one up
            await limits.use(db, "u", "deck")
        with pytest.raises(HTTPException) as err:
            await limits.require(db, "u", "deck", peek=True)
        assert "4 new decks" in err.value.detail
        assert (await limits.summary(db, "u"))["usage"]["deck"] == {"used": 4, "limit": 4}

        await limits.check_total(db, "u", "automation")
        await db.automations.insert_one({"id": "a1", "userId": "u"})
        with pytest.raises(limits.LimitReached):
            await limits.check_total(db, "u", "automation")
        await db.automations.delete_one({"id": "a1"})
        await limits.check_total(db, "u", "automation")  # deleting one frees a slot

    run(scenario())


def test_paid_plans_get_more_and_switch_off_has_no_limits(db, monkeypatch):
    async def scenario():
        await db.users.insert_many([{"id": "pro", "plan": "pro"}, {"id": "max", "plan": "max"}])
        for _ in range(30):
            await limits.use(db, "pro", "build")
        with pytest.raises(limits.LimitReached, match="Upgrade to Max"):
            await limits.use(db, "pro", "build")
        for _ in range(31):
            await limits.use(db, "max", "build")
        assert await limits.is_pro(db, "max") and not await limits.is_pro(db, "u")

        monkeypatch.setenv("FREE_LIMITS", "off")
        await db.automations.insert_many([{"id": "a1", "userId": "u"}, {"id": "a2", "userId": "u"}])
        await limits.check_total(db, "u", "automation")
        assert await limits.can_publish(db, "u")

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
        assert (await limits.summary(db, "u"))["usage"]["picture"]["used"] == 0
        for _ in range(3):
            await limits.use(db, "u", "picture")
        with pytest.raises(ValueError, match="3 pictures"):
            await tools._generate_image(ctx, {"prompt": "a cat"})
        assert "3 pictures" in ctx.limit_hit  # streamed to the app, which pops up the upgrade message

    run(scenario())
