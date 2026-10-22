"""What Pro and Max get beyond the daily counts: the paid picture and video engines, Think on a premium model
(with a daily cap on premium messages), longer videos, bigger uploads and a longer memory. MongoDB is mongomock."""
import os
import sys
import time
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        yield c


def _user(client, email, plan="basic"):
    import server
    r = client.post("/api/auth/register", json={"name": "Asha", "email": email, "password": "secret1"})
    assert r.status_code == 200, r.text
    uid = r.json()["user"]["id"]

    async def set_plan():
        await server.db.users.update_one({"id": uid}, {"$set": {"plan": plan}})
    client.portal.call(set_plan)
    return uid


def test_basic_gets_the_free_picture_and_video_engines(monkeypatch):
    import media
    from agent import video
    monkeypatch.setenv("FAL_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("PAID_MEDIA", raising=False)
    monkeypatch.delenv("IMAGE_PROVIDER", raising=False)
    monkeypatch.delenv("VIDEO_PROVIDER", raising=False)
    assert media._image_providers()[:2] == ["fal", "openai"] and video.provider() == "fal"
    token = media.PREMIUM_MEDIA.set(False)
    try:
        assert not {"fal", "openai"} & set(media._image_providers())
        assert video.provider() in ("pollinations", "slideshow", None)
        monkeypatch.setenv("IMAGE_PROVIDER", "fal")  # an owner's choice of a paid engine is for paid plans too
        assert "fal" not in media._image_providers()
        monkeypatch.setenv("PAID_MEDIA", "all")
        assert "fal" in media._image_providers()
    finally:
        media.PREMIUM_MEDIA.reset(token)


def test_plans_list_their_quality(client):
    import limits
    plans = {p["id"]: p for p in limits.public_plans()}
    basic, pro = plans["basic"]["quality"], plans["pro"]["quality"]
    assert plans["pro"]["price"] == 299
    assert basic["media"] == "free" and pro["media"] == "premium"
    assert pro["videoSeconds"] > basic["videoSeconds"] and pro["uploadMb"] > basic["uploadMb"]
    assert pro["memory"] > basic["memory"] and pro["premiumDaily"] > 0


def test_think_uses_a_premium_model_on_pro_only(client, monkeypatch):
    import server
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    pro, basic = _user(client, "think-pro@test.com", "pro"), _user(client, "think-basic@test.com")
    pick = lambda uid, think: client.portal.call(server._pick_model, uid, {}, server.AI_MODEL, think)
    assert pick(pro, True) == "claude-sonnet-5-5"
    assert pick(pro, False) == server.AI_MODEL
    assert pick(basic, True) == server.AI_MODEL


def test_premium_messages_have_a_daily_cap(client, monkeypatch):
    import limits
    import server
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setitem(limits.PLANS["pro"]["quality"], "premiumDaily", 2)
    uid = _user(client, "cap-pro@test.com", "pro")
    picks = [client.portal.call(server._pick_model, uid, {}, "claude-sonnet-5-5", False) for _ in range(3)]
    assert picks == ["claude-sonnet-5-5", "claude-sonnet-5-5", server.AI_MODEL]


def test_uploads_and_memory_follow_the_plan(client):
    import limits
    import memory
    import server
    from fastapi import HTTPException
    basic, pro = _user(client, "up-basic@test.com"), _user(client, "up-pro@test.com", "pro")
    big = b"x" * (30 * 1024 * 1024)
    with pytest.raises(HTTPException) as err:
        client.portal.call(server._check_upload_size, basic, big, "File")
    assert err.value.status_code == 413 and "20MB" in err.value.detail and "Pro" in err.value.detail
    client.portal.call(server._check_upload_size, pro, big, "File")  # 30MB fits in Pro's 50MB
    assert client.portal.call(memory._keeps, server.db, basic) == limits.PLANS["basic"]["quality"]["memory"]
    assert client.portal.call(memory._keeps, server.db, pro) == limits.PLANS["pro"]["quality"]["memory"]


def test_video_length_follows_the_plan(client, monkeypatch):
    import media
    import server
    from agent import tools, video
    basic, pro = _user(client, "vid-basic@test.com"), _user(client, "vid-pro@test.com", "pro")
    seen = []

    async def fake(prompt, seconds, *rest):
        seen.append((seconds, media.PREMIUM_MEDIA.get()))
        return {"data": b"\x00\x00\x00\x18ftypmp42", "contentType": "video/mp4", "method": "ai_video"}
    monkeypatch.setattr(video, "generate", fake)
    for uid in (basic, pro):
        ctx = tools.ToolContext(db=server.db, user_id=uid)
        client.portal.call(tools._generate_video, ctx, {"prompt": "a sunrise", "seconds": 30})
    assert seen == [(8, False), (12, True)]
    assert media.PREMIUM_MEDIA.get() is True  # set only while the video is made
