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
SEQUENTIAL_TOOLS = {"browser"}
# Some models (Gemini Flash Lite) sometimes end a turn after their tool calls without a word.
ANSWER_NUDGE = ("Now answer my question in plain words, using the tool results above. Don't call any more "
                "tools.")


async def run_agent(stream_fn: Callable, registry: ToolRegistry, ctx: ToolContext,
                    model: str, messages: List[dict], use_tools: bool = True,
                    max_steps: int = MAX_STEPS) -> AsyncIterator[dict]:
    tools = registry.schemas(ctx) if use_tools else []
    labels = {t.name: (t.label or t.name) for t in registry.active(ctx)}
    said = False
    for step in range(max_steps):
        # Last step: withhold tools so the model must answer with what it has.
        step_tools = tools if step < max_steps - 1 else []
        text, calls = [], []
        async for ev in stream_fn(model, messages, step_tools):
            if ev["type"] == "text":
                text.append(ev["text"])
                said = said or bool(ev["text"].strip())
                yield ev
            elif ev["type"] == "tool_calls":
                calls = ev["calls"]
            elif ev["type"] == "heartbeat":
                yield ev
        if not calls:
            if not said and step > 0 and not ctx.app_id:
                # Tools ran but nothing was said: ask once more, without tools, for the answer itself.
                messages.append({"role": "user", "content": ANSWER_NUDGE})
                async for ev in stream_fn(model, messages, []):
                    if ev["type"] in ("text", "heartbeat"):
                        yield ev
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
        # Calls from one step run at the same time (several searches, an image and a file...), except
        # calls to a tool that keeps state between calls (the browser), which run one after another.
        tasks, last = [], {}
        for call in calls:
            task = asyncio.create_task(_after(last.get(call["name"]),
                                              lambda c=call: registry.run(c["name"], c["arguments"], ctx)))
            if call["name"] in SEQUENTIAL_TOOLS:
                last[call["name"]] = task
            tasks.append(task)
        reported = set()
        try:
            while len(reported) < len(tasks):
                for i, (call, task) in enumerate(zip(calls, tasks)):
                    if task.done() and i not in reported:
                        reported.add(i)
                        out = task.result()
                        yield {"type": "tool_end", "id": call["id"], "name": call["name"], "ok": out.ok,
                               "summary": out.summary, "output": out.content[:UI_OUTPUT_CHARS], "media": out.media}
                running = [t for t in tasks if not t.done()]
                if running:
                    # Slow tools (video, browsing) run for minutes: keep the stream alive meanwhile.
                    done, _ = await asyncio.wait(running, timeout=HEARTBEAT_SECONDS,
                                                 return_when=asyncio.FIRST_COMPLETED)
                    if not done:
                        yield {"type": "heartbeat"}
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
        for call, task in zip(calls, tasks):
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": task.result().content})


async def _after(prev, run):
    """Run run() once prev (an earlier task, or None) has finished."""
    if prev is not None:
        try:
            await asyncio.shield(prev)
        except Exception:
            pass
    return await run()
