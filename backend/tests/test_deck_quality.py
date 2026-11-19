"""Decks that match the ask (slide count, language) and look designed: new layouts, motion, Indian scripts."""
import asyncio
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "radha_test")
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")
os.environ["DECK_IMAGES"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pptx import Presentation  # noqa: E402

import deck_render  # noqa: E402
import preview  # noqa: E402
import server  # noqa: E402
from agent import ToolContext, default_registry, documents  # noqa: E402
from preview import slide_shapes  # noqa: E402

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

EN = [
    {"layout": "title", "title": "Solar Power in India", "subtitle": "Class 10 science project"},
    {"layout": "agenda", "title": "What we will cover", "bullets": ["How panels work", "Growth", "Challenges", "What you can do"]},
    {"layout": "cards", "title": "Three steps", "items": [{"icon": "☀️", "title": "Light hits", "text": "Photons hit silicon."},
                                                          {"icon": "⚡", "title": "Electrons move", "text": "A current flows."},
                                                          {"icon": "🔌", "title": "Inverter", "text": "DC becomes AC."}]},
    {"layout": "section", "title": "Growth", "subtitle": "Ten times in eight years"},
    {"layout": "timeline", "title": "Milestones", "items": [{"title": "2010", "text": "Solar Mission"},
                                                            {"title": "2015", "text": "100 GW target"},
                                                            {"title": "2024", "text": "Rooftop scheme"}]},
    {"layout": "chart", "title": "Capacity grew fast", "body": "About ten times.",
     "chart": {"type": "bar", "labels": ["2016", "2020", "2024"], "series": [{"name": "GW", "values": [9, 39, 90]}]}},
    {"layout": "two_column", "title": "Pros and cons", "left_title": "Pros", "left": ["Clean"], "right_title": "Cons", "right": ["Night"]},
    {"layout": "closing", "title": "Thank you", "subtitle": "Questions?"},
]
HI = [
    {"layout": "title", "title": "डिजिटल इंडिया", "subtitle": "तकनीक से बदलता भारत"},
    {"layout": "bullets", "title": "मुख्य बातें", "bullets": ["गाँवों तक इंटरनेट पहुँचाना", "सरकारी सेवाएँ ऑनलाइन", "यूपीआई से आसान भुगतान"]},
    {"layout": "closing", "title": "धन्यवाद", "subtitle": "कोई प्रश्न?"},
]


def deck(slides, **kw):
    return Presentation(io.BytesIO(documents.build_pptx(slides, title="Solar Power in India", **kw)))


def test_every_slide_has_a_transition_and_content_that_builds_in():
    prs = deck(EN)
    for slide in prs.slides:
        el = slide._element
        tags = [child.tag for child in el]
        assert P + "transition" in tags, "each slide moves in"
        # the schema order: cSld, clrMapOvr, transition, timing
        assert tags.index(P + "clrMapOvr") < tags.index(P + "transition")
        timing = el.find(P + "timing")
        assert timing is not None
        ids = {sh.shape_id for sh in slide.shapes} | {s.shape_id for g in slide.shapes if g.shape_type == 6 for s in g.shapes}
        targets = [int(t.get("spid")) for t in timing.iter(P + "spTgt")]
        assert targets and set(targets) <= ids, "animations point at real shapes"
        assert tags.index(P + "transition") < tags.index(P + "timing")
    section = prs.slides[3]._element.find(P + "transition")
    assert section.find(P + "push") is not None


def test_motion_can_be_turned_off():
    data = deck_render.build_deck_pptx("T", EN, "aurora", motion=False)
    for slide in Presentation(io.BytesIO(data)).slides:
        assert slide._element.find(P + "transition") is None and slide._element.find(P + "timing") is None


def test_bullets_build_line_by_line():
    prs = deck([{"layout": "bullets", "title": "Points", "bullets": ["a", "b", "c"]}])
    timing = prs.slides[0]._element.find(P + "timing")
    paras = [r.get("st") for r in timing.iter(P + "pRg")]
    assert sorted(set(paras)) == ["0", "1", "2"]
    assert any(b.get("build") == "p" for b in timing.iter(P + "bldP"))


def test_new_layouts_and_preview_text():
    prs = deck(EN)
    texts = [" ".join(sh.text_frame.text for sh in slide_shapes(s.shapes) if sh.has_text_frame) for s in prs.slides]
    assert "How panels work" in texts[1] and "Challenges" in texts[1]
    assert "2015" in texts[4] and "100 GW target" in texts[4]
    assert "Photons hit silicon." in texts[2]
    shown = preview.build_preview(preview.PPTX, documents.build_pptx(EN, title="Solar Power in India"), "d.pptx")["slides"]
    assert shown[3]["title"] == "Growth"  # not the "PART" label or the part number
    assert shown[2]["title"] == "Three steps" and "☀️" not in shown[2]["lines"]
    assert all("Solar Power in India" not in line for s in shown[1:] for line in s["lines"])  # footer left out


def test_indian_scripts_get_a_font_of_their_own():
    prs = deck(HI, theme="sunset")
    fonts = {cs.get("typeface") for s in prs.slides for cs in s._element.iter(A + "cs")}
    assert fonts == {deck_render.COMPLEX_SCRIPT_FONT}


def test_check_deck_holds_the_slide_count_and_language():
    assert documents.check_deck(EN, {"slide_count": 8, "language": "English"}) is None
    assert "exactly 10" in documents.check_deck(EN, {"slide_count": 10, "language": "English"})
    assert documents.check_deck(EN, {"slide_count": 0, "language": "Hindi"})  # asked for Hindi, got English
    assert documents.check_deck(HI, {"slide_count": 3, "language": "Hindi (Devanagari)"}) is None
    assert documents.check_deck(EN, {"slide_count": 8, "language": "Hinglish"}) is None
    assert documents.check_deck(HI, {"slide_count": 3, "language": "Hindi and English"}) is None
    assert documents.check_deck(EN, None) is None


def test_create_presentation_sends_a_wrong_deck_back_to_the_model():
    import json

    async def go():
        ctx = ToolContext(db=None, user_id="u")
        args = {"filename": "solar", "slides": EN, "brief": {"topic": "Solar", "slide_count": 10, "language": "English"}}
        return await default_registry().run("create_presentation", json.dumps(args), ctx)

    out = asyncio.run(go())
    assert not out.ok and "exactly 10" in out.content and not out.media


def test_deck_asks_are_recognised_with_typos_and_in_hindi():
    for text in ["solar pe ppt bana do", "make a presentaion on AI", "10 slides on water", "Prezentation chahiye",
                 "डिजिटल इंडिया पर प्रेजेंटेशन", "स्लाइड बनाओ", "pitch deck for investors"]:
        assert server._DECK_ASK.search(text), text
        assert not server._quick_chat([{"role": "user", "content": text}]), text
    for text in ["present tense ka example", "represent india", "what is the capital of France"]:
        assert not server._DECK_ASK.search(text), text
