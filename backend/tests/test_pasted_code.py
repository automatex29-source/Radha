"""Code pasted into the App Builder chat is pulled out and saved verbatim (apps.split_pasted_code)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402

PAGE = """<!DOCTYPE html>
<html lang="en">
<head><style>header { background: linear-gradient(#4f46e5, #312e81); }</style></head>
<body><header><h1>Serial Number Finder Tool</h1></header>
<input type="file" id="msmf"><input type="file" id="rfs">
<script>const x = "</div>";</script>
</body>
</html>"""


def test_raw_page_only():
    files, rest = apps.split_pasted_code(PAGE)
    assert files == {"index.html": PAGE + "\n"}
    assert rest == ""


def test_page_with_instructions_around_it():
    files, rest = apps.split_pasted_code(f"Here is my tool:\n{PAGE}\n\nmake the search button green")
    assert files["index.html"] == PAGE + "\n"
    assert rest.startswith("Here is my tool:") and rest.endswith("make the search button green")
    assert "<html" not in rest


def test_fenced_page_and_named_files():
    msg = f"use these\n```html\n{PAGE}\n```\n```css style.css\nbody{{color:red}}\n```\n```js app.js\nlet a = 1;\n```"
    files, rest = apps.split_pasted_code(msg)
    assert files == {"index.html": PAGE + "\n", "style.css": "body{color:red}\n", "app.js": "let a = 1;\n"}
    assert rest == "use these"


def test_plain_requests_are_untouched():
    for msg in ["make a to-do app", "change the <h1> to say Hello", "```js\nconsole.log(1)\n```"]:
        files, rest = apps.split_pasted_code(msg)
        assert files == {} and rest == msg


def test_absorb_saves_verbatim_and_commits():
    import asyncio
    import pytest
    mongomock_motor = pytest.importorskip("mongomock_motor")

    async def go():
        apps.init(mongomock_motor.AsyncMongoMockClient()["t"])
        await apps.db.apps.insert_one({"id": "a1", "name": "Tool"})
        stored, reply = await apps.absorb_pasted_code("a1", PAGE)
        assert reply and "exactly as you gave it" in reply and "<html" not in stored
        assert (await apps.snapshot("a1"))["index.html"] == PAGE + "\n"
        assert (await apps.head_commit("a1"))["author"] == "You"
        stored, reply = await apps.absorb_pasted_code("a1", f"{PAGE}\nmake the header red")
        assert reply is None and stored.startswith("make the header red") and "change only what they ask" in stored
        assert await apps.absorb_pasted_code("a1", "add dark mode") is None

    asyncio.run(go())
