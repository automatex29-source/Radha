"""Shared streaming helper for Emergent-backed providers.

Every provider that runs through the Emergent LLM integration shares the same
streaming mechanics; only the (provider, model) pair differs. Keeping this in
one place means adding a provider is a ~10-line class.
"""
from typing import AsyncIterator

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

from .types import AIRequest

_DEFAULT_SYSTEM = "You are RADHA, a premium AI assistant by A.utomateX."


async def stream_via_emergent(api_key: str, provider: str, request: AIRequest) -> AsyncIterator[str]:
    system = request.system or _DEFAULT_SYSTEM
    history = [{"role": m.role, "content": m.content} for m in request.messages[:-1]]

    chat = LlmChat(
        api_key=api_key,
        session_id=request.session_id,
        system_message=system,
        initial_messages=[{"role": "system", "content": system}] + history,
    ).with_model(provider, request.model)

    last = request.messages[-1]
    async for event in chat.stream_message(UserMessage(text=last.content)):
        if isinstance(event, TextDelta):
            yield event.content
        elif isinstance(event, StreamDone):
            break
