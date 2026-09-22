"""Model router.

RADHA -> AI Runtime -> ModelRouter -> ModelProvider -> LLM

The router owns the registry of providers and resolves an incoming model id
to the provider that serves it. New providers are added by registering them
here; the chat system never changes.
"""
from typing import AsyncIterator, List

from .base import ModelProvider
from .types import AIRequest


class ModelRouter:
    def __init__(self, default_model: str):
        self._providers: List[ModelProvider] = []
        self._default_model = default_model

    def register(self, provider: ModelProvider) -> "ModelRouter":
        self._providers.append(provider)
        return self

    def resolve(self, model: str) -> ModelProvider:
        for provider in self._providers:
            if provider.supports(model):
                return provider
        raise ValueError(f"No registered provider supports model '{model}'")

    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        model = request.model or self._default_model
        provider = self.resolve(model)
        async for delta in provider.stream(request):
            yield delta
