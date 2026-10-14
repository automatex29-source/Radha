"""OpenRouter provider (LiteLLM with OPENROUTER_API_KEY). Serves any "openrouter/..." model, such as the free
coding model Krish Coder."""
from typing import AsyncIterator

from .base import ModelProvider
from .types import AIRequest
from ._backend import stream_via_litellm


class OpenRouterProvider(ModelProvider):
    name = "openrouter"

    def supports(self, model: str) -> bool:
        return model.startswith("openrouter/")

    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        async for delta in stream_via_litellm(request):
            yield delta
