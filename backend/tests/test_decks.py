"""Offline tests for Decks: JSON parsing, slide clean-up, edit operations, generation and the .pptx renderer."""
import asyncio
import io
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")
os.environ["DECK_IMAGES"] = "0"

import deck_render  # noqa: E402
import decks  # noqa: E402

ALL_LAYOUTS = [
    {"layout": "cover", "title": "Solar Power", "subtitle": "Cheaper than ever"},
    {"layout": "section", "title": "Why now"},
    {"layout": "bullets", "title": "Key facts", "body": "Intro line", "bullets": ["one", "two", "three"]},
    {"layout": "image_right", "title": "Rooftops", "bullets": ["a", "b"], "image_query": "solar roof"},
    {"layout": "image_left", "title": "Farms", "body": "Big fields"},
    {"layout": "cards", "title": "Benefits", "items": [{"icon": "💡", "title": "Cheap", "text": "Low cost"},
                                                     {"icon": "🌍", "title": "Clean", "text": "No smoke"},
                                                     {"icon": "⚡", "title": "Fast", "text": "Quick build"}]},
    {"layout": "stats", "title": "Numbers", "stats": [{"value": "90%", "label": "cost drop"}, {"value": "1 TW", "label": "installed"}]},
    {"layout": "steps", "title": "How", "items": [{"title": "Plan", "text": "x"}, {"title": "Build", "text": "y"},
                                                 {"title": "Run", "text": "z"}]},
    {"layout": "quote", "quote": "The sun is the future", "author": "Someone"},
    {"layout": "comparison", "title": "Solar vs coal", "left": {"title": "Solar", "bullets": ["clean"]},
     "right": {"title": "Coal", "bullets": ["dirty"]}},
    {"layout": "closing", "title": "Thank you", "subtitle": "Questions?"},
]


def test_parse_json_handles_fences_and_chatter():
    assert decks.parse_json('Sure!\n```json\n{"a": "x}y", "b": [1]}\n```\nthanks') == {"a": "x}y", "b": [1]}
    with pytest.raises(ValueError):
        decks.parse_json("no json here")


def test_normalize_slide_maps_aliases_and_clamps():
    s = deck_render.normalize_slide({"layout": "two-column", "title": "x" * 300, "bullets": "- only one",
                                     "image": {"url": "javascript:alert(1)"}})
    assert s["layout"] == "comparison"
    assert len(s["title"]) == 90
    assert s["bullets"] == ["only one"]
    assert s["image"] is None
    assert deck_render.normalize_slide({"layout": "weird"})["layout"] == "bullets"


@pytest.mark.parametrize("theme", deck_render.THEME_IDS)
def test_pptx_renders_every_layout_in_every_theme(theme):
    from pptx import Presentation

    data = deck_render.build_deck_pptx("Solar", ALL_LAYOUTS, theme)
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == len(ALL_LAYOUTS)
    texts = " ".join(sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
    for word in ("Solar Power", "Benefits", "90%", "Solar vs coal", "The sun is the future"):
        assert word in texts


def test_pptx_embeds_and_crops_images():
    from PIL import Image
    from pptx import Presentation

    buf = io.BytesIO()
    Image.new("RGB", (1600, 400), "red").save(buf, "JPEG")
    img = {"url": "https://example.com/a.jpg", "credit": "Photo by A"}
    slides = [{**ALL_LAYOUTS[0], "image": img}, {**ALL_LAYOUTS[3], "image": img}]
    prs = Presentation(io.BytesIO(deck_render.build_deck_pptx("T", slides, "snow", lambda url: buf.getvalue())))
    pics = [sh for sl in prs.slides for sh in sl.shapes if sh.shape_type == 13]
    assert len(pics) == 2
    assert pics[0].crop_left > 0.2  # a very wide photo is trimmed at the sides
    assert "Photo by A" in prs.slides[0].notes_slide.notes_text_frame.text


def _deck():
    slides = [deck_render.normalize_slide(s) for s in ALL_LAYOUTS[:4]]
    return {"id": "d", "title": "T", "theme": "aurora", "slides": slides}


def test_apply_ops_uses_original_indexes():
    deck = _deck()
    ids = [s["id"] for s in deck["slides"]]
    ops = [{"op": "delete", "index": 0},
           {"op": "update", "index": 2, "slide": {"layout": "bullets", "title": "New", "bullets": ["x"]}},
           {"op": "insert", "after": 1, "slide": {"layout": "quote", "quote": "Hi"}},
           {"op": "move", "index": 3, "after": -1},
           {"op": "theme", "theme": "paper"}, {"op": "theme", "theme": "nope"},
           {"op": "title", "title": "Renamed"}, "junk", {"op": "update", "index": 99, "slide": {}}]
    slides, changed = decks.apply_ops(deck, ops)
    assert [s["id"] for s in slides][0] == ids[3]
    assert [s["layout"] for s in slides] == ["image_right", "section", "quote", "bullets"]
    assert slides[3]["id"] == ids[2] and slides[3]["title"] == "New"
    assert deck["theme"] == "paper" and deck["title"] == "Renamed"
    assert len(changed) == 1  # only the inserted slide needs a new picture


def test_compact_deck_drops_empty_fields():
    compact = json.loads(decks.compact_deck(_deck()))
    assert "id" not in compact["slides"][0] and "left" not in compact["slides"][0]
    assert compact["slides"][2]["bullets"] == ["one", "two", "three"]


def test_outline_generation_edit_and_undo(monkeypatch):
    mongomock_motor = pytest.importorskip("mongomock_motor")
    db = mongomock_motor.AsyncMongoMockClient()["t"]
    decks.init(db, "test-model")
    calls = []

    async def fake_complete(model, system, user):
        calls.append(system)
        if system == decks.OUTLINE_SYSTEM:
            return json.dumps({"title": "Solar", "slides": [{"title": f"S{i}", "points": ["p"]} for i in range(6)]})
        if system == decks.SLIDES_SYSTEM:
            n = int(user.split("exactly ")[1].split(" ")[0])
            return "```json\n" + json.dumps({"slides": [ALL_LAYOUTS[i % len(ALL_LAYOUTS)] for i in range(n)]}) + "\n```"
        return json.dumps({"reply": "Made it green.", "ops": [{"op": "theme", "theme": "forest"}]})

    monkeypatch.setattr(decks, "_complete", fake_complete)

    async def scenario():
        out = await decks.make_outline(decks.OutlineIn(prompt="solar energy", slides=6), user_id="u")
        assert out["title"] == "Solar" and len(out["outline"]) == 6
        deck = await decks.create_deck(decks.DeckIn(prompt="solar energy", outline=out["outline"], theme="snow"), user_id="u")
        assert deck["status"] == "generating"
        await asyncio.gather(*decks._tasks)
        ready = await decks.get_deck(deck["id"], user_id="u")
        assert ready["status"] == "ready" and ready["slideCount"] == 6
        assert calls.count(decks.SLIDES_SYSTEM) == 2  # 6 slides in batches of 4

        edited = await decks.edit_deck(deck["id"], decks.EditIn(instruction="make it green"), user_id="u")
        assert edited["reply"] == "Made it green." and edited["deck"]["theme"] == "forest" and edited["deck"]["canUndo"]
        undone = await decks.undo_deck(deck["id"], user_id="u")
        assert undone["theme"] == "snow"

        with pytest.raises(Exception):
            await decks.get_deck(deck["id"], user_id="someone-else")

    asyncio.run(scenario())
