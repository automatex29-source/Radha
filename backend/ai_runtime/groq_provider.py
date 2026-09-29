"""Groq provider (LiteLLM with GROQ_API_KEY; free tier at console.groq.com).

The Emergent integration doesn't serve Groq, so this always goes through LiteLLM.
"""
from typing import AsyncIterator

from .base import ModelProvider
from .types import AIRequest
from ._backend import stream_via_litellm

_MODELS = {"llama-3.3-70b-versatile", "llama-3.1-8b-instant"}


class GroqProvider(ModelProvider):
    name = "groq"

    def supports(self, model: str) -> bool:
        return model in _MODELS

    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        async for delta in stream_via_litellm(request):
            yield delta
