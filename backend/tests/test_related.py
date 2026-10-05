import asyncio

import live_search
import related
from agent import web


def test_split_removes_related_line():
    text = "Delhi is the capital of India [1].\n\nRelated: What is the population of Delhi? | When did Delhi become the capital? | What is NCR?"
    body, qs = related.split(text)
    assert body == "Delhi is the capital of India [1]."
    assert qs == ["What is the population of Delhi?", "When did Delhi become the capital?", "What is NCR?"]


def test_split_handles_bold_label_and_numbers():
    body, qs = related.split("Answer.\n**Related:** 1. One more? | 2. Two more?")
    assert body == "Answer." and qs == ["One more?", "Two more?"]


def test_split_without_line_keeps_text():
    assert related.split("Just an answer.") == ("Just an answer.", [])


def test_split_ignores_related_mid_text():
    text = "Related: this word starts a line\nbut the answer goes on."
    assert related.split(text) == (text, [])


def test_fact_questions_search():
    assert live_search.needs_lookup("who is the ceo of tata motors")
    assert live_search.needs_lookup("best phones under 20000")
    assert live_search.needs_lookup("iphone 17 vs pixel 10")
    assert not live_search.needs_lookup("write a story about a king")


def test_gather_returns_cards_and_cite_note(monkeypatch):
    async def fake_search(query, limit):
        assert limit == 8  # the Search button asks for more results
        return [{"title": "Tata Motors", "url": "https://www.tatamotors.com/about", "snippet": "About us"}]
    monkeypatch.setattr(web, "search", fake_search)
    text, cards = asyncio.run(live_search.gather(["tell me about tata motors"], force=True))
    assert "[1] Tata Motors" in text and "square brackets" in text
    assert cards == [{"type": "web", "title": "Tata Motors", "url": "https://www.tatamotors.com/about",
                      "domain": "tatamotors.com", "snippet": "About us"}]


def test_gather_skips_without_force(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("should not search")
    monkeypatch.setattr(web, "search", boom)
    assert asyncio.run(live_search.gather(["tell me about tata motors"])) == (None, [])
