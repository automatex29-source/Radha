"""Krish AI: the free models are one model that picks which of them answers each question."""
import asyncio

from tests.test_builder_models import FakeDB, _server
from tests.test_code_and_ideas import answering_model

GEMINI, GROQ, CEREBRAS = "gemini-3.5-flash-lite", "openai/gpt-oss-120b", "cerebras/gpt-oss-120b"


def keys(monkeypatch, *names):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY"):
        if name in names:
            monkeypatch.setenv(name, "test")
        else:
            monkeypatch.delenv(name, raising=False)


def test_free_plan_menu_has_one_free_model():
    server = _server()
    free = [m for m in server.AVAILABLE_MODELS if not m["pro"]]
    assert [m["id"] for m in free] == [server.AUTO_MODEL] and free[0]["label"] == "Krish AI"
    assert all(m["pro"] for m in server.AVAILABLE_MODELS[1:])


def test_krish_ai_is_free_and_works_wherever_a_model_id_goes(monkeypatch):
    from agent import llm
    keys(monkeypatch, "GROQ_API_KEY")
    assert llm.configured(llm.AUTO) and not llm.paid(llm.AUTO)
    assert llm.concrete(llm.AUTO) == GROQ and llm.provider_for(llm.AUTO) == "groq" and llm.lean(llm.AUTO)
    keys(monkeypatch, "GEMINI_API_KEY", "GROQ_API_KEY")
    assert llm.concrete(llm.AUTO) == GEMINI and llm.concrete(CEREBRAS) == CEREBRAS
    keys(monkeypatch)
    assert not llm.configured(llm.AUTO)


def test_each_question_goes_to_the_right_free_model(monkeypatch):
    server = _server()
    keys(monkeypatch, "GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY")
    pick = lambda docs: server._auto_model(docs, docs[-1]["content"])  # noqa: E731
    assert pick([{"role": "user", "content": "hi"}]) == GEMINI
    assert pick([{"role": "user", "content": "prove that the square root of 2 is irrational step by step"}]) == CEREBRAS
    assert pick([{"role": "user", "content": "what's in this?", "images": ["i1"]}]) == GEMINI
    long_chat = [{"role": "user", "content": "x" * 30000}, {"role": "assistant", "content": "ok"},
                 {"role": "user", "content": "and?"}]
    assert pick(long_chat) == CEREBRAS
    keys(monkeypatch, "GROQ_API_KEY")  # only Groq set up: everything goes there
    assert pick([{"role": "user", "content": "hi"}]) == GROQ
    assert pick(long_chat) == GROQ


def test_coding_questions_still_go_to_krish_coder(monkeypatch):
    server = _server()
    keys(monkeypatch, "GEMINI_API_KEY", "GROQ_API_KEY")
    answered, kept = answering_model(monkeypatch, "fix this python KeyError", model=server.AUTO_MODEL)
    assert answered == server.CODER_MODEL and kept == server.AUTO_MODEL  # the chat stays on Krish AI
    assert answering_model(monkeypatch, "hi there", model=server.AUTO_MODEL)[0] == GEMINI


def test_basic_plan_gets_krish_ai_instead_of_paid_models(monkeypatch):
    server = _server()
    keys(monkeypatch, "GROQ_API_KEY")
    monkeypatch.setattr(server, "db", FakeDB(None))
    monkeypatch.setattr(server, "AI_MODEL", server.AUTO_MODEL)
    monkeypatch.delenv("PAID_MODELS", raising=False)
    assert asyncio.run(server._pick_model("u1", {}, "claude-sonnet-5-5")) == server.AUTO_MODEL
    assert asyncio.run(server._pick_model("u1", {}, server.AUTO_MODEL)) == server.AUTO_MODEL
    monkeypatch.setattr(server, "db", FakeDB("pro"))
    assert asyncio.run(server._pick_model("u1", {}, "claude-sonnet-5-5")) == "claude-sonnet-5-5"
