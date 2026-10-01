"""Tool-capable, multimodal LLM streaming via LiteLLM.

The Emergent chat integration streams plain text only, so agent turns and
messages with images go through LiteLLM, which speaks one OpenAI-style
interface (tools + image parts) for Anthropic, OpenAI, Gemini and Groq.

Keys: ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / GROQ_API_KEY, or route everything
through an OpenAI-compatible gateway with LLM_GATEWAY_URL + LLM_GATEWAY_KEY.
"""
import asyncio
import json
import logging
import os
import re
from typing import AsyncIterator, List, Optional

_PROVIDER_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY",
                 "groq": "GROQ_API_KEY"}


def provider_for(model: str) -> str:
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gemini"):
        return "gemini"
    if model.startswith(("llama", "openai/gpt-oss", "qwen/")):
        return "groq"
    return "openai"


def gateway() -> Optional[dict]:
    url = os.environ.get("LLM_GATEWAY_URL")
    return {"api_base": url, "api_key": os.environ.get("LLM_GATEWAY_KEY", "")} if url else None


def configured(model: str) -> bool:
    return bool(gateway() or os.environ.get(_PROVIDER_KEYS[provider_for(model)]))


def supports_images(model: str) -> bool:
    """False for text-only models (Groq's gpt-oss and qwen); their images are sent as text instead."""
    if gateway():
        return True
    return provider_for(model) != "groq" or "llama-4" in model or "vision" in model


def missing_key_message(model: str) -> str:
    return (f"To use {model}, set {_PROVIDER_KEYS[provider_for(model)]} (or LLM_GATEWAY_URL) in your "
            ".env file and restart Krish AI.")


# Groq's free tier allows about 8,000 tokens per minute per request, counting the prompt AND max_tokens,
# so Groq requests are trimmed to fit (override with GROQ_TPM on a paid plan).
_CHARS_PER_TOKEN = 3.0
_MIN_OUTPUT = 1500
_MAX_OUTPUT = 8192
_RATE_LIMIT_RETRIES = 3
_TOOL_CALL_RETRIES = 2
logger = logging.getLogger("radha.agent")
_HEARTBEAT_SECONDS = 10
# Groq counts max_tokens against the per-minute budget, so a plain answer (no tools) asks for less room
# and the next message isn't kept waiting.
_PLAIN_OUTPUT = 3000
# Groq's limits are per model: when the big model is rate limited, its smaller sibling answers right away
# instead of the user waiting up to a minute.
_FALLBACK = {"openai/gpt-oss-120b": "openai/gpt-oss-20b"}


def lean(model: str) -> bool:
    """True when the model has a small per-minute token budget (Groq's free tier)."""
    return provider_for(model) == "groq" and not gateway()


def token_budget() -> int:
    try:
        return int(os.environ.get("GROQ_TPM", "8000")) - 300
    except ValueError:
        return 7700


def estimate_tokens(obj) -> int:
    return int(len(json.dumps(obj, ensure_ascii=False)) / _CHARS_PER_TOKEN) + 1


def _shorten(text: str, keep: int) -> str:
    return text if len(text) <= keep else text[:keep] + f"\n… [{len(text) - keep} chars omitted]"


def _compact_call(call: dict) -> dict:
    """Replace a large tool-call argument (e.g. a whole written file) with a placeholder."""
    args = call["function"].get("arguments") or ""
    if len(args) <= 400:
        return call
    try:
        parsed = json.loads(args)
        parsed = {k: (f"[{len(v)} chars, omitted to save space]" if isinstance(v, str) and len(v) > 200 else v)
                  for k, v in parsed.items()} if isinstance(parsed, dict) else {}
        args = json.dumps(parsed)
    except json.JSONDecodeError:
        args = "{}"
    return {**call, "function": {**call["function"], "arguments": args}}


def fit_messages(messages: List[dict], tools: List[dict], budget: int) -> List[dict]:
    """Shrink a conversation so the prompt leaves room for at least _MIN_OUTPUT tokens.

    1. Older tool results and tool-call arguments are shortened (the latest step stays intact).
    2. If that isn't enough, the oldest turns are dropped, keeping the system prompt and
       never splitting an assistant tool call from its results.
    """
    limit = budget - _MIN_OUTPUT - estimate_tokens(tools)
    if estimate_tokens(messages) <= limit:
        return messages
    last_call = max((i for i, m in enumerate(messages) if m.get("tool_calls")), default=len(messages))
    out = []
    for i, m in enumerate(messages):
        if i < last_call and m["role"] == "tool":
            m = {**m, "content": _shorten(m.get("content") or "", 600)}
        elif i < last_call and m.get("tool_calls"):
            m = {**m, "tool_calls": [_compact_call(c) for c in m["tool_calls"]]}
        elif i < len(messages) - 1 and m["role"] in ("user", "assistant") and isinstance(m.get("content"), str):
            m = {**m, "content": _shorten(m["content"], 2000)}
        out.append(m)
    head = [m for m in out[:1] if m["role"] == "system"]
    rest = out[len(head):]
    while len(rest) > 1 and estimate_tokens(head + rest) > limit:
        rest = rest[1:]
        while len(rest) > 1 and rest[0]["role"] == "tool":
            rest = rest[1:]  # a tool result can't start the conversation
    if estimate_tokens(head + rest) > limit and head:
        head = [{**head[0], "content": _shorten(head[0]["content"], max(1000, int(limit * _CHARS_PER_TOKEN * 0.5)))}]
    return head + rest


def _retry_after(exc: Exception) -> float:
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(exc))
    if not m:
        return 20.0
    return min(60.0, int(m.group(1) or 0) * 60 + float(m.group(2)) + 0.5)


def _bad_tool_call(exc: Exception) -> bool:
    """Groq rejects a tool call whose arguments don't match the schema; asking again usually works."""
    text = str(exc).lower()
    return "tool call validation failed" in text or "tool_use_failed" in text or "failed to call a function" in text


async def stream_completion(model: str, messages: List[dict], tools: List[dict],
                            think: bool = False) -> AsyncIterator[dict]:
    """Yield {"type": "text", "text"} deltas, then one {"type": "tool_calls", "calls"} if the model called tools.

    While waiting out a rate limit it yields {"type": "heartbeat"} so the stream stays open. A rejected tool
    call is retried (up to _TOOL_CALL_RETRIES times) as long as nothing but heartbeats was sent yet.
    `think` (the Think button) asks reasoning models to reason longer before answering.
    """
    for attempt in range(_TOOL_CALL_RETRIES + 1):
        sent = False
        try:
            async for event in _stream_once(model, messages, tools, think):
                sent = sent or event["type"] != "heartbeat"
                yield event
            return
        except Exception as exc:
            if sent or attempt == _TOOL_CALL_RETRIES or not _bad_tool_call(exc):
                raise
            logger.warning("model sent an invalid tool call, asking again: %s", str(exc)[:300])


def reasoning_effort(model: str, think: bool) -> Optional[str]:
    """How hard a reasoning model should think. Groq's free budget counts reasoning, so Think there is "medium"."""
    if lean(model):
        if not model.startswith("openai/gpt-oss"):
            return None
        return "medium" if think else "low"
    return "high" if think else None


async def _stream_once(model: str, messages: List[dict], tools: List[dict], think: bool = False) -> AsyncIterator[dict]:
    import litellm

    kwargs = {"model": f"{provider_for(model)}/{model}", "messages": messages, "stream": True, "max_tokens": _MAX_OUTPUT}
    gw = gateway()
    if gw:
        kwargs.update(model=f"openai/{model}", **gw)
    if tools:
        kwargs["tools"] = tools
    if lean(model):
        budget = token_budget()
        fitted = fit_messages(messages, tools, budget)
        room = budget - estimate_tokens(fitted) - estimate_tokens(tools)
        cap = _MAX_OUTPUT if tools else _PLAIN_OUTPUT
        kwargs.update(messages=fitted, max_tokens=max(_MIN_OUTPUT // 2, min(cap, room)))
    effort = reasoning_effort(model, think)
    if effort:
        kwargs.update(reasoning_effort=effort, drop_params=True)

    fallback = _FALLBACK.get(model) if lean(model) else None
    attempt = 0
    while True:
        try:
            resp = await litellm.acompletion(**kwargs)
            break
        except litellm.RateLimitError as exc:
            if fallback:
                logger.info("%s is rate limited, answering with %s", model, fallback)
                kwargs["model"] = f"{provider_for(fallback)}/{fallback}"
                fallback = None
                continue
            if attempt == _RATE_LIMIT_RETRIES or "per day" in str(exc).lower():
                raise
            attempt += 1
            wait = _retry_after(exc)
            while wait > 0:
                await asyncio.sleep(min(wait, _HEARTBEAT_SECONDS))
                wait -= _HEARTBEAT_SECONDS
                yield {"type": "heartbeat"}

    calls = {}
    async for chunk in resp:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if getattr(delta, "content", None):
            yield {"type": "text", "text": delta.content}
        for tc in getattr(delta, "tool_calls", None) or []:
            slot = calls.setdefault(tc.index if tc.index is not None else len(calls),
                                    {"id": None, "name": "", "arguments": ""})
            if tc.id:
                slot["id"] = tc.id
            fn = tc.function
            if fn is not None:
                if fn.name:
                    slot["name"] = fn.name if fn.name.startswith(slot["name"]) else slot["name"] + fn.name
                if fn.arguments:
                    slot["arguments"] += fn.arguments
    if calls:
        ordered = [calls[k] for k in sorted(calls)]
        for i, c in enumerate(ordered):
            c["id"] = c["id"] or f"call_{i}"
        yield {"type": "tool_calls", "calls": ordered}
