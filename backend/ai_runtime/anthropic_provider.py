"""Anthropic (Claude) provider (Emergent LLM integration, or LiteLLM with your own key)."""
from typing import AsyncIterator

from .base import ModelProvider
from .types import AIRequest
from ._backend import stream_text

_MODELS = {
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
}


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def supports(self, model: str) -> bool:
        return model in _MODELS

    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        async for delta in stream_text(self._api_key, "anthropic", request):
            yield delta
