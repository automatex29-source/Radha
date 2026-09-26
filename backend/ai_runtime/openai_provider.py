"""OpenAI provider (Emergent LLM integration, or LiteLLM with your own key)."""
from typing import AsyncIterator

from .base import ModelProvider
from .types import AIRequest
from ._backend import stream_text

_MODELS = {"gpt-5.4", "gpt-5.4-mini", "gpt-5.2"}


class OpenAIProvider(ModelProvider):
    name = "openai"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def supports(self, model: str) -> bool:
        return model in _MODELS

    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        async for delta in stream_text(self._api_key, "openai", request):
            yield delta
