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


def test_live_3d_scenes_and_new_styles():
    assert d.choose("make it liquid glass", "glass", "a1", False) == "liquid"
    assert d.choose("a claymorphism learning app for kids", None, "a1", True) == "clay"
    assert d.choose("a retro sunset cafe", None, "a1", True) == "sunset"
    block = d.prompt_block("liquid")
    assert 'data-scene="glass"' in block and "scene-bg" in block and "split" in block
    assert "three@0.160.0" in apps.KIT_JS and "scene-fallback" in apps.KIT_JS
    assert ".scene.scene-ready" in apps.KIT_CSS and "theme-liquid" in apps.KIT_CSS


def test_each_style_links_only_its_own_fonts_and_indian_scripts_get_noto():
    page = '<html><head><link rel="stylesheet" href="krish-ui.css"></head><body class="theme-luxury"><h1>Cakes</h1></body></html>'
    served = apps._serve({"index.html": page}, "index.html", bridge=False, cache="no-store").body.decode()
    assert "family=Manrope" in served and "Fraunces" in served and "fonts.googleapis.com/css2?family=Noto" not in served and "krish-indic')" not in served
    hindi = page.replace("Cakes", "स्वादिष्ट केक").replace("theme-luxury", "theme-glass")
    served = apps._serve({"index.html": hindi}, "index.html", bridge=False, cache="no-store").body.decode()
    assert "Noto+Sans+Devanagari" in served and "family=Sora" in served and "krish-indic" in served
    assert served.index("Noto+Sans+Devanagari") < served.index("<h1>")  # in the head, so it loads at once
    assert apps.script_fonts("வணக்கம்") == ["family=Noto+Sans+Tamil:wght@400..700"]
    assert "var(--indic)" in apps.KIT_CSS and "text-wrap: balance" in apps.KIT_CSS
    zipped = apps.portable({"index.html": hindi})["index.html"]
    assert "Noto+Sans+Devanagari" in zipped and '<script src="krish-ui.js"></script>' in zipped


def test_transitions_are_built_into_the_kit_and_the_prompt():
    from pathlib import Path
    kit = Path(__file__).resolve().parents[1] / "app_kit"
    css, js = (kit / "krish-ui.css").read_text(), (kit / "krish-ui.js").read_text()
    assert "@view-transition { navigation: auto; }" in css
    for move in ("slide", "zoom", "fade", "blur", "wipe"):
        assert f'html[data-transition="{move}"]' in css
    assert "startViewTransition" in js and "data-morph" in js and "data-theme-toggle" in js
    assert "[data-theme-toggle]" in css  # the dark mode button stays on phones
    block = d.prompt_block("neon")
    assert 'data-transition="wipe"' in block and 'data-show="#menu"' in block and "krish.transition" in block
    assert all("transition" in t for t in d.THEMES.values())
