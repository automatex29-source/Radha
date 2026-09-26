"""Tool-capable, multimodal LLM streaming via LiteLLM.

The Emergent chat integration streams plain text only, so agent turns and
messages with images go through LiteLLM, which speaks one OpenAI-style
interface (tools + image parts) for Anthropic, OpenAI and Gemini.

Keys: ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY, or route everything
through an OpenAI-compatible gateway with LLM_GATEWAY_URL + LLM_GATEWAY_KEY.
"""
import os
from typing import AsyncIterator, List, Optional

_PROVIDER_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def provider_for(model: str) -> str:
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gemini"):
        return "gemini"
    return "openai"


def gateway() -> Optional[dict]:
    url = os.environ.get("LLM_GATEWAY_URL")
    return {"api_base": url, "api_key": os.environ.get("LLM_GATEWAY_KEY", "")} if url else None


def configured(model: str) -> bool:
    return bool(gateway() or os.environ.get(_PROVIDER_KEYS[provider_for(model)]))


def missing_key_message(model: str) -> str:
    return (f"To use {model}, set {_PROVIDER_KEYS[provider_for(model)]} (or LLM_GATEWAY_URL) in your "
            ".env file and restart RADHA.")


async def stream_completion(model: str, messages: List[dict], tools: List[dict]) -> AsyncIterator[dict]:
    """Yield {"type": "text", "text"} deltas, then one {"type": "tool_calls", "calls"} if the model called tools."""
    import litellm

    kwargs = {"model": f"{provider_for(model)}/{model}", "messages": messages, "stream": True, "max_tokens": 8192}
    gw = gateway()
    if gw:
        kwargs.update(model=f"openai/{model}", **gw)
    if tools:
        kwargs["tools"] = tools
    resp = await litellm.acompletion(**kwargs)

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
