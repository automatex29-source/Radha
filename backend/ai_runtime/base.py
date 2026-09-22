"""Provider abstraction.

Every concrete model provider (Anthropic today; OpenAI / Gemini / future
A.utomateX models later) implements this interface. The chat system only ever
talks to a ModelProvider, never to a vendor SDK directly.
"""
from abc import ABC, abstractmethod
from typing import AsyncIterator

from .types import AIRequest, AIResponse


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, model: str) -> bool:
        """Whether this provider can serve the requested model id."""
        raise NotImplementedError

    @abstractmethod
    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        """Yield text deltas as they arrive from the model."""
        raise NotImplementedError
        yield  # pragma: no cover
