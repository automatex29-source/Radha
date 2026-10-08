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
    run(collect(llm.stream_completion(GROQ, [{"role": "user", "content": "hi"}], [], max_output=llm.PLAIN_OUTPUT)))
    assert seen[0]["max_tokens"] == llm.PLAIN_OUTPUT
    run(collect(llm.stream_completion(GROQ, [{"role": "user", "content": "hi"}], [])))
    assert seen[1]["max_tokens"] > llm.PLAIN_OUTPUT  # decks and other JSON answers keep the full room


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


def test_gemini_out_of_free_requests_falls_back_to_groq(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    seen = fake_completion(monkeypatch, failures=1)
    events = run(collect(llm.stream_completion("gemini-2.5-flash", [{"role": "user", "content": "hi"}], [])))
    assert [kw["model"] for kw in seen] == ["gemini/gemini-3.5-flash-lite", "groq/openai/gpt-oss-120b"]  # old name -> current
    assert events == []


def test_gemini_blocked_key_falls_back_to_groq(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    seen = []

    async def acompletion(**kwargs):
        seen.append(kwargs)
        if len(seen) == 1:
            raise litellm.BadRequestError("Your project has been denied access. PERMISSION_DENIED", "gemini-2.5-flash",
                                          "gemini")
        return FakeStream()

    monkeypatch.setattr(litellm, "acompletion", acompletion)
    run(collect(llm.stream_completion("gemini-3.5-flash-lite", [{"role": "user", "content": "hi"}], [])))
    assert [kw["model"] for kw in seen] == ["gemini/gemini-3.5-flash-lite", "groq/openai/gpt-oss-120b"]


def test_gemini_without_groq_or_with_pictures_does_not_fall_back(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert llm.fallback_for("gemini-2.5-flash", [{"role": "user", "content": "hi"}]) is None
    monkeypatch.setenv("GROQ_API_KEY", "x")
    picture = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:x"}}]}]
    assert llm.fallback_for("gemini-2.5-flash", picture) is None


def test_gemini_busy_mid_stream_falls_back_before_any_text(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    seen = []

    class Busy:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise litellm.ServiceUnavailableError("model is experiencing high demand", "gemini", "gemini-3.5-flash-lite")

    async def acompletion(**kwargs):
        seen.append(kwargs)
        return Busy() if len(seen) == 1 else FakeStream() if len(seen) == 2 else Answer("Hello")

    monkeypatch.setattr(litellm, "acompletion", acompletion)
    monkeypatch.setattr(llm, "_GEMINI_RETRY_PAUSE", 0)
    events = run(collect(llm.stream_completion("gemini-3.5-flash-lite", [{"role": "user", "content": "hi"}], [])))
    # Busy: Gemini is asked once more, and Groq answers when Gemini still has nothing.
    assert [kw["model"] for kw in seen] == ["gemini/gemini-3.5-flash-lite", "gemini/gemini-3.5-flash-lite",
                                            "groq/openai/gpt-oss-120b"]
    assert events == [{"type": "text", "text": "Hello"}]


class Answer:
    """A stream that says `text`."""

    def __init__(self, text):
        self.chunks = [text]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        delta = type("Delta", (), {"content": self.chunks.pop(), "tool_calls": None})()
        choice = type("Choice", (), {"delta": delta, "finish_reason": "stop"})()
        return type("Chunk", (), {"choices": [choice]})()


def scripted(monkeypatch, replies):
    """Each call gets the next reply: an exception to raise, or the text to answer ("" = empty reply)."""
    seen = []

    async def acompletion(**kwargs):
        seen.append(kwargs["model"])
        reply = replies[len(seen) - 1]
        if isinstance(reply, Exception):
            raise reply
        return Answer(reply) if reply else FakeStream()

    monkeypatch.setattr(litellm, "acompletion", acompletion)
    monkeypatch.setattr(llm, "_GEMINI_RETRY_PAUSE", 0)
    return seen


def texts(events):
    return "".join(e["text"] for e in events if e["type"] == "text")


def test_gemini_empty_reply_is_asked_again(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    seen = scripted(monkeypatch, ["", "Hi there"])
    events = run(collect(llm.stream_completion("gemini-3.5-flash-lite", [{"role": "user", "content": "hi"}], [])))
    assert seen == ["gemini/gemini-3.5-flash-lite", "gemini/gemini-3.5-flash-lite"]
    assert texts(events) == "Hi there"


def test_gemini_silent_twice_hands_over_to_groq(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    seen = scripted(monkeypatch, [" ", "", "From Groq"])
    events = run(collect(llm.stream_completion("gemini-3.5-flash-lite", [{"role": "user", "content": "hi"}], [])))
    assert seen == ["gemini/gemini-3.5-flash-lite", "gemini/gemini-3.5-flash-lite", "groq/openai/gpt-oss-120b"]
    assert texts(events).strip() == "From Groq"


def test_gemini_out_of_requests_is_not_asked_again(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    quota = litellm.RateLimitError("You exceeded your current quota", "gemini", "gemini-3.5-flash-lite")
    seen = scripted(monkeypatch, [quota, "From Groq"])
    run(collect(llm.stream_completion("gemini-3.5-flash-lite", [{"role": "user", "content": "hi"}], [])))
    assert seen == ["gemini/gemini-3.5-flash-lite", "groq/openai/gpt-oss-120b"]


def test_cerebras_answers_when_gemini_and_groq_cannot(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("CEREBRAS_API_KEY", "x")
    quota = litellm.RateLimitError("You exceeded your current quota", "gemini", "gemini-3.5-flash-lite")
    groq_day = litellm.RateLimitError("Rate limit reached: tokens per day", "groq", GROQ)
    seen = scripted(monkeypatch, [quota, groq_day, groq_day, "From Cerebras"])
    events = run(collect(llm.stream_completion("gemini-3.5-flash-lite", [{"role": "user", "content": "hi"}], [])))
    assert seen == ["gemini/gemini-3.5-flash-lite", "groq/openai/gpt-oss-120b", "groq/openai/gpt-oss-20b",
                    "cerebras/gpt-oss-120b"]
    assert texts(events) == "From Cerebras"


def test_gemini_with_pictures_is_asked_again_then_errors(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    busy = litellm.ServiceUnavailableError("model is experiencing high demand", "gemini", "gemini-3.5-flash-lite")
    seen = scripted(monkeypatch, [busy, busy])
    picture = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:x"}}]}]
    try:
        run(collect(llm.stream_completion("gemini-3.5-flash-lite", picture, [])))
        raise AssertionError("expected the second failure to reach the chat")
    except litellm.ServiceUnavailableError:
        pass
    assert seen == ["gemini/gemini-3.5-flash-lite", "gemini/gemini-3.5-flash-lite"]


def test_gemini_tool_calls_are_sent_back_signed():
    call = {"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": '{"q": "news"}'}}
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": None, "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "c1", "content": "ok"}]
    sent = llm.request_kwargs("gemini-3.5-flash-lite", msgs, [])["messages"]
    block = sent[1]["thinking_blocks"][0]
    assert json.loads(block["thinking"]) == {"function_call": {"name": "web_search", "args": {"q": "news"}}}
    assert block["signature"] == "skip_thought_signature_validator"
    assert "thinking_blocks" not in msgs[1]  # the conversation itself is untouched
    assert "thinking_blocks" not in llm.request_kwargs(GROQ, msgs, [])["messages"][1]
