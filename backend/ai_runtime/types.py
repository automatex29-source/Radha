"""Core AI runtime data structures.

These provider-agnostic types are the contract between RADHA's chat system
and any underlying model provider. Adding a new provider must not require
changing these shapes.
"""
from dataclasses import dataclass, field
from typing import List, Literal, Optional

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class AIRequest:
    """A single inference request flowing through the runtime."""
    messages: List[ChatMessage]
    model: str
    system: Optional[str] = None
    session_id: str = "radha-session"
    max_tokens: int = 4096


@dataclass
class AIResponse:
    """Aggregated response metadata (used for non-streaming callers)."""
    content: str
    model: str
    provider: str
    usage: dict = field(default_factory=dict)
