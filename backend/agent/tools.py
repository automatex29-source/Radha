"""Agent tool-use framework: tool definitions, registry, and the built-in tools.

A tool is a name, a description, a JSON-schema for its arguments, and an async
handler. The registry exposes OpenAI-style function schemas to the model and
runs calls safely (bad arguments or handler errors come back to the model as
tool errors instead of crashing the turn). Adding a tool = one `register()`.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import media
from . import sandbox, web

logger = logging.getLogger("radha.agent")

MAX_TOOL_CONTENT = 16_000


@dataclass
class ToolContext:
    db: Any
    user_id: str
    conversation_id: Optional[str] = None


@dataclass
class ToolOutput:
    content: str  # what the model sees
    summary: str = ""  # one line for the UI
    media: List[dict] = field(default_factory=list)  # public_media dicts to show in the UI
    ok: bool = True


Handler = Callable[[ToolContext, dict], Awaitable[ToolOutput]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Handler
    label: str = ""
    available: Callable[[], bool] = lambda: True

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> "ToolRegistry":
        self._tools[tool.name] = tool
        return self

    def active(self) -> List[Tool]:
        return [t for t in self._tools.values() if t.available()]

    def schemas(self) -> List[dict]:
        return [t.schema() for t in self.active()]

    def describe(self) -> List[dict]:
        return [{"name": t.name, "label": t.label or t.name, "available": t.available()} for t in self._tools.values()]

    async def run(self, name: str, raw_args: str, ctx: ToolContext) -> ToolOutput:
        tool = self._tools.get(name)
        if not tool or not tool.available():
            return ToolOutput(content=f"Error: unknown or unavailable tool '{name}'.", summary="Unknown tool", ok=False)
        try:
            args = json.loads(raw_args or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (ValueError, json.JSONDecodeError) as exc:
            return ToolOutput(content=f"Error: invalid JSON arguments ({exc}).", summary="Invalid arguments", ok=False)
        try:
            out = await tool.handler(ctx, args)
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return ToolOutput(content=f"Error running {name}: {exc}", summary=str(exc)[:160], ok=False)
        if len(out.content) > MAX_TOOL_CONTENT:
            out.content = out.content[:MAX_TOOL_CONTENT] + "\n… [truncated]"
        return out


# ------------------------------------------------------------ built-in tools
def _require(args: dict, key: str) -> str:
    val = args.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"'{key}' is required")
    return val.strip()


async def _web_search(ctx: ToolContext, args: dict) -> ToolOutput:
    query = _require(args, "query")
    results = await web.search(query, int(args.get("max_results") or 6))
    if not results:
        return ToolOutput(content="No results found.", summary=f"No results for “{query}”")
    lines = [f"{i + 1}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results)]
    return ToolOutput(content="\n".join(lines), summary=f"{len(results)} results for “{query}”")


async def _fetch_url(ctx: ToolContext, args: dict) -> ToolOutput:
    url = _require(args, "url")
    page = await web.fetch_page(url)
    links = "\n".join(f"- [{l['text']}]({l['url']})" for l in page["links"])
    content = f"URL: {page['url']}\nStatus: {page['status']}\nTitle: {page['title']}\n\n{page['text']}"
    if links:
        content += f"\n\nLinks on the page:\n{links}"
    return ToolOutput(content=content, summary=f"Read {page['title'] or page['url']}"[:160])


async def _run_python(ctx: ToolContext, args: dict) -> ToolOutput:
    code = _require(args, "code")
    res = await sandbox.run_python(code)
    saved = []
    for art in res.artifacts:
        try:
            saved.append(await media.save_media(ctx.db, ctx.user_id, art.data, art.content_type, "code_output",
                                                name=art.name, conversation_id=ctx.conversation_id))
        except ValueError:
            pass
    parts = []
    if res.stdout:
        parts.append(f"stdout:\n{res.stdout}")
    if res.stderr:
        parts.append(f"stderr:\n{res.stderr}")
    if res.timed_out:
        parts.append(f"Timed out after {sandbox.WALL_SECONDS}s and was killed.")
    else:
        parts.append(f"exit code: {res.exit_code}")
    if saved:
        parts.append("Files produced (already shown to the user): " + ", ".join(m["name"] for m in saved))
    ok = not res.timed_out and res.exit_code == 0
    summary = "Ran successfully" if ok else ("Timed out" if res.timed_out else f"Exited with code {res.exit_code}")
    return ToolOutput(content="\n\n".join(parts), summary=summary, media=saved, ok=ok)


async def _generate_image(ctx: ToolContext, args: dict) -> ToolOutput:
    prompt = _require(args, "prompt")
    data = await media.generate_image(prompt, args.get("size") or "1024x1024")
    saved = await media.save_media(ctx.db, ctx.user_id, data, "image/png", "generated",
                                   name="image.png", conversation_id=ctx.conversation_id)
    return ToolOutput(content="Image generated and shown to the user. Do not embed it; just describe it briefly.",
                      summary=f"Generated “{prompt[:80]}”", media=[saved])


def default_registry() -> ToolRegistry:
    return (
        ToolRegistry()
        .register(Tool(
            name="web_search", label="Web search",
            description="Search the web for current information. Returns titles, URLs and snippets. "
                        "Follow up with fetch_url to read a result in full.",
            parameters={"type": "object", "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "1-10, default 6"},
            }, "required": ["query"]},
            handler=_web_search))
        .register(Tool(
            name="fetch_url", label="Read web page",
            description="Fetch a public web page and return its readable text and main links.",
            parameters={"type": "object", "properties": {
                "url": {"type": "string", "description": "Absolute http(s) URL"},
            }, "required": ["url"]},
            handler=_fetch_url))
        .register(Tool(
            name="run_python", label="Run Python",
            description="Execute Python 3 code in an isolated sandbox with no network access and a "
                        f"{sandbox.WALL_SECONDS}s limit. Print results to stdout. Files written to the "
                        "current directory (png, csv, json, txt, md, html, svg) are returned to the user, "
                        "so save charts with plt.savefig('chart.png'). Only the standard library is guaranteed.",
            parameters={"type": "object", "properties": {
                "code": {"type": "string", "description": "Complete Python program"},
            }, "required": ["code"]},
            handler=_run_python))
        .register(Tool(
            name="generate_image", label="Generate image",
            description="Create an image from a detailed text description.",
            parameters={"type": "object", "properties": {
                "prompt": {"type": "string", "description": "Detailed description of the image"},
                "size": {"type": "string", "enum": ["1024x1024", "1536x1024", "1024x1536"]},
            }, "required": ["prompt"]},
            handler=_generate_image, available=media.openai_configured))
    )
