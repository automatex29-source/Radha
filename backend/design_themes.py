"""A design style for each app Krish designs, so two apps never come out looking the same.

The design kit (app_kit/krish-ui.css) has whole looks switched on with one class on <body>: glass, aurora, bento,
bold, luxury, minimal, playful and neon. The first build of a new app picks one: the style the user named
("make it glassy", "dark neon", "brutalist"), otherwise one that suits the kind of app, varied by the app's id so
two salons don't get the same site. The choice is kept on the app, so later changes stay in the same style, until
the user names another style or asks for a new look.
"""
import hashlib
import re
from typing import Optional

THEMES = {
    "glass": {
        "label": "Glass",
        "brief": "Glassmorphism: frosted, see-through panels floating over a soft, slowly moving colour field. Light and airy.",
        "effects": "glass cards over the colour field, an orb or rings shape in the hero, spin-border on the main card or "
                   "pricing plan, tilt on feature cards, reveal-stagger on card grids",
    },
    "aurora": {
        "label": "Aurora",
        "brief": "Dark and glowing: northern-lights gradients drifting behind the hero, cards with light borders that "
                 "glow on hover, gradient headline. Futuristic and premium.",
        "effects": "an orb in the hero, text-shimmer on one key word, spin-border on the main call to action card, "
                   "spotlight and tilt on cards, counting stats (data-count), reveal-stagger on grids",
    },
    "bento": {
        "label": "Bento",
        "brief": "Calm, Apple-like product page: neutral grey and white, large rounded tiles laid out as a bento grid "
                 "of different sizes, big confident headlines, very little colour.",
        "effects": "a bento grid (span-2, tall and wide tiles) for features or stats, counting numbers (data-count), "
                   "zoom photos inside tiles, reveal-stagger on the bento grid",
    },
    "bold": {
        "label": "Bold",
        "brief": "Neo-brutalist: thick black outlines, hard offset shadows, loud flat colour blocks, chunky uppercase "
                 "headlines. Fun, confident and different.",
        "effects": "a marquee strip of words or offers under the hero, tilted badges, cards that press in, "
                   "typed words in the headline (typed with data-words), reveal-stagger on grids",
    },
    "luxury": {
        "label": "Luxury",
        "brief": "Editorial luxury: an elegant serif display font, ivory and ink, fine gold lines, lots of space, big "
                 "photography, uppercase letter-spaced buttons. Like a premium fashion or hotel brand.",
        "effects": "large full-width photos with zoom, a marquee of press names or collections, reveal on every "
                   "section, slow fade-ins, few but large elements",
    },
    "minimal": {
        "label": "Minimal",
        "brief": "Swiss minimal: black on white, tight bold type, a strict grid, thin lines, no gradients. Clean and "
                 "fast, the content does the talking.",
        "effects": "big numbers that count up (data-count), a marquee of client names, reveal-stagger on lists and "
                   "grids, crisp hover states",
    },
    "playful": {
        "label": "Playful",
        "brief": "Playful and friendly: candy pastel colours, round friendly type, bouncy hovers, emoji or icon tiles, "
                 "blob shapes. Warm and joyful.",
        "effects": "float and blob shapes, cards that wiggle on hover, typed words in the headline (typed with "
                   "data-words), reveal-stagger on grids, a cheerful toast after actions",
    },
    "neon": {
        "label": "Neon",
        "brief": "Cyber neon: near-black with a faint grid, electric cyan and magenta glow, mono labels, a bold wide "
                 "display font. Gaming and tech energy.",
        "effects": "glowing spin-border cards, text-shimmer on the headline, rings in the hero, counting stats "
                   "(data-count), tilt and spotlight on cards, a marquee strip",
    },
}

# Words in a request that name a style.
_ASKED = [
    ("glass", r"glass|glassy|glassmorph|frosted|transparent|see.?through|kaanch|kanch"),
    ("aurora", r"aurora|northern light|glow(ing)?\b|gradient dark|futuristic|premium dark|space\b|galaxy"),
    ("bento", r"bento|apple|tiles?\b|clean product"),
    ("bold", r"brutal|neo.?brutal|bold|loud|chunky|retro|comic|funky"),
    ("luxury", r"luxury|luxurious|elegant|premium|classy|royal|gold(en)?\b|serif|editorial|wedding|jewel"),
    ("minimal", r"minimal|minimalist|simple|swiss|black and white|monochrome|clean\b"),
    ("playful", r"playful|cute|fun\b|kids?\b|pastel|cartoon|colou?rful|bubbly|cheerful"),
    ("neon", r"neon|cyber|hacker|matrix|synthwave|esports|dark mode gaming|tron"),
]
_ASKED_RE = [(t, re.compile(r"\b(?:" + w + r")", re.IGNORECASE)) for t, w in _ASKED]
# "make it look different", "new design", "change the style": a new look, in a style the app doesn't have yet.
_NEW_LOOK = re.compile(r"\b(new|different|another|fresh|change( the)?|other)\s+(look|style|design|theme|ui)\b|"
                       r"\bredesign\b|\brestyle\b|\bmake it (look )?different\b|\bdesign (badlo|change)\b|"
                       r"\b(look|style|design) (badlo|change karo)\b", re.IGNORECASE)

_ABOUT_LOOK = re.compile(r"\b(look|looks|style|styled|design|theme|ui|feel|vibe|make it|banao|bana do|karo)\b", re.IGNORECASE)

# Styles that suit each kind of app; the app's id picks among them.
_FITS = [
    (r"salon|spa|beauty|wedding|jewel|fashion|boutique|hotel|resort|interior|perfume|wine|villa|real estate|architect",
     ["luxury", "glass", "minimal"]),
    (r"game|gaming|esports|crypto|nft|hacker|cyber|music|dj|night ?club|tech event|hackathon", ["neon", "aurora", "bold"]),
    (r"ai\b|startup|saas|app landing|software|tool for|platform|fintech|analytics|dashboard|admin|crm",
     ["aurora", "glass", "bento", "minimal"]),
    (r"kids|school|toy|candy|ice ?cream|pet|party|birthday|quiz|cake|bakery|dessert", ["playful", "bold", "glass"]),
    (r"restaurant|cafe|café|coffee|food|pizza|dhaba|kitchen|burger|bar\b", ["bold", "luxury", "playful", "glass"]),
    (r"portfolio|resume|cv\b|photograph|designer|agency|studio|freelanc", ["minimal", "bento", "bold", "aurora"]),
    (r"shop|store|product|sell|e-?commerce|cart", ["bento", "glass", "bold", "minimal"]),
    (r"gym|fitness|sport|yoga|trainer", ["bold", "neon", "aurora"]),
    (r"doctor|clinic|hospital|health|dentist|lawyer|bank|insurance|consult", ["minimal", "glass", "bento"]),
    (r"todo|to-do|notes?|habit|timer|calculator|converter|tracker|planner", ["glass", "bento", "minimal", "playful", "aurora"]),
]
_ALL = list(THEMES)


def asked_for(text: str) -> Optional[str]:
    """The style the user named in `text`, or None."""
    found = [(m.start(), theme) for theme, pattern in _ASKED_RE for m in [pattern.search(text or "")] if m]
    return min(found)[1] if found else None  # the first style named


def _pick(options, seed: str, avoid: Optional[str] = None) -> str:
    choices = [t for t in options if t != avoid] or [t for t in _ALL if t != avoid]
    n = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16)
    return choices[n % len(choices)]


def suited(text: str, seed: str, avoid: Optional[str] = None) -> str:
    """A style that suits the kind of app the request describes, different apps getting different ones."""
    for pattern, options in _FITS:
        if re.search(pattern, text or "", re.IGNORECASE):
            return _pick(options, seed, avoid)
    return _pick(_ALL, seed, avoid)


def choose(request: str, current: Optional[str], seed: str, first_build: bool) -> Optional[str]:
    """The style for this turn: the named one, a new one for "a new look", one that suits a new app, or the
    current one. None when the app has no style and this isn't a new app (the user's own code keeps its look)."""
    named = asked_for(request)
    # After the first build a style word alone ("keep it simple", "a bold headline") isn't a new style.
    if named and (first_build or _ABOUT_LOOK.search(request or "")):
        return named
    if _NEW_LOOK.search(request or ""):
        return suited(request, seed + ":" + (current or ""), avoid=current)
    if current:
        return current
    return suited(request, seed) if first_build else None


def prompt_block(theme: Optional[str]) -> str:
    """The design direction for the builder."""
    t = THEMES.get(theme or "")
    if not t:
        return ""
    return (
        f"Design style for this app: {t['label']}. {t['brief']}\n"
        f"- Put class=\"theme-{theme}\" on <body> (Krish UI then sets the fonts, colours, surfaces and shadows of "
        "this style), keep it on every page, and design every section to fit this style. You may still set the "
        "brand colours with :root{--accent;--accent-2} when the business has its own.\n"
        f"- Make it feel alive with this style's signature motion: {t['effects']}. Use 2 to 4 of these, where they "
        "help, never on every element. All motion is built in and switched on by class: reveal, reveal-stagger "
        "(children animate in one by one), tilt, spotlight, spin-border (rotating light border), orb, rings, "
        "marquee > marquee-track (repeat the items twice), text-shimmer, gradient-anim, noise, float, glow, shine, "
        "zoom, <span data-count=\"1200\" data-suffix=\"+\">0</span>, <span class=\"typed\" data-words=\"a|b|c\"></span>, "
        "and bento > card.span-2/.tall/.wide. Phones get a menu button for nav-links by themselves.\n"
        "- If the user's request is a change to the content or a feature, keep this style exactly as it is.\n"
    )


def labels() -> list:
    return [{"id": k, "label": v["label"]} for k, v in THEMES.items()]
