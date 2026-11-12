"""Offline tests: small side jobs (research queries, deck briefs, prompt rewrites) go to a free model even when the
chat is on a paid one, and fall back to the chat's own model when the free one fails."""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUTH_SECRET", "test-secret-for-unit-tests-0123456789")
os.environ["DECK_IMAGES"] = "0"

import decks  # noqa: E402
from agent import llm, prompt_boost, research  # noqa: E402

_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY",
         "OPENROUTER_API_KEY", "LLM_GATEWAY_URL", "HELPER_MODEL", "PROMPT_BOOST_MODEL", "AI_MODEL")


@pytest.fixture
def keys(monkeypatch):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    return monkeypatch


def test_paid_chat_gets_a_free_helper(keys):
    assert llm.helper_model("claude-sonnet-5-5") == "openai/gpt-oss-20b"
    assert llm.helper_model(llm.PRO) == "openai/gpt-oss-20b"
    assert not llm.paid(llm.helper_model(llm.PRO))


def test_free_chat_keeps_its_model(keys):
    assert llm.helper_model("gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"
    assert llm.helper_model(llm.AUTO) == llm.AUTO


def test_no_free_key_keeps_the_paid_model(keys):
    keys.delenv("GROQ_API_KEY")
    assert llm.helper_model("claude-sonnet-5-5") == "claude-sonnet-5-5"


def test_helper_setting(keys):
    keys.setenv("GEMINI_API_KEY", "g")
    keys.setenv("HELPER_MODEL", "gemini-3.5-flash-lite")
    assert llm.helper_model("claude-sonnet-5-5") == "gemini-3.5-flash-lite"
    keys.setenv("HELPER_MODEL", "off")
    assert llm.helper_model("claude-sonnet-5-5") == "claude-sonnet-5-5"


def test_gateway_keeps_the_chat_model(keys):
    keys.setenv("LLM_GATEWAY_URL", "https://gw.example")
    assert llm.helper_model("claude-sonnet-5-5") == "claude-sonnet-5-5"


def test_research_queries_written_by_free_model(keys):
    asked = []

    async def ask(model, prompt, max_tokens):
        asked.append(model)
        return '["solar price 2026", "solar vs wind"]'

    queries = asyncio.run(research.plan("Is solar worth it?", "", "claude-sonnet-5-5", ask))
    assert asked == ["openai/gpt-oss-20b"] and len(queries) == 3


def test_research_queries_fall_back_to_chat_model(keys):
    asked = []

    async def ask(model, prompt, max_tokens):
        asked.append(model)
        if model == "openai/gpt-oss-20b":
            raise RuntimeError("rate limited")
        return '["solar price 2026"]'

    queries = asyncio.run(research.plan("Is solar worth it?", "", "claude-sonnet-5-5", ask))
    assert asked == ["openai/gpt-oss-20b", "claude-sonnet-5-5"] and "solar price 2026" in queries


def test_deck_brief_by_free_model_then_chosen_model(keys, monkeypatch):
    asked = []

    async def complete(model, system, user):
        asked.append(model)
        if model != "claude-sonnet-5-5":
            raise RuntimeError("busy")
        return "Topic: Solar\nAudience: kids"

    monkeypatch.setattr(decks, "_complete", complete)
    out = asyncio.run(decks.rephrase_prompt(decks.RephraseIn(prompt="solar ppt", model="claude-sonnet-5-5"), user_id="u"))
    assert asked == ["openai/gpt-oss-20b", "claude-sonnet-5-5"] and out["prompt"].startswith("Topic: Solar")


def test_prompt_boost_skips_a_paid_default(keys):
    keys.setenv("AI_MODEL", "claude-sonnet-5-5")
    assert prompt_boost._model() == "openai/gpt-oss-120b"
    keys.setenv("PROMPT_BOOST_MODEL", "claude-haiku-5-5")
    assert prompt_boost._model() == "claude-haiku-5-5"
    keys.delenv("PROMPT_BOOST_MODEL")
    keys.delenv("GROQ_API_KEY")
    assert prompt_boost._model() == "claude-sonnet-5-5"
