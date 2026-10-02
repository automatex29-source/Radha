"""Code pasted or attached in the chat is shown exactly as given, with no AI rewrite (server.show_as_is)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")

import server  # noqa: E402

PAGE = "<!doctype html>\n<html><head><style>h1{color:#e11d48}</style></head><body><h1>Sweet Delight</h1></body></html>"


def test_whole_page_comes_back_unchanged():
    reply = server.show_as_is(PAGE)
    assert "exactly as you gave it" in reply
    assert f"```html index.html\n{PAGE}\n```" in reply


def test_show_words_still_count_as_no_instructions():
    for msg in [f"show this\n{PAGE}", f"{PAGE}\nplease preview it same", "<div class='card'>Hello</div>"]:
        assert server.show_as_is(msg), msg


def test_real_instructions_go_to_the_ai():
    for msg in [f"make the heading blue\n{PAGE}", "what does <b>bold</b> do?", "make a cake shop website"]:
        assert server.show_as_is(msg) is None, msg


def test_attached_files_and_inner_fences():
    msg = "```html index.html\n<h1>x</h1>\n```\n\n````js app.js\nconst md = '```';\n````"
    reply = server.show_as_is(msg)
    assert "```html index.html\n<h1>x</h1>\n```" in reply
    assert "````js app.js\nconst md = '```';\n````" in reply
