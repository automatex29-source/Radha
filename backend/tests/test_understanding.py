"""Messy, fast phone typing (typos, stretched letters, short forms, Hinglish) is read for what the user means."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import counsellor  # noqa: E402
import languages  # noqa: E402
import live_search  # noqa: E402
from tests.test_builder_models import _server  # noqa: E402


def test_tidy_cleans_fast_typing():
    assert live_search.tidy("plzzz tell me weathr in delhi tmrw") == "please tell me weather in delhi tomorrow"
    assert live_search.tidy("gold ka pric kya hai aaj") == "gold ka price kya hai aaj"
    assert live_search.tidy("gogle krke batao latst nws") == "google krke batao latest news"
    assert live_search.tidy("sooo goood") == "soo good"
    assert live_search.tidy("hiiiii") == "hii"


def test_tidy_leaves_real_words_alone():
    for text in ["see www.example.com", "R vs Python for data", "I need 2 tickets", "Ok", "", "u and r"]:
        assert live_search.tidy(text) == text, text


def test_messy_questions_are_still_spotted():
    assert live_search.suggests_web("gold ka pric kya hai")
    assert live_search.suggests_web("latst nws on electon")
    assert live_search.asks_for_search("gogle krke batao ipl score")
    assert live_search.asks_for_search("serch karo iphone 17 pric")
    assert not live_search.suggests_web("hiiiii")
    assert not live_search.needs_lookup("hiiiii")
    assert not live_search.needs_lookup("okkkkk")


def test_search_uses_the_tidied_question(monkeypatch):
    asked = []

    async def fake_search(text, limit=5, focus="web"):
        asked.append(text)
        return None

    monkeypatch.setattr(live_search, "_search", fake_search)
    asyncio.run(live_search.gather(["plzzz tell latst nws abt isro"], force=True))
    assert asked == ["please tell latest news about isro"]


def test_prompts_ask_krish_to_read_intent():
    server = _server()
    assert "Understanding the user" in server.SYSTEM_PROMPT
    assert "Never correct, mention or joke about their spelling" in server.SYSTEM_PROMPT
    assert "Hinglish in English letters gets Hinglish in English letters" in server.SYSTEM_PROMPT
    assert "clarifying question" in server.SYSTEM_PROMPT
    assert "Hinglish" in server.BUILDER_PROMPT
    assert "misheard" in server.voice_prompt("hi")
    assert "never correct their" in counsellor.PROMPT


def test_settings_language_still_mirrors_roman_typing():
    line = languages.prompt_line("hi")
    assert "Always reply in Hindi" in line and "English letters" in line
    assert "English letters" not in languages.prompt_line("ta")  # Tamil script users keep their script
