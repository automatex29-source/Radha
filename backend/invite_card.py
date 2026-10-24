"""The picture that goes with an invite: "Asha invited you to Krish AI · 7 days of Pro, free".

It is the link preview on WhatsApp, Telegram, X and email (og:image of /i/CODE), and the picture phones attach
when the Invite window shares. 1200 x 630, the size link previews expect. Made with Pillow and cached.
"""
import io
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE / "assets" / "fonts"
ICON = HERE / "assets" / "krish-icon-512.png"
W, H = 1200, 630
BG, GOLD = (11, 12, 20), (255, 176, 72)
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


def _glow(size, center, radius, color, strength):
    """A soft round light, for the dark background."""
    layer = Image.new("RGB", size, (0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for i in range(40, 0, -1):
        t = i / 40
        c = tuple(int(v * strength * (1 - t) ** 1.6) for v in color)
        r = int(radius * t)
        ld.ellipse((center[0] - r, center[1] - r, center[0] + r, center[1] + r), fill=c)
    return layer.filter(ImageFilter.GaussianBlur(24))


def _card(top: str, bottom: str, accent: str, pill: str, line: str) -> bytes:
    """A dark, premium card: the logo in a soft light on the left; the words on the right."""
    from PIL import ImageChops
    img = Image.new("RGB", (W, H), BG)
    img = ImageChops.add(img, _glow((W, H), (300, 315), 420, (255, 138, 30), 0.55))
    img = ImageChops.add(img, _glow((W, H), (1150, -40), 520, (99, 102, 241), 0.45))
    d = ImageDraw.Draw(img)
    # A thin frame, like a gift card.
    d.rounded_rectangle((24, 24, W - 24, H - 24), radius=34, outline=(48, 50, 66), width=2)
    if ICON.is_file():
        icon = Image.open(ICON).convert("RGB").resize((236, 236), Image.LANCZOS)
        mask = Image.new("L", icon.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 236, 236), fill=255)
        d.ellipse((300 - 134, 315 - 134, 300 + 134, 315 + 134), outline=(255, 170, 90), width=3)
        img.paste(icon, (300 - 118, 315 - 118), mask)

    x, right = 540, 1120
    d.text((x, 120), "KRISH AI  ·  BY EMPIREX", font=_font("Medium", 20), fill=(150, 154, 175))
    d.text((x, 168), top, font=_fit(d, top, "ExtraBold", 64, right - x), fill=(255, 255, 255))
    font = _fit(d, bottom + accent, "ExtraBold", 64, right - x)
    d.text((x, 246), bottom, font=font, fill=(255, 255, 255))
    d.text((x + d.textlength(bottom, font=font), 246), accent, font=font, fill=GOLD)

    pf = _font("ExtraBold", 30)
    pw = d.textlength(pill, font=pf)
    d.rounded_rectangle((x, 362, x + pw + 48, 418), radius=28, fill=GOLD)
    d.text((x + 24, 373), pill, font=pf, fill=BG)
    d.text((x, 452), line, font=_fit(d, line, "Medium", 26, right - x), fill=(190, 194, 210))

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


@lru_cache(maxsize=512)
def render(name: str, days: int) -> bytes:
    """The invite picture: "<Name> invited you to Krish AI · N days of Pro, free"."""
    who = first_name(name)
    return _card(f"{who} invited you" if who else "You're invited", "to Krish ", "AI", f"A gift: {days} days of Pro",
                 "Your AI for answers, study, writing and creating.")


@lru_cache(maxsize=256)
def welcome(name: str, plan: str = "") -> bytes:
    """The picture in welcome emails: "Welcome, <Name> · to Krish AI" or "· to Krish AI Pro"."""
    who = first_name(name)
    pill = {"pro": "Pro is on", "max": "Max is on"}.get(plan, "Free to start")
    line = ("More pictures, decks, apps and premium AI." if plan else
            "Ask anything. Write, study, plan and build.")
    return _card(f"Welcome, {who}" if who else "Welcome", "to Krish ", "AI", pill, line)
