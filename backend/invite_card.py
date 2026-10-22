"""The picture that goes with an invite: "Asha invited you to Krish AI · 7 days of Pro, free".

It is the link preview on WhatsApp, Telegram, X and email (og:image of /i/CODE), and the picture phones attach
when the Invite window shares. 1200 x 630, the size link previews expect. Made with Pillow and cached.
"""
import io
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE / "assets" / "fonts"
ICON = HERE / "assets" / "krish-icon-512.png"
W, H = 1200, 630
INK, MUTED, ORANGE, SOFT = (17, 17, 17), (95, 99, 112), (255, 138, 30), (255, 240, 225)
# Inter covers Latin names; anything else (Devanagari, emoji...) falls back to "A friend".
_LATIN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' .-]+$")


def _font(weight: str, size: int):
    for path in (FONTS / f"Inter-{weight}.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")):
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def first_name(name: str) -> str:
    first = (name or "").strip().split(" ")[0][:16]
    return first if first and _LATIN.match(first) else ""


def _fit(draw, text: str, weight: str, size: int, width: int):
    """The biggest font, from `size` down, that keeps `text` within `width`."""
    while size > 28:
        font = _font(weight, size)
        if draw.textlength(text, font=font) <= width:
            return font
        size -= 4
    return _font(weight, size)


def _card(top: str, bottom: str, accent: str, pill: str, line: str) -> bytes:
    """Logo on the left; two big lines (the end of `bottom` in orange), an orange pill and a grey line."""
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    # A soft orange glow behind the logo.
    for i in range(14, 0, -1):
        t = i / 14
        c = tuple(int(255 - (255 - s) * (1 - t)) for s in SOFT)
        r = int(150 + 170 * t)
        d.ellipse((270 - r, 315 - r, 270 + r, 315 + r), fill=c)
    if ICON.is_file():
        icon = Image.open(ICON).convert("RGB").resize((300, 300), Image.LANCZOS)
        mask = Image.new("L", icon.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 300, 300), fill=255)
        img.paste(icon, (120, 165), mask)

    x, right = 510, 1130
    d.text((x, 150), top, font=_fit(d, top, "ExtraBold", 72, right - x), fill=INK)
    font = _fit(d, bottom + accent, "ExtraBold", 72, right - x)
    d.text((x, 235), bottom, font=font, fill=INK)
    d.text((x + d.textlength(bottom, font=font), 235), accent, font=font, fill=ORANGE)

    pf = _font("ExtraBold", 38)
    pw = d.textlength(pill, font=pf)
    d.rounded_rectangle((x, 350, x + pw + 56, 420), radius=35, fill=ORANGE)
    d.text((x + 28, 362), pill, font=pf, fill=(255, 255, 255))
    d.text((x, 452), line, font=_fit(d, line, "Medium", 30, right - x), fill=MUTED)
    d.text((x, 520), "B Y   E M P I R E X", font=_font("Medium", 20), fill=(140, 144, 156))

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


@lru_cache(maxsize=512)
def render(name: str, days: int) -> bytes:
    """The invite picture: "<Name> invited you to Krish AI · N days of Pro, free"."""
    who = first_name(name)
    return _card(f"{who} invited you" if who else "You're invited", "to Krish ", "AI", f"{days} days of Pro, free",
                 "Chat, study, build apps and get Gita guidance.")


@lru_cache(maxsize=256)
def welcome(name: str, plan: str = "") -> bytes:
    """The picture in welcome emails: "Welcome, <Name> · to Krish AI" or "· to Krish AI Pro"."""
    who = first_name(name)
    pill = {"pro": "Pro is on", "max": "Max is on"}.get(plan, "Free to start")
    line = ("More pictures, decks, videos and premium AI." if plan else
            "Ask anything. Write, study, plan and build.")
    return _card(f"Welcome, {who}" if who else "Welcome", "to Krish ", "AI", pill, line)
