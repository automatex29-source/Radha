"""Deck themes, slide normalisation and the PowerPoint renderer for the Decks page.

A deck is a list of slide dicts (see normalize_slide). The browser draws the same
slides on a 1280x720 canvas, and this module draws them into a 16:9 .pptx with the
same coordinates (1 px = 9525 EMU at 96 dpi), so the download matches the preview.
"""
import io
import re
import uuid
from typing import Callable, Dict, List, Optional

LAYOUTS = ("cover", "section", "agenda", "bullets", "image_right", "image_left", "cards", "stats", "chart", "steps",
           "timeline", "quote", "comparison", "table", "closing")
CHART_TYPES = ("bar", "line", "pie", "doughnut")
IMAGE_LAYOUTS = ("cover", "image_right", "image_left")
MAX_SLIDES = 30

# html_* fonts are Google Fonts the preview loads; pptx_* are safe fonts PowerPoint has everywhere.
THEMES: List[dict] = [
    {"id": "aurora", "name": "Aurora", "dark": True, "bg": "0B1020", "bg2": "1E1B4B", "surface": "161B33",
     "title": "FFFFFF", "text": "CBD5E1", "muted": "94A3B8", "accent": "818CF8", "accent2": "22D3EE",
     "html_heading": "Plus Jakarta Sans", "html_body": "Inter", "pptx_heading": "Segoe UI Semibold", "pptx_body": "Segoe UI"},
    {"id": "midnight", "name": "Midnight", "dark": True, "bg": "0A0A0F", "bg2": "0A0A0F", "surface": "17171F",
     "title": "F8FAFC", "text": "D4D4D8", "muted": "A1A1AA", "accent": "F59E0B", "accent2": "FB923C",
     "html_heading": "Space Grotesk", "html_body": "Inter", "pptx_heading": "Segoe UI Semibold", "pptx_body": "Segoe UI"},
    {"id": "ocean", "name": "Ocean", "dark": True, "bg": "042F4B", "bg2": "0C4A6E", "surface": "0B3D5C",
     "title": "FFFFFF", "text": "E0F2FE", "muted": "7DD3FC", "accent": "38BDF8", "accent2": "2DD4BF",
     "html_heading": "Outfit", "html_body": "Inter", "pptx_heading": "Segoe UI Semibold", "pptx_body": "Segoe UI"},
    {"id": "sunset", "name": "Sunset", "dark": True, "bg": "2A0E2E", "bg2": "7C2D12", "surface": "3B1537",
     "title": "FFF7ED", "text": "FED7AA", "muted": "FDBA74", "accent": "FB7185", "accent2": "FBBF24",
     "html_heading": "Outfit", "html_body": "Inter", "pptx_heading": "Segoe UI Semibold", "pptx_body": "Segoe UI"},
    {"id": "forest", "name": "Forest", "dark": True, "bg": "052E16", "bg2": "14532D", "surface": "0F3D22",
     "title": "F0FDF4", "text": "D1FAE5", "muted": "86EFAC", "accent": "4ADE80", "accent2": "A3E635",
     "html_heading": "DM Serif Display", "html_body": "Inter", "pptx_heading": "Georgia", "pptx_body": "Segoe UI"},
    {"id": "paper", "name": "Paper", "dark": False, "bg": "FAF7F2", "bg2": "F3EDE3", "surface": "FFFFFF",
     "title": "1C1917", "text": "44403C", "muted": "78716C", "accent": "C2410C", "accent2": "B45309",
     "html_heading": "Playfair Display", "html_body": "Inter", "pptx_heading": "Georgia", "pptx_body": "Calibri"},
    {"id": "snow", "name": "Snow", "dark": False, "bg": "FFFFFF", "bg2": "EEF2FF", "surface": "F8FAFC",
     "title": "0F172A", "text": "334155", "muted": "64748B", "accent": "4F46E5", "accent2": "0EA5E9",
     "html_heading": "Plus Jakarta Sans", "html_body": "Inter", "pptx_heading": "Segoe UI Semibold", "pptx_body": "Segoe UI"},
    {"id": "candy", "name": "Candy", "dark": False, "bg": "FDF2F8", "bg2": "EDE9FE", "surface": "FFFFFF",
     "title": "4A044E", "text": "581C87", "muted": "9D4EDD", "accent": "DB2777", "accent2": "7C3AED",
     "html_heading": "Outfit", "html_body": "Inter", "pptx_heading": "Segoe UI Semibold", "pptx_body": "Segoe UI"},
    {"id": "mono", "name": "Mono", "dark": False, "bg": "F5F5F4", "bg2": "F5F5F4", "surface": "FFFFFF",
     "title": "0C0A09", "text": "292524", "muted": "57534E", "accent": "0C0A09", "accent2": "57534E",
     "html_heading": "Space Grotesk", "html_body": "Inter", "pptx_heading": "Segoe UI Semibold", "pptx_body": "Segoe UI"},
]
THEME_IDS = [t["id"] for t in THEMES]
DEFAULT_THEME = "aurora"


def get_theme(theme_id: str) -> dict:
    return next((t for t in THEMES if t["id"] == theme_id), THEMES[0])


# ----------------------------------------------------------- normalisation
def _s(v, limit: int) -> str:
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _strs(v, n: int, limit: int) -> List[str]:
    items = v if isinstance(v, list) else ([v] if v else [])
    out = [_s(x.get("text") if isinstance(x, dict) else x, limit) for x in items]
    return [x.lstrip("-•* ").strip() for x in out if x][:n]


def _items(v, n: int) -> List[dict]:
    out = []
    for it in (v if isinstance(v, list) else [])[:n]:
        if isinstance(it, dict):
            out.append({"icon": _s(it.get("icon"), 8), "title": _s(it.get("title"), 60), "text": _s(it.get("text"), 170)})
        elif it:
            out.append({"icon": "", "title": _s(it, 60), "text": ""})
    return out


def _stats(v) -> List[dict]:
    out = []
    for it in (v if isinstance(v, list) else [])[:4]:
        if isinstance(it, dict) and (it.get("value") or it.get("label")):
            out.append({"value": _s(it.get("value"), 12), "label": _s(it.get("label"), 80)})
    return out


def _column(v) -> dict:
    v = v if isinstance(v, dict) else {"bullets": v}
    return {"title": _s(v.get("title"), 50), "bullets": _strs(v.get("bullets"), 5, 110)}


def _image(v) -> Optional[dict]:
    url = str(v.get("url") or "") if isinstance(v, dict) else ""
    if not (url.startswith("https://") or re.fullmatch(r"/api/media/[\w-]{8,64}", url)):
        return None
    return {k: str(v.get(k) or "")[:500] for k in ("url", "thumb", "credit", "link")}


def _num(v) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v or "").replace(",", ""))
    return float(m.group()) if m else None


def _chart(v) -> Optional[dict]:
    """{type, labels, series: [{name, values}]} with numbers only; None when there is no usable data."""
    if not isinstance(v, dict):
        return None
    labels = [_s(x, 30) for x in (v.get("labels") or [])][:12]
    series = []
    for sr in (v.get("series") or [])[:4]:
        if not isinstance(sr, dict):
            continue
        vals = [_num(x) for x in (sr.get("values") or [])][: len(labels)]
        vals += [None] * (len(labels) - len(vals))
        if any(x is not None for x in vals):
            series.append({"name": _s(sr.get("name"), 40) or f"Series {len(series) + 1}",
                           "values": [x if x is not None else 0.0 for x in vals]})
    if not labels or not series:
        return None
    kind = str(v.get("type") or "bar").lower()
    kind = {"column": "bar", "donut": "doughnut", "area": "line"}.get(kind, kind)
    if kind not in CHART_TYPES:
        kind = "bar"
    if kind in ("pie", "doughnut"):
        series = series[:1]
    return {"type": kind, "labels": labels, "series": series, "unit": _s(v.get("unit"), 12)}


def _table(v) -> Optional[dict]:
    """{columns, rows} of short strings, at most 6 columns and 10 rows; None when empty."""
    if not isinstance(v, dict):
        return None
    cols = [_s(c, 40) for c in (v.get("columns") or [])][:6]
    rows = [[_s(c, 60) for c in r][:6] for r in (v.get("rows") or []) if isinstance(r, list)][:10]
    if not rows:
        return None
    n = max(len(cols), max(len(r) for r in rows))
    return {"columns": cols + [""] * (n - len(cols)) if cols else [], "rows": [r + [""] * (n - len(r)) for r in rows]}


def normalize_slide(raw: dict, keep_id: bool = True) -> dict:
    """Clamp a model- or user-written slide to the fields and lengths the layouts can draw."""
    raw = raw if isinstance(raw, dict) else {}
    layout = str(raw.get("layout") or "bullets").strip().lower().replace("-", "_").replace(" ", "_")
    layout = {"graph": "chart", "data": "chart", "title": "cover", "two_column": "comparison", "image": "image_right",
              "end": "closing", "thanks": "closing", "contents": "agenda", "outline": "agenda", "toc": "agenda",
              "process": "steps", "history": "timeline", "milestones": "timeline", "features": "cards",
              "icons": "cards", "numbers": "stats", "versus": "comparison", "vs": "comparison"}.get(layout, layout)
    if layout not in LAYOUTS:
        layout = "bullets"
    slide = {
        "id": str(raw.get("id") or "") if keep_id and raw.get("id") else uuid.uuid4().hex[:12],
        "layout": layout,
        "title": _s(raw.get("title"), 90),
        "subtitle": _s(raw.get("subtitle"), 160),
        "body": _s(raw.get("body"), 320),
        "bullets": _strs(raw.get("bullets"), 6, 140),
        "items": _items(raw.get("items") or raw.get("cards") or raw.get("steps"),
                        {"steps": 5, "timeline": 6}.get(layout, 4)),
        "stats": _stats(raw.get("stats")),
        "quote": _s(raw.get("quote"), 240),
        "author": _s(raw.get("author"), 80),
        "left": _column(raw.get("left")),
        "right": _column(raw.get("right")),
        "chart": _chart(raw.get("chart")),
        "table": _table(raw.get("table")),
        "image_query": _s(raw.get("image_query"), 60),
        "image_prompt": _s(raw.get("image_prompt"), 400),
        "image": _image(raw.get("image")),
        "notes": str(raw.get("notes") or "")[:2000],
    }
    return slide


def _mix(a: str, b: str, k: float) -> str:
    ca, cb = [int(a[i:i + 2], 16) for i in (0, 2, 4)], [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(x + (y - x) * k):02X}" for x, y in zip(ca, cb))


def palette(t: dict) -> List[str]:
    """Chart colours from the theme: accents first, then blends that stay readable on the background."""
    return [t["accent"], t["accent2"], _mix(t["accent"], t["title"], 0.45), _mix(t["accent2"], t["bg"], 0.35),
            _mix(t["accent"], t["accent2"], 0.5), t["muted"], _mix(t["accent"], t["bg"], 0.5), _mix(t["accent2"], t["title"], 0.5)]


# ------------------------------------------------------------------ motion
# Every slide gets a transition, and its content builds in after the title (cards one by one, bullets line by
# line, a chart fading up), on its own: the presenter only moves between slides. It is plain PowerPoint XML,
# so PowerPoint, Keynote, Google Slides and LibreOffice all play it (or show the finished slide).
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
TRANSITIONS = {"cover": '<p:fade/>', "closing": '<p:fade/>', "section": '<p:push dir="u"/>',
               "quote": '<p:fade/>'}
DEFAULT_TRANSITION = '<p:wipe dir="r"/>'
# Indian scripts aren't in the deck's Latin fonts: PowerPoint uses this font for them (Windows ships it;
# other systems fall back to their own Devanagari, Tamil... font).
COMPLEX_SCRIPT_FONT = "Nirmala UI"


def _transition_xml(layout: str) -> str:
    return (f'<p:transition xmlns:p="{_P_NS}" spd="med">'
            f'{TRANSITIONS.get(layout, DEFAULT_TRANSITION)}</p:transition>')


def _timing_xml(effects: List[dict]) -> str:
    """Entrance effects that start by themselves once the slide is shown, each `delay` ms after the first.

    An effect is {spid, kind: fade|rise, delay, para (paragraph index, for a line-by-line list),
    build: "text" | "graphic" | None}."""
    ids = iter(range(5, 10_000))
    pars, builds = [], {}
    for i, e in enumerate(effects):
        spid = e["spid"]
        tgt = (f'<p:spTgt spid="{spid}"/>' if e.get("para") is None else
               f'<p:spTgt spid="{spid}"><p:txEl><p:pRg st="{e["para"]}" end="{e["para"]}"/></p:txEl></p:spTgt>')
        dur = 600 if e["kind"] == "rise" else 500
        cid, sid, fid = next(ids), next(ids), next(ids)
        grp = ' grpId="0"' if e.get("build") else ""
        if e.get("build") == "text":
            by_line = ' build="p"' if e.get("para") is not None else ""
            builds[spid] = f'<p:bldP spid="{spid}" grpId="0"{by_line}/>'
        elif e.get("build") == "graphic":
            builds[spid] = f'<p:bldGraphic spid="{spid}" grpId="0"><p:bldAsOne/></p:bldGraphic>'
        motion = ""
        if e["kind"] == "rise":
            motion = (f'<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="{next(ids)}" '
                      f'dur="{dur}" fill="hold"/><p:tgtEl>{tgt}</p:tgtEl><p:attrNameLst><p:attrName>ppt_y'
                      f'</p:attrName></p:attrNameLst></p:cBhvr><p:tavLst><p:tav tm="0"><p:val><p:strVal '
                      f'val="#ppt_y+0.05"/></p:val></p:tav><p:tav tm="100000"><p:val><p:strVal val="#ppt_y"/>'
                      f'</p:val></p:tav></p:tavLst></p:anim>')
        preset = 47 if e["kind"] == "rise" else 10  # Ascend / Fade
        pars.append(
            f'<p:par><p:cTn id="{cid}" presetID="{preset}" presetClass="entr" presetSubtype="0" fill="hold"{grp} '
            f'nodeType="{"afterEffect" if i == 0 else "withEffect"}"><p:stCondLst><p:cond delay="{e["delay"]}"/>'
            f'</p:stCondLst><p:childTnLst><p:set><p:cBhvr><p:cTn id="{sid}" dur="1" fill="hold"><p:stCondLst>'
            f'<p:cond delay="0"/></p:stCondLst></p:cTn><p:tgtEl>{tgt}</p:tgtEl><p:attrNameLst><p:attrName>'
            f'style.visibility</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to>'
            f'</p:set><p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{fid}" dur="{dur}"/>'
            f'<p:tgtEl>{tgt}</p:tgtEl></p:cBhvr></p:animEffect>{motion}</p:childTnLst></p:cTn></p:par>')
    bld = f'<p:bldLst>{"".join(builds.values())}</p:bldLst>' if builds else ""
    return (
        f'<p:timing xmlns:p="{_P_NS}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" '
        f'nodeType="tmRoot"><p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" '
        f'nodeType="mainSeq"><p:childTnLst><p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond '
        f'delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst>'
        f'<p:childTnLst><p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
        f'<p:childTnLst>{"".join(pars)}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>'
        f'</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl>'
        f'</p:cond></p:prevCondLst><p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/>'
        f'</p:tgtEl></p:cond></p:nextCondLst></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>{bld}</p:timing>')


def _add_motion(slide, layout: str, effects: List[dict]):
    from lxml import etree

    el = slide._element
    anchor = el.find(f"{{{_P_NS}}}clrMapOvr")
    at = list(el).index(anchor) + 1 if anchor is not None else len(el)
    el.insert(at, etree.fromstring(_transition_xml(layout)))
    if effects:
        el.insert(at + 1, etree.fromstring(_timing_xml(effects)))


def _script_fonts(slide):
    """Name a complex-script font on every run, so Hindi and other Indian scripts get a real font."""
    from lxml import etree

    for rpr in slide._element.iter(f"{{{_A_NS}}}rPr", f"{{{_A_NS}}}defRPr"):
        latin = rpr.find(f"{{{_A_NS}}}latin")
        if latin is not None and rpr.find(f"{{{_A_NS}}}cs") is None:
            latin.addnext(etree.Element(f"{{{_A_NS}}}cs", typeface=COMPLEX_SCRIPT_FONT))


# --------------------------------------------------------------- PowerPoint
def _fit(size: float, text: str, soft: int) -> float:
    """Shrink a font a little for long text so it stays inside its box."""
    n = len(text or "")
    if n <= soft:
        return size
    return max(size * 0.62, size * (soft / n) ** 0.5)


def _fit_width(size: float, text: str, width: float, em: float = 0.6) -> float:
    """The largest size up to `size` at which a one-line value fits in `width` px."""
    n = max(1, len(text or ""))
    return max(20.0, min(size, width / (n * em)))


def build_deck_pptx(title: str, slides: List[dict], theme_id: str,
                    image_bytes: Optional[Callable[[str], Optional[bytes]]] = None, motion: bool = True) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Pt

    t = get_theme(theme_id)
    rgb = RGBColor.from_string
    px = lambda v: Emu(int(v * 9525))  # noqa: E731
    W, H, PAD = 1280, 720, 80
    on_accent = t["bg"] if t["dark"] else "FFFFFF"

    prs = Presentation()
    prs.slide_width, prs.slide_height = px(W), px(H)
    prs.core_properties.title = title or "Presentation"
    prs.core_properties.author = "Krish AI"
    blank = prs.slide_layouts[6]

    def see_through(shape, opacity: float):
        fill = shape.fill._xPr.find(qn("a:solidFill"))
        if fill is not None and len(fill):
            fill[0].append(fill[0].makeelement(qn("a:alpha"), {"val": str(int(opacity * 100000))}))

    def rect(sh, x, y, w, h, color, radius=None, line=None, opacity=None):
        shape = sh.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                             px(x), px(y), px(w), px(h))
        if radius:
            shape.adjustments[0] = min(0.5, radius / max(1, min(w, h)))
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(color)
        if opacity is not None:
            see_through(shape, opacity)
        if line:
            shape.line.color.rgb = rgb(line)
            shape.line.width = Pt(0.75)
        else:
            shape.line.fill.background()
        shape.shadow.inherit = False
        return shape

    def oval(sh, x, y, d, color, opacity=None, ring=None):
        shape = sh.add_shape(MSO_SHAPE.OVAL, px(x), px(y), px(d), px(d))
        if ring:  # an outline only
            shape.fill.background()
            shape.line.color.rgb = rgb(color)
            shape.line.width = Pt(ring)
        else:
            shape.fill.solid()
            shape.fill.fore_color.rgb = rgb(color)
            if opacity is not None:
                see_through(shape, opacity)
            shape.line.fill.background()
        shape.shadow.inherit = False
        return shape

    def text(sh, x, y, w, h, value, size, color, bold=False, italic=False, align="left", anchor="top",
             heading=False, spacing=1.1):
        if not value:
            return None
        box = sh.add_textbox(px(x), px(y), px(w), px(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[anchor]
        p = tf.paragraphs[0]
        p.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
        p.line_spacing = spacing
        run = p.add_run()
        run.text = value
        f = run.font
        f.size = Pt(size * 0.75)
        f.bold, f.italic = bold, italic
        f.name = t["pptx_heading"] if heading else t["pptx_body"]
        f.color.rgb = rgb(color)
        return box

    def label(box, kind="Label"):
        """Name decoration text, so previews and text extraction skip it (see preview.DECOR_NAMES)."""
        if box is not None:
            box.name = kind
        return box

    def badge(sh, x, y, d, value, color, size=None):
        """A tinted circle with an emoji or a number in the middle."""
        oval(sh, x, y, d, color, opacity=0.2 if t["dark"] else 0.14)
        label(text(sh, x, y, d, d, value, size or d * 0.46, color, bold=True, heading=True, align="center",
                   anchor="middle", spacing=1.0))

    def bullet_list(sh, x, y, w, h, items, size=26):
        if not items:
            return None
        size = min(size, 26 if len(items) <= 4 else 22)

        def height(sz):  # rough height of the list at this size: ~0.5em per character, 1.15 line height
            per_line = max(8, int((w - sz) / (sz * 0.5)))
            lines = sum(-(-len(it) // per_line) for it in items)
            return lines * sz * 1.15 * 1.2 + len(items) * sz * 0.7

        while size > 14 and height(size) > h:
            size -= 1
        box = sh.add_textbox(px(x), px(y), px(w), px(h))
        tf = box.text_frame
        tf.word_wrap = True
        # The size is worked out above: viewers that "shrink text on overflow" (LibreOffice, Google Slides)
        # otherwise shrink lists to a tiny size.
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(size * 0.75 * 0.7)
            p.line_spacing = 1.15
            dot = p.add_run()
            dot.text = "●  "
            dot.font.size = Pt(size * 0.75 * 0.6)
            dot.font.color.rgb = rgb(t["accent"] if i % 2 == 0 else t["accent2"])
            dot.font.name = t["pptx_body"]
            r = p.add_run()
            r.text = item
            r.font.size = Pt(size * 0.75)
            r.font.name = t["pptx_body"]
            r.font.color.rgb = rgb(t["text"])
        return box

    def picture(sh, img: Optional[dict], x, y, w, h):
        data = image_bytes(img["url"]) if (img and image_bytes) else None
        if not data:
            # No photo: a soft accent panel with rings keeps the layout balanced.
            panel = rect(sh, x, y, w, h, t["surface"])
            panel.fill.gradient()
            panel.fill.gradient_angle = 45
            panel.fill.gradient_stops[0].color.rgb = rgb(t["accent"])
            panel.fill.gradient_stops[1].color.rgb = rgb(t["accent2"])
            oval(sh, x + w * 0.18, y + h * 0.22, min(w, h) * 0.64, "FFFFFF", opacity=0.12)
            oval(sh, x + w * 0.32, y + h * 0.36, min(w, h) * 0.36, "FFFFFF", opacity=0.14)
            return panel
        from PIL import Image

        try:
            iw, ih = Image.open(io.BytesIO(data)).size
        except Exception:
            return None
        pic = sh.add_picture(io.BytesIO(data), px(x), px(y), px(w), px(h))
        box_ratio, img_ratio = w / h, iw / ih
        if img_ratio > box_ratio:  # too wide: crop the sides
            cut = (1 - box_ratio / img_ratio) / 2
            pic.crop_left = pic.crop_right = cut
        else:  # too tall: crop top and bottom
            cut = (1 - img_ratio / box_ratio) / 2
            pic.crop_top = pic.crop_bottom = cut
        return pic

    def add_chart(sh, ch, x, y, w, h):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION

        data = CategoryChartData()
        data.categories = ch["labels"]
        for sr in ch["series"]:
            data.add_series(sr["name"], sr["values"])
        kind = {"bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS, "pie": XL_CHART_TYPE.PIE,
                "doughnut": XL_CHART_TYPE.DOUGHNUT}[ch["type"]]
        frame = sh.add_chart(kind, px(x), px(y), px(w), px(h), data)
        chart = frame.chart
        chart.has_title = False
        chart.font.size = Pt(13)
        chart.font.name = t["pptx_body"]
        chart.font.color.rgb = rgb(t["text"])
        colors = palette(t)
        round_pie = ch["type"] in ("pie", "doughnut")
        chart.has_legend = round_pie or len(ch["series"]) > 1
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.RIGHT if round_pie else XL_LEGEND_POSITION.TOP
            chart.legend.include_in_layout = False
            chart.legend.font.color.rgb = rgb(t["text"])
            chart.legend.font.size = Pt(15)
        plot = chart.plots[0]
        if round_pie:
            for i, point in enumerate(plot.series[0].points):
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = rgb(colors[i % len(colors)])
            plot.has_data_labels = True
            plot.data_labels.show_percentage = True
            plot.data_labels.show_value = False
            plot.data_labels.number_format = "0%"
            plot.data_labels.number_format_is_linked = False
            plot.data_labels.font.color.rgb = rgb("FFFFFF")
            plot.data_labels.font.bold = True
        else:
            for i, sr in enumerate(plot.series):
                color = rgb(colors[i % len(colors)])
                if ch["type"] == "line":
                    sr.format.line.color.rgb = color
                    sr.format.line.width = Pt(3.5)
                    sr.smooth = True
                else:
                    sr.format.fill.solid()
                    sr.format.fill.fore_color.rgb = color
            if ch["type"] == "bar":
                plot.gap_width = 60
                if len(ch["series"]) == 1:  # one series: each bar its own shade, the latest one strongest
                    n_bars = len(ch["labels"])
                    for i, point in enumerate(plot.series[0].points):
                        point.format.fill.solid()
                        point.format.fill.fore_color.rgb = rgb(_mix(t["accent"], t["bg"], 0.55 * (1 - (i + 1) / n_bars))
                                                               if n_bars > 1 else t["accent"])
            if len(ch["series"]) == 1 and len(ch["labels"]) <= 8:
                plot.has_data_labels = True
                plot.data_labels.font.color.rgb = rgb(t["title"])
                plot.data_labels.font.bold = True
                if ch["type"] == "bar":
                    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
            for axis in (chart.category_axis, chart.value_axis):
                axis.format.line.color.rgb = rgb(t["muted"])
                axis.tick_labels.font.color.rgb = rgb(t["muted"])
            chart.value_axis.has_major_gridlines = True
            chart.value_axis.major_gridlines.format.line.color.rgb = rgb(t["surface"])
        return frame

    def heading(sh, value, y=64, w=W - 2 * PAD, x=PAD):
        text(sh, x, y, w, 70, value, _fit(44, value, 40), t["title"], bold=True, heading=True, anchor="bottom")
        rect(sh, x, y + 86, 64, 6, t["accent"], radius=3)
        rect(sh, x + 72, y + 86, 14, 6, t["accent2"], radius=3)

    def background(s):
        fill = s.background.fill
        if t["bg2"] != t["bg"]:
            fill.gradient()
            fill.gradient_angle = 135
            fill.gradient_stops[0].color.rgb = rgb(t["bg"])
            fill.gradient_stops[1].color.rgb = rgb(t["bg2"])
        else:
            fill.solid()
            fill.fore_color.rgb = rgb(t["bg"])

    def decor(sh, n, lay):
        """Soft circles in a corner, so a slide reads as designed and not as a blank page with text."""
        soft = 0.10 if t["dark"] else 0.08
        if lay in ("cover", "closing"):
            oval(sh, W - 420, -220, 640, t["accent"], opacity=soft + 0.06)
            oval(sh, -240, H - 260, 480, t["accent2"], opacity=soft + 0.02)
            oval(sh, W - 250, H - 230, 300, t["accent2"], ring=1.5)
            oval(sh, 120, 90, 18, t["accent2"], opacity=0.8)
            oval(sh, W - 200, 560, 12, t["accent"], opacity=0.8)
        elif lay in ("image_right", "image_left"):
            x = 520 if lay == "image_right" else 1080
            oval(sh, x, H - 140, 240, t["accent"], opacity=soft)
        elif n % 2:
            oval(sh, W - 230, -170, 400, t["accent"], opacity=soft)
            oval(sh, W - 120, 150, 14, t["accent2"], opacity=0.7)
        else:
            oval(sh, -170, H - 210, 380, t["accent2"], opacity=soft)
            oval(sh, W - 150, 70, 14, t["accent"], opacity=0.7)

    total = len(slides)
    part = 0
    for n, sl in enumerate(slides, 1):
        sl = normalize_slide(sl)
        s = prs.slides.add_slide(blank)
        S = s.shapes
        background(s)
        lay = sl["layout"]
        decor(S, n, lay)
        fx: List[dict] = []  # entrance effects, in the order they play

        def animate(shape, kind="rise", build=None, para=None, gap=180):
            if shape is None:
                return
            delay = 0 if not fx else fx[-1]["delay"] + gap
            fx.append({"spid": shape.shape_id, "kind": kind, "build": build, "para": para, "delay": delay})

        def animate_list(box, count, gap=160):
            if box is not None:
                for i in range(count):
                    animate(box, "fade", build="text", para=i, gap=gap)

        if lay in ("cover", "closing"):
            has_img = lay == "cover" and sl["image"] is not None and image_bytes is not None
            tw = 560 if has_img else W - 2 * PAD - 120
            tx = PAD if has_img else (W - tw) / 2
            align = "left" if has_img else "center"
            if has_img:
                picture(S, sl["image"], 680, 0, 600, H)
            text(S, tx, 150, tw, 250, sl["title"], _fit(64, sl["title"], 36), t["title"], bold=True, heading=True,
                 align=align, anchor="bottom", spacing=1.0)
            bar = rect(S, tx if has_img else (W - 90) / 2, 420, 90, 7, t["accent"], radius=3)
            sub = text(S, tx, 452, tw, 130, sl["subtitle"] or sl["body"], _fit(26, sl["subtitle"] or sl["body"], 110),
                       t["muted"], align=align)
            animate(bar, "fade")
            animate(sub, "rise", build="text")
        elif lay == "section":
            part += 1
            d = 460
            ring = oval(S, W - PAD - d + 40, (H - d) / 2, d, t["accent"], ring=2)
            disc = oval(S, W - PAD - d + 100, (H - d) / 2 + 60, d - 120, t["accent"])
            disc.fill.gradient()
            disc.fill.gradient_angle = 45
            disc.fill.gradient_stops[0].color.rgb = rgb(t["accent"])
            disc.fill.gradient_stops[1].color.rgb = rgb(t["accent2"])
            num = label(text(S, W - PAD - d + 100, (H - d) / 2 + 60, d - 120, d - 120, f"{part:02d}", 150, on_accent,
                             bold=True, heading=True, align="center", anchor="middle", spacing=1.0))
            text(S, PAD, 190, 600, 250, sl["title"], _fit(56, sl["title"], 30), t["title"], bold=True,
                 heading=True, anchor="bottom", spacing=1.0)
            label(text(S, PAD, 140, 200, 30, "PART", 18, t["accent"], bold=True, heading=True))
            rect(S, PAD, 462, 90, 7, t["accent"], radius=3)
            sub = text(S, PAD, 494, 600, 140, sl["subtitle"] or sl["body"], _fit(24, sl["subtitle"] or sl["body"], 120),
                       t["muted"])
            animate(ring, "fade")
            animate(disc, "rise")
            animate(num, "fade", build="text", gap=0)
            animate(sub, "rise", build="text")
        elif lay == "agenda":
            heading(S, sl["title"])
            entries = sl["bullets"] or [it["title"] for it in sl["items"] if it["title"]]
            entries = entries[:6]
            cols = 2 if len(entries) > 3 else 1
            per_col = -(-len(entries) // cols) if entries else 1
            gap = 40
            cw = (W - 2 * PAD - gap * (cols - 1)) / cols
            row_h = min(130, (H - 220 - 70) / per_col)
            for i, entry in enumerate(entries):
                col, row = divmod(i, per_col)
                x, y = PAD + col * (cw + gap), 215 + row * row_h
                g = S.add_group_shape()
                color = t["accent"] if i % 2 == 0 else t["accent2"]
                rect(g.shapes, x, y, cw, row_h - 18, t["surface"], radius=16, line=None if t["dark"] else _mix(t["accent"], t["bg"], 0.8))
                badge(g.shapes, x + 20, y + (row_h - 18 - 56) / 2, 56, f"{i + 1:02d}", color, size=22)
                text(g.shapes, x + 96, y, cw - 120, row_h - 18, entry, _fit(26 if cols == 1 else 23, entry, 34),
                     t["title"], heading=True, anchor="middle")
                animate(g, "rise", gap=150)
        elif lay == "bullets":
            heading(S, sl["title"])
            y = 200
            if sl["body"]:
                intro = text(S, PAD, y, W - 2 * PAD, 80, sl["body"], _fit(24, sl["body"], 160), t["muted"])
                animate(intro, "fade", build="text")
                y += 100
            box = bullet_list(S, PAD, y, W - 2 * PAD - 120, H - y - 70, sl["bullets"])
            animate_list(box, len(sl["bullets"]))
        elif lay in ("image_right", "image_left"):
            img_x = 680 if lay == "image_right" else 0
            tx = PAD if lay == "image_right" else 680
            pic = picture(S, sl["image"], img_x, 0, 600, H)
            heading(S, sl["title"], w=520, x=tx)
            y = 200
            animate(pic, "fade")
            if sl["body"]:
                intro = text(S, tx, y, 520, 110, sl["body"], _fit(22, sl["body"], 150), t["muted"])
                animate(intro, "fade", build="text")
                y += 130
            box = bullet_list(S, tx, y, 520, H - y - 60, sl["bullets"], 22)
            animate_list(box, len(sl["bullets"]))
        elif lay == "cards":
            heading(S, sl["title"])
            items = sl["items"] or [{"icon": "", "title": b, "text": ""} for b in sl["bullets"][:4]]
            k = max(1, len(items))
            gap = 28
            cw = (W - 2 * PAD - gap * (k - 1)) / k
            per_line = max(8, (cw - 56) / 10)  # characters per line at 19px
            longest = max((len(it["text"]) for it in items), default=0)
            ch = min(430, max(330, 230 + -(-longest // int(per_line)) * 29 + 40))
            for i, it in enumerate(items):
                cx = PAD + i * (cw + gap)
                color = t["accent"] if i % 2 == 0 else t["accent2"]
                g = S.add_group_shape()
                rect(g.shapes, cx, 220, cw, ch, t["surface"], radius=20,
                     line=None if t["dark"] else _mix(t["accent"], t["bg"], 0.75))
                rect(g.shapes, cx + 28, 220, 56, 5, color)
                badge(g.shapes, cx + 28, 252, 72, it["icon"] or str(i + 1), color, size=34 if it["icon"] else 30)
                text(g.shapes, cx + 28, 346, cw - 56, 64, it["title"], _fit(24, it["title"], 24), t["title"], bold=True,
                     heading=True)
                text(g.shapes, cx + 28, 414, cw - 56, ch - 214, it["text"], _fit(19, it["text"], 110), t["text"],
                     spacing=1.2)
                animate(g, "rise", gap=200)
        elif lay == "chart":
            heading(S, sl["title"])
            ch = sl["chart"]
            cw = 780 if sl["body"] else W - 2 * PAD
            if ch:
                frame = add_chart(S, ch, PAD, 205, cw, 450)
                animate(frame, "fade", build="graphic")
            else:
                text(S, PAD, 300, cw, 80, "Add numbers to show a chart here.", 22, t["muted"])
            if sl["body"]:
                g = S.add_group_shape()
                bx = PAD + cw + 40
                rect(g.shapes, bx, 215, W - PAD - bx, 330, t["surface"], radius=18,
                     line=None if t["dark"] else _mix(t["accent"], t["bg"], 0.75))
                rect(g.shapes, bx, 215, 6, 330, t["accent"])
                label(text(g.shapes, bx + 28, 240, 220, 24, "KEY POINT", 13, t["accent"], bold=True, heading=True))
                text(g.shapes, bx + 28, 275, W - PAD - bx - 52, 250, sl["body"], _fit(22, sl["body"], 150), t["text"],
                     spacing=1.3)
                animate(g, "rise", gap=350)
        elif lay == "stats":
            heading(S, sl["title"])
            stats = sl["stats"]
            k = max(1, len(stats))
            gap = 28
            cw = (W - 2 * PAD - gap * (k - 1)) / k
            for i, st in enumerate(stats):
                cx = PAD + i * (cw + gap)
                color = t["accent"] if i % 2 == 0 else t["accent2"]
                g = S.add_group_shape()
                rect(g.shapes, cx, 225, cw, 300, t["surface"], radius=20,
                     line=None if t["dark"] else _mix(t["accent"], t["bg"], 0.75))
                rect(g.shapes, cx, 225, cw, 6, color)
                text(g.shapes, cx + 32, 260, cw - 64, 120, st["value"], _fit_width(80, st["value"], cw - 64), color,
                     bold=True, heading=True, anchor="bottom", spacing=1.0)
                rect(g.shapes, cx + 32, 395, 48, 4, t["title"] if not t["dark"] else t["muted"], radius=2)
                text(g.shapes, cx + 32, 415, cw - 64, 100, st["label"], _fit(21, st["label"], 50), t["text"],
                     spacing=1.2)
                animate(g, "rise", gap=200)
            if sl["body"]:
                note = text(S, PAD, 560, W - 2 * PAD, 80, sl["body"], 19, t["muted"])
                animate(note, "fade", build="text")
        elif lay == "steps":
            heading(S, sl["title"])
            steps = sl["items"] or [{"icon": "", "title": b, "text": ""} for b in sl["bullets"][:5]]
            k = max(1, len(steps))
            cw = (W - 2 * PAD) / k
            line = rect(S, PAD + 28, 298, W - 2 * PAD - cw + 0, 4, t["accent2"], opacity=0.6)
            animate(line, "fade")
            for i, st in enumerate(steps):
                cx = PAD + i * cw
                g = S.add_group_shape()
                oval(g.shapes, cx - 8, 264, 72, t["accent"], opacity=0.22)
                circle = oval(g.shapes, cx, 272, 56, t["accent"] if i % 2 == 0 else t["accent2"])
                tf = circle.text_frame
                tf.margin_left = tf.margin_right = 0
                p = tf.paragraphs[0]
                p.alignment = PP_ALIGN.CENTER
                r = p.add_run()
                r.text = str(i + 1)
                r.font.size, r.font.bold, r.font.name = Pt(18), True, t["pptx_heading"]
                r.font.color.rgb = rgb(on_accent)
                text(g.shapes, cx, 360, cw - 30, 70, st["title"], _fit(24, st["title"], 24), t["title"], bold=True,
                     heading=True)
                text(g.shapes, cx, 432, cw - 30, 200, st["text"], _fit(18, st["text"], 110), t["text"], spacing=1.2)
                animate(g, "rise", gap=220)
        elif lay == "timeline":
            heading(S, sl["title"])
            events = sl["items"] or [{"icon": "", "title": b, "text": ""} for b in sl["bullets"][:6]]
            k = max(1, len(events))
            cw = (W - 2 * PAD) / k
            line = rect(S, PAD, 398, W - 2 * PAD, 4, t["accent2"], opacity=0.5)
            animate(line, "fade")
            for i, ev in enumerate(events):
                cx = PAD + i * cw
                mid = cx + cw / 2
                color = t["accent"] if i % 2 == 0 else t["accent2"]
                g = S.add_group_shape()
                text(g.shapes, cx + 10, 300, cw - 20, 70, ev["title"], _fit_width(34, ev["title"], cw - 20, 0.58),
                     color, bold=True, heading=True, align="center", anchor="bottom")
                oval(g.shapes, mid - 20, 380, 40, color, opacity=0.25)
                oval(g.shapes, mid - 11, 389, 22, color)
                text(g.shapes, cx + 12, 440, cw - 24, 200, ev["text"], _fit(18, ev["text"], 90), t["text"],
                     align="center", spacing=1.2)
                animate(g, "rise", gap=220)
        elif lay == "quote":
            label(text(S, PAD, 90, 200, 160, "“", 200, t["accent"], bold=True, heading=True))
            q = sl["quote"] or sl["title"]
            qbox = text(S, 160, 200, W - 320, 300, q, _fit(40, q, 110), t["title"], italic=True, heading=True,
                        align="center", anchor="middle", spacing=1.15)
            animate(qbox, "fade", build="text")
            if sl["author"]:
                who = text(S, 160, 540, W - 320, 50, f"— {sl['author']}", 22, t["muted"], align="center")
                animate(who, "rise", build="text", gap=400)
        elif lay == "comparison":
            heading(S, sl["title"])
            cw = (W - 2 * PAD - 32) / 2
            most = max(sum(1 + len(b) // 46 for b in sl[side]["bullets"]) for side in ("left", "right"))
            box_h = min(420, max(260, 150 + most * 44))
            for i, side in enumerate(("left", "right")):
                col = sl[side]
                cx = PAD + i * (cw + 32)
                color = t["accent"] if i == 0 else t["accent2"]
                g = S.add_group_shape()
                rect(g.shapes, cx, 220, cw, box_h, t["surface"], radius=20,
                     line=None if t["dark"] else _mix(t["accent"], t["bg"], 0.75))
                rect(g.shapes, cx, 220, cw, 8, color)
                text(g.shapes, cx + 36, 256, cw - 72, 50, col["title"], 28, color, bold=True, heading=True)
                bullet_list(g.shapes, cx + 36, 330, cw - 72, box_h - 130, col["bullets"], 22)
                animate(g, "rise", gap=250)
            vs = oval(S, (W - 64) / 2, 220 + box_h / 2 - 32, 64, t["title"] if not t["dark"] else t["accent"])
            tf = vs.text_frame
            tf.margin_left = tf.margin_right = 0
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = "VS"
            r.font.size, r.font.bold, r.font.name = Pt(15), True, t["pptx_heading"]
            r.font.color.rgb = rgb(t["bg"] if t["dark"] else "FFFFFF")
            label(vs)
            animate(vs, "fade", gap=200)
        elif lay == "table":
            heading(S, sl["title"])
            tb = sl["table"]
            if tb:
                all_rows = ([tb["columns"]] if tb["columns"] else []) + tb["rows"]
                n_rows, n_cols = len(all_rows), len(all_rows[0])
                top = 210 if not sl["body"] else 280
                if sl["body"]:
                    text(S, PAD, 200, W - 2 * PAD, 60, sl["body"], _fit(22, sl["body"], 150), t["muted"])
                row_h = min(52, (H - top - 70) / n_rows)
                size = 20 if row_h >= 46 and n_cols <= 4 else 17 if row_h >= 38 else 15
                shape = S.add_table(n_rows, n_cols, px(PAD), px(top), px(W - 2 * PAD), px(row_h * n_rows))
                table = shape.table
                tbl_pr = shape._element.graphic.graphicData.tbl.tblPr
                tbl_pr.set("bandRow", "0")
                tbl_pr.set("firstRow", "0")
                style_id = tbl_pr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId")
                if style_id is not None:
                    style_id.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # "No Style, No Grid"
                stripe = _mix(t["surface"], t["bg"], 0.35)
                num_re = r"[-+₹$€£]?\s?[\d.,]+\s?(%|x|Cr|L|K|M|B|Cr\.?)?"
                numeric_col = [c > 0 and sum(bool(re.fullmatch(num_re, r[c] or "")) for r in tb["rows"]) * 2 > len(tb["rows"])
                               for c in range(n_cols)]
                for r, row in enumerate(all_rows):
                    table.rows[r].height = px(row_h)
                    head = r == 0 and bool(tb["columns"])
                    for c, value in enumerate(row):
                        cell = table.cell(r, c)
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = rgb(t["accent"] if head else (t["surface"] if r % 2 else stripe))
                        cell.margin_left = cell.margin_right = px(18)
                        cell.margin_top = cell.margin_bottom = px(4)
                        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                        tf = cell.text_frame
                        tf.word_wrap = True
                        p = tf.paragraphs[0]
                        p.alignment = PP_ALIGN.CENTER if numeric_col[c] else PP_ALIGN.LEFT
                        run = p.add_run()
                        run.text = value
                        run.font.size = Pt(size * 0.75)
                        run.font.bold = head or c == 0
                        run.font.name = t["pptx_heading"] if head else t["pptx_body"]
                        run.font.color.rgb = rgb(on_accent if head else (t["title"] if c == 0 else t["text"]))
                animate(shape, "fade")
            else:
                box = bullet_list(S, PAD, 220, W - 2 * PAD, H - 290, sl["bullets"])
                animate_list(box, len(sl["bullets"]))

        if lay not in ("cover", "closing", "image_right", "image_left") and total > 1:
            label(text(S, W - PAD - 100, H - 48, 100, 24, f"{n} / {total}", 14, t["muted"], align="right"), "Footer")
            if title and lay != "section":
                label(text(S, PAD, H - 48, 700, 24, title, 14, t["muted"]), "Footer")
        notes = sl["notes"]
        if sl["image"] and sl["image"].get("credit"):
            notes = (notes + "\n\n" if notes else "") + f"Image: {sl['image']['credit']} {sl['image'].get('link', '')}"
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        _script_fonts(s)
        if motion:
            _add_motion(s, lay, fx)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def public_themes() -> List[Dict]:
    return THEMES
