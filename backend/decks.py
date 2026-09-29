"""Decks: Gamma-style presentations.

Flow: the user types a topic -> RADHA writes an editable outline -> the user picks a
theme -> slides are written a few at a time in the background (the page polls and
shows them as they arrive) -> the user edits slides by chat, switches themes,
presents full screen and downloads a .pptx (or prints to PDF from the browser).

Model calls are small and separate (outline, then batches of slides, then one call
per chat edit) so each fits Groq's free per-minute token budget.

Storage (MongoDB): decks  {id, userId, title, prompt, theme, status, slides, history, ...}
"""
import asyncio
import io
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional
from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from auth import decode_token, get_user_id_from_request
from deck_render import (DEFAULT_THEME, IMAGE_LAYOUTS, LAYOUTS, MAX_SLIDES, THEME_IDS, build_deck_pptx,
                         normalize_slide, public_themes)

router = APIRouter(prefix="/api")
logger = logging.getLogger("radha.decks")
db = None
DEFAULT_MODEL = ""
BATCH = 4  # slides per model call
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
    "The last slide is a conclusion or call to action. 2-4 short points per slide. Titles are specific and punchy, "
    "not generic ('Solar costs fell 90% in a decade', not 'Costs'). Write in the language of the user's topic."
)

SLIDE_SCHEMA = (
    "Each slide is an object with a \"layout\" and only the fields that layout uses:\n"
    "- cover: title, subtitle, image_query\n"
    "- section: title, subtitle (a divider between parts)\n"
    "- bullets: title, body (optional one-sentence intro), bullets [3-6 strings]\n"
    "- image_right / image_left: title, body, bullets [2-4], image_query\n"
    "- cards: title, items [3-4 {icon: one emoji, title: 2-4 words, text}]\n"
    "- stats: title, stats [2-4 {value: short number like \"87%\" or \"$4.2B\", label}], body (optional source/insight)\n"
    "- steps: title, items [3-5 {title, text}] (a process or timeline, in order)\n"
    "- quote: quote, author\n"
    "- comparison: title, left {title, bullets [2-4]}, right {title, bullets [2-4]}\n"
    "- closing: title, subtitle\n"
    "Every slide may also have notes (2-3 sentences the speaker can say).\n"
    "image_query is 2-4 plain English words for a stock photo search (e.g. \"solar panels rooftop\")."
)

SLIDES_SYSTEM = (
    "You write polished presentation slides, like Gamma.app. Reply with ONLY a JSON object: "
    '{"slides": [ ... ]}\n' + SLIDE_SCHEMA + "\n"
    "Design rules: vary layouts so no two neighbouring slides share one; use cards, stats, steps, comparison and "
    "image layouts often and plain bullets rarely; use stats only with real, well-known figures (never invent "
    "precise numbers; round and hedge instead); the first slide is cover, the last is closing. Write in the "
    "language of the outline."
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
    "slide's picture, update it with a new image_query. Write in the language of the deck."
)


# ------------------------------------------------------------------ images
_image_cache: dict = {}


async def _search_images(query: str) -> List[dict]:
    """Free photo search: Pexels or Unsplash when a key is set, otherwise Openverse (no key needed)."""
    if query in _image_cache:
        return _image_cache[query]
    results: List[dict] = []
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                     headers={"User-Agent": "RADHA/1.0 (presentation builder)"}) as client:
            if os.environ.get("PEXELS_API_KEY"):
                r = await client.get(f"https://api.pexels.com/v1/search?query={quote_plus(query)}"
                                     "&orientation=landscape&per_page=8",
                                     headers={"Authorization": os.environ["PEXELS_API_KEY"]})
                r.raise_for_status()
                results = [{"url": p["src"]["large2x"], "thumb": p["src"]["medium"],
                            "credit": f"Photo by {p.get('photographer', '')} on Pexels", "link": p.get("url", "")}
                           for p in r.json().get("photos", [])]
            elif os.environ.get("UNSPLASH_ACCESS_KEY"):
                r = await client.get(f"https://api.unsplash.com/search/photos?query={quote_plus(query)}"
                                     "&orientation=landscape&per_page=8",
                                     headers={"Authorization": f"Client-ID {os.environ['UNSPLASH_ACCESS_KEY']}"})
                r.raise_for_status()
                results = [{"url": p["urls"]["regular"], "thumb": p["urls"]["small"],
                            "credit": f"Photo by {p['user']['name']} on Unsplash", "link": p["links"]["html"]}
                           for p in r.json().get("results", [])]
            else:
                r = await client.get(f"https://api.openverse.org/v1/images/?q={quote_plus(query)}"
                                     "&page_size=12&aspect_ratio=wide&mature=false&category=photograph")
                r.raise_for_status()
                for p in r.json().get("results", []):
                    url = p.get("url") or ""
                    if not url.startswith("https://") or not re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I):
                        continue
                    if (p.get("width") or 1200) < 800:
                        continue
                    who = p.get("creator") or "unknown"
                    lic = (p.get("license") or "").upper()
                    results.append({"url": url, "thumb": p.get("thumbnail") or url,
                                    "credit": f"Photo by {who} ({'CC ' + lic if lic and lic != 'CC0' else lic or 'CC'})",
                                    "link": p.get("foreign_landing_url") or ""})
    except Exception as exc:  # pictures are a nice-to-have: never fail the deck over them
        logger.info("image search failed for %r: %s", query, exc)
    if results:
        _image_cache[query] = results
        if len(_image_cache) > 300:
            _image_cache.pop(next(iter(_image_cache)))
    return results


async def find_image(query: str, used: set) -> Optional[dict]:
    if not query or os.environ.get("DECK_IMAGES", "1") == "0":
        return None
    for img in await _search_images(query):
        if img["url"] not in used:
            used.add(img["url"])
            return img
    return None


async def add_images(slides: List[dict], force_ids: Optional[set] = None) -> None:
    """Fill in photos for image layouts that don't have one (or whose image_query changed)."""
    used = {s["image"]["url"] for s in slides if s.get("image")}
    for s in slides:
        wants = s["layout"] in IMAGE_LAYOUTS and s.get("image_query")
        if wants and (not s.get("image") or (force_ids and s["id"] in force_ids)):
            s["image"] = await find_image(s["image_query"], used) or s.get("image")


def download_image(url: str) -> Optional[bytes]:
    """Fetch a photo for the .pptx, shrunk so the file stays small."""
    try:
        with httpx.stream("GET", url, timeout=12, follow_redirects=True,
                          headers={"User-Agent": "RADHA/1.0 (presentation builder)"}) as r:
            r.raise_for_status()
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > 8 * 1024 * 1024:
                    return None
        from PIL import Image

        img = Image.open(io.BytesIO(bytes(buf)))
        img = img.convert("RGB")
        img.thumbnail((1600, 1600))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=84, optimize=True)
        return out.getvalue()
    except Exception as exc:
        logger.info("image download failed for %s: %s", url, exc)
        return None


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
    base = (f"Deck title: {deck['title']}\nTopic / brief: {deck['prompt']}\n"
            f"Text amount: {DENSITY.get(deck.get('density'), DENSITY['medium'])}\n"
            f"Pictures: {'use image layouts where they fit' if deck.get('images', True) else 'no image layouts'}\n\n"
            f"Full outline ({total} slides):\n{outline_text(outline)}\n\n")
    slides: List[dict] = []
    try:
        for start in range(0, total, BATCH):
            end = min(total, start + BATCH)
            prev = slides[-1]["layout"] if slides else "none"
            data = await ask_json(model, SLIDES_SYSTEM,
                                  base + f"Write slides {start + 1} to {end} only (exactly {end - start} slides), "
                                  f"following the outline. The previous slide's layout was {prev}.")
            batch = [normalize_slide(s, keep_id=False) for s in (data.get("slides") or [])][: end - start]
            if not deck.get("images", True):
                for s in batch:
                    if s["layout"] in ("image_right", "image_left"):
                        s["layout"] = "bullets"
            else:
                await add_images(slides + batch)
            slides += batch
            await db.decks.update_one({"id": deck_id}, {"$set": {"slides": slides, "updatedAt": _now()}})
        await db.decks.update_one({"id": deck_id}, {"$set": {"status": "ready", "updatedAt": _now()}})
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
        slim = {k: v for k, v in s.items() if v and k not in ("id", "image", "notes")}
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


# ------------------------------------------------------------------ API
class OutlineIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=6000)
    slides: int = Field(8, ge=3, le=20)
    model: Optional[str] = None


class DeckIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=6000)
    title: str = Field("", max_length=200)
    outline: List[dict] = Field(default_factory=list)
    theme: str = DEFAULT_THEME
    density: str = "medium"
    images: bool = True
    model: Optional[str] = None


class DeckPatch(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    theme: Optional[str] = None
    slides: Optional[List[dict]] = None


class EditIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=3000)
    slide: Optional[int] = None
    model: Optional[str] = None


def public_deck(doc: dict, full: bool = True) -> dict:
    out = {k: doc.get(k) for k in ("id", "title", "prompt", "theme", "status", "error", "createdAt", "updatedAt",
                                   "density", "images")}
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
    if doc.get("status") == "generating":
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(doc["updatedAt"])).total_seconds()
        if age > STALE_SECONDS:  # the server restarted mid-generation
            doc["status"] = "ready" if doc.get("slides") else "error"
            doc["error"] = "Generation stopped before the end. Ask RADHA to add the missing slides."
            await db.decks.update_one({"id": deck_id}, {"$set": {"status": doc["status"], "error": doc["error"]}})
    return doc


async def save_with_history(deck: dict, updates: dict):
    snap = {"title": deck["title"], "theme": deck["theme"], "slides": deck["slides"]}
    history = ([snap] + (deck.get("history") or []))[:HISTORY]
    await db.decks.update_one({"id": deck["id"]}, {"$set": {**updates, "history": history, "updatedAt": _now()}})


@router.get("/decks/themes")
async def list_themes():
    return {"themes": public_themes(), "layouts": list(LAYOUTS)}


@router.get("/decks")
async def list_decks(user_id: str = Depends(current_user_id)):
    docs = await db.decks.find({"userId": user_id}, {"_id": 0, "history": 0}).sort("updatedAt", -1).to_list(300)
    return [public_deck(d, full=False) for d in docs]


@router.post("/decks/outline")
async def make_outline(body: OutlineIn, user_id: str = Depends(current_user_id)):
    model = body.model or DEFAULT_MODEL
    try:
        data = await ask_json(model, OUTLINE_SYSTEM,
                              f"Topic / brief:\n{body.prompt}\n\nNumber of slides: {body.slides}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("outline failed")
        raise HTTPException(status_code=502, detail=_model_error(exc))
    outline = clean_outline(data.get("slides"))
    if not outline:
        raise HTTPException(status_code=502, detail="The AI returned an empty outline. Please try again.")
    return {"title": str(data.get("title") or outline[0]["title"])[:200], "outline": outline}


@router.post("/decks")
async def create_deck(body: DeckIn, user_id: str = Depends(current_user_id)):
    outline = clean_outline(body.outline)
    if not outline:
        raise HTTPException(status_code=400, detail="Add at least one slide to the outline")
    ts = _now()
    doc = {
        "id": str(uuid.uuid4()), "userId": user_id, "title": (body.title or outline[0]["title"]).strip()[:200],
        "prompt": body.prompt.strip(), "theme": body.theme if body.theme in THEME_IDS else DEFAULT_THEME,
        "density": body.density if body.density in DENSITY else "medium", "images": body.images,
        "outline": outline, "slides": [], "history": [], "status": "generating", "error": None,
        "createdAt": ts, "updatedAt": ts,
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
        requery = {s["id"] for s in slides if s["id"] in old and s["image_query"] != old[s["id"]].get("image_query")}
        await add_images(slides, force_ids=requery)
        updates["slides"] = slides
    if updates:
        await save_with_history(deck, updates)
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
    try:
        data = await ask_json(body.model or DEFAULT_MODEL, EDIT_SYSTEM,
                              f"Deck:\n{compact_deck(deck)}\n\n{selected}Request: {body.instruction}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("deck edit failed")
        raise HTTPException(status_code=502, detail=_model_error(exc))
    before = {"title": deck["title"], "theme": deck["theme"]}
    slides, changed = apply_ops(deck, data.get("ops"))
    await add_images(slides, force_ids=changed)
    updates = {"slides": slides, "title": deck["title"], "theme": deck["theme"]}
    deck.update(before)  # history keeps the pre-edit title/theme
    await save_with_history(deck, updates)
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


@router.post("/decks/{deck_id}/slides/{index}/image")
async def new_image(deck_id: str, index: int, user_id: str = Depends(current_user_id)):
    """Swap a slide's photo for the next search result."""
    deck = await owned_deck(deck_id, user_id)
    if not 0 <= index < len(deck["slides"]):
        raise HTTPException(status_code=404, detail="Slide not found")
    slides = [dict(s) for s in deck["slides"]]
    s = slides[index]
    query = s.get("image_query") or s.get("title") or deck["title"]
    used = {x["image"]["url"] for x in slides if x.get("image")}
    img = await find_image(query, used)
    if not img:
        raise HTTPException(status_code=404, detail="No other picture found. Try asking for a different picture.")
    s["image"], s["image_query"] = img, query
    await save_with_history(deck, {"slides": slides})
    return public_deck(await owned_deck(deck_id, user_id))


@router.get("/decks/{deck_id}/export")
async def export_deck(deck_id: str, request: Request, auth: Optional[str] = Query(None)):
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    deck = await owned_deck(deck_id, decode_token(token)["sub"])
    if not deck.get("slides"):
        raise HTTPException(status_code=400, detail="This presentation has no slides yet")
    urls = {s["image"]["url"] for s in deck["slides"] if s.get("image")}
    loop = asyncio.get_running_loop()
    fetched = dict(zip(urls, await asyncio.gather(*(loop.run_in_executor(None, download_image, u) for u in urls))))
    data = await loop.run_in_executor(None, lambda: build_deck_pptx(deck["title"], deck["slides"], deck["theme"],
                                                                     fetched.get))
    name = re.sub(r"[^\w\-]+", "-", deck["title"]).strip("-")[:80] or "presentation"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{name}.pptx"'})
