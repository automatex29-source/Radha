"""Making videos is switched off by default: no generate_video tool, no video lines in the chat prompt or on the
Plans page, and Krish offers a slideshow or an animated web page instead. VIDEO_GENERATION=on brings it all back."""
import sys
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import media  # noqa: E402
from agent import video  # noqa: E402


def _server():
    if "server" in sys.modules:
        return sys.modules["server"]
    import os
    import motor.motor_asyncio
    env = dict(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0", AI_MODEL="openai/gpt-oss-120b")
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import server
    for k, v in saved.items():  # a fake Groq key left behind would send other tests' prompts to Groq
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return server


def test_video_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("VIDEO_GENERATION", raising=False)
    monkeypatch.setenv("VIDEO_PROVIDER", "slideshow")
    assert not media.video_enabled() and not video.available()
    for on in ("on", "1", "true"):
        monkeypatch.setenv("VIDEO_GENERATION", on)
        assert media.video_enabled() and video.available()
    monkeypatch.setenv("VIDEO_GENERATION", "off")
    assert not video.available()


def test_tool_and_prompt_follow_the_switch(monkeypatch):
    server = _server()
    monkeypatch.setenv("VIDEO_PROVIDER", "slideshow")
    monkeypatch.setenv("VIDEO_GENERATION", "off")
    prompt = server.agent_prompt()
    assert "generate_video" not in prompt and "{media}" not in prompt
    assert "slideshow" in prompt and "animated web page" in prompt and "never say you can't make videos" in prompt
    assert not any(t["name"] == "generate_video" and t["available"] for t in server.tool_registry.describe())

    monkeypatch.setenv("VIDEO_GENERATION", "on")
    assert "generate_video" in server.agent_prompt()
    assert any(t["name"] == "generate_video" and t["available"] for t in server.tool_registry.describe())
