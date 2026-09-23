"""The agent loop: model -> tool calls -> tool results -> model, until it answers.

Yields UI events as it goes:
  {"type": "text", "text"}                                   streamed answer text
  {"type": "tool_start", "id", "name", "label", "args"}      a tool call began
  {"type": "tool_end", "id", "name", "ok", "summary", "output", "media"}
  {"type": "heartbeat"}                                      a slow tool is still running
"""
import asyncio
import json
from typing import AsyncIterator, Callable, List

from .tools import ToolContext, ToolRegistry

MAX_STEPS = 8
HEARTBEAT_SECONDS = 10
UI_OUTPUT_CHARS = 4000


async def run_agent(stream_fn: Callable, registry: ToolRegistry, ctx: ToolContext,
                    model: str, messages: List[dict], use_tools: bool = True) -> AsyncIterator[dict]:
    tools = registry.schemas() if use_tools else []
    labels = {t.name: (t.label or t.name) for t in registry.active()}
    for step in range(MAX_STEPS):
        # Last step: withhold tools so the model must answer with what it has.
        step_tools = tools if step < MAX_STEPS - 1 else []
        text, calls = [], []
        async for ev in stream_fn(model, messages, step_tools):
            if ev["type"] == "text":
                text.append(ev["text"])
                yield ev
            elif ev["type"] == "tool_calls":
                calls = ev["calls"]
        if not calls:
            return
        if text:
            # Separate pre-tool narration from what comes next.
            yield {"type": "text", "text": "\n\n"}
        messages.append({
            "role": "assistant",
            "content": "".join(text) or None,
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in calls],
        })
        for call in calls:
            try:
                args = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {"_raw": call["arguments"]}
            yield {"type": "tool_start", "id": call["id"], "name": call["name"],
                   "label": labels.get(call["name"], call["name"]), "args": args}
            task = asyncio.create_task(registry.run(call["name"], call["arguments"], ctx))
            try:
                # Slow tools (video, browsing) run for minutes: keep the stream alive meanwhile.
                while not task.done():
                    await asyncio.wait({task}, timeout=HEARTBEAT_SECONDS)
                    if not task.done():
                        yield {"type": "heartbeat"}
            finally:
                if not task.done():
                    task.cancel()
            out = task.result()
            yield {"type": "tool_end", "id": call["id"], "name": call["name"], "ok": out.ok,
                   "summary": out.summary, "output": out.content[:UI_OUTPUT_CHARS], "media": out.media}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": out.content})
