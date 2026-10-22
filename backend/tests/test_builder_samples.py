"""Files attached in the App Builder go into the app whole (samples/, assets/), so Krish builds a file tool for the
file's real layout and shows the user's own logo; the guide asks for a domain audit with a styled ExcelJS export."""
import asyncio
import base64
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402
from tests.test_builder_models import _server  # noqa: E402


def amos_log(cells: int = 400) -> str:
    """A site log shaped like an AMOS / moshell session: thousands of words, the useful parts far down."""
    lines = ["LO01INMH414433> st cell", "", "Proxy  Adm State     Op. State     MO"]
    lines += [f"{1000 + i:<6} 1 (UNLOCKED)  1 (ENABLED)   ENodeBFunction=1,EUtranCellFDD=LO01_{i}" for i in range(cells)]
    lines += ["", "LO01INMH414433> alt", "", "Date & Time (Local) S Specific Problem      MO (Cause/AdditionalInfo)",
              "2026-10-20 10:01:02 M Link Failure          FieldReplaceableUnit=RRU-2 (VSWR Over Threshold)", ""]
    return "\n".join(lines) + "\n"


@pytest.fixture()
def db():
    mongomock_motor = pytest.importorskip("mongomock_motor")
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    apps.init(database)
    return database


def keep(name, data, text=""):
    return asyncio.run(apps.keep_upload("a1", name, data, text))


def test_sample_log_goes_into_the_app_unchanged(db):
    log = amos_log()
    assert len(log.split()) > 5 * 450  # far more than the 450 words a free builder got in its prompt
    assert keep("LO01INMH414433.dat", log.encode()) == "samples/LO01INMH414433.dat"
    files = asyncio.run(apps.snapshot("a1"))
    assert files["samples/LO01INMH414433.dat"] == log  # every line, so search_files finds the alarms at the end


def test_logo_goes_into_assets_as_a_picture_the_page_can_show(db):
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (240, 80), "#3326c4").save(out, "PNG")
    assert keep("Vedang logo.png", out.getvalue()) == "assets/Vedang-logo.svg"
    svg = asyncio.run(apps.snapshot("a1"))["assets/Vedang-logo.svg"]
    assert 'width="240" height="80"' in svg
    assert base64.b64encode(out.getvalue()).decode() in svg
    assert keep("mark.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="4"/></svg>') == "assets/mark.svg"


def test_big_logo_is_shrunk_to_fit(db):
    import os
    from PIL import Image
    out = io.BytesIO()
    Image.frombytes("RGB", (1600, 1600), os.urandom(1600 * 1600 * 3)).save(out, "PNG")  # noise: about 7 MB
    path = keep("logo.png", out.getvalue())
    assert path == "assets/logo.svg"
    assert 'width="800"' in asyncio.run(apps.snapshot("a1"))[path]


def test_documents_go_in_as_their_text_and_unreadable_files_are_skipped(db):
    assert keep("report.pdf", b"%PDF-1.4\x00\x01\x02", "Site LO01 passed 12 of 14 checks") == "samples/report.pdf.txt"
    assert asyncio.run(apps.snapshot("a1"))["samples/report.pdf.txt"].startswith("Site LO01")
    assert keep("firmware.bin", b"\x00\x01\x02\x03" * 100) is None


def test_huge_sample_is_cut_on_a_whole_line(db):
    log = amos_log(cells=20000)
    assert len(log.encode()) > apps.MAX_FILE_BYTES
    path = keep("big.log", log.encode())
    kept = asyncio.run(apps.snapshot("a1"))[path]
    assert len(kept.encode()) < apps.MAX_FILE_BYTES and kept.endswith("\n") and log.startswith(kept)


def test_guide_asks_for_a_real_audit_and_a_real_logo():
    guide = apps.DESIGN_GUIDE
    assert "ExcelJS" in guide and "not SheetJS" in guide
    assert "Pass, Fail or Attention" in guide and "node --test" in guide
    assert "A logo, or any picture with words in it, is never a made-up picture link" in guide


def test_builder_prompt_points_at_samples_and_assets(db):
    async def go():
        await db.apps.insert_one({"id": "a1", "name": "Audit"})
        await apps.write_file("a1", "samples/site.log", amos_log(5))
        return await apps.app_prompt(db, "a1")
    prompt = asyncio.run(go())
    assert "- samples/site.log" in prompt
    assert "study the sample before you write any code" in prompt
    assert "Show the user's logo from assets/" in prompt


def test_attached_file_lands_in_the_app_and_the_prompt_says_where(monkeypatch):
    server = _server()
    import mongomock_motor
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", database)
    apps.init(database)
    log = amos_log()

    async def go():
        await database.files.insert_one({"id": "f1", "userId": "u1", "conversationId": "c1", "is_deleted": False,
                                         "original_filename": "site.log", "chunk_count": 20, "status": "ready"})
        await server._keep_in_app("a1", "f1", "site.log", log.encode())
        ctx, _ = await server._file_context("c1", "u1", None, "build the audit tool", server.FILE_WORDS_LEAN_TOOLS)
        return ctx, await apps.snapshot("a1")
    ctx, files = asyncio.run(go())
    assert files["samples/site.log"] == log
    assert "the whole file is in the app as samples/site.log" in ctx and "search_files" in ctx


def test_builder_turns_reason_harder(monkeypatch):
    server = _server()
    import mongomock_motor
    from agent import llm
    database = mongomock_motor.AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", database)
    apps.init(database)
    seen = []

    async def fake_stream(model, messages, tools, think=False, max_output=None):
        seen.append(think)
        yield {"type": "text", "text": "Built."}
        yield {"type": "done", "finish_reason": "stop"}
    monkeypatch.setattr(server.agent_llm, "stream_completion", fake_stream)

    async def go():
        await database.apps.insert_one({"id": "a1", "name": "Audit", "userId": "u1"})
        await database.conversations.insert_one({"id": "c1", "userId": "u1", "appId": "a1"})
        await database.messages.insert_one({"id": "m1", "conversationId": "c1", "role": "user",
                                            "content": "make a post integration audit tool", "createdAt": "1"})
        [c async for c in server.run_turn("c1", "openai/gpt-oss-120b")]
    asyncio.run(go())
    assert seen and seen[0] == llm.DEEPER
