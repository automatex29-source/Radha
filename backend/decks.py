"""Decks: Gamma-style presentations.

Flow: the user types a topic (or brings a file, link or video) -> the AI writes an editable outline -> the user picks a
theme -> slides are written a few at a time in the background (the page polls and
shows them as they arrive) -> the user edits slides by chat, switches themes,
presents full screen and downloads a .pptx (or prints to PDF from the browser).

Model calls are small and separate (outline, then batches of slides, then one call
per chat edit) so each fits Groq's free per-minute token budget.

Storage (MongoDB): decks  {id, userId, title, prompt, theme, status, slides, history, ...}
"""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import deck_images
from auth import decode_token, get_user_id_from_request
from deck_render import (DEFAULT_THEME, IMAGE_LAYOUTS, LAYOUTS, MAX_SLIDES, THEME_IDS, build_deck_pptx,
                         normalize_slide, public_themes)

router = APIRouter(prefix="/api")
logger = logging.getLogger("radha.decks")
db = None
DEFAULT_MODEL = ""
BATCH = 4  # slides per model call
SOURCE_IN_SLIDES = 2500  # characters of source material repeated in each slide call
MAX_SOURCE = 60_000
HISTORY = 15
STALE_SECONDS = 600
_tasks: set = set()


def init(database, default_model: str):
    global db, DEFAULT_MODEL
    db = database
    DEFAULT_MODEL = default_model


async def ensure_indexes():
    await db.decks.create_index([("userId", 1), ("updatedAt", -1)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def current_user_id(request: Request) -> str:
    return get_user_id_from_request(request)


# ------------------------------------------------------------------ model
async def _complete(model: str, system: str, user: str) -> str:
    """One non-streaming answer from the model (tests replace this)."""
    from agent import llm

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out = []
    async for ev in llm.stream_completion(model, messages, []):
        if ev["type"] == "text":
            out.append(ev["text"])
    return "".join(out)


def parse_json(text: str):
    """Pull the JSON object out of a model answer (tolerates ```json fences and chatter)."""
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in the answer")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unfinished JSON in the answer")


async def ask_json(model: str, system: str, user: str) -> dict:
    last = None
    for attempt in range(2):
        answer = await _complete(model, system, user if attempt == 0 else
                                 user + "\n\nYour last answer was not valid JSON. Reply with ONLY the JSON object.")
        try:
            data = parse_json(answer)
            if isinstance(data, dict):
                return data
        except (ValueError, json.JSONDecodeError) as exc:
            last = exc
    raise HTTPException(status_code=502, detail=f"The AI answer could not be read ({last}). Please try again.")


def _model_error(exc: Exception) -> str:
    msg = str(exc)
    if "per day" in msg.lower() or "rate" in msg.lower():
        return "The free AI limit was reached. Please wait a minute and try again."
    if "api_key" in msg.lower() or "api key" in msg.lower():
        return "No AI key is set up on the server."
    return "The AI could not finish. Please try again."


DENSITY = {
    "brief": "Keep text very short: titles plus 3 short bullets or short card texts (under 12 words).",
    "medium": "Use concise, informative text: 3-5 bullets of up to 18 words; card texts of 1-2 sentences.",
    "detailed": "Be thorough: 4-6 bullets of up to 25 words, card texts of 2 sentences, and a short body paragraph.",
}

OUTLINE_SYSTEM = (
    "You plan presentations. Reply with ONLY a JSON object, no prose:\n"
    '{"title": "deck title", "slides": [{"title": "slide title", "points": ["key point", "..."]}]}\n'
    "Rules: exactly the requested number of slides. Slide 1 is the cover (title + one-line hook as its only point). "
    "The last slide is a conclusion or call to action. 2-5 points per slide with specific facts, names and numbers "
    "where you know them. Titles are specific and punchy, not generic ('Solar costs fell 90% in a decade', not "
    "'Costs'). Follow every instruction in the brief (audience, tone, slides the user asked for, things to include). "
    "When source material is given, build the deck from it: keep its real facts and figures, don't invent new ones, "
    "and when it has numbers that compare or change over time, plan a slide for them and copy the exact numbers "
    "into its points (label: value). Write in the language of the brief."
)

REPHRASE_SYSTEM = (
    "You turn a rough request for a presentation into a clear brief for a slide designer. Keep every detail the "
    "user gave and fix spelling. Write plain text, no markdown headings, at most 120 words:\n"
    "Topic: ...\nAudience: ...\nGoal: ...\nTone: ...\nMust cover: point; point; point\n"
    "Guess sensible values for anything missing. Write in the user's language."
)

SLIDE_SCHEMA = (
    "Each slide is an object with a \"layout\" and only the fields that layout uses:\n"
    "- cover: title, subtitle, image_query, image_prompt\n"
    "- section: title, subtitle (a divider between parts)\n"
    "- bullets: title, body (optional one-sentence intro), bullets [3-6 strings]\n"
    "- image_right / image_left: title, body, bullets [2-4], image_query, image_prompt\n"
    "- cards: title, items [3-4 {icon: one emoji, title: 2-4 words, text}]\n"
    "- stats: title, stats [2-4 {value: short number like \"87%\" or \"$4.2B\", label}], body (optional source/insight)\n"
    "- chart: title, chart {type: bar|line|pie|doughnut, labels [2-10], series [1-3 {name, values [numbers]}], "
    "unit}, body (one-sentence takeaway). Use line for change over time, pie/doughnut for parts of a whole.\n"
    "- steps: title, items [3-5 {title, text}] (a process or timeline, in order)\n"
    "- quote: quote, author\n"
    "- comparison: title, left {title, bullets [2-4]}, right {title, bullets [2-4]}\n"
    "- closing: title, subtitle\n"
    "Every slide may also have notes (2-3 sentences the speaker can say).\n"
    "Pictures must match the slide exactly. image_query is 2-4 concrete English words for a photo search that "
    "names something you can see (\"farmer checking wheat field\", not \"growth\" or \"strategy\"). image_prompt "
    "is one English sentence (15-35 words) describing a realistic photo for this exact slide: subject, action, "
    "setting, and the country/culture when the topic has one."
)

SLIDES_SYSTEM = (
    "You write polished presentation slides, like Gamma.app. Reply with ONLY a JSON object: "
    '{"slides": [ ... ]}\n' + SLIDE_SCHEMA + "\n"
    "Design rules: vary layouts so no two neighbouring slides share one; use cards, stats, chart, steps, comparison "
    "and image layouts often and plain bullets rarely; use chart and stats only with numbers from the outline or "
    "source, or real, well-known figures (never invent precise numbers; round and hedge instead); the first slide "
    "is cover, the last is closing. Write in the language of the outline."
)

EDIT_SYSTEM = (
    "You edit a presentation. You get the deck as JSON (slides are numbered from 0) and the user's request. "
    "Reply with ONLY a JSON object: {\"reply\": \"one short sentence saying what you changed\", \"ops\": [ ... ]}\n"
    "Operations (indexes refer to the deck as given, before any change):\n"
    '- {"op": "update", "index": i, "slide": {full new slide}}\n'
    '- {"op": "insert", "after": i, "slide": {new slide}}  (after -1 puts it first)\n'
    '- {"op": "delete", "index": i}\n'
    '- {"op": "move", "index": i, "after": j}\n'
    '- {"op": "theme", "theme": one of ' + json.dumps(THEME_IDS) + "}\n"
    '- {"op": "title", "title": "new deck title"}\n'
    + SLIDE_SCHEMA + "\n"
    "Change only what the request asks. When the user says 'this slide', they mean the selected slide. To change a "
    "slide's picture, update it with a new image_query and image_prompt. Write in the language of the deck."
)


# ------------------------------------------------------------------ pictures
PICTURE_MODES = ("ai", "stock", "none")


def picture_mode(deck: dict) -> str:
    mode = deck.get("pictures")
    if mode in PICTURE_MODES:
        return mode
    return "stock" if deck.get("images", True) else "none"  # decks made before picture modes


def needs_picture(slide: dict) -> bool:
    return slide["layout"] in IMAGE_LAYOUTS and not slide.get("image")


async def fill_pictures(deck_id: str, only_ids: Optional[set] = None):
    """Give every picture slide an image, one at a time, saving each as soon as it is ready."""
    deck = await db.decks.find_one({"id": deck_id})
    if not deck:
        return
    mode = picture_mode(deck)
    topic = deck.get("title") or deck.get("prompt") or ""
    used = {s["image"]["url"] for s in deck["slides"] if s.get("image")}
    try:
        for slide in deck["slides"]:
            if mode == "none" or not deck_images.enabled():
                break
            if not needs_picture(slide) and not (only_ids and slide["id"] in only_ids and slide["layout"] in IMAGE_LAYOUTS):
                continue
            img = None
            if mode == "ai":
                try:
                    img = await deck_images.make_ai(db, deck["userId"], slide, topic)
                except Exception as exc:
                    logger.info("AI picture failed, using a photo instead: %s", exc)
            if img is None:
                img = await deck_images.find_stock(slide, used, topic)
            if img:
                await db.decks.update_one({"id": deck_id, "slides.id": slide["id"]}, {"$set": {"slides.$.image": img}})
    finally:
        await db.decks.update_one({"id": deck_id}, {"$set": {"picturesPending": False, "updatedAt": _now()}})


async def pictures_later(deck: dict, slides: List[dict], changed: set) -> bool:
    """Clear pictures whose search words changed and fetch new ones in the background. True if any are coming."""
    if picture_mode(deck) == "none":
        return False
    for s in slides:
        if s["id"] in changed and s["layout"] in IMAGE_LAYOUTS:
            s["image"] = None
    return any(needs_picture(s) for s in slides)


# ------------------------------------------------------------------ deck generation
def outline_text(outline: List[dict]) -> str:
    return "\n".join(f"{i + 1}. {s['title']}" + "".join(f"\n   - {p}" for p in s.get("points", []))
                     for i, s in enumerate(outline))


def clean_outline(raw) -> List[dict]:
    out = []
    for s in (raw if isinstance(raw, list) else [])[:MAX_SLIDES]:
        if isinstance(s, dict) and str(s.get("title") or "").strip():
            out.append({"title": str(s["title"]).strip()[:120],
                        "points": [str(p).strip()[:200] for p in (s.get("points") or []) if str(p).strip()][:6]})
        elif isinstance(s, str) and s.strip():
            out.append({"title": s.strip()[:120], "points": []})
    return out


async def generate_slides(deck_id: str, model: str):
    deck = await db.decks.find_one({"id": deck_id})
    outline, total = deck["outline"], len(deck["outline"])
    mode = picture_mode(deck)
    source = deck.get("source") or ""
    base = (f"Deck title: {deck['title']}\nBrief: {deck['prompt']}\n"
            f"Text amount: {DENSITY.get(deck.get('density'), DENSITY['medium'])}\n"
            f"Pictures: {'no image layouts' if mode == 'none' else 'use image layouts where a picture helps'}\n"
            + (f"\nSource material (excerpt, use its facts):\n{source[:SOURCE_IN_SLIDES]}\n" if source else "")
            + f"\nFull outline ({total} slides):\n{outline_text(outline)}\n\n")
    slides: List[dict] = []
    try:
        for start in range(0, total, BATCH):
            end = min(total, start + BATCH)
            prev = slides[-1]["layout"] if slides else "none"
            data = await ask_json(model, SLIDES_SYSTEM,
                                  base + f"Write slides {start + 1} to {end} only (exactly {end - start} slides), "
                                  f"following the outline. The previous slide's layout was {prev}.")
            batch = [normalize_slide(s, keep_id=False) for s in (data.get("slides") or [])][: end - start]
            for s in batch:
                if s["layout"] == "chart" and not s["chart"]:
                    s["layout"] = "bullets"
                if mode == "none" and s["layout"] in ("image_right", "image_left"):
                    s["layout"] = "bullets"
            slides += batch
            await db.decks.update_one({"id": deck_id}, {"$set": {"slides": slides, "updatedAt": _now()}})
        pending = mode != "none" and any(needs_picture(s) for s in slides)
        await db.decks.update_one({"id": deck_id}, {"$set": {"status": "ready", "picturesPending": pending,
                                                             "updatedAt": _now()}})
        if pending:
            await fill_pictures(deck_id)
    except Exception as exc:
        logger.exception("deck generation failed")
        detail = exc.detail if isinstance(exc, HTTPException) else _model_error(exc)
        await db.decks.update_one({"id": deck_id}, {"$set": {"status": "ready" if slides else "error",
                                                             "error": detail, "updatedAt": _now()}})


def _spawn(coro):
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def compact_deck(deck: dict) -> str:
    slides = []
    for s in deck["slides"]:
        slim = {k: v for k, v in s.items() if v and k not in ("id", "image", "notes", "image_prompt")}
        if not slim.get("left", {}).get("bullets") and not slim.get("left", {}).get("title"):
            slim.pop("left", None)
        if not slim.get("right", {}).get("bullets") and not slim.get("right", {}).get("title"):
            slim.pop("right", None)
        slides.append(slim)
    return json.dumps({"title": deck["title"], "theme": deck["theme"], "slides": slides}, ensure_ascii=False)


def apply_ops(deck: dict, ops: list) -> tuple:
    """Apply edit operations; indexes refer to the deck before the edit. Returns (slides, changed ids)."""
    slides = [dict(s) for s in deck["slides"]]
    ids = [s["id"] for s in slides]
    changed = set()

    def pos(index):
        try:
            return next(i for i, s in enumerate(slides) if s["id"] == ids[int(index)])
        except (StopIteration, IndexError, ValueError, TypeError):
            return None

    for op in ops if isinstance(ops, list) else []:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "update" and isinstance(op.get("slide"), dict):
            i = pos(op.get("index"))
            if i is not None:
                old = slides[i]
                new = normalize_slide({**op["slide"], "id": old["id"]})
                if new["image_query"] == old.get("image_query"):
                    new["image"] = old.get("image")
                else:
                    changed.add(new["id"])
                if not new["notes"]:
                    new["notes"] = old.get("notes", "")
                slides[i] = new
        elif kind == "insert" and isinstance(op.get("slide"), dict) and len(slides) < MAX_SLIDES:
            after = op.get("after", len(ids) - 1)
            i = -1 if str(after) == "-1" else pos(after)
            new = normalize_slide(op["slide"], keep_id=False)
            changed.add(new["id"])
            slides.insert((i + 1) if i is not None else len(slides), new)
        elif kind == "delete" and len(slides) > 1:
            i = pos(op.get("index"))
            if i is not None:
                slides.pop(i)
        elif kind == "move":
            i = pos(op.get("index"))
            if i is not None:
                moving = slides.pop(i)
                after = op.get("after", -1)
                j = -1 if str(after) == "-1" else pos(after)
                slides.insert((j + 1) if j is not None else len(slides), moving)
        elif kind == "theme" and op.get("theme") in THEME_IDS:
            deck["theme"] = op["theme"]
        elif kind == "title" and str(op.get("title") or "").strip():
            deck["title"] = str(op["title"]).strip()[:120]
    return slides, changed


# ------------------------------------------------------------------ sources
YOUTUBE_ID = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})")
FILE_EXTS = {"pdf", "docx", "pptx", "xlsx", "xlsm", "csv", "json", "txt", "md", "markdown", "log",
             "png", "jpg", "jpeg", "webp"}


def _youtube_transcript(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    try:
        listing = api.list(video_id)
        codes = [t.language_code for t in listing]
        fetched = api.fetch(video_id, languages=(["en", "hi"] + codes) or ["en"])
    except Exception:
        fetched = api.fetch(video_id)
    return " ".join(getattr(x, "text", "") or (x.get("text", "") if isinstance(x, dict) else "") for x in fetched)


async def read_video(url: str, video_id: str) -> dict:
    """Transcript of a YouTube video; falls back to its title and description when captions are off."""
    from agent import web

    title, description, note = "", "", ""
    try:
        page = await web._get(f"https://www.youtube.com/watch?v={video_id}")
        html = page.content.decode("utf-8", "replace")
        m = re.search(r'<meta name="title" content="([^"]*)"', html) or re.search(r"<title>([^<]*)</title>", html)
        title = (m.group(1) if m else "").replace(" - YouTube", "").strip()
        m = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html)
        if m:
            description = json.loads(f'"{m.group(1)}"')
    except Exception as exc:
        logger.info("youtube page failed: %s", exc)
    try:
        transcript = await asyncio.get_running_loop().run_in_executor(None, _youtube_transcript, video_id)
    except Exception as exc:
        logger.info("youtube transcript failed: %s", exc)
        transcript = ""
    if not transcript:
        note = "This video has no captions I could read, so the deck uses its title and description."
    text = "\n\n".join(x for x in (f"Video: {title}" if title else "", description, transcript) if x)
    if len(text) < 40:
        raise HTTPException(status_code=422, detail="I couldn't read this video. Try another link, or paste its "
                                                    "text or notes instead.")
    return {"kind": "video", "title": title or "YouTube video", "text": text[:MAX_SOURCE], "note": note, "url": url}


def source_block(source: str, model: str) -> str:
    from agent import llm

    limit = 11_000 if llm.lean(model) else 40_000  # Groq's free tier: keep the whole call under ~8K tokens
    text = source.strip()
    if len(text) > limit:
        text = text[:limit] + "\n[… the rest was cut to fit]"
    return f"\n\nSource material:\n\"\"\"\n{text}\n\"\"\""


# ------------------------------------------------------------------ API
class OutlineIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=6000)
    slides: int = Field(8, ge=3, le=20)
    source: str = Field("", max_length=MAX_SOURCE)
    model: Optional[str] = None


class RephraseIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=6000)
    model: Optional[str] = None


class UrlIn(BaseModel):
    url: str = Field(min_length=4, max_length=2000)


class DeckIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=6000)
    title: str = Field("", max_length=200)
    outline: List[dict] = Field(default_factory=list)
    theme: str = DEFAULT_THEME
    density: str = "medium"
    pictures: Optional[str] = None
    images: bool = True  # older clients: False means no pictures
    source: str = Field("", max_length=MAX_SOURCE)
    model: Optional[str] = None


class DeckPatch(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    theme: Optional[str] = None
    pictures: Optional[str] = None
    slides: Optional[List[dict]] = None


class EditIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=3000)
    slide: Optional[int] = None
    model: Optional[str] = None


class ImageIn(BaseModel):
    image: Optional[dict] = None  # a chosen picture {url, thumb, credit, link}; empty = next search result


class AiImageIn(BaseModel):
    prompt: str = Field("", max_length=1000)


def public_deck(doc: dict, full: bool = True) -> dict:
    out = {k: doc.get(k) for k in ("id", "title", "prompt", "theme", "status", "error", "createdAt", "updatedAt",
                                   "density")}
    out["pictures"] = picture_mode(doc)
    out["picturesPending"] = bool(doc.get("picturesPending"))
    out["slideCount"] = len(doc.get("slides") or [])
    out["total"] = len(doc.get("outline") or []) or out["slideCount"]
    out["canUndo"] = bool(doc.get("history"))
    if full:
        out["slides"] = doc.get("slides") or []
    else:
        first = (doc.get("slides") or [None])[0]
        out["cover"] = first
    return out


async def owned_deck(deck_id: str, user_id: str) -> dict:
    doc = await db.decks.find_one({"id": deck_id, "userId": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Presentation not found")
    if doc.get("status") == "generating" or doc.get("picturesPending"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(doc["updatedAt"])).total_seconds()
        if age > STALE_SECONDS:  # the server restarted mid-generation
            fix = {"picturesPending": False}
            if doc.get("status") == "generating":
                fix["status"] = "ready" if doc.get("slides") else "error"
                fix["error"] = "Generation stopped before the end. Ask Krish AI to add the missing slides."
            doc.update(fix)
            await db.decks.update_one({"id": deck_id}, {"$set": fix})
    return doc


async def save_with_history(deck: dict, updates: dict):
    snap = {"title": deck["title"], "theme": deck["theme"], "slides": deck["slides"]}
    history = ([snap] + (deck.get("history") or []))[:HISTORY]
    await db.decks.update_one({"id": deck["id"]}, {"$set": {**updates, "history": history, "updatedAt": _now()}})


async def _ask_model(model: str, system: str, user: str, what: str) -> dict:
    try:
        return await ask_json(model, system, user)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("%s failed", what)
        raise HTTPException(status_code=502, detail=_model_error(exc))


@router.get("/decks/themes")
async def list_themes():
    return {"themes": public_themes(), "layouts": list(LAYOUTS), "pictureModes": list(PICTURE_MODES)}


@router.get("/decks")
async def list_decks(user_id: str = Depends(current_user_id)):
    docs = await db.decks.find({"userId": user_id}, {"_id": 0, "history": 0, "source": 0}).sort("updatedAt", -1).to_list(300)
    return [public_deck(d, full=False) for d in docs]


@router.post("/decks/rephrase")
async def rephrase_prompt(body: RephraseIn, user_id: str = Depends(current_user_id)):
    """Turn a rough request into a clear brief the user can edit."""
    try:
        text = (await _complete(body.model or DEFAULT_MODEL, REPHRASE_SYSTEM, body.prompt)).strip()
    except Exception as exc:
        logger.exception("rephrase failed")
        raise HTTPException(status_code=502, detail=_model_error(exc))
    text = re.sub(r"^```\w*|```$", "", text, flags=re.M).strip()
    if len(text) < 10:
        raise HTTPException(status_code=502, detail="The AI could not improve this. Please try again.")
    return {"prompt": text[:3000]}


@router.post("/decks/import/file")
async def import_file(file: UploadFile = File(...), user_id: str = Depends(current_user_id)):
    """Read a document, spreadsheet or picture so a deck can be built from it."""
    from extract import extract_text

    name = file.filename or "file"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in FILE_EXTS:
        raise HTTPException(status_code=415, detail="Use a PDF, Word, PowerPoint, Excel, CSV, text or picture file.")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="That file is too big (max 20 MB).")
    try:
        text = await asyncio.get_running_loop().run_in_executor(None, extract_text, data, ext, file.content_type or "")
    except Exception as exc:
        logger.info("deck import failed: %s", exc)
        text = ""
    text = (text or "").strip()
    if len(text) < 20:
        raise HTTPException(status_code=422, detail="I couldn't find readable text in that file.")
    return {"kind": "file", "title": name, "text": text[:MAX_SOURCE], "note": "", "url": ""}


@router.post("/decks/import/url")
async def import_url(body: UrlIn, user_id: str = Depends(current_user_id)):
    """Read a web page or a YouTube video (its captions) so a deck can be built from it."""
    from agent import web

    url = body.url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    m = YOUTUBE_ID.search(url)
    if m:
        return await read_video(url, m.group(1))
    try:
        page = await web.fetch_page(url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"I couldn't open that link ({str(exc)[:120]}).")
    text = (page.get("text") or "").strip()
    if len(text) < 40:
        raise HTTPException(status_code=422, detail="That page has almost no text I can use. Try another link.")
    return {"kind": "link", "title": page.get("title") or url, "text": text[:MAX_SOURCE], "note": "", "url": page["url"]}


@router.get("/decks/images/search")
async def search_images(q: str = Query(..., min_length=1, max_length=100), user_id: str = Depends(current_user_id)):
    return {"results": await deck_images.search(q)}


@router.post("/decks/outline")
async def make_outline(body: OutlineIn, user_id: str = Depends(current_user_id)):
    model = body.model or DEFAULT_MODEL
    data = await _ask_model(model, OUTLINE_SYSTEM,
                            f"Brief:\n{body.prompt}\n\nNumber of slides: {body.slides}"
                            + (source_block(body.source, model) if body.source.strip() else ""), "outline")
    outline = clean_outline(data.get("slides"))
    if not outline:
        raise HTTPException(status_code=502, detail="The AI returned an empty outline. Please try again.")
    return {"title": str(data.get("title") or outline[0]["title"])[:200], "outline": outline}


@router.post("/decks")
async def create_deck(body: DeckIn, user_id: str = Depends(current_user_id)):
    outline = clean_outline(body.outline)
    if not outline:
        raise HTTPException(status_code=400, detail="Add at least one slide to the outline")
    pictures = body.pictures if body.pictures in PICTURE_MODES else ("stock" if body.images else "none")
    ts = _now()
    doc = {
        "id": str(uuid.uuid4()), "userId": user_id, "title": (body.title or outline[0]["title"]).strip()[:200],
        "prompt": body.prompt.strip(), "theme": body.theme if body.theme in THEME_IDS else DEFAULT_THEME,
        "density": body.density if body.density in DENSITY else "medium", "pictures": pictures,
        "source": body.source.strip(), "outline": outline, "slides": [], "history": [], "status": "generating",
        "error": None, "picturesPending": False, "createdAt": ts, "updatedAt": ts,
    }
    await db.decks.insert_one(dict(doc))
    _spawn(generate_slides(doc["id"], body.model or DEFAULT_MODEL))
    return public_deck(doc)


@router.get("/decks/{deck_id}")
async def get_deck(deck_id: str, user_id: str = Depends(current_user_id)):
    return public_deck(await owned_deck(deck_id, user_id))


@router.patch("/decks/{deck_id}")
async def update_deck(deck_id: str, body: DeckPatch, user_id: str = Depends(current_user_id)):
    deck = await owned_deck(deck_id, user_id)
    updates = {}
    if body.title is not None and body.title.strip():
        updates["title"] = body.title.strip()[:200]
    if body.theme is not None:
        if body.theme not in THEME_IDS:
            raise HTTPException(status_code=400, detail="Unknown theme")
        updates["theme"] = body.theme
    if body.pictures in PICTURE_MODES:
        updates["pictures"] = deck["pictures"] = body.pictures
    later = False
    if body.slides is not None:
        if not body.slides or len(body.slides) > MAX_SLIDES:
            raise HTTPException(status_code=400, detail=f"A deck needs 1 to {MAX_SLIDES} slides")
        slides = [normalize_slide(s) for s in body.slides]
        seen = set()
        for s in slides:  # duplicated slides arrive with the same id
            if s["id"] in seen:
                s["id"] = uuid.uuid4().hex[:12]
            seen.add(s["id"])
        old = {s["id"]: s for s in deck["slides"]}
        requery = {s["id"] for s in slides if s["id"] in old and s["image_query"] != old[s["id"]].get("image_query")
                   and (s.get("image") or {}).get("url") == (old[s["id"]].get("image") or {}).get("url")}
        later = await pictures_later(deck, slides, requery)
        updates["slides"] = slides
    if updates:
        if later:
            updates["picturesPending"] = True
        await save_with_history(deck, updates)
        if later:
            _spawn(fill_pictures(deck_id))
    return public_deck(await owned_deck(deck_id, user_id))


@router.delete("/decks/{deck_id}")
async def delete_deck(deck_id: str, user_id: str = Depends(current_user_id)):
    await owned_deck(deck_id, user_id)
    await db.decks.delete_one({"id": deck_id})
    return {"ok": True}


@router.post("/decks/{deck_id}/edit")
async def edit_deck(deck_id: str, body: EditIn, user_id: str = Depends(current_user_id)):
    deck = await owned_deck(deck_id, user_id)
    if deck.get("status") == "generating":
        raise HTTPException(status_code=409, detail="Wait until the slides finish, then ask again.")
    selected = ""
    if body.slide is not None and 0 <= body.slide < len(deck["slides"]):
        selected = f"The selected slide is index {body.slide}.\n"
    model = body.model or DEFAULT_MODEL
    data = await _ask_model(model, EDIT_SYSTEM,
                            f"Deck:\n{compact_deck(deck)}\n\n{selected}Request: {body.instruction}", "deck edit")
    before = {"title": deck["title"], "theme": deck["theme"]}
    slides, changed = apply_ops(deck, data.get("ops"))
    for s in slides:
        if s["layout"] == "chart" and not s["chart"]:
            s["layout"] = "bullets"
    later = await pictures_later(deck, slides, changed)
    updates = {"slides": slides, "title": deck["title"], "theme": deck["theme"]}
    if later:
        updates["picturesPending"] = True
    deck.update(before)  # history keeps the pre-edit title/theme
    await save_with_history(deck, updates)
    if later:
        _spawn(fill_pictures(deck_id))
    fresh = await owned_deck(deck_id, user_id)
    return {"reply": str(data.get("reply") or "Done.")[:500], "deck": public_deck(fresh)}


@router.post("/decks/{deck_id}/undo")
async def undo_deck(deck_id: str, user_id: str = Depends(current_user_id)):
    deck = await owned_deck(deck_id, user_id)
    history = deck.get("history") or []
    if not history:
        raise HTTPException(status_code=400, detail="Nothing to undo")
    prev, rest = history[0], history[1:]
    await db.decks.update_one({"id": deck_id}, {"$set": {**prev, "history": rest, "updatedAt": _now()}})
    return public_deck(await owned_deck(deck_id, user_id))


# Layouts that can take a picture without losing their words, and the picture layout they become.
PICTURE_LAYOUT = {"bullets": "image_right", "section": "cover", "closing": "cover"}


def picture_layout(layout: str) -> str:
    return layout if layout in IMAGE_LAYOUTS else PICTURE_LAYOUT.get(layout, layout)


def _slide_at(deck: dict, index: int) -> List[dict]:
    if not 0 <= index < len(deck["slides"]):
        raise HTTPException(status_code=404, detail="Slide not found")
    return [dict(s) for s in deck["slides"]]


@router.post("/decks/{deck_id}/slides/{index}/image")
async def set_image(deck_id: str, index: int, body: Optional[ImageIn] = None,
                    user_id: str = Depends(current_user_id)):
    """Put a chosen picture on a slide, or swap it for the next search result."""
    deck = await owned_deck(deck_id, user_id)
    slides = _slide_at(deck, index)
    s = slides[index]
    if body and body.image:
        img = normalize_slide({"image": body.image})["image"]
        if not img:
            raise HTTPException(status_code=400, detail="That picture link isn't usable. Use an https:// link.")
    else:
        used = {x["image"]["url"] for x in slides if x.get("image")}
        img = await deck_images.find_stock(s, used, deck["title"])
        if not img:
            raise HTTPException(status_code=404, detail="No other picture found. Try different search words.")
    s["image"] = img
    s["layout"] = picture_layout(s["layout"])
    await save_with_history(deck, {"slides": slides})
    return public_deck(await owned_deck(deck_id, user_id))


@router.delete("/decks/{deck_id}/slides/{index}/image")
async def remove_image(deck_id: str, index: int, user_id: str = Depends(current_user_id)):
    """Take the picture off a slide (picture layouts become plain text layouts)."""
    deck = await owned_deck(deck_id, user_id)
    slides = _slide_at(deck, index)
    s = slides[index]
    s["image"], s["image_query"] = None, ""
    if s["layout"] in ("image_right", "image_left"):
        s["layout"] = "bullets"
    await save_with_history(deck, {"slides": slides})
    return public_deck(await owned_deck(deck_id, user_id))


@router.post("/decks/{deck_id}/slides/{index}/ai-image")
async def ai_image(deck_id: str, index: int, body: AiImageIn, user_id: str = Depends(current_user_id)):
    """Make a new AI picture for one slide (from the user's words, or the slide's own description)."""
    deck = await owned_deck(deck_id, user_id)
    _slide_at(deck, index)
    slide = deck["slides"][index]
    try:
        img = await deck_images.make_ai(db, user_id, slide, deck["title"], prompt=body.prompt or None)
    except Exception as exc:
        logger.info("AI slide picture failed: %s", exc)
        raise HTTPException(status_code=502, detail="The picture maker is busy or unavailable. Try again in a "
                                                    "minute, or pick a photo instead.")
    deck = await owned_deck(deck_id, user_id)  # the slides may have changed while the picture was drawn
    slides = [dict(s) for s in deck["slides"]]
    target = next((s for s in slides if s["id"] == slide["id"]), None)
    if not target:
        raise HTTPException(status_code=409, detail="That slide was deleted.")
    target["image"] = img
    if body.prompt:
        target["image_prompt"] = body.prompt[:400]
    target["layout"] = picture_layout(target["layout"])
    await save_with_history(deck, {"slides": slides})
    return public_deck(await owned_deck(deck_id, user_id))


@router.get("/decks/{deck_id}/export")
async def export_deck(deck_id: str, request: Request, auth: Optional[str] = Query(None)):
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_token(token)["sub"]
    deck = await owned_deck(deck_id, user_id)
    if not deck.get("slides"):
        raise HTTPException(status_code=400, detail="This presentation has no slides yet")
    urls = list({s["image"]["url"] for s in deck["slides"] if s.get("image")})
    loop = asyncio.get_running_loop()

    async def fetch(url: str):
        if url.startswith("/api/media/"):
            return await deck_images.stored_bytes(db, user_id, url)
        return await loop.run_in_executor(None, deck_images.download, url)

    fetched = dict(zip(urls, await asyncio.gather(*(fetch(u) for u in urls))))
    data = await loop.run_in_executor(None, lambda: build_deck_pptx(deck["title"], deck["slides"], deck["theme"],
                                                                     fetched.get))
    name = re.sub(r"[^\w\-]+", "-", deck["title"]).strip("-")[:80] or "presentation"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{name}.pptx"'})
