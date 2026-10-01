"""Groq free-tier budget handling: prompts are trimmed, output is capped, rate limits are waited out.

Offline: litellm.acompletion is replaced with a fake.
"""
import asyncio
import json
import sys
from pathlib import Path

import litellm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import Tool, ToolContext, ToolOutput, ToolRegistry  # noqa: E402
from agent import llm  # noqa: E402

GROQ = "openai/gpt-oss-120b"


def run(coro):
    return asyncio.run(coro)


async def collect(gen):
    return [ev async for ev in gen]


class FakeStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def fake_completion(monkeypatch, failures=0):
    seen = []

    async def acompletion(**kwargs):
        seen.append(kwargs)
        if len(seen) <= failures:
            raise litellm.RateLimitError("Rate limit reached. Please try again in 0.01s.", "groq", GROQ)
        return FakeStream()

    monkeypatch.setattr(litellm, "acompletion", acompletion)
    return seen


def big_history(turns=12):
    msgs = [{"role": "system", "content": "You are RADHA."}]
    for i in range(turns):
        msgs.append({"role": "user", "content": f"make change {i}"})
        msgs.append({"role": "assistant", "content": None, "tool_calls": [{
            "id": f"c{i}", "type": "function",
            "function": {"name": "write_file", "arguments": json.dumps({"path": "index.html", "content": "x" * 6000})}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "y" * 3000})
    return msgs


def test_small_prompt_is_untouched():
    msgs = [{"role": "system", "content": "hi"}, {"role": "user", "content": "hello"}]
    assert llm.fit_messages(msgs, [], 7700) is msgs


def test_large_history_fits_budget_and_keeps_structure():
    msgs = big_history()
    fitted = llm.fit_messages(msgs, [], 7700)
    assert llm.estimate_tokens(fitted) <= 7700 - llm._MIN_OUTPUT
    assert fitted[0]["role"] == "system"
    assert fitted[1]["role"] != "tool"
    # every tool result still follows its call
    ids = set()
    for m in fitted:
        for c in m.get("tool_calls") or []:
            ids.add(c["id"])
        if m["role"] == "tool":
            assert m["tool_call_id"] in ids
    # the latest step keeps its full arguments
    assert fitted[-2]["tool_calls"][0] == msgs[-2]["tool_calls"][0]


def test_groq_request_caps_output_and_lowers_reasoning(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    seen = fake_completion(monkeypatch)
    run(collect(llm.stream_completion(GROQ, big_history(), [])))
    kw = seen[0]
    assert kw["reasoning_effort"] == "low"
    assert llm.estimate_tokens(kw["messages"]) + kw["max_tokens"] <= llm.token_budget()


def test_other_providers_are_not_trimmed(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    seen = fake_completion(monkeypatch)
    msgs = big_history()
    run(collect(llm.stream_completion("gpt-4o", msgs, [])))
    assert seen[0]["messages"] is msgs and seen[0]["max_tokens"] == llm._BIG_OUTPUT


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    seen = fake_completion(monkeypatch, failures=2)
    events = run(collect(llm.stream_completion("openai/gpt-oss-20b", [{"role": "user", "content": "hi"}], [])))
    assert len(seen) == 3
    assert [e["type"] for e in events] == ["heartbeat", "heartbeat"]


def test_rate_limited_big_model_falls_back_at_once(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    seen = fake_completion(monkeypatch, failures=1)
    events = run(collect(llm.stream_completion(GROQ, [{"role": "user", "content": "hi"}], [])))
    assert [kw["model"] for kw in seen] == ["groq/openai/gpt-oss-120b", "groq/openai/gpt-oss-20b"]
    assert events == []  # no waiting


def test_plain_answer_asks_for_less_output(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    seen = fake_completion(monkeypatch)
    run(collect(llm.stream_completion(GROQ, [{"role": "user", "content": "hi"}], [])))
    assert seen[0]["max_tokens"] == llm._PLAIN_OUTPUT


def test_retry_after_parsing():
    assert abs(llm._retry_after(Exception("Please try again in 7.5s")) - 8.0) < 1e-6
    assert llm._retry_after(Exception("Please try again in 1m2s")) == 60.0
    assert llm._retry_after(Exception("slow down")) == 20.0


def test_focused_app_context_offers_only_app_tools():
    async def h(ctx, args):
        return ToolOutput(content="")

    reg = (ToolRegistry()
           .register(Tool("web_search", "Search", {"type": "object"}, h))
           .register(Tool("write_file", "Write", {"type": "object"}, h, scope="app")))
    names = lambda ctx: [t.name for t in reg.active(ctx)]  # noqa: E731
    assert names(ToolContext(None, "u", app_id="a", focused=True)) == ["write_file"]
    assert names(ToolContext(None, "u", app_id="a")) == ["web_search", "write_file"]
    assert names(ToolContext(None, "u")) == ["web_search"]
