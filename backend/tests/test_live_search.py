"""Unit tests for automatic live lookups in plain chat. Offline: network calls are faked."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import live_search  # noqa: E402
from agent import web  # noqa: E402


def test_detects_questions_that_need_live_info():
    assert live_search.needs_lookup("WHAT IS DOLLAR RATE TODA")
    assert live_search.needs_lookup("latest news on the election")
    assert live_search.needs_lookup("can you do google search")
    assert not live_search.needs_lookup("write a poem about the sea")
    assert not live_search.needs_lookup("explain recursion in python")


def test_short_follow_up_joins_previous_question():
    assert live_search._recent_user_text(["what is the dollar rate", "USD"]) == "what is the dollar rate USD"
    assert live_search._recent_user_text(["hi", "tell me a long story about dragons"]) == "tell me a long story about dragons"


def test_lookup_skips_ordinary_questions(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("should not search")
    monkeypatch.setattr(web, "search", boom)
    assert asyncio.run(live_search.lookup(["write a poem"])) is None


def test_lookup_combines_rates_and_search(monkeypatch):
    async def fake_search(query, limit):
        return [{"title": "USD to INR", "url": "https://x.test", "snippet": "1 USD = 88 INR"}]

    async def fake_rates(text):
        return "Live exchange rates:\n1 USD = 88.0000 INR"
    monkeypatch.setattr(web, "search", fake_search)
    monkeypatch.setattr(live_search, "_rates", fake_rates)
    out = asyncio.run(live_search.lookup(["what is dollar rate today"]))
    assert "1 USD = 88.0000 INR" in out and "https://x.test" in out


def test_lookup_survives_failures(monkeypatch):
    async def broken(*a, **k):
        raise RuntimeError("blocked")
    monkeypatch.setattr(web, "search", broken)
    assert asyncio.run(live_search.lookup(["latest news"])) is None


def test_parses_duckduckgo_lite():
    html = """<table>
      <tr><td>1.</td><td><a rel="nofollow" href="https://example.org/a" class='result-link'>First</a></td></tr>
      <tr><td></td><td class='result-snippet'>Snippet one.</td></tr>
      <tr><td>2.</td><td><a href="//duckduckgo.com/y.js?ad=1" class='result-link'>Ad</a></td></tr>
      <tr><td></td><td class='result-snippet'>ad</td></tr>
    </table>"""
    assert web.parse_ddg_lite(html, 5) == [{"title": "First", "url": "https://example.org/a", "snippet": "Snippet one."}]


KNOWN = {"USD", "INR", "IRR", "EUR", "GBP", "JPY", "AED", "CNY", "CAD", "AUD", "SGD", "SAR"}


def test_guesses_misspelled_currency():
    codes, notes = web.pick_currencies("USD to IRHT exchange rate", KNOWN)
    assert codes[0] == "INR"
    assert notes and "INR" in notes[0]


def test_understands_names_and_exact_codes():
    codes, notes = web.pick_currencies("dollar to rupees", KNOWN)
    assert codes[0] == "INR" and not notes
    codes, notes = web.pick_currencies("USD to JPY", KNOWN)
    assert codes[0] == "JPY" and not notes


def test_agent_turns_only_fetch_rates(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("agent turns search with their own tool")

    async def fake_rates(text):
        return "1 USD = 88.0000 INR"
    monkeypatch.setattr(web, "search", boom)
    monkeypatch.setattr(live_search, "_rates", fake_rates)
    assert asyncio.run(live_search.lookup(["USD to IRHT"], search=False)) == "1 USD = 88.0000 INR"
    assert asyncio.run(live_search.lookup(["latest news"], search=False)) is None


def test_web_search_tool_adds_rates_even_when_search_fails(monkeypatch):
    from agent import tools

    async def broken(*a, **k):
        raise RuntimeError("blocked")

    async def fake_rates(text):
        return "1 USD = 88.0000 INR"
    monkeypatch.setattr(web, "search", broken)
    monkeypatch.setattr(web, "exchange_rates", fake_rates)
    out = asyncio.run(tools._web_search(None, {"query": "USD to IRHT exchange rate"}))
    assert "88.0000 INR" in out.content
