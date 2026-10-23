"""What Pro and Max get beyond a bigger usage meter: the paid picture and video engines, Think on a premium model
(premium messages use the meter), longer videos (credits by the second) and bigger uploads. Memory has no
plan limit. MongoDB is mongomock."""
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
    for k, v in saved.items():  # a fake Groq key left behind would send other tests' prompts to Groq
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


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
    assert "memory" not in pro
    assert plans["max"]["quality"]["videoSeconds"] == 60


def test_think_uses_a_premium_model_on_pro_only(client, monkeypatch):
    import server
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    pro, basic = _user(client, "think-pro@test.com", "pro"), _user(client, "think-basic@test.com")
    pick = lambda uid, think: client.portal.call(server._pick_model, uid, {}, server.AI_MODEL, think)
    assert pick(pro, True) == "claude-sonnet-5-5"
    assert pick(pro, False) == server.AI_MODEL
    assert pick(basic, True) == server.AI_MODEL


def test_premium_messages_use_the_meter_by_length(client, monkeypatch):
    import limits
    import server
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setitem(limits.PLANS["pro"], "meter", {"session": 3, "week": 100})
    uid = _user(client, "cap-pro@test.com", "pro")
    pick = lambda chars: client.portal.call(server._pick_model, uid, {}, "claude-sonnet-5-5", False, "x" * chars)
    assert pick(10) == "claude-sonnet-5-5"  # 1 credit
    assert pick(6500) == server.AI_MODEL  # 3 credits don't fit in the 2 left: Krish Basic answers
    assert pick(10) == "claude-sonnet-5-5"

def test_uploads_follow_the_plan(client):
    import server
    from fastapi import HTTPException
    basic, pro = _user(client, "up-basic@test.com"), _user(client, "up-pro@test.com", "pro")
    big = b"x" * (30 * 1024 * 1024)
    with pytest.raises(HTTPException) as err:
        client.portal.call(server._check_upload_size, basic, big, "File")
    assert err.value.status_code == 413 and "20MB" in err.value.detail and "Pro" in err.value.detail
    client.portal.call(server._check_upload_size, pro, big, "File")  # 30MB fits in Pro's 50MB


def test_memory_keeps_learning_when_it_is_long(client, monkeypatch):
    import memory
    import server
    monkeypatch.setattr(memory, "MAX_FACTS", 3)
    uid = _user(client, "mem-basic@test.com")
    replies = iter(['{"add": ["Likes tea"]}', '{"add": ["Lives in Pune"]}', '{"add": ["Has a cat"]}',
                    '{"add": ["Studies law"]}'])

    async def ask(model, prompt):
        return next(replies)
    for text in ("I like tea", "I live in Pune", "I have a cat", "I study law"):
        client.portal.call(memory.learn, server.db, uid, f"remember that {text}", "openai/gpt-oss-120b", ask)

    async def facts():
        return [m["content"] for m in await server.db.memories.find({"userId": uid}).sort("createdAt", 1).to_list(10)]
    assert client.portal.call(facts) == ["Lives in Pune", "Has a cat", "Studies law"]  # the oldest made room


def test_long_videos_use_more_credits(client, monkeypatch):
    import limits
    import server
    from agent import tools, video
    uid = _user(client, "long-max@test.com", "max")
    seen = []

    async def fake(prompt, seconds, *rest):
        seen.append(seconds)
        return {"data": b"\x00\x00\x00\x18ftypmp42", "contentType": "video/mp4", "method": "ai_video"}
    monkeypatch.setattr(video, "generate", fake)
    ctx = tools.ToolContext(db=server.db, user_id=uid)
    client.portal.call(tools._generate_video, ctx, {"prompt": "a road trip", "seconds": 90})
    assert seen == [60]

    async def used():
        return (await limits.summary(server.db, uid))["meter"]["session"]["used"]
    assert client.portal.call(used) == 600  # 60 seconds on the premium engine, 10 credits a second
    monkeypatch.setitem(limits.PLANS["max"], "meter", {"session": 900, "week": 9000})
    with pytest.raises(ValueError, match="needs 600 credits and you have 300 left"):
        client.portal.call(tools._generate_video, ctx, {"prompt": "another trip", "seconds": 60})
    assert client.portal.call(used) == 600  # nothing taken for the video that couldn't be made


def test_long_video_is_clips_joined(monkeypatch):
    import subprocess
    import tempfile
    from agent import prompt_boost, slideshow, video
    if not slideshow.ffmpeg_path():
        pytest.skip("ffmpeg not available")
    made = []

    async def clip(prompt, seconds, portrait):
        made.append(prompt)
        with tempfile.TemporaryDirectory() as tmp:
            out = f"{tmp}/c.mp4"
            subprocess.run([slideshow.ffmpeg_path(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"color=c=blue:s=64x36:d={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
                           check=True)
            return open(out, "rb").read()

    async def same(prompt, *a, **k):
        return prompt

    async def no_scenes(*a, **k):
        return None
    monkeypatch.setattr(video, "_fal", clip)
    monkeypatch.setattr(prompt_boost, "video_prompt", same)
    monkeypatch.setattr(prompt_boost, "video_scenes", no_scenes)
    monkeypatch.setenv("FAL_KEY", "k")
    out = asyncio.run(video.generate("a sunrise", 20, scenes=["dawn", "sun up", "noon"]))
    assert out["method"] == "ai_video" and len(made) == 3  # 20 seconds is three 8-second clips
    assert "Part 1 of 3: dawn" in made[0] and "Part 3 of 3: noon" in made[2]
    info = subprocess.run([slideshow.ffmpeg_path(), "-i", "pipe:0"], input=out["data"], capture_output=True).stderr
    assert b"00:00:24" in info  # three clips, end to end


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
