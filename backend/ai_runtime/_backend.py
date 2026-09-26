"""Chooses how plain chat reaches a model.

On Emergent (emergentintegrations installed and AI_API_KEY set) chat streams
through the Emergent LLM integration. Everywhere else it goes through LiteLLM
with your own provider keys (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)
or an OpenAI-compatible gateway (LLM_GATEWAY_URL).
"""
from typing import AsyncIterator

from .types import AIRequest

try:
    from ._emergent import stream_via_emergent

    EMERGENT_AVAILABLE = True
except ImportError:  # running outside Emergent
    EMERGENT_AVAILABLE = False

_DEFAULT_SYSTEM = "You are RADHA, a premium AI assistant by A.utomateX."


def uses_emergent(api_key: str) -> bool:
    return EMERGENT_AVAILABLE and bool(api_key)


async def stream_via_litellm(request: AIRequest) -> AsyncIterator[str]:
    from agent import llm  # shares key/gateway handling with agent mode

    messages = [{"role": "system", "content": request.system or _DEFAULT_SYSTEM}]
    messages += [{"role": m.role, "content": m.content} for m in request.messages]
    async for event in llm.stream_completion(request.model, messages, []):
        if event["type"] == "text":
            yield event["text"]


async def stream_text(api_key: str, provider: str, request: AIRequest) -> AsyncIterator[str]:
    if uses_emergent(api_key):
        async for delta in stream_via_emergent(api_key, provider, request):
            yield delta
    else:
        async for delta in stream_via_litellm(request):
            yield delta
