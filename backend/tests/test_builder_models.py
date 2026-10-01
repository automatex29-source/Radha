"""The App Builder's model choice: Cerebras (free, bigger budget), BUILDER_MODEL, and Claude prompt caching.

Offline: litellm.acompletion is replaced with a fake; the model picker gets a fake database.
"""
import asyncio
import sys
from pathlib import Path

import litellm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import llm  # noqa: E402
from tests.test_lean_budget import big_history, collect, fake_completion, run  # noqa: E402

CEREBRAS = "cerebras/gpt-oss-120b"


def test_cerebras_routing_and_budget(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.delenv("CEREBRAS_TPM", raising=False)
    assert llm.provider_for(CEREBRAS) == "cerebras"
    assert llm.litellm_model(CEREBRAS) == CEREBRAS  # not cerebras/cerebras/...
    assert llm.litellm_model("openai/gpt-oss-120b") == "groq/openai/gpt-oss-120b"
    assert llm.lean(CEREBRAS) and not llm.supports_images(CEREBRAS) and not llm.paid(CEREBRAS)
    assert llm.token_budget(CEREBRAS) > 3 * llm.token_budget("openai/gpt-oss-120b")
    monkeypatch.setenv("CEREBRAS_API_KEY", "k")
    assert llm.configured(CEREBRAS)


def test_cerebras_keeps_more_history_than_groq(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    msgs = big_history(5)  # about 15K tokens: too much for Groq's free tier, fine for Cerebras's
    seen = fake_completion(monkeypatch)
    run(collect(llm.stream_completion(CEREBRAS, msgs, [])))
    run(collect(llm.stream_completion("openai/gpt-oss-120b", msgs, [])))
    cerebras, groq = seen
    assert cerebras["model"] == CEREBRAS and cerebras["reasoning_effort"] == "medium"
    assert cerebras["messages"] is msgs and groq["messages"] is not msgs
    assert llm.estimate_tokens(cerebras["messages"]) + cerebras["max_tokens"] <= llm.token_budget(CEREBRAS)


def test_rate_limited_cerebras_falls_back_to_groq_refitted(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    seen = fake_completion(monkeypatch, failures=1)
    run(collect(llm.stream_completion(CEREBRAS, big_history(), [])))
    assert [kw["model"] for kw in seen] == [CEREBRAS, "groq/openai/gpt-oss-120b"]
    assert llm.estimate_tokens(seen[1]["messages"]) + seen[1]["max_tokens"] <= llm.token_budget("openai/gpt-oss-120b")


def test_claude_system_prompt_is_cached(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    seen = fake_completion(monkeypatch)
    msgs = [{"role": "system", "content": "Build apps."}, {"role": "user", "content": "hi"}]
    run(collect(llm.stream_completion("claude-sonnet-5-5", msgs, [])))
    sent = seen[0]
    assert sent["model"] == "anthropic/claude-sonnet-5-5" and llm.paid("claude-sonnet-5-5")
    assert sent["messages"][0]["content"][0] == {"type": "text", "text": "Build apps.",
                                                  "cache_control": {"type": "ephemeral"}}
    assert sent["messages"][1:] == msgs[1:] and msgs[0]["content"] == "Build apps."  # caller's list untouched


class FakeUsers:
    def __init__(self, plan):
        self.plan = plan

    async def find_one(self, *_a, **_k):
        return {"plan": self.plan}


class FakeDB:
    def __init__(self, plan=None):
        self.users = FakeUsers(plan)


def _server():
    """Import the server the way the other server tests do (an in-memory database), whichever runs first."""
    if "server" not in sys.modules:
        import os
        import mongomock_motor
        import motor.motor_asyncio
        os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                          AI_MODEL="openai/gpt-oss-120b")
        motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import server
    return server


def pick(monkeypatch, requested, app=True, plan=None, ai_model="openai/gpt-oss-120b"):
    server = _server()
    monkeypatch.setattr(server, "db", FakeDB(plan))
    monkeypatch.setattr(server, "AI_MODEL", ai_model)
    conv = {"appId": "a1"} if app else {}
    return asyncio.run(server._pick_model("u1", conv, requested))


def test_builder_moves_to_cerebras_when_its_key_is_set(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.delenv("BUILDER_MODEL", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    assert pick(monkeypatch, "openai/gpt-oss-120b") == "openai/gpt-oss-120b"
    monkeypatch.setenv("CEREBRAS_API_KEY", "k")
    assert pick(monkeypatch, "openai/gpt-oss-120b") == CEREBRAS
    assert pick(monkeypatch, "openai/gpt-oss-120b", app=False) == "openai/gpt-oss-120b"  # chat keeps its pick


def test_builder_model_override_is_for_everyone(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("BUILDER_MODEL", "claude-sonnet-5-5")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert pick(monkeypatch, "openai/gpt-oss-120b") == "openai/gpt-oss-120b"  # no key: ignored
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert pick(monkeypatch, "openai/gpt-oss-120b") == "claude-sonnet-5-5"


def test_paid_chat_models_are_for_pro(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.delenv("BUILDER_MODEL", raising=False)
    monkeypatch.delenv("PAID_MODELS", raising=False)
    assert pick(monkeypatch, "claude-sonnet-5-5", app=False) == "openai/gpt-oss-120b"
    assert pick(monkeypatch, "claude-sonnet-5-5", app=False, plan="pro") == "claude-sonnet-5-5"
    monkeypatch.setenv("PAID_MODELS", "all")
    assert pick(monkeypatch, "claude-sonnet-5-5", app=False) == "claude-sonnet-5-5"
    monkeypatch.delenv("PAID_MODELS")
    # When the owner only has a paid key, it's the default and isn't blocked.
    assert pick(monkeypatch, "claude-sonnet-5-5", app=False, ai_model="claude-sonnet-5-5") == "claude-sonnet-5-5"
