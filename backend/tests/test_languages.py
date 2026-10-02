"""The Settings language: which codes are allowed, and the line that makes Krish reply in it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import languages  # noqa: E402


def test_at_least_ten_languages():
    assert len(languages.LANGUAGES) >= 10
    assert {"en", "hi", "ta", "bn"} <= set(languages.LANGUAGES)


def test_unknown_or_missing_falls_back_to_english():
    assert languages.normalize(None) == "en"
    assert languages.normalize("xx") == "en"
    assert languages.normalize("hi") == "hi"


def test_prompt_line_names_the_language():
    assert languages.prompt_line("en") is None
    assert languages.prompt_line(None) is None
    line = languages.prompt_line("ta")
    assert "Tamil" in line and "reply in Tamil" in line
