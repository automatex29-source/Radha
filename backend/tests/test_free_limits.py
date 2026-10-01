"""Offline tests for the free plan limits (MongoDB is mongomock)."""
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


def test_chats_stop_after_thirty_a_day(db):
    async def scenario():
        for _ in range(30):
            await limits.use(db, "u", "chat")
        with pytest.raises(limits.LimitReached):
            await limits.use(db, "u", "chat")
        await limits.use(db, "someone-else", "chat")  # each user has their own allowance
        summary = await limits.summary(db, "u")
        assert summary["chats"] == {"used": 30, "limit": 30}
        with pytest.raises(HTTPException) as err:
            await limits.require(db, "u", "chat")
        assert err.value.status_code == 429 and "30 free chats" in err.value.detail

    run(scenario())


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
        assert "4 free decks" in err.value.detail
        assert (await limits.summary(db, "u"))["decks"] == {"used": 4, "limit": 4}

        await limits.check_total(db, "u", "automation")
        await db.automations.insert_one({"id": "a1", "userId": "u"})
        with pytest.raises(limits.LimitReached):
            await limits.check_total(db, "u", "automation")
        await db.automations.delete_one({"id": "a1"})
        await limits.check_total(db, "u", "automation")  # deleting one frees a slot

    run(scenario())


def test_pro_users_and_switch_off_have_no_limits(db, monkeypatch):
    async def scenario():
        await db.users.insert_one({"id": "pro", "plan": "pro"})
        for _ in range(40):
            await limits.use(db, "pro", "chat")
        assert (await limits.summary(db, "pro"))["plan"] == "unlimited"

        monkeypatch.setenv("FREE_LIMITS", "off")
        await db.automations.insert_many([{"id": "a1", "userId": "u"}, {"id": "a2", "userId": "u"}])
        await limits.check_total(db, "u", "automation")

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
        assert (await limits.summary(db, "u"))["pictures"]["used"] == 0
        for _ in range(3):
            await limits.use(db, "u", "picture")
        with pytest.raises(ValueError, match="3 free pictures"):
            await tools._generate_image(ctx, {"prompt": "a cat"})

    run(scenario())
