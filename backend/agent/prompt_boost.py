"""Turn a short request into a pro-level image prompt before it reaches the image model.

Free image models follow long, concrete prompts far better than short ones, so
one quick call to the chat model rewrites the prompt like an art director would:
subject, composition, lens, lighting, color, mood and style details. For videos
it also writes the scene list so every scene shows the same characters and look.
Any failure falls back to the original text; this step must never block a picture.
"""
import asyncio
import json
import logging
import os
import re
from typing import List, Optional

import media

from . import llm, styles

logger = logging.getLogger("radha.agent")

TIMEOUT = float(os.environ.get("PROMPT_BOOST_TIMEOUT_SECONDS", "25"))
_MODELS = ["openai/gpt-oss-120b", "gemini-3.5-flash-lite", "claude-haiku-4-5-20251001", "gpt-5.4", "claude-sonnet-4-6"]

IMAGE_SYSTEM = (
    "You are an award-winning art director writing prompts for an AI image model. Rewrite the user's request as "
    "ONE vivid English prompt of 60-110 words. Keep every detail the user gave (names, text to show, colors, "
    "brand, subject). Add: precise subject description, action, setting, composition and camera angle, lens, "
    "lighting, color palette, textures, mood, and the style notes given. {text_rule} Describe only what should "
    "be visible; never write negatives. Output only the prompt, no preamble."
)
TEXT_RULE_PREMIUM = "If words must appear in the picture, put them in double quotes and keep them short."
# Free image models can't spell: any writing they draw comes out as gibberish.
TEXT_RULE_FREE = (
    "The image model cannot spell, so the picture must tell its story without any writing: show people, "
    "objects, places and actions. Any phone, laptop or screen glows with abstract colors and simple shapes, "
    "and signs, pages, packaging and clothing are plain. Only if the request itself asks for words, keep them "
    "to at most four short words in double quotes."
)

VIDEO_SYSTEM = (
    "You are a film director writing a prompt for an AI video model (like Veo) that makes one {seconds}-second "
    "shot with sound. Rewrite the user's request as ONE English prompt of 70-120 words: subject and look, the "
    "action as it unfolds, camera movement (dolly, pan, tracking, drone), lens, lighting, setting, mood, the "
    "style notes, and the sounds (ambience, music feel, short spoken lines in quotes if fitting). Keep every "
    "detail the user gave. Output only the prompt."
)

SCENES_SYSTEM = (
    "You are a film director planning a short video made of {n} still shots. Write the shots as JSON: "
    '{{"character": "...", "scenes": ["...", ...]}}. "character" fixes how the main subject looks (age, face, '
    "hair, clothes, colors, product design) so every shot matches. Each scene is 40-70 English words: what "
    "happens, camera angle and lens, lighting, setting, and the style notes, and it repeats the key look of the "
    "main subject. Shots show no writing at all (captions are added later): screens glow with abstract colors, "
    "signs and labels are plain. The shots must tell the story in order with a strong opening and ending. Output only JSON."
)


def _model() -> Optional[str]:
    wanted = os.environ.get("PROMPT_BOOST_MODEL") or os.environ.get("AI_MODEL")
    for m in ([wanted] if wanted else []) + _MODELS:
        if m and llm.configured(m):
            return m
    return None


def enabled() -> bool:
    return os.environ.get("PROMPT_BOOST", "1") != "0" and _model() is not None


async def _ask(system: str, user: str) -> str:
    out = []

    async def run():
        async for ev in llm.stream_completion(_model(), [{"role": "system", "content": system},
                                                         {"role": "user", "content": user}], []):
            if ev["type"] == "text":
                out.append(ev["text"])

    await asyncio.wait_for(run(), TIMEOUT)
    return "".join(out).strip()


def available() -> bool:
    """True when some configured model can answer a quick rewrite request."""
    return _model() is not None


async def ask(system: str, user: str) -> str:
    """One short, non-streamed answer from the rewrite model (used to draft automation tasks)."""
    return await _ask(system, user)


async def image_prompt(prompt: str, style: str = "") -> str:
    """The rewritten prompt with the style's words, or the original + style words on any failure.

    Unless a premium model that can spell is set up, the result is kept free of writing (see media.text_free)
    when the person did not ask for words.
    """
    premium = media.spells_well()
    plain = not premium and not media.asks_for_text(prompt)
    fallback = styles.styled_image_prompt(prompt, style)
    fallback = media.text_free(fallback) if plain else fallback
    if not enabled():
        return fallback
    key = styles.normalize(style, styles.IMAGE_STYLES)
    notes = styles.IMAGE_STYLES.get(key, "")
    system = IMAGE_SYSTEM.format(text_rule=TEXT_RULE_PREMIUM if premium else TEXT_RULE_FREE)
    try:
        text = await _ask(system, f"Request: {prompt}\nStyle notes: {notes or 'choose the best fitting look'}")
    except Exception as exc:
        logger.info("prompt boost failed, using the original prompt: %s", exc)
        return fallback
    text = text.strip().strip('"').strip()
    if len(text) < 40:
        return fallback
    text = f"{text[:1400]}. {notes}" if notes and notes.split(",")[0] not in text else text[:1500]
    return media.text_free(text) if plain else text


async def video_scenes(prompt: str, scenes: Optional[List[str]], style: str, count: int) -> Optional[List[str]]:
    """Consistent, detailed scene prompts for a picture video, or None to keep the plain ones."""
    if not enabled():
        return None
    notes = styles.video_scene_words(style)
    have = "\n".join(f"- {s}" for s in scenes or [])
    user = f"Video idea: {prompt}\nStyle notes: {notes}\n" + (f"Shots planned so far:\n{have}\n" if have else "")
    try:
        text = await _ask(SCENES_SYSTEM.format(n=len(scenes) if scenes else count), user)
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0) if match else text)
        character = str(data.get("character") or "").strip()
        out = [str(s).strip() for s in data.get("scenes") or [] if str(s).strip()]
    except Exception as exc:
        logger.info("scene boost failed, using plain scenes: %s", exc)
        return None
    if not out:
        return None
    return [f"{s} {character}".strip() for s in out[:6]]


async def video_prompt(prompt: str, style_words: str = "", seconds: int = 8) -> str:
    """A cinematic prompt for a true AI video model, or the original on any failure."""
    fallback = f"{prompt}. {style_words}" if style_words else prompt
    if not enabled():
        return fallback
    try:
        text = await _ask(VIDEO_SYSTEM.format(seconds=seconds),
                          f"Request: {prompt}\nStyle notes: {style_words or 'choose the best fitting look'}")
    except Exception as exc:
        logger.info("video prompt boost failed, using the original prompt: %s", exc)
        return fallback
    text = text.strip().strip('"').strip()
    return text[:1800] if len(text) >= 40 else fallback
