"""edit_file tolerates what models get wrong: copied line numbers and whitespace (apps.locate_snippet)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402

FILE = """<body>
  <header class="hero">
    <h1>Serial Number Finder Tool</h1>
  </header>
  <button id="search" class="btn">Search</button>
  <button id="cancel" class="btn">Cancel</button>
</body>
"""


def span(old):
    start, end, problem = apps.locate_snippet(FILE, old)
    return FILE[start:end] if problem is None else problem


def test_exact():
    assert span('<button id="search" class="btn">Search</button>') == '<button id="search" class="btn">Search</button>'


def test_copied_line_numbers():
    old = '   2    <header class="hero">\n   3      <h1>Serial Number Finder Tool</h1>'
    assert span(old) == '  <header class="hero">\n    <h1>Serial Number Finder Tool</h1>'


def test_whitespace_differences():
    assert span('<header class="hero">\n<h1>Serial Number Finder Tool</h1>') == \
        '<header class="hero">\n    <h1>Serial Number Finder Tool</h1>'


def test_ambiguous_and_missing_explain_themselves():
    assert "matches 2 places (lines 5, 6)" in span('class="btn"')
    msg = span('<button id="serch" class="btn">Search</button>')
    assert "not found" in msg and '   5    <button id="search"' in msg


def test_builder_summary_never_silent():
    import importlib, os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:1")
    os.environ.setdefault("DB_NAME", "t")
    server = importlib.import_module("server")
    ok = {"name": "edit_file", "status": "done", "args": {"path": "index.html"}}
    bad = {"name": "edit_file", "status": "error", "args": {"path": "index.html"}}
    assert "I changed index.html" in server._builder_summary([ok, bad])
    assert "nothing was changed" in server._builder_summary([bad, bad])
    assert "didn't change anything" in server._builder_summary([{"name": "read_file", "status": "done", "args": {}}])
