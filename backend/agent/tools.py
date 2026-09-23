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
from . import browser, documents, sandbox, video, web

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


async def _save_file(ctx: ToolContext, data: bytes, ext: str, filename: str) -> dict:
    name = documents.safe_filename(filename, ext)
    return await media.save_media(ctx.db, ctx.user_id, data, documents.CONTENT_TYPES[ext], "document",
                                  name=name, conversation_id=ctx.conversation_id)


async def _create_spreadsheet(ctx: ToolContext, args: dict) -> ToolOutput:
    sheets = args.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise ValueError("'sheets' must be a non-empty list")
    saved = await _save_file(ctx, documents.build_xlsx(sheets), "xlsx", args.get("filename") or "spreadsheet")
    rows = sum(len(s.get("rows") or []) for s in sheets)
    return ToolOutput(content=f"Created {saved['name']} ({len(sheets)} sheet(s), {rows} rows). It is shown to the user "
                              "with a preview and download button; don't paste its contents.",
                      summary=f"Created {saved['name']}", media=[saved])


async def _create_presentation(ctx: ToolContext, args: dict) -> ToolOutput:
    slides = args.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("'slides' must be a non-empty list")
    data = documents.build_pptx(slides, title=args.get("title") or "", theme=args.get("theme") or "dark")
    saved = await _save_file(ctx, data, "pptx", args.get("filename") or args.get("title") or "presentation")
    return ToolOutput(content=f"Created {saved['name']} with {len(slides)} slides. It is shown to the user with a "
                              "preview and download button.", summary=f"Created {saved['name']}", media=[saved])


async def _create_document(ctx: ToolContext, args: dict) -> ToolOutput:
    fmt = (args.get("format") or "docx").lower()
    if fmt not in ("docx", "pdf"):
        raise ValueError("format must be 'docx' or 'pdf'")
    markdown = _require(args, "markdown")
    title = args.get("title") or ""
    data = documents.build_docx(markdown, title) if fmt == "docx" else documents.build_pdf(markdown, title)
    saved = await _save_file(ctx, data, fmt, args.get("filename") or title or "document")
    return ToolOutput(content=f"Created {saved['name']}. It is shown to the user with a preview and download button.",
                      summary=f"Created {saved['name']}", media=[saved])


async def _create_html(ctx: ToolContext, args: dict) -> ToolOutput:
    page = _require(args, "html")
    if "<html" not in page.lower():
        page = f"<!doctype html>\n<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'></head><body>\n{page}\n</body></html>"
    saved = await _save_file(ctx, page.encode("utf-8"), "html", args.get("filename") or "page")
    return ToolOutput(content=f"Created {saved['name']}. The user sees a live preview of it.",
                      summary=f"Created {saved['name']}", media=[saved])


async def _generate_video(ctx: ToolContext, args: dict) -> ToolOutput:
    prompt = _require(args, "prompt")
    data, ctype = await video.generate_video(prompt, int(args.get("seconds") or 8), args.get("orientation") or "landscape")
    saved = await media.save_media(ctx.db, ctx.user_id, data, ctype, "generated", name="video.mp4",
                                   conversation_id=ctx.conversation_id)
    return ToolOutput(content="Video generated and shown to the user. Briefly describe what you asked for.",
                      summary=f"Generated video “{prompt[:70]}”", media=[saved])


async def _browser(ctx: ToolContext, args: dict) -> ToolOutput:
    action = _require(args, "action")
    snap = await browser.manager.act(f"{ctx.user_id}:{ctx.conversation_id}", action, args)
    shot = await media.save_media(ctx.db, ctx.user_id, snap["screenshot"], "image/jpeg", "screenshot",
                                  name="screenshot.jpg", conversation_id=ctx.conversation_id)
    return ToolOutput(content=browser.describe(snap), summary=f"{snap['title'] or snap['url']}"[:160], media=[shot])


_CELL_NOTE = "Cell values as strings; numeric strings become numbers and strings starting with '=' become Excel formulas."


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
        .register(Tool(
            name="create_spreadsheet", label="Create Excel file",
            description="Create an Excel .xlsx workbook with styled headers, optional number formats, formulas and a "
                        "native chart per sheet. " + _CELL_NOTE,
            parameters={"type": "object", "properties": {
                "filename": {"type": "string"},
                "sheets": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "columns": {"type": "array", "items": {"type": "string"}, "description": "Header row"},
                    "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                    "column_formats": {"type": "object", "description": "Column name -> Excel number format, e.g. {\"Revenue\": \"$#,##0.00\", \"Share\": \"0.0%\"}"},
                    "chart": {"type": "object", "properties": {
                        "type": {"type": "string", "enum": ["bar", "line", "pie"]},
                        "title": {"type": "string"},
                        "category_column": {"type": "string"},
                        "value_columns": {"type": "array", "items": {"type": "string"}},
                    }},
                }, "required": ["name", "rows"]}},
            }, "required": ["filename", "sheets"]},
            handler=_create_spreadsheet))
        .register(Tool(
            name="create_presentation", label="Create PowerPoint",
            description="Create a designed 16:9 PowerPoint .pptx deck. Layouts: title, section, bullets, two_column, "
                        "table, quote. Keep bullets short (max ~6 per slide); indent a bullet with two leading spaces "
                        "to nest it. Put detail in speaker notes.",
            parameters={"type": "object", "properties": {
                "filename": {"type": "string"},
                "title": {"type": "string"},
                "theme": {"type": "string", "enum": ["dark", "light"]},
                "slides": {"type": "array", "items": {"type": "object", "properties": {
                    "layout": {"type": "string", "enum": ["title", "section", "bullets", "two_column", "table", "quote"]},
                    "title": {"type": "string"},
                    "subtitle": {"type": "string", "description": "title/section/quote slides (quote: attribution)"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                    "left_title": {"type": "string"}, "left": {"type": "array", "items": {"type": "string"}},
                    "right_title": {"type": "string"}, "right": {"type": "array", "items": {"type": "string"}},
                    "table": {"type": "object", "properties": {
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                    }},
                    "quote": {"type": "string"},
                    "notes": {"type": "string", "description": "Speaker notes"},
                }, "required": ["layout", "title"]}},
            }, "required": ["filename", "slides"]},
            handler=_create_presentation))
        .register(Tool(
            name="create_document", label="Create document",
            description="Create a Word (.docx) or PDF document from Markdown: headings, bold/italic, links, nested "
                        "lists, block quotes, tables and code blocks are all formatted properly.",
            parameters={"type": "object", "properties": {
                "filename": {"type": "string"},
                "format": {"type": "string", "enum": ["docx", "pdf"]},
                "title": {"type": "string"},
                "markdown": {"type": "string", "description": "Full document content in Markdown"},
            }, "required": ["filename", "format", "markdown"]},
            handler=_create_document))
        .register(Tool(
            name="create_html", label="Create web page",
            description="Create a self-contained HTML page (inline CSS/JS; CDN scripts allowed) that the user can "
                        "preview live and download: landing pages, dashboards, reports, small apps and games.",
            parameters={"type": "object", "properties": {
                "filename": {"type": "string"},
                "html": {"type": "string", "description": "Complete HTML document"},
            }, "required": ["filename", "html"]},
            handler=_create_html))
        .register(Tool(
            name="generate_video", label="Generate video",
            description="Generate a short video clip from a detailed text description (subject, action, camera, "
                        "style, lighting). Takes one to several minutes.",
            parameters={"type": "object", "properties": {
                "prompt": {"type": "string"},
                "seconds": {"type": "integer", "description": "4, 8 or 12 (default 8)"},
                "orientation": {"type": "string", "enum": ["landscape", "portrait"]},
            }, "required": ["prompt"]},
            handler=_generate_video, available=video.available))
        .register(Tool(
            name="browser", label="Browser",
            description="Control a real web browser to use websites interactively (search forms, navigation, "
                        "multi-page tasks, JavaScript-heavy sites). Actions: open {url}; click {ref}; type {ref, text, "
                        "submit}; press {key}; scroll {direction}; back; read (full page text); wait {seconds}. Every "
                        "result lists interactive elements as [ref] to use in the next action. Prefer fetch_url for "
                        "simply reading a page. Never enter passwords or payment details.",
            parameters={"type": "object", "properties": {
                "action": {"type": "string", "enum": ["open", "click", "type", "press", "scroll", "back", "read", "wait"]},
                "url": {"type": "string"},
                "ref": {"type": "integer", "description": "Element number from the last result"},
                "text": {"type": "string", "description": "Text to type"},
                "submit": {"type": "boolean", "description": "Press Enter after typing"},
                "key": {"type": "string", "description": "e.g. Enter, Tab, Escape, ArrowDown"},
                "direction": {"type": "string", "enum": ["up", "down"]},
                "seconds": {"type": "number"},
                "selector": {"type": "string", "description": "CSS selector, only if no ref fits"},
            }, "required": ["action"]},
            handler=_browser, available=browser.available))
    )
