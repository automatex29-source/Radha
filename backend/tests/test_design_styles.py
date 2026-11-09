"""Each app Krish designs gets a style of its own (design_themes.py), and the kit's motion script reaches every
page that uses the kit: in the preview, on the published site and in the ZIP."""
import asyncio

import apps
import design_themes as d


def test_named_style_wins_and_is_kept():
    assert d.choose("a dark neon gaming site", None, "a1", True) == "neon"
    assert d.choose("Design style: Luxury\nA bakery with cakes", None, "a1", True) == "luxury"
    assert d.choose("add a contact form", "luxury", "a1", False) == "luxury"
    assert d.choose("make the title bold", "glass", "a1", False) == "glass"  # a style word alone is not a restyle
    assert d.choose("make it look glassy", "luxury", "a1", False) == "glass"


def test_new_look_changes_style_and_own_code_keeps_its_look():
    assert d.choose(apps.NEW_LOOK_PROMPT, "glass", "a1", False) not in (None, "glass")
    assert d.choose("remove the footer", None, "a1", False) is None


def test_different_apps_of_one_kind_get_different_styles():
    assert len({d.suited("a booking site for my salon", f"app-{i}") for i in range(20)}) > 1


def test_prompt_tells_the_builder_the_style():
    block = d.prompt_block("aurora")
    assert 'class="theme-aurora"' in block and "spin-border" in block
    assert d.prompt_block(None) == ""
    assert all(f".theme-{t}" in apps.KIT_CSS or f"theme-{t})" in apps.KIT_CSS for t in d.THEMES)


def test_kit_pages_get_the_motion_script():
    page = '<html><head><link rel="stylesheet" href="krish-ui.css"></head><body class="theme-glass"><nav class="nav"></nav></body></html>'
    served = apps._serve({"index.html": page, "krish-ui.css": apps.KIT_CSS}, "index.html", bridge=False, cache="no-store")
    assert b"__krishUI" in served.body
    plain = apps._serve({"index.html": "<html><body>hi</body></html>"}, "index.html", bridge=False, cache="no-store")
    assert b"__krishUI" not in plain.body
    out = apps.portable({"shop/index.html": page.replace('href="krish-ui.css"', 'href="../krish-ui.css"')})
    assert '<script src="../krish-ui.js"></script>' in out["shop/index.html"] and out["krish-ui.js"] == apps.KIT_JS


def test_new_look_idea_for_styled_apps():
    ideas = apps.next_ideas({"index.html": '<body class="theme-bold"><form></form>', "app.js": "x"})
    assert ideas[-1]["label"] == "Try a new look" and len(ideas) <= apps.MAX_IDEAS
