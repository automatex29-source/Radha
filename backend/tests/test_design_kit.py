"""Krish UI, the built-in design kit: one stylesheet shared by the chat preview and the App Builder."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apps  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def test_backend_and_frontend_kits_match():
    assert (ROOT / "backend/app_kit/krish-ui.css").read_text() == (ROOT / "frontend/src/lib/krish-ui.css").read_text()


def test_guide_teaches_the_kit():
    assert 'href="krish-ui.css"' in apps.DESIGN_GUIDE and "krish-image.invalid" in apps.DESIGN_GUIDE


def test_page_linking_the_kit_gets_the_file():
    mongomock_motor = pytest.importorskip("mongomock_motor")
    apps.init(mongomock_motor.AsyncMongoMockClient()["t"])

    async def go():
        await apps.write_file("a1", "index.html", '<link rel="stylesheet" href="krish-ui.css"><h1>Cakes</h1>')
        await apps.write_file("a1", "shop/index.html", '<link rel="stylesheet" href="../krish-ui.css">')
        await apps.write_file("a2", "index.html", "<h1>No kit</h1>")
        return await apps.snapshot("a1"), await apps.snapshot("a2")

    one, two = asyncio.run(go())
    assert one["krish-ui.css"] == apps.KIT_CSS and sorted(one) == ["index.html", "krish-ui.css", "shop/index.html"]
    assert apps.app_problems(one) == []
    assert "krish-ui.css" not in two
