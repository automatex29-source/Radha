"""Plain conversation skips the tool list on Groq's free tier, so replies start sooner."""
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "radha_test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402


def user(text, **kw):
    return {"role": "user", "content": text, **kw}


def test_small_talk_needs_no_tools():
    assert server._quick_chat([user("hi")])
    assert server._quick_chat([user("explain photosynthesis simply")])
    assert server._quick_chat([user("hello"), {"role": "assistant", "content": "Hi!"}, user("tell me a joke")])


def test_tool_asks_keep_tools():
    for text in ["make a logo for my shop", "search the latest news", "give me a pdf report",
                 "what's the weather in Pune", "open https://example.com", "build a todo app"]:
        assert not server._quick_chat([user(text)]), text


def test_follow_ups_and_images_keep_tools():
    assert not server._quick_chat([user("what is this", images=["m1"])])
    assert not server._quick_chat([user("draw a cat"), {"role": "assistant", "content": "", "steps": [{"id": 1}]},
                                   user("now in blue")])
    # the previous question carries over to a short follow-up
    assert not server._quick_chat([user("create an excel of my sales"), {"role": "assistant", "content": "Sure"},
                                   user("yes please")])
