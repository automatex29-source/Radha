"""Anthropic (Claude) provider backed by the Emergent LLM integration.

This is the single concrete provider implemented for V1. It wraps
emergentintegrations' LlmChat and exposes it through the generic
ModelProvider interface so the rest of RADHA stays vendor-neutral.
"""
from typing import AsyncIterator

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

from .base import ModelProvider
from .types import AIRequest

_ANTHROPIC_MODELS = {
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
        return model in _ANTHROPIC_MODELS

    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        system = request.system or "You are RADHA, a premium AI assistant by A.utomateX."

        # History (everything except the final user turn) is replayed to the model.
        history = []
        for m in request.messages[:-1]:
            history.append({"role": m.role, "content": m.content})

        chat = LlmChat(
            api_key=self._api_key,
            session_id=request.session_id,
            system_message=system,
            initial_messages=[{"role": "system", "content": system}] + history,
        ).with_model("anthropic", request.model)

        last = request.messages[-1]
        async for event in chat.stream_message(UserMessage(text=last.content)):
            if isinstance(event, TextDelta):
                yield event.content
            elif isinstance(event, StreamDone):
                break
