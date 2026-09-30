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
from . import browser, documents, prompt_boost, research, sandbox, styles, video, web

logger = logging.getLogger("radha.agent")

MAX_TOOL_CONTENT = 16_000


@dataclass
class ToolContext:
    db: Any
    user_id: str
    conversation_id: Optional[str] = None
    app_id: Optional[str] = None
    focused: bool = False  # in an app, offer only the app tools (keeps prompts small for free models)
    model: str = ""  # the chat model, for tools that call a model themselves (deep_research)


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
    scope: str = "general"  # "app" tools are only offered inside an app-builder conversation

    def usable(self, ctx: Optional[ToolContext]) -> bool:
        if self.scope == "app" and not (ctx and ctx.app_id):
            return False
        if self.scope != "app" and ctx and ctx.app_id and ctx.focused:
            return False
        return self.available()

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> "ToolRegistry":
        self._tools[tool.name] = tool
        return self

    def active(self, ctx: Optional[ToolContext] = None) -> List[Tool]:
        return [t for t in self._tools.values() if t.usable(ctx)]

    def schemas(self, ctx: Optional[ToolContext] = None) -> List[dict]:
        return [t.schema() for t in self.active(ctx)]

    def describe(self) -> List[dict]:
        return [{"name": t.name, "label": t.label or t.name, "available": t.available(), "scope": t.scope}
                for t in self._tools.values()]

    async def run(self, name: str, raw_args: str, ctx: ToolContext) -> ToolOutput:
        tool = self._tools.get(name)
        if not tool or not tool.usable(ctx):
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
    rates = ""
    if web.CURRENCY.search(query):  # live rates beat search snippets for currency questions
        try:
            rates = await web.exchange_rates(query)
        except Exception as exc:
            logger.warning("Exchange rates failed: %s", exc)
            rates = ""
    try:
        results = await web.search(query, int(args.get("max_results") or 6))
    except Exception:
        if not rates:
            raise
        results = []
    lines = [f"{i + 1}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results)]
    content = "\n\n".join(part for part in (rates, "\n".join(lines)) if part)
    if not content:
        return ToolOutput(content="No results found. Try a simpler or corrected query.", summary=f"No results for “{query}”")
    return ToolOutput(content=content, summary=f"{len(results)} results for “{query}”" + (" + live rates" if rates else ""))


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
    final = await prompt_boost.image_prompt(prompt, args.get("style") or "")
    data = await media.generate_image(final, args.get("size") or "1024x1024", args.get("quality"))
    ctype = media.image_type(data) or "image/png"
    ext = {"image/jpeg": "jpg", "image/webp": "webp"}.get(ctype, "png")
    name = documents.safe_filename(args.get("filename") or prompt[:40] or "image", ext)
    saved = await media.save_media(ctx.db, ctx.user_id, data, ctype, "generated",
                                   name=name, conversation_id=ctx.conversation_id)
    return ToolOutput(content="Image generated and shown to the user with a download button. Do not embed it or "
                              "paste a link; just describe it in one short sentence.",
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


async def _deep_research(ctx: ToolContext, args: dict) -> ToolOutput:
    question = _require(args, "question")
    result = await research.run(question, ctx.model or research.planner_model(""), focus=args.get("focus") or "")
    fmt = "docx" if (args.get("format") or "").lower() == "docx" else "pdf"
    body = result["markdown"]
    data = documents.build_docx(body) if fmt == "docx" else documents.build_pdf(body)
    saved = await _save_file(ctx, data, fmt, args.get("filename") or result["title"])
    links = "\n".join(f"[{i}] {s['title']} - {s['url']}" for i, s in enumerate(result["sources"], 1))
    return ToolOutput(
        content=(f"Wrote the report {saved['name']} from {len(result['sources'])} sources; it is shown to the user "
                 "with a download button. Give the user the key answer in 3-6 short lines with [n] citations and "
                 f"say the full report is attached. Don't paste the whole report.\n\nReport summary:\n"
                 f"{result['summary']}\n\nSources:\n{links}"),
        summary=f"Researched {len(result['sources'])} sources, wrote {saved['name']}", media=[saved])


async def _create_html(ctx: ToolContext, args: dict) -> ToolOutput:
    page = _require(args, "html")
    if "<html" not in page.lower():
        page = f"<!doctype html>\n<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'></head><body>\n{page}\n</body></html>"
    saved = await _save_file(ctx, page.encode("utf-8"), "html", args.get("filename") or "page")
    return ToolOutput(content=f"Created {saved['name']}. The user sees a live preview of it.",
                      summary=f"Created {saved['name']}", media=[saved])


async def _create_file(ctx: ToolContext, args: dict) -> ToolOutput:
    name, ctype = documents.text_file(_require(args, "filename"))
    content = args.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("'content' is required")
    saved = await media.save_media(ctx.db, ctx.user_id, content.encode("utf-8"), ctype, "document",
                                   name=name, conversation_id=ctx.conversation_id)
    return ToolOutput(content=f"Created {saved['name']}. It is shown to the user with a preview and download "
                              "button; don't paste its contents again.",
                      summary=f"Created {saved['name']}", media=[saved])


async def _create_zip(ctx: ToolContext, args: dict) -> ToolOutput:
    files = args.get("files")
    name = documents.safe_filename(args.get("filename") or "project", "zip")
    data = documents.build_zip(files, folder=name[:-4])
    saved = await media.save_media(ctx.db, ctx.user_id, data, documents.CONTENT_TYPES["zip"], "document",
                                   name=name, conversation_id=ctx.conversation_id)
    return ToolOutput(content=f"Created {saved['name']} with {len(files)} files. It is shown to the user with a "
                              "download button; don't paste the files again, just say how to run it.",
                      summary=f"Created {saved['name']} ({len(files)} files)", media=[saved])


async def _generate_video(ctx: ToolContext, args: dict) -> ToolOutput:
    prompt = _require(args, "prompt")
    scenes = args.get("scenes") if isinstance(args.get("scenes"), list) else None
    captions = args.get("captions") if isinstance(args.get("captions"), list) else None
    try:
        seconds = int(float(args.get("seconds") or 12))
    except (TypeError, ValueError):
        seconds = 12
    out = await video.generate(prompt, seconds, str(args.get("orientation") or "").lower(),
                               args.get("quality"), scenes, args.get("style") or "", captions)
    name = documents.safe_filename(args.get("filename") or prompt[:40] or "video", "mp4")
    saved = await media.save_media(ctx.db, ctx.user_id, out["data"], out["contentType"], "generated", name=name,
                                   conversation_id=ctx.conversation_id)
    if out["method"] == "slideshow":
        content = (out.get("note", "") + "Made a video from AI-generated images of each scene, with slow camera "
                   "moves and fades between them (a free method; it is not full motion video). It is shown to the "
                   "user with a download button. Tell them that in one plain sentence.")
    else:
        content = "Video generated and shown to the user. Briefly describe what you asked for."
    return ToolOutput(content=content, summary=f"Generated video “{prompt[:70]}”", media=[saved])


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
            description="Create an image (photo, ad, product shot, poster, logo, thumbnail, anime, 3D, art...) from a "
                        "text description; pick the matching 'style'. Write "
                        "a rich prompt in English: subject, setting, composition, lighting, style, colors, mood. Use "
                        "1536x1024 for landscape scenes and 1024x1536 for portraits and posters. Call once per image.",
            parameters={"type": "object", "properties": {
                "prompt": {"type": "string", "description": "Detailed description of the image"},
                "filename": {"type": "string", "description": "Short file name without extension"},
                # No enums: Groq rejects the whole reply when a model writes a value outside one.
                "style": {"type": "string", "description": "One of: " + ", ".join(styles.image_style_names())},
                "size": {"type": "string", "description": "1024x1024, 1536x1024 (landscape) or 1024x1536 (portrait)"},
                "quality": {"type": "string", "description": "high (default), medium or low"},
            }, "required": ["prompt"]},
            handler=_generate_image, available=media.image_available))
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
            name="create_file", label="Create file",
            description="Create any text or code file the user can download: .txt, .md, .csv, .json, .py, .js, "
                        ".ts, .css, .html, .sql, .sh, .java, .c, .go, .yaml, Dockerfile and more. Write the "
                        "complete, working file.",
            parameters={"type": "object", "properties": {
                "filename": {"type": "string", "description": "Name with extension, e.g. main.py or data.csv"},
                "content": {"type": "string", "description": "Full file content"},
            }, "required": ["filename", "content"]},
            handler=_create_file))
        .register(Tool(
            name="create_zip", label="Create ZIP project",
            description="Create a downloadable .zip of a multi-file project (Node, Python, websites, etc.). "
                        "Include every file needed to run it (package.json / requirements.txt, README).",
            parameters={"type": "object", "properties": {
                "filename": {"type": "string", "description": "Project name"},
                "files": {"type": "array", "items": {"type": "object", "properties": {
                    "path": {"type": "string", "description": "Relative path, e.g. src/index.js"},
                    "content": {"type": "string"},
                }, "required": ["path", "content"]}},
            }, "required": ["filename", "files"]},
            handler=_create_zip))
        .register(Tool(
            name="deep_research", label="Deep research",
            description="Research a question in depth: runs several web searches, reads the best pages and writes a "
                        "cited report (PDF, or Word) with summary, findings, comparison table and recommendation. Use "
                        "it when the user asks for research, a report, a detailed comparison of tools, prices or "
                        "options, or market/competitor analysis. For a quick fact use web_search instead.",
            parameters={"type": "object", "properties": {
                "question": {"type": "string", "description": "The full research question, with any constraints"},
                "focus": {"type": "string", "description": "Optional: country, budget, audience or angle to focus on"},
                "format": {"type": "string", "description": "pdf (default) or docx"},
                "filename": {"type": "string", "description": "Short file name without extension"},
            }, "required": ["question"]},
            handler=_deep_research))
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
            description="Generate a short video: ads, movie scenes, trailers, 3D animation, anime, cartoons, music "
                        "videos, reels, travel, food, real estate and more (pick 'style'). Depending on the service "
                        "it is true AI video or a video made from AI images of several scenes with camera moves and "
                        "transitions. Always give 3-6 'scenes' that tell a story in order with the same characters, "
                        "and for ads, reels, trailers and explainers give short on-screen 'captions' (headline, "
                        "benefits, then a call to action with the brand name). Takes one to a few minutes.",
            parameters={"type": "object", "properties": {
                "prompt": {"type": "string", "description": "What the video is about, with subject and setting"},
                "style": {"type": "string", "description": "One of: " + ", ".join(styles.video_style_names())},
                "scenes": {"type": "array", "items": {"type": "string"},
                           "description": "3-6 detailed shot descriptions in order, same characters and look"},
                "captions": {"type": "array", "items": {"type": "string"},
                             "description": "Optional text shown on each scene (max ~8 words each; '' for none)"},
                "seconds": {"type": "integer", "description": "Length in seconds (default 12, up to 30)"},
                "orientation": {"type": "string", "description": "landscape, or portrait for reels/stories/shorts"},
                "quality": {"type": "string", "description": "high (default) or standard (faster, 720p)"},
                "filename": {"type": "string", "description": "Short file name without extension"},
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
