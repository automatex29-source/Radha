"""App builder: projects with a virtual file system, version history, live preview,
sandboxed commands, one-click publishing and git export.

Storage (MongoDB):
  apps          one document per app
  app_files     the working copy: {appId, path, content}
  app_blobs     content-addressed file versions: {hash, content}
  app_commits   snapshots: {id, appId, parent, message, author, files: {path: hash}}

Preview and published sites are served from RADHA's API origin, so every response
carries a CSP `sandbox` header: the page runs in an opaque origin and can never
read RADHA's storage or call its API with the user's session.
"""
import asyncio
import difflib
import hashlib
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

from auth import JWT_ALGORITHM, _secret, decode_token, get_user_id_from_request
from agent import Tool, ToolOutput, sandbox
from agent import browser as agent_browser
import appdata
import site_images
import github_push
import design_themes
import jsx_compile
import limits

router = APIRouter(prefix="/api")
db = None  # set by init()

MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 400
READ_CHARS = 12_000  # per read_file call, so a big file can't flood a small model's context
MAX_TOTAL_BYTES = 20 * 1024 * 1024
PREVIEW_TOKEN_HOURS = 12
_PATH_RE = re.compile(r"^[A-Za-z0-9_\-. ][A-Za-z0-9_\-./ ]*$")
SANDBOX_CSP = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads"
PREVIEW_ORIGIN = "https://app.radha.local/"

TEMPLATES = {
    "blank": {
        "index.html": """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>My App</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <main class="card">
    <h1>Hello from Krish AI</h1>
    <p>Ask the builder to turn this into anything.</p>
    <button id="btn">Clicked 0 times</button>
  </main>
  <script src="app.js"></script>
</body>
</html>
""",
        "style.css": """* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: system-ui, sans-serif;
       background: #0b0d14; color: #e5e7eb; }
.card { padding: 2.5rem; border: 1px solid #262c3e; border-radius: 16px; background: #11141d; text-align: center; }
button { margin-top: 1rem; padding: .7rem 1.2rem; border: 0; border-radius: 10px; background: #6366f1; color: white;
         font-weight: 600; cursor: pointer; }
""",
        "app.js": """let clicks = 0;
document.getElementById("btn").addEventListener("click", (e) => {
  clicks += 1;
  e.target.textContent = `Clicked ${clicks} time${clicks === 1 ? "" : "s"}`;
});
""",
    },
    "react": {
        "index.html": """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>React App</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100">
  <div id="root"></div>
  <script type="module" src="app.js"></script>
</body>
</html>
""",
        "app.js": """import React, { useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);

function App() {
  const [count, setCount] = useState(0);
  return html`
    <main class="min-h-screen grid place-items-center">
      <div class="p-10 rounded-2xl border border-slate-800 bg-slate-900 text-center">
        <h1 class="text-3xl font-bold">React + Tailwind</h1>
        <p class="mt-2 text-slate-400">Built with Krish AI</p>
        <button class="mt-6 px-5 py-2 rounded-lg bg-indigo-500 font-semibold" onClick=${() => setCount(count + 1)}>
          Count: ${count}
        </button>
      </div>
    </main>`;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
""",
    },
}

def _load_templates():
    """Ready-made starter apps in app_templates/<id>/ (to-do, dashboard, landing page, shop, game)."""
    root = os.path.join(os.path.dirname(__file__), "app_templates")
    if not os.path.isdir(root):
        return
    for tid in sorted(os.listdir(root)):
        folder = os.path.join(root, tid)
        if os.path.isdir(folder):
            TEMPLATES[tid] = {}
            for name in sorted(os.listdir(folder)):
                with open(os.path.join(folder, name), encoding="utf-8") as fh:
                    TEMPLATES[tid][name] = fh.read()


_load_templates()

# Shared by plain chat and the app builder so every generated app meets the same bar.
DESIGN_GUIDE = (
    "Quality bar for new apps you design yourself (work like a senior product designer and engineer):\n"
    "- Style it with Krish UI, the built-in design kit: put <link rel=\"stylesheet\" href=\"krish-ui.css\"> in the "
    "head (Krish AI adds that file itself: never write or edit it) and set the brand colours once with "
    "<style>:root{--accent:#db2777;--accent-2:#f97316}</style>. It makes plain HTML look premium, so write little CSS. "
    "Its classes: nav (sticky header) > container with brand, nav-links and a btn; hero (eyebrow, h1, p, actions; "
    "grid-2 to put a photo beside the text; hero-dark or hero-image for colour); section > container with section-title "
    "(eyebrow, h2, p); section-alt for a tinted band; grid-2, grid-3, grid-4; card (an img first in it becomes its "
    "cover photo; h3, p, row with price and a button; badge, stars, icon); btn, btn-outline, btn-light, btn-sm, btn-lg "
    "(a plain <button> is already styled); cta (gradient call-to-action box); footer; form, chip, toast (add class "
    "show), gradient-text, lead, muted, center, fade-up. Pick the layout for what is being built: a website, shop "
    "or portfolio uses nav + hero + sections; a tool or small app (to-do, notes, calculator, converter, quiz) uses a "
    "page (or page-wide) with panel, panel-title, toolbar, list > list-item (grow, done), empty, tabs > tab.active, "
    "keypad + display, progress > span, input.switch; a dashboard or admin uses app > sidebar (brand, side-link.active) "
    "+ main > topbar, then grid-4 of stat-card (stat-label, stat, trend up/down), panels with tables and charts "
    "(Chart.js from cdn.jsdelivr.net/npm/chart.js), badge green/red/amber/blue; a game uses stage > score + board of "
    "tile buttons; dialogs use modal.open > modal-box. Add body class dark for a dark theme. Add Tailwind (<script src=\"https://cdn.tailwindcss.com\">"
    "</script>) classes only for extra tweaks, and Lucide icons if wanted (<script src=\"https://unpkg.com/lucide@latest\">"
    "</script>, <i data-lucide=\"cake\"></i>, then lucide.createIcons()).\n"
    "- Graphics: use pictures made for this site, never empty boxes or grey placeholders: "
    "<img src=\"https://krish-image.invalid/chocolate-truffle-cake-on-marble-table-soft-light.jpg?w=800&h=600\" "
    "alt=\"...\"> (describe exactly what the picture shows, words joined by dashes, in English; w and h are the size "
    "it is shown at). Krish AI makes each picture. They work in CSS too, e.g. a hero-image background. Faces for "
    "reviews and teams: https://i.pravatar.cc/120?img=12 (img 1 to 70). Icons: Lucide, or an emoji in an icon tile. "
    "Add depth: blob top-right / blob bottom-left shapes (inside a relative or hero element), bg-mesh, bg-dots or "
    "bg-grid backgrounds, glass cards over photos, glow, float, shine, zoom on hover, and reveal on sections so they "
    "animate in on scroll. Whole looks come from one class on <body>: theme-glass, theme-liquid, theme-aurora, "
    "theme-bento, theme-bold, theme-luxury, theme-minimal, theme-playful, theme-neon, theme-clay or theme-sunset. "
    "A live 3D hero: <div class=\"scene\" data-scene=\"glass\"></div> (or blob, galaxy, waves, rings). More motion: split, magnetic, reveal-stagger, tilt, "
    "spotlight, spin-border, orb, rings, marquee > marquee-track, text-shimmer, gradient-anim, data-count numbers, "
    "typed words (class typed with data-words) and a bento grid.\n"
    "- Make it look like a modern, premium product: a clear hierarchy with a proper header, generous spacing, one "
    "accent color over a cohesive palette, soft gradients, rounded-2xl cards with subtle borders and shadows, "
    "hover, focus and active states, smooth transitions, friendly empty states and toasts instead of alert().\n"
    "- A logo, or any picture with words in it, is never a made-up picture link: the picture maker can't spell "
    "and doesn't know the brand. Use the user's own logo when they gave one; otherwise make a text logo "
    "(the name in a bold font beside a coloured icon tile).\n"
    "- A tool that reads a file and gives a report (an audit, a checker, a converter, a parser for logs or exports) "
    "is judged on the analysis, not the look, so put most of the work there, the way an expert in that field "
    "would check it: work from a real sample of the input (ask for one in a line if there is none), recognise "
    "its real structure and the domain's terms, turn what it finds into named checks, each with a Pass, Fail or "
    "Attention verdict, the value found, what was expected and why it matters, then show a summary (counts by "
    "verdict, the problems first), a section per area with its table, and a search or filter. Keep the parsing in "
    "its own plain module (e.g. parser.js, with no page code) and test it with node --test on the sample. An Excel "
    "export uses ExcelJS (https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js), which can style cells, "
    "not SheetJS: a Summary sheet first, then one sheet per area, with a coloured bold header row, frozen header, "
    "filters, column widths that fit, wrapped text and green, red and amber fills for the verdicts. Read files in "
    "the browser (nothing uploaded), handle a wrong or empty file with a clear message, and add a \"Try with "
    "sample\" button when a sample exists.\n"
    "- Responsive from phone to desktop, with labelled inputs and good contrast.\n"
    "- Fonts: each Krish UI style brings its own font pair, and when the app is in Hindi, Tamil, Bengali or another "
    "Indian script it gets matching fonts by itself, so don't link fonts yourself. Only when the user names a font, link it from "
    "Google Fonts and set :root{--font:\"Its Name\", sans-serif; --display:\"Its Name\", sans-serif}. Set <html "
    "lang> to the page's language (hi for Hindi). Don't put Indian-script text in all caps or tight letter spacing.\n"
    "- All app text (labels, placeholders, buttons, headings, sample data) in ONE language: English, unless the "
    "user asks for another language (\"in Hindi\", \"Tamil mein\") or writes the whole request in that language's "
    "own script. A request in Hinglish or another language written in English letters (\"cake shop ki website "
    "banao\") still means an English app. Never show two languages side by side or mix scripts (no \"नाम / Name\", "
    "no Hindi subtitle under an English heading, no language switch) unless the user asks for a bilingual app.\n"
    "- Every feature works for real: all buttons do something, input is validated, data persists in localStorage "
    "when that helps, and sample content is realistic (no lorem ipsum, no TODOs, no placeholders). Add the extra "
    "features a user would expect (e.g. for a to-do app: edit, complete, delete, filter, counts, clear completed).\n"
    "- Need a library? Any npm package loads from https://esm.sh/<name> inside a <script type=\"module\">.\n"
    "- Before you finish, check your own code: every id and function used in JS exists in the HTML/JS, scripts run "
    "after the elements they use (put them at the end of body), and nothing throws in the console."
)

# Sandboxed pages have an opaque origin, where touching localStorage throws; give them an in-memory one.
_STORAGE_SHIM = """<script>(function(){try{window.localStorage.getItem("x")}catch(e){function S(){var m={};return{getItem:function(k){return Object.prototype.hasOwnProperty.call(m,k)?m[k]:null},setItem:function(k,v){m[k]=String(v)},removeItem:function(k){delete m[k]},clear:function(){m={}},key:function(i){return Object.keys(m)[i]||null},get length(){return Object.keys(m).length}}}try{Object.defineProperty(window,"localStorage",{value:S(),configurable:true});Object.defineProperty(window,"sessionStorage",{value:S(),configurable:true})}catch(e){}}})();</script>"""
_CONSOLE_BRIDGE = """<script>(function(){function s(l,a){try{parent.postMessage({source:"radha-preview",level:l,message:Array.prototype.map.call(a,function(x){try{return typeof x==="string"?x:(x instanceof Error?x.message:JSON.stringify(x))}catch(e){return String(x)}}).join(" ")},"*")}catch(e){}}["log","info","warn","error"].forEach(function(l){var o=console[l];console[l]=function(){s(l,arguments);return o.apply(console,arguments)}});addEventListener("error",function(e){s("error",[e.message+(e.filename?" ("+e.filename.split("/").pop()+":"+e.lineno+")":"")])});addEventListener("unhandledrejection",function(e){s("error",["Unhandled promise rejection: "+((e.reason&&e.reason.message)||e.reason)])})})();</script>"""

# Click to edit: the builder asks the preview to let the user pick an element; the page outlines what's under the
# pointer and sends back the clicked element (a CSS path, its HTML and text) instead of running the click.
_PICK_BRIDGE = """<script>(function(){var on=false,box=null,tip=null;function css(e){if(e.id)return"#"+e.id;var p=[];while(e&&e.nodeType===1&&e!==document.body&&p.length<4){var s=e.tagName.toLowerCase();if(e.id){p.unshift("#"+e.id);break}var c=(e.getAttribute("class")||"").trim().split(/\\s+/).filter(function(x){return x&&x.indexOf(":")<0}).slice(0,2);if(c.length)s+="."+c.join(".");var sib=e.parentNode?Array.prototype.filter.call(e.parentNode.children,function(x){return x.tagName===e.tagName}):[];if(sib.length>1)s+=":nth-of-type("+(sib.indexOf(e)+1)+")";p.unshift(s);e=e.parentElement}return p.join(" > ")}function ui(){if(box)return;box=document.createElement("div");box.style.cssText="position:fixed;pointer-events:none;z-index:2147483647;border:2px solid #8b5cf6;background:rgba(139,92,246,.12);border-radius:4px;transition:all .06s";tip=document.createElement("div");tip.style.cssText="position:fixed;pointer-events:none;z-index:2147483647;background:#8b5cf6;color:#fff;font:600 11px system-ui;padding:2px 6px;border-radius:4px";document.documentElement.appendChild(box);document.documentElement.appendChild(tip)}function off(){on=false;if(box){box.remove();tip.remove();box=tip=null}document.documentElement.style.cursor=""}function over(ev){if(!on)return;ui();var r=ev.target.getBoundingClientRect();box.style.left=r.left+"px";box.style.top=r.top+"px";box.style.width=r.width+"px";box.style.height=r.height+"px";tip.textContent=ev.target.tagName.toLowerCase()+(ev.target.id?"#"+ev.target.id:"");tip.style.left=r.left+"px";tip.style.top=Math.max(0,r.top-20)+"px"}function click(ev){if(!on)return;ev.preventDefault();ev.stopPropagation();var e=ev.target,h=e.outerHTML||"";if(h.length>700)h=h.slice(0,700)+"…";try{parent.postMessage({source:"radha-preview",kind:"pick",selector:css(e),html:h,text:(e.innerText||"").trim().slice(0,160),tag:e.tagName.toLowerCase(),raw:(e.textContent||"").trim().slice(0,500),leaf:!e.children.length,color:getComputedStyle(e).color,bg:getComputedStyle(e).backgroundColor},"*")}catch(x){}off()}addEventListener("mouseover",over,true);addEventListener("click",click,true);addEventListener("keydown",function(e){if(on&&e.key==="Escape"){off();try{parent.postMessage({source:"radha-preview",kind:"pick-cancel"},"*")}catch(x){}}},true);addEventListener("message",function(e){if(e.source!==parent||!e.data||e.data.source!=="radha-builder")return;if(e.data.pick){on=true;document.documentElement.style.cursor="crosshair"}else off()})})();</script>"""


def init(database):
    global db
    db = database


async def ensure_indexes():
    await db.apps.create_index([("userId", 1), ("updatedAt", -1)])
    info = await db.apps.index_information()
    partial = {"published.slug": {"$type": "string"}}
    if "published.slug_1" in info and info["published.slug_1"].get("partialFilterExpression") != partial:
        await db.apps.drop_index("published.slug_1")
    await db.apps.create_index("published.slug", unique=True, partialFilterExpression=partial)
    await db.app_files.create_index([("appId", 1), ("path", 1)], unique=True)
    await db.app_blobs.create_index("hash", unique=True)
    await db.app_commits.create_index([("appId", 1), ("createdAt", -1)])
    await db.apps.create_index("domain", unique=True, partialFilterExpression={"domain": {"$type": "string"}})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def current_user_id(request: Request) -> str:
    return get_user_id_from_request(request)


def clean_path(path: str) -> str:
    path = (path or "").strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if (not path or len(path) > 200 or path.startswith("/") or ".." in path.split("/") or "//" in path
            or not _PATH_RE.match(path) or path.split("/")[0] in (".git", ".radha")):
        raise ValueError(f"Invalid file path '{path}'")
    return path


# ------------------------------------------------------------ core operations
async def owned_app(app_id: str, user_id: str) -> dict:
    app = await db.apps.find_one({"id": app_id, "userId": user_id})
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


async def snapshot(app_id: str) -> Dict[str, str]:
    return {f["path"]: f["content"] async for f in db.app_files.find({"appId": app_id})}


async def write_file(app_id: str, path: str, content: str):
    path = clean_path(path)
    size = len(content.encode("utf-8"))
    if size > MAX_FILE_BYTES:
        raise ValueError(f"{path} is too large (max {MAX_FILE_BYTES // 1024} KB)")
    existing = await db.app_files.find_one({"appId": app_id, "path": path}, {"_id": 1})
    if not existing:
        if await db.app_files.count_documents({"appId": app_id}) >= MAX_FILES:
            raise ValueError(f"Too many files (max {MAX_FILES})")
    total = sum([len(f["content"].encode("utf-8")) async for f in db.app_files.find({"appId": app_id, "path": {"$ne": path}})])
    if total + size > MAX_TOTAL_BYTES:
        raise ValueError("App is too large")
    await db.app_files.update_one({"appId": app_id, "path": path},
                                  {"$set": {"content": content, "updatedAt": _now()}}, upsert=True)
    await _add_kit(app_id, path, content)
    await db.apps.update_one({"id": app_id}, {"$set": {"updatedAt": _now()}})
    return path


KIT_NAME = "krish-ui.css"
KIT_CSS = (Path(__file__).parent / "app_kit" / KIT_NAME).read_text(encoding="utf-8")
_KIT_REF_RE = re.compile(r"""href\s*=\s*["']([^"']*krish-ui\.css)["']""", re.IGNORECASE)
# The kit's motion half (phone menu button, scroll reveals, 3D tilt, count-ups): added to every page that links the
# kit when it is served, and as a file beside it in the ZIP and on GitHub. The model never writes it.
KIT_JS_NAME = "krish-ui.js"
KIT_JS = (Path(__file__).parent / "app_kit" / KIT_JS_NAME).read_text(encoding="utf-8")


# Each style's fonts, linked in the page's head so they start loading at once (the kit's CSS only imports the
# default pair). A page in Hindi or another Indian script also gets the matching Noto font.
_GF = "https://fonts.googleapis.com/css2?"
THEME_FONTS = {
    "glass": "family=Sora:wght@500..800", "liquid": "family=Inter+Tight:wght@500..800",
    "aurora": "family=Space+Grotesk:wght@500..700", "bento": "family=Manrope:wght@400..800",
    "bold": "family=Space+Grotesk:wght@400..700&family=Bricolage+Grotesque:opsz,wght@12..96,600..800",
    "luxury": "family=Manrope:wght@400..700&family=Fraunces:opsz,wght@9..144,400..700",
    "minimal": "family=Inter+Tight:wght@400..800", "playful": "family=Fredoka:wght@400..700",
    "neon": "family=Syne:wght@600..800&family=JetBrains+Mono:wght@500;700", "clay": "family=Nunito:wght@500..900",
    "sunset": "family=Manrope:wght@400..700&family=Instrument+Serif:ital@0;1",
}
_SCRIPTS = [(r"[\u0900-\u097F]", "Noto+Sans+Devanagari"), (r"[\u0980-\u09FF]", "Noto+Sans+Bengali"),
            (r"[\u0A00-\u0A7F]", "Noto+Sans+Gurmukhi"), (r"[\u0A80-\u0AFF]", "Noto+Sans+Gujarati"),
            (r"[\u0B00-\u0B7F]", "Noto+Sans+Oriya"), (r"[\u0B80-\u0BFF]", "Noto+Sans+Tamil"),
            (r"[\u0C00-\u0C7F]", "Noto+Sans+Telugu"), (r"[\u0C80-\u0CFF]", "Noto+Sans+Kannada"),
            (r"[\u0D00-\u0D7F]", "Noto+Sans+Malayalam"), (r"[\u0600-\u06FF]", "Noto+Naskh+Arabic")]
_SCRIPTS_RE = [(re.compile(r), f) for r, f in _SCRIPTS]
_THEME_CLASS_RE = re.compile(r"""<body\b[^>]*\bclass\s*=\s*["'][^"']*\btheme-(\w+)""", re.IGNORECASE)


def script_fonts(text: str) -> List[str]:
    """The Noto fonts for the Indian scripts (and Urdu) the text is written in."""
    return [f"family={family}:wght@400..700" for pattern, family in _SCRIPTS_RE if pattern.search(text or "")]


def font_tags(html: str) -> str:
    """<link>s for the fonts a kit page needs: its style's fonts and any Indian script it uses."""
    m = _THEME_CLASS_RE.search(html)
    families = ([THEME_FONTS[m.group(1)]] if m and m.group(1) in THEME_FONTS else []) + script_fonts(html)
    tags = ""
    if families:
        tags = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                f'<link rel="stylesheet" href="{_GF}{"&".join(families)}&display=swap">')
    if script_fonts(html):
        tags += "<script>document.documentElement.classList.add('krish-indic')</script>"
    return tags


def _after_head(html: str, tag: str) -> str:
    m = re.search(r"<head\b[^>]*>", html, re.IGNORECASE)
    return html[:m.end()] + tag + html[m.end():] if m else tag + html


def uses_kit(html: str) -> bool:
    return bool(_KIT_REF_RE.search(html)) and KIT_JS_NAME not in html


def _before_body_end(html: str, tag: str) -> str:
    idx = html.lower().rfind("</body>")
    return html[:idx] + tag + html[idx:] if idx >= 0 else html + tag


async def _add_kit(app_id: str, path: str, content: str) -> None:
    """A page that links the built-in design kit (krish-ui.css) gets the file next to it, so the preview,
    the published site, the ZIP and GitHub all have it."""
    if not path.endswith((".html", ".htm")):
        return
    for ref in _KIT_REF_RE.findall(content):
        target = _resolve(path, ref)
        if target and not await db.app_files.find_one({"appId": app_id, "path": target}, {"_id": 1}):
            await db.app_files.update_one({"appId": app_id, "path": target},
                                          {"$set": {"content": KIT_CSS, "updatedAt": _now()}}, upsert=True)


# Files the user attaches in the builder chat are copied into the app, so the model can read all of a sample
# (the chat's file context gives a free model only a few hundred words of it) and the app can use the user's
# own logo. Krish built a generic "key = value" parser for a 4,000-line AMOS log it had seen 450 words of,
# and asked the picture maker for a logo.
SAMPLE_DIR = "samples"
ASSET_DIR = "assets"
_IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}
IMAGE_EXTS = {"svg", *_IMAGE_TYPES}
_RAW_TEXT_EXTS = {"txt", "log", "dat", "csv", "tsv", "json", "md", "html", "htm", "xml", "yaml", "yml", "ini", "cfg"}
_MAX_IMAGE_BYTES = 600 * 1024  # base64 grows it by a third and the file must stay under MAX_FILE_BYTES


def _upload_name(filename: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.\-]+", "-", os.path.basename(filename or "file")).strip("-.") or "file"
    return stem[:80]


def _image_svg(data: bytes, ext: str) -> Optional[str]:
    """A raster picture as an SVG that embeds it: app files are text, and <img src="assets/logo.svg"> shows it."""
    import base64
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(data))
        width, height = img.size
        if len(data) > _MAX_IMAGE_BYTES:
            img.thumbnail((800, 800))
            width, height = img.size
            out = io.BytesIO()
            if img.mode in ("RGBA", "LA", "P"):
                img.save(out, "PNG", optimize=True)
                ext = "png"
            else:
                img.convert("RGB").save(out, "JPEG", quality=85)
                ext = "jpg"
            data = out.getvalue()
            if len(data) > _MAX_IMAGE_BYTES:
                return None
    except Exception:
        return None
    href = f"data:{_IMAGE_TYPES[ext]};base64,{base64.b64encode(data).decode()}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<image width="{width}" height="{height}" href="{href}" xlink:href="{href}"/></svg>')


async def keep_upload(app_id: str, filename: str, data: bytes, text: str = "") -> Optional[str]:
    """Copy a file attached in the builder chat into the app; returns its path there, or None.

    Pictures go to assets/ (an SVG logo as it is, a PNG or JPEG inside an SVG); text files go to samples/ unchanged,
    so a parser is built for their real layout; other documents (PDF, Word, Excel) go in as their extracted text."""
    import extract
    name = _upload_name(filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "svg" and not extract.is_binary(data):
        path, content = f"{ASSET_DIR}/{name}", extract._decode(data)
    elif ext in _IMAGE_TYPES:
        content = _image_svg(data, ext)
        path = f"{ASSET_DIR}/{name.rsplit('.', 1)[0]}.svg"
    elif (ext in _RAW_TEXT_EXTS or not ext) and not extract.is_binary(data):
        path, content = f"{SAMPLE_DIR}/{name}", extract._decode(data)
    elif text.strip():
        path, content = f"{SAMPLE_DIR}/{name}.txt", text
    else:
        return None
    if not content:
        return None
    limit = MAX_FILE_BYTES - 1024
    if len(content.encode("utf-8")) > limit:
        if path.startswith(ASSET_DIR):
            return None
        content = content.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
        content = content[:content.rfind("\n") + 1] or content  # end on a whole line
    try:
        return await write_file(app_id, path, content)
    except ValueError:
        return None


async def delete_file(app_id: str, path: str) -> bool:
    res = await db.app_files.delete_one({"appId": app_id, "path": clean_path(path)})
    await db.apps.update_one({"id": app_id}, {"$set": {"updatedAt": _now()}})
    return res.deleted_count > 0


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def head_commit(app_id: str) -> Optional[dict]:
    return await db.app_commits.find_one({"appId": app_id}, sort=[("createdAt", -1), ("seq", -1)])


async def commit_files(commit: dict) -> Dict[str, str]:
    hashes = commit["files"]
    blobs = {b["hash"]: b["content"] async for b in db.app_blobs.find({"hash": {"$in": list(set(hashes.values()))}})}
    return {path: blobs[h] for path, h in hashes.items()}


async def changed_paths(app_id: str) -> Dict[str, str]:
    """{path: added|modified|deleted} between the last commit and the working copy."""
    working = {p: _hash(c) for p, c in (await snapshot(app_id)).items()}
    head = await head_commit(app_id)
    committed = head["files"] if head else {}
    out = {}
    for p in working.keys() | committed.keys():
        if p not in committed:
            out[p] = "added"
        elif p not in working:
            out[p] = "deleted"
        elif working[p] != committed[p]:
            out[p] = "modified"
    return dict(sorted(out.items()))


async def commit(app_id: str, message: str, author: str = "You") -> Optional[dict]:
    files = await snapshot(app_id)
    hashes = {p: _hash(c) for p, c in files.items()}
    head = await head_commit(app_id)
    if head and head["files"] == hashes:
        return None
    for path, content in files.items():
        await db.app_blobs.update_one({"hash": hashes[path]}, {"$setOnInsert": {"content": content}}, upsert=True)
    doc = {
        "id": uuid.uuid4().hex[:12],
        "appId": app_id,
        "parent": head["id"] if head else None,
        "seq": (head.get("seq", 0) + 1) if head else 1,
        "message": (message or "Update").strip()[:500],
        "author": author,
        "files": hashes,
        "createdAt": _now(),
    }
    await db.app_commits.insert_one(doc)
    return public_commit(doc)


async def checkpoint(app_id: str, message: str, author: str = "Krish AI") -> Optional[str]:
    """Save the working copy as a version if it changed, and return the id of the version it now matches."""
    made = await commit(app_id, message, author=author)
    if made:
        return made["id"]
    head = await head_commit(app_id)
    return head["id"] if head else None


def public_commit(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("id", "parent", "message", "author", "createdAt")} | {"fileCount": len(doc["files"])}


def unified_diff(before: Dict[str, str], after: Dict[str, str]) -> List[dict]:
    out = []
    for path in sorted(before.keys() | after.keys()):
        a, b = before.get(path), after.get(path)
        if a == b:
            continue
        status = "added" if a is None else "deleted" if b is None else "modified"
        diff = "".join(difflib.unified_diff((a or "").splitlines(True), (b or "").splitlines(True),
                                            fromfile=f"a/{path}", tofile=f"b/{path}", n=3))
        out.append({"path": path, "status": status, "diff": diff[:60_000]})
    return out


async def restore(app_id: str, commit_id: str, author: str = "You") -> Optional[dict]:
    target = await db.app_commits.find_one({"appId": app_id, "id": commit_id})
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")
    files = await commit_files(target)
    await db.app_files.delete_many({"appId": app_id})
    if files:
        await db.app_files.insert_many([{"appId": app_id, "path": p, "content": c, "updatedAt": _now()} for p, c in files.items()])
    return await commit(app_id, f"Restore version {commit_id}: {target['message']}"[:200], author)


def public_origin() -> str:
    """This server's public address (Render sets RENDER_EXTERNAL_URL), for links in files that leave it."""
    return (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")


def portable(files: Dict[str, str]) -> Dict[str, str]:
    """Files as they should leave Krish AI (ZIP, GitHub): AI picture links point at this server."""
    origin = public_origin()
    out = {p: site_images.rewrite(c, origin) if origin else c for p, c in files.items()}
    for p, c in list(out.items()):
        if p.endswith((".html", ".htm")) and uses_kit(c):
            ref = _KIT_REF_RE.search(c).group(1).replace(KIT_NAME, KIT_JS_NAME)
            out[p] = _before_body_end(_after_head(c, font_tags(c)), f'<script src="{ref}"></script>\n')
            target = _resolve(p, ref)
            if target and target not in out:
                out[target] = KIT_JS
    return out


async def export_zip(app: dict, include_git: bool = True) -> bytes:
    working = portable(await snapshot(app["id"]))
    workdir = tempfile.mkdtemp(prefix="radha-export-")
    try:
        if include_git:
            commits = await db.app_commits.find({"appId": app["id"]}).sort([("createdAt", 1), ("seq", 1)]).to_list(5000)
            if commits:
                _build_git_repo(workdir, commits, {c["id"]: await commit_files(c) for c in commits})
        for path, content in working.items():
            target = os.path.join(workdir, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)
        buf = io.BytesIO()
        root = re.sub(r"[^\w\-]+", "-", app["name"]).strip("-").lower() or "app"
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _, filenames in os.walk(workdir):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    zf.write(full, os.path.join(root, os.path.relpath(full, workdir)))
        return buf.getvalue()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _build_git_repo(workdir: str, commits: List[dict], contents: Dict[str, Dict[str, str]]):
    """Real git history (one git commit per RADHA version) via dulwich."""
    from dulwich.objects import Blob, Commit, Tree
    from dulwich.repo import Repo

    repo = Repo.init(workdir)
    store = repo.object_store

    def build_tree(files: Dict[str, str]) -> bytes:
        nested: dict = {}
        for path, content in files.items():
            node = nested
            parts = path.split("/")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = content

        def make(node) -> bytes:
            tree = Tree()
            for name, value in node.items():
                if isinstance(value, dict):
                    tree.add(name.encode(), 0o040000, make(value))
                else:
                    blob = Blob.from_string(value.encode("utf-8"))
                    store.add_object(blob)
                    tree.add(name.encode(), 0o100644, blob.id)
            store.add_object(tree)
            return tree.id

        return make(nested)

    parent = None
    for c in commits:
        gc = Commit()
        gc.tree = build_tree(contents[c["id"]])
        gc.parents = [parent] if parent else []
        who = f"{c.get('author') or 'Krish AI'} <krish@empirex.ai>".encode()
        gc.author = gc.committer = who
        ts = int(datetime.fromisoformat(c["createdAt"]).timestamp())
        gc.author_time = gc.commit_time = ts
        gc.author_timezone = gc.commit_timezone = 0
        gc.encoding = b"UTF-8"
        gc.message = (c["message"] + "\n").encode("utf-8")
        store.add_object(gc)
        parent = gc.id
    repo.refs[b"refs/heads/main"] = parent
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")
    # Check out the last commit and write the index, so `git status` is clean.
    from dulwich.index import build_index_from_tree

    build_index_from_tree(repo.path, repo.index_path(), store, store[parent].tree)
    repo.close()


def app_prompt_files(files: Dict[str, str]) -> str:
    return "\n".join(f"- {p} ({len(c.encode('utf-8'))} bytes)" for p, c in sorted(files.items())) or "(no files yet)"


REACT_HTM_RULE = ("For React, import react and react-dom/client from esm.sh and write components with htm "
                  "(import htm from \"https://esm.sh/htm\") instead of JSX, since there is no build step.")
REACT_JSX_RULE = ("For a React app, write it like a Vite project: index.html with <div id=\"root\"> and "
                  "<script type=\"module\" src=\"src/main.jsx\">, then src/main.jsx, src/App.jsx and one .jsx file "
                  "per component, in normal JSX (TypeScript .tsx works too). Krish AI compiles JSX and TypeScript "
                  "itself, and plain imports (import { useState } from \"react\", import confetti from "
                  "\"canvas-confetti\", import \"./App.css\") just work: there is no npm install. Use React for "
                  "apps with many screens or a lot of state; plain HTML/JS is fine for simple pages.")


async def app_prompt(database, app_id: str) -> str:
    app = await database.apps.find_one({"id": app_id})
    files = await snapshot(app_id)
    changes = await changed_paths(app_id)
    return (
        f"You are Krish AI's app builder, working on the app “{app['name']}”"
        + (f" — {app['description']}" if app.get("description") else "") + ".\n"
        "The user sees the live preview, the files and the version history beside this chat.\n\n"
        f"Project files:\n{app_prompt_files(files)}\n"
        + (f"Uncommitted changes: {', '.join(f'{p} ({s})' for p, s in changes.items())}\n" if changes else "")
        + "\nHow to work:\n"
        "- The app is a static web app served from index.html. Use HTML/CSS/JS; load libraries from CDNs "
        "(esm.sh, unpkg, cdn.jsdelivr.net, cdn.tailwindcss.com). There is no npm install or build step, but any npm "
        "package works as an ES module from esm.sh, e.g. import confetti from \"https://esm.sh/canvas-confetti\" in a "
        "<script type=\"module\">. " + (REACT_JSX_RULE if jsx_compile.available() else REACT_HTM_RULE) + "\n"
        "- When asked for a new app or a big change, first write a short plan in your reply (3 to 6 bullets: the "
        "screens, the features, the files), then build the whole working app right away with write_file. Replace the "
        "starter files instead of building around them. Don't stop at a skeleton or placeholders: every button, form "
        "and link must work, with sample content so the app looks alive on first open.\n"
        "- A short request like \"make a cake shop website\" still means a complete, polished, multi-section site: "
        "for a website, a nav bar, a hero with a call to action, the main content with real sample items (products with "
        "names, prices and images), about, reviews, contact and a footer; for an app, every screen it needs. Never "
        "ask questions first; pick sensible details yourself.\n"
        "- Write index.html first with all the markup and ids, then the CSS, then the JS, which may only use ids that "
        "index.html has.\n"
        "- Each of your steps has limited room. Write a long file in parts: write_file with the first part (about "
        "120 lines), then append_file with each next part, until the file is complete.\n"
        "- Split the app into small files, each under about 250 lines, so each one is written in a single step and "
        "edited easily: index.html (markup), styles.css (or Tailwind classes), and JS modules such as app.js, ui.js, "
        "data.js loaded with <script type=\"module\">. Write the files one by one, and never cut a file short.\n"
        "- Before you finish, read back the files you wrote and check that every id, class, import and function "
        "they use exists, and that the layout works on a phone. Fix what you find.\n"
        "- When the user gives you their own code (pasted HTML is saved for you unchanged as index.html), it is "
        "theirs: keep its structure, CSS, colors, layout and wording exactly, change only what they ask, and never "
        "rewrite or restyle it (the quality bar below is for apps you design yourself). Make each change with "
        "edit_file; use search_files and read_file with line ranges to find the spot in a large file.\n"
        "- Files in samples/ are real files the user gave you (logs, exports, reports) and files in assets/ are "
        "their own pictures. When the app reads or processes files like a sample, study the sample before you "
        "write any code: search_files for its commands, headings and table headers, and read_file the parts that "
        "matter, in line ranges. Then build for that exact layout (its sections, columns, units, OK and error "
        "values), not a generic \"key = value\" or \"any text\" parser. Use the sample as a \"Try with sample\" "
        "button (fetch('samples/<name>')) and to test the parser. Show the user's logo from assets/ with <img>.\n"
        "- Read files before editing them. Prefer edit_file for small changes and write_file for new or rewritten files.\n"
        + ("- After changing the UI, call check_preview to see a screenshot and any console errors, and fix them.\n"
           if agent_browser.available() else "")
        + "- Put logic worth testing in plain modules and add tests (e.g. tests/*.test.mjs run with `node --test`, "
        "or Python unittest) and run them with run_command.\n"
        "- When a change works, call commit with a short message describing it.\n"
        "- Backend: every app already has a database and user accounts with no setup, through the global RADHA "
        "object (works in the preview and on the published site): await RADHA.auth.signup(email, password, name), "
        "await RADHA.auth.login(email, password), RADHA.auth.user (null when signed out), RADHA.auth.logout(); "
        "await RADHA.db.list(collection, {mine: true}) returns [{id, data, ownerId, createdAt}] newest first; "
        "RADHA.db.add(collection, data, {private: true}), RADHA.db.update(collection, id, data), "
        "RADHA.db.remove(collection, id). All calls return promises and throw Error with a readable message. "
        "Filter with RADHA.db.list(collection, {where: {status: 'open'}, limit: 20}); live updates with "
        "RADHA.db.watch(collection, rows => render(rows)) (returns a stop function). "
        "Use it when data must be shared between visitors or the app needs accounts; otherwise use localStorage.\n"
        "- More backend, all free and ready, use them to make the app really work instead of faking it: "
        "await RADHA.ai(prompt, {system, history: [{role, content}]}) returns the AI's answer text ({json: true} "
        "returns parsed JSON) for chatbots, writing, summaries, quizzes and recommendations; "
        "await RADHA.notify({subject, message, replyTo, ...fields}) emails the app's owner (contact forms, orders, "
        "bookings, leads) and saves it to their inbox; await RADHA.files.upload(fileInput.files[0]) stores a "
        "picture or document (max 2 MB) and returns {url, name}; await RADHA.fetch(url, {method, headers, body}) "
        "calls any public API from the server (no CORS problems) and returns {status, ok, data, text}. "
        "Show a loading state while these run and a friendly message if they fail.\n"
        "- Keep your chat replies short: say what you built or changed.\n\n"
        + DESIGN_GUIDE
    )


_HTML_BODY = r"((?:<!doctype html[^>]*>\s*)?<html[\s>].*</html>)"
_HTML_FENCED_RE = re.compile(r"```[ \t]*html?[^\n]*\n\s*" + _HTML_BODY + r"\s*?\n[ \t]*```", re.IGNORECASE | re.DOTALL)
_HTML_DOC_RE = re.compile(_HTML_BODY, re.IGNORECASE | re.DOTALL)
_NAMED_BLOCK_RE = re.compile(r"```[ \t]*\w*[ \t:]+([\w\-./]+\.(?:html?|css|m?js|json|svg|txt|md))[ \t]*\n(.*?)\n[ \t]*```", re.DOTALL)


def split_pasted_code(content: str):
    """Pull a whole pasted HTML page, and fenced blocks that name a file, out of a chat message.

    Returns ({path: code}, the rest of the message).
    """
    files, rest = {}, content or ""
    m = _HTML_FENCED_RE.search(rest) or _HTML_DOC_RE.search(rest)
    if m:
        files["index.html"] = m.group(1).strip() + "\n"
        rest = rest[:m.start()] + rest[m.end():]
    for m in list(_NAMED_BLOCK_RE.finditer(rest)):
        try:
            files[clean_path(m.group(1))] = m.group(2) + "\n"
        except ValueError:
            continue
        rest = rest.replace(m.group(0), "", 1)
    return files, rest.strip()


async def absorb_pasted_code(app_id: str, content: str):
    """Save code the user pasted into the builder chat exactly as given, before any AI sees it.

    Free models can't hold a large page in their context and would rebuild it from what they
    remember, losing the user's design. Returns None when nothing was pasted, else
    (the message to store and show the AI, a ready reply when the user gave no instructions).
    """
    files, rest = split_pasted_code(content)
    if not files:
        return None
    for path, code in files.items():
        await write_file(app_id, path, code)
    await commit(app_id, "Add your code: " + ", ".join(files), author="You")
    listing = ", ".join(f"{p} ({max(1, len(c.encode('utf-8')) // 1024)} KB)" for p, c in files.items())
    note = (f"[Pasted code saved exactly as given: {listing}. It is the user's own design: keep it as it is "
            "and change only what they ask, with small edit_file changes.]")
    stored = f"{rest}\n\n{note}" if rest else note
    reply = None if rest else (f"Saved your code exactly as you gave it ({listing}). It's in the preview now. "
                               "Tell me what you'd like to change and I'll change only that.")
    return stored, reply


def preview_token(app_id: str, user_id: str) -> str:
    payload = {"sub": app_id, "uid": user_id, "type": "preview",
               "exp": datetime.now(timezone.utc) + timedelta(hours=PREVIEW_TOKEN_HOURS)}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def _decode_preview(token: str) -> dict:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Preview link expired — reopen the preview")
    if payload.get("type") != "preview":
        raise HTTPException(status_code=401, detail="Invalid preview token")
    return payload


def _serve(files: Dict[str, str], path: str, bridge: bool, cache: str, app_id: Optional[str] = None) -> Response:
    path = unquote(path or "").lstrip("/")
    if not path or path.endswith("/"):
        path += "index.html"
    content = files.get(path)
    if content is None and "." not in path.rsplit("/", 1)[-1]:
        content, path = files.get("index.html"), "index.html"  # single-page-app fallback
    headers = {"Content-Security-Policy": SANDBOX_CSP, "X-Content-Type-Options": "nosniff", "Cache-Control": cache,
               "Referrer-Policy": "no-referrer"}
    if content is None:
        return Response("Not found", status_code=404, media_type="text/plain", headers=headers)
    ctype = mimetypes.guess_type(path)[0] or "text/plain"
    if path.endswith((".js", ".mjs") + jsx_compile.COMPILED_EXTS):
        ctype = "text/javascript"
        if jsx_compile.available() and jsx_compile.needs_compile(path, content):
            content = jsx_compile.compile_file(path, files)
    if ctype in ("text/html", "text/css", "text/javascript"):
        content = site_images.rewrite(content)  # AI pictures (krish-image.invalid links) come from this server
    if ctype == "text/html":
        content = jsx_compile.relative_html(path, content, files)
        if uses_kit(content):
            content = _before_body_end(_after_head(content, font_tags(content)), "<script>" + KIT_JS + "</script>")
        inject = _STORAGE_SHIM + (_CONSOLE_BRIDGE + _PICK_BRIDGE if bridge else "") + (appdata.sdk_script(app_id) if app_id else "")
        idx = content.lower().find("<head>")
        content = content[:idx + 6] + inject + content[idx + 6:] if idx >= 0 else inject + content
    return Response(content, media_type=f"{ctype}; charset=utf-8" if ctype.startswith("text/") else ctype, headers=headers)


async def check_preview(files: Dict[str, str], path: str = "index.html", app_id: Optional[str] = None) -> dict:
    """Load the working copy in headless Chromium; return console output, errors and a screenshot."""
    browser = await agent_browser.manager._ensure_browser()
    context = await browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=False)
    allowed: dict = {}
    logs: List[str] = []

    async def handler(route):
        url = route.request.url
        if url.startswith(PREVIEW_ORIGIN):
            rel = unquote(urlparse(url).path.lstrip("/"))
            resp = _serve(files, rel, bridge=False, cache="no-store", app_id=app_id)
            await route.fulfill(status=resp.status_code, body=resp.body,
                                headers={"Content-Type": resp.media_type or "text/plain"})
        else:
            await agent_browser.manager._guard(route, allowed)

    try:
        await context.route("**/*", handler)
        page = await context.new_page()
        page.on("console", lambda m: logs.append(f"[console.{m.type}] {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"[uncaught error] {e}"))
        page.on("requestfailed", lambda r: logs.append(f"[request failed] {r.url} ({r.failure})"))
        page.on("response", lambda r: logs.append(f"[http {r.status}] {r.url}") if r.status >= 400 else None)
        await page.goto(PREVIEW_ORIGIN + clean_path(path), wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(800)
        text = await page.evaluate("document.body ? document.body.innerText : ''")
        shot = await page.screenshot(type="jpeg", quality=65)
        return {"title": await page.title(), "text": text[:3000], "logs": logs[:60], "screenshot": shot}
    finally:
        await context.close()


_CLICKABLE = "button, [role=button], input[type=button], input[type=submit]"
_SMOKE_CLICKS = 8
# Console noise that isn't the app's fault.
_NOISE_RE = re.compile(r"favicon\.ico|cdn\.tailwindcss\.com should not be used in production|DevTools|"
                       r"Download the React DevTools|net::ERR_|ERR_BLOCKED|Failed to load resource", re.IGNORECASE)


async def smoke_test(files: Dict[str, str], path: str = "index.html", app_id: Optional[str] = None) -> List[str]:
    """Open the app in headless Chromium the way a person would: load it, then press its buttons one by one.

    Returns the errors that broke something, each said in a line the model can act on: uncaught errors and
    console errors on load and after each click (with the button that caused them), and the app's own
    files that failed to load. Static checks (check_app) can't see these: "x is not defined", a typo in a
    method name, a CDN import that doesn't exist.
    """
    browser = await agent_browser.manager._ensure_browser()
    context = await browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=False)
    allowed: dict = {}
    errors: List[str] = []
    stage = ["on load"]

    async def handler(route):
        url = route.request.url
        if url.startswith(PREVIEW_ORIGIN + "api/"):
            await route.abort("blockedbyclient")  # never reach the real backend from a test
        elif url.startswith(PREVIEW_ORIGIN):
            rel = unquote(urlparse(url).path.lstrip("/"))
            resp = _serve(files, rel, bridge=False, cache="no-store", app_id=app_id)
            await route.fulfill(status=resp.status_code, body=resp.body,
                                headers={"Content-Type": resp.media_type or "text/plain"})
        else:
            await agent_browser.manager._guard(route, allowed)

    def note(kind: str, text: str):
        text = " ".join(str(text).split())[:220]
        if text and not _NOISE_RE.search(text):
            line = f"{kind} {stage[0]}: {text}"
            if line not in errors:
                errors.append(line)

    try:
        await context.route("**/*", handler)
        page = await context.new_page()
        page.on("pageerror", lambda e: note("Uncaught error", e))
        page.on("console", lambda m: note("Console error", m.text) if m.type == "error" else None)
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        page.on("response", lambda r: note("Missing file", f"{r.url[len(PREVIEW_ORIGIN):]} returned {r.status}")
                if r.status >= 400 and r.url.startswith(PREVIEW_ORIGIN) and "favicon" not in r.url else None)
        await page.goto(PREVIEW_ORIGIN + clean_path(path), wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(600)
        buttons = page.locator(_CLICKABLE)
        count = min(await buttons.count(), 40)
        clicked = 0
        for i in range(count):
            if clicked >= _SMOKE_CLICKS or len(errors) >= 6:
                break
            button = buttons.nth(i)
            try:
                if not await button.is_visible() or not await button.is_enabled():
                    continue
                label = " ".join(((await button.inner_text(timeout=500)) or await button.get_attribute("aria-label")
                                  or await button.get_attribute("value") or "").split())[:40] or f"button {i + 1}"
                stage[0] = f"after clicking “{label}”"
                await button.click(timeout=1500, no_wait_after=True)
                clicked += 1
                await page.wait_for_timeout(350)
            except Exception:
                continue  # covered, detached or moved away: not the app's error
            if not page.url.startswith(PREVIEW_ORIGIN):
                break
        if len(errors) < 6:
            # A fresh load for the deeper checks, so the clicks above can't hide a form or open a dialog.
            stage[0] = "on load"
            await page.goto(PREVIEW_ORIGIN + clean_path(path), wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(700)
            for problem in await _link_problems(page, files, path):
                note("Broken link", problem)
            await _form_problems(page, path, stage, note)
        if len(errors) < 6:
            stage[0] = "(390px wide)"
            for problem in await _phone_problems(browser, handler, path):
                note("On a phone", problem)
        return errors[:6]
    finally:
        await context.close()


# What the browser checks read from the page (one evaluate each, so a slow page can't stall the test).
_LINKS_JS = """() => [...document.querySelectorAll('a[href]')].filter(a => a.offsetParent !== null || a.getClientRects().length)
  .slice(0, 60).map(a => ({href: a.getAttribute('href'), text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 40)}))"""
_ID_EXISTS_JS = "(id) => !!document.getElementById(id) || !!document.getElementsByName(id).length"


async def _link_problems(page, files: Dict[str, str], path: str) -> List[str]:
    """Nav and in-page links that lead nowhere: #pricing with no element of that id, or a page that isn't there."""
    out = []
    try:
        links = await page.evaluate(_LINKS_JS)
    except Exception:
        return out
    seen = set()
    for link in links:
        href, label = (link.get("href") or "").strip(), link.get("text") or "a link"
        if not href or href in seen or href in ("#", "#!") or href.startswith(("javascript:", "mailto:", "tel:", "sms:", "whatsapp:")):
            continue
        seen.add(href)
        if href.startswith("#"):
            target = unquote(href[1:])
            if re.match(r"^[\w\-:.]+$", target) and not await page.evaluate(_ID_EXISTS_JS, target):
                out.append(f"“{label}” goes to {href}, but no section has id=\"{target}\". Add that id to the section it means.")
        else:
            local = _resolve(path, href.split("#")[0].split("?")[0])
            if local and local not in files and local + "/index.html" not in files and local + ".html" not in files \
                    and not local.endswith("/") and "." in local.rsplit("/", 1)[-1]:
                out.append(f"“{label}” opens {href}, which isn't one of the app's files.")
        if len(out) >= 3:
            break
    return out


_FORMS_JS = """() => [...document.forms].filter(f => f.offsetParent !== null && f.querySelector('input:not([type=hidden]),textarea,select'))
  .slice(0, 2).map((f, i) => { f.setAttribute('data-krish-test', i); return {i, name: (f.getAttribute('aria-label') || f.id ||
  (f.querySelector('button,[type=submit]') || {}).innerText || 'form').trim().slice(0, 40)}; })"""
# Fill a form the way a careful person would: a real-looking value for every field, then submit it.
_FILL_JS = """(i) => {
  const f = document.querySelector(`form[data-krish-test="${i}"]`); if (!f) return null;
  const pad = n => String(n).padStart(2, '0'), d = new Date(Date.now() + 3 * 864e5);
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const set = (el, v) => { const proto = Object.getPrototypeOf(el), desc = Object.getOwnPropertyDescriptor(proto, 'value');
    desc && desc.set ? desc.set.call(el, v) : (el.value = v); el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); };
  for (const el of f.querySelectorAll('input,textarea,select')) {
    if (el.disabled || el.readOnly) continue;
    const t = (el.type || '').toLowerCase(), hint = ((el.name || '') + ' ' + (el.id || '') + ' ' + (el.placeholder || '')).toLowerCase();
    if (t === 'hidden' || t === 'submit' || t === 'button' || t === 'file' || t === 'reset') continue;
    if (t === 'checkbox') { if (el.required || !el.checked) { el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); } continue; }
    if (t === 'radio') { if (!f.querySelector(`input[type=radio][name="${el.name}"]:checked`)) { el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); } continue; }
    if (el.tagName === 'SELECT') { const o = [...el.options].find((o, k) => k > 0 && o.value) || el.options[0]; if (o) set(el, o.value); continue; }
    let v = 'Asha Patel';
    if (t === 'email' || /mail/.test(hint)) v = 'asha.patel@example.com';
    else if (t === 'tel' || /phone|mobile|tel/.test(hint)) v = '9876543210';
    else if (t === 'number' || t === 'range') v = String(Math.max(Number(el.min) || 1, 1));
    else if (t === 'date') v = date; else if (t === 'time') v = '11:30'; else if (t === 'datetime-local') v = date + 'T11:30';
    else if (t === 'month') v = date.slice(0, 7); else if (t === 'url') v = 'https://example.com'; else if (t === 'color') v = '#3366ff';
    else if (t === 'password') v = 'Krish-Test-2026'; else if (t === 'search') v = 'test';
    else if (el.tagName === 'TEXTAREA') v = 'Hello! I would like to know more, please call me back.';
    else if (/city|address|location/.test(hint)) v = 'Jaipur'; else if (/pin|zip/.test(hint)) v = '302001';
    if (el.maxLength > 0) v = v.slice(0, el.maxLength);
    set(el, v);
  }
  if (!f.checkValidity()) { const bad = f.querySelector(':invalid'); return {invalid: bad ? (bad.name || bad.id || bad.type) : 'a field'}; }
  window.__krishBefore = document.body.innerText.length + '|' + document.body.innerHTML.length;
  window.__krishDialog = 0; for (const k of ['alert', 'confirm']) { const o = window[k]; window[k] = function () { window.__krishDialog++; return k === 'confirm' ? true : undefined; }; }
  const btn = f.querySelector('button[type=submit],input[type=submit],button:not([type])');
  btn ? btn.click() : f.requestSubmit();
  return {submitted: true};
}"""
_CHANGED_JS = ("() => window.__krishDialog > 0 || "
               "window.__krishBefore !== (document.body.innerText.length + '|' + document.body.innerHTML.length)")


async def _form_problems(page, path: str, stage: list, note) -> None:
    """Fill in and submit each form: errors, a page reload (the form isn't handled) or nothing happening at all."""
    try:
        forms = await page.evaluate(_FORMS_JS)
    except Exception:
        return
    for form in forms:
        stage[0] = f"after submitting the “{form['name']}” form"
        try:
            before = page.url
            res = await page.evaluate(_FILL_JS, form["i"])
            if not res:
                continue
            if res.get("invalid"):
                note("Form problem", f"filled with valid details, the field “{res['invalid']}” still isn't accepted, so the "
                     "form can't be sent. Check its type, pattern and required settings.")
                continue
            await page.wait_for_timeout(900)
            if page.url != before and page.url.split("#")[0].split("?")[0] == before.split("#")[0].split("?")[0]:
                note("Form problem", "submitting it reloads the page and the details are lost. Handle the submit in "
                     "JavaScript (event.preventDefault()), save or send the details, and show a confirmation.")
                await page.goto(PREVIEW_ORIGIN + clean_path(path), wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(500)
                await page.evaluate(_FORMS_JS)  # the reload dropped the forms' test marks
                continue
            if page.url.startswith(PREVIEW_ORIGIN) and not await page.evaluate(_CHANGED_JS):
                note("Form problem", "submitting it with valid details does nothing the user can see. Make it do its "
                     "job and show a clear confirmation (a message, a toast or the new item in a list).")
        except Exception:
            continue


_PHONE_JS = r"""() => {
  const W = document.documentElement.clientWidth || innerWidth, out = {};
  if (document.documentElement.scrollWidth > W + 4) {
    let worst = null, wide = 0;
    for (const el of document.body.querySelectorAll('*')) {
      const r = el.getBoundingClientRect(); if (!r.width || getComputedStyle(el).position === 'fixed') continue;
      const over = r.right - W; if (over > wide + 1 && r.width > W * 0.3) { wide = over; worst = el; }
    }
    if (worst) { const c = (worst.getAttribute('class') || '').trim().split(/\s+/).slice(0, 2).join('.');
      out.wide = {what: worst.tagName.toLowerCase() + (worst.id ? '#' + worst.id : '') + (c ? '.' + c : ''), px: Math.round(document.documentElement.scrollWidth)}; }
  }
  const head = document.querySelector('header, nav, .nav');
  if (head) {
    const links = [...head.querySelectorAll('a[href]')].filter(a => !a.closest('.brand') && a !== head.querySelector('a'));
    const shown = links.filter(a => a.getClientRects().length && getComputedStyle(a).visibility !== 'hidden');
    const toggles = [...head.querySelectorAll('button, [role=button], summary, label[for]')].filter(b => b.getClientRects().length);
    if (links.length >= 3 && shown.length === 0 && toggles.length === 0) out.menu = links.length;
  }
  const small = [...document.querySelectorAll('button, a.btn, [role=button]')].filter(b => { const r = b.getBoundingClientRect();
    return r.width && r.height && r.height < 28 && r.width < 28 && getComputedStyle(b).visibility !== 'hidden'; });
  if (small.length >= 3) out.small = small.length;
  return out;
}"""


async def _phone_problems(browser, handler, path: str) -> List[str]:
    """Open the app as a phone (390px wide, touch): sideways scrolling, a menu with no way to open it, tiny buttons."""
    out = []
    phone = await browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                      device_scale_factor=2, accept_downloads=False)
    try:
        await phone.route("**/*", handler)
        page = await phone.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        await page.goto(PREVIEW_ORIGIN + clean_path(path), wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        await page.wait_for_timeout(500)
        found = await page.evaluate(_PHONE_JS)
        if found.get("wide"):
            out.append(f"the page scrolls sideways ({found['wide']['px']}px wide on a 390px screen); "
                       f"{found['wide']['what']} is too wide. Let it wrap or shrink (max-width: 100%, flex-wrap, grids "
                       "that drop to one column) so nothing sticks out.")
        if found.get("menu"):
            out.append("the menu links are hidden and there's no button to open them. Add a menu button that shows "
                       "them (with Krish UI, put the links in .nav-links inside .nav and it appears by itself).")
        if found.get("small"):
            out.append(f"{found['small']} buttons are smaller than a fingertip (under 28px). Make tap targets at least 40px.")
    except Exception:
        pass
    finally:
        await phone.close()
    return out


# ------------------------------------------------------------- agent tools
_ID_DEF_RE = re.compile(r"""\bid\s*=\s*["'`]([\w\-:.]+)["'`]|\.id\s*=\s*["'`]([\w\-:.]+)["'`]|setAttribute\(\s*["']id["']\s*,\s*["'`]([\w\-:.]+)""")
_ID_USE_RE = re.compile(r"""getElementById\(\s*["'`]([\w\-:.]+)["'`]\s*\)|querySelector(?:All)?\(\s*["'`]#([\w\-]+)["'`]\s*\)|\$\(\s*["'`]#([\w\-]+)["'`]\s*\)""")
_LOCAL_REF_RE = re.compile(r"""<(?:script|link|img)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"'#?]+)""", re.IGNORECASE)
_IMPORT_RE = re.compile(r"""(?:\bimport\b[^'"]*?|\bimport\(\s*)["'](\.{1,2}/[^"']+)["']""")


def _resolve(base: str, ref: str) -> Optional[str]:
    """The app path a relative reference points to, or None for an outside URL."""
    if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//)", ref, re.IGNORECASE):
        return None
    parts = ([] if ref.startswith("/") else base.split("/")[:-1]) + ref.split("/")
    out = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if out:
                out.pop()
        else:
            out.append(part)
    return "/".join(out) or None


def app_problems(files: Dict[str, str]) -> List[str]:
    """Mistakes that leave a page blank or crash it, found without running it: elements the code looks up
    by id that no file creates, and local files that are loaded but don't exist."""
    problems = []
    if "index.html" not in files:
        problems.append("There is no index.html, so the preview is empty.")
    web = {p: c for p, c in files.items() if p.endswith((".html", ".htm", ".js", ".mjs", ".jsx"))}
    defined = {next(g for g in m.groups() if g) for c in web.values() for m in _ID_DEF_RE.finditer(c)}
    missing_ids = {}
    for path, content in web.items():
        for m in _ID_USE_RE.finditer(content):
            ident = next(g for g in m.groups() if g)
            if ident not in defined and "${" not in ident:
                missing_ids.setdefault(ident, path)
    for ident, path in list(missing_ids.items())[:8]:
        problems.append(f'{path} looks up the element #{ident}, but no HTML has id="{ident}" '
                        "(this crashes the page with \"Cannot read/set properties of null\").")
    missing_files = {}
    for path, content in web.items():
        refs = _LOCAL_REF_RE.findall(content) if path.endswith((".html", ".htm")) else []
        refs += _IMPORT_RE.findall(content)
        for ref in refs:
            target = _resolve(path, ref.strip())
            if target and target not in files and target.rsplit(".", 1)[-1].lower() in ("js", "mjs", "css", "jsx"):
                missing_files.setdefault(target, path)
    for target, path in list(missing_files.items())[:8]:
        problems.append(f"{path} loads {target}, which doesn't exist yet.")
    return problems


def _is_module(path: str, files: Dict[str, str]) -> bool:
    if path.endswith(".mjs"):
        return True
    name = path.rsplit("/", 1)[-1]
    tagged = any(re.search(r"<script[^>]*type=[\"']module[\"'][^>]*" + re.escape(name), c, re.IGNORECASE)
                 for p, c in files.items() if p.endswith((".html", ".htm")))
    return tagged or bool(re.search(r"^\s*(?:import\s|export\s)", files[path], re.MULTILINE))


_INLINE_SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
_SCRIPT_TYPE_RE = re.compile(r"""\btype\s*=\s*["']?([\w/+.-]+)""", re.IGNORECASE)


def _inline_scripts(html: str) -> List[tuple]:
    """(first line, code, is_module) for each script written inside a page, not loaded from a file."""
    out = []
    for m in _INLINE_SCRIPT_RE.finditer(html):
        attrs, code = m.group(1), m.group(2)
        if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE) or not code.strip():
            continue
        kind = (_SCRIPT_TYPE_RE.search(attrs) or [None, ""])[1].lower()
        if kind not in ("", "text/javascript", "application/javascript", "module"):
            continue  # JSON, templates, Babel/JSX: not plain JavaScript
        out.append((html.count("\n", 0, m.start(2)) + 1, code, kind == "module"))
    return out


async def _inline_syntax_errors(files: Dict[str, str], node: str, tmp: str) -> List[str]:
    """Scripts inside HTML pages that don't parse, so the page's buttons and features do nothing."""
    problems = []
    for path, html in files.items():
        if not path.endswith((".html", ".htm")):
            continue
        for n, (first, code, module) in enumerate(_inline_scripts(html)[:6]):
            target = os.path.join(tmp, f"inline{n}_" + re.sub(r"[^\w.-]", "_", path) + (".mjs" if module else ".cjs"))
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(code)
            try:
                proc = await asyncio.create_subprocess_exec(node, "--check", target, stdout=asyncio.subprocess.DEVNULL,
                                                            stderr=asyncio.subprocess.PIPE)
                _, err = await asyncio.wait_for(proc.communicate(), timeout=10)
            except (asyncio.TimeoutError, OSError):
                continue
            if proc.returncode:
                lines = [l for l in err.decode("utf-8", "replace").splitlines() if l.strip()]
                where = next((l.rsplit(":", 1)[-1] for l in lines if target in l and ":" in l), "")
                error = next((l for l in lines if "Error" in l), "a syntax error")
                line = f" near line {first + int(where) - 1}" if where.isdigit() else ""
                problems.append(f"{path} has a JavaScript syntax error in a <script>{line} ({error.strip()[:160]}), "
                                "so none of that script runs.")
    return problems


async def _syntax_errors(files: Dict[str, str]) -> List[str]:
    """JavaScript that doesn't parse (usually a file cut off mid-way), in .js files and in pages' own <script>
    tags, checked with `node --check`."""
    # JSX and TypeScript are checked by compiling them (jsx_compile), not by node, which can't read them.
    jsx = [p for p in files if jsx_compile.needs_compile(p, files[p])]
    problems = []
    if jsx and jsx_compile.available():
        for path in jsx[:20]:
            try:
                await asyncio.to_thread(jsx_compile._esbuild, files[path], jsx_compile._loader(path))
            except Exception as exc:
                problems.append(f"{path} doesn't compile ({str(exc).strip()[:300]}), so none of it runs.")
    scripts = [p for p in files if p.endswith((".js", ".mjs")) and p not in jsx]
    node = shutil.which("node")
    pages = any(p.endswith((".html", ".htm")) for p in files)
    if not (scripts or pages) or not node:
        return problems
    with tempfile.TemporaryDirectory() as tmp:
        for path in scripts[:12]:
            target = os.path.join(tmp, re.sub(r"[^\w.-]", "_", path) + (".mjs" if _is_module(path, files) else ".cjs"))
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(files[path])
            try:
                proc = await asyncio.create_subprocess_exec(node, "--check", target, stdout=asyncio.subprocess.DEVNULL,
                                                            stderr=asyncio.subprocess.PIPE)
                _, err = await asyncio.wait_for(proc.communicate(), timeout=10)
            except (asyncio.TimeoutError, OSError):
                continue
            if proc.returncode:
                lines = [l for l in err.decode("utf-8", "replace").splitlines() if l.strip()]
                where = next((l.rsplit(":", 1)[-1] for l in lines if target in l and ":" in l), "")
                error = next((l for l in lines if "Error" in l), "a syntax error")
                at_end = where.isdigit() and int(where) >= len(files[path].rstrip().splitlines()) - 1
                cut = " The file looks cut off: add the missing rest with append_file." \
                    if at_end or "end of input" in error or "Unterminated" in error else ""
                problems.append(f"{path} has a syntax error{f' near line {where}' if where.isdigit() else ''} "
                                f"({error.strip()[:160]}), so none of it runs.{cut}")
        problems += await _inline_syntax_errors(files, node, tmp)
    return problems


async def check_app(files: Dict[str, str]) -> List[str]:
    """Everything that would crash or blank the page: app_problems plus JavaScript syntax errors."""
    return app_problems(files) + await _syntax_errors(files)


async def _with_problems(app_id: str, text: str) -> str:
    problems = await check_app(await snapshot(app_id))
    if not problems:
        return text
    return text + "\nProblems in the app right now (fix them before you finish):\n- " + "\n- ".join(problems)


def _tool_output(content: str, summary: str, ok: bool = True, media=None) -> ToolOutput:
    return ToolOutput(content=content, summary=summary[:160], ok=ok, media=media or [])


async def _t_list(ctx, args):
    files = await snapshot(ctx.app_id)
    return _tool_output(app_prompt_files(files), f"{len(files)} files")


async def _t_read(ctx, args):
    path = clean_path(args.get("path", ""))
    doc = await db.app_files.find_one({"appId": ctx.app_id, "path": path})
    if not doc:
        return _tool_output(f"{path} does not exist.", f"{path} not found", ok=False)
    lines = doc["content"].split("\n")
    start = max(1, int(args.get("start_line") or 1))
    end = min(len(lines), int(args.get("end_line") or len(lines)))
    numbered = "\n".join(f"{i:4d}  {lines[i - 1]}" for i in range(start, end + 1))
    if len(numbered) > READ_CHARS:
        cut = numbered[:READ_CHARS].rsplit("\n", 1)[0]
        last = start + cut.count("\n")
        numbered = cut + f"\n… (file has {len(lines)} lines; read more with start_line={last + 1})"
    return _tool_output(numbered, f"Read {path}" + (f" lines {start}-{end}" if (start, end) != (1, len(lines)) else ""))


async def _t_search(ctx, args):
    query = (args.get("query") or "").strip()
    if not query:
        raise ValueError("'query' is required")
    hits = []
    async for f in db.app_files.find({"appId": ctx.app_id}).sort("path", 1):
        for i, line in enumerate(f["content"].split("\n"), 1):
            if query.lower() in line.lower():
                hits.append(f"{f['path']}:{i}: {line.strip()[:200]}")
    shown = hits[:60]
    body = "\n".join(shown) + (f"\n… and {len(hits) - 60} more" if len(hits) > 60 else "")
    return _tool_output(body or f"No line contains “{query}”.", f"{len(hits)} match(es) for “{query[:40]}”")


async def _t_write(ctx, args):
    content = args.get("content")
    if not isinstance(content, str):
        raise ValueError("'content' is required")
    path = await write_file(ctx.app_id, args.get("path", ""), content)
    return _tool_output(await _with_problems(ctx.app_id, f"Wrote {path} ({len(content)} chars)."), f"Wrote {path}")


async def _t_append(ctx, args):
    content = args.get("content")
    if not isinstance(content, str):
        raise ValueError("'content' is required")
    path = clean_path(args.get("path", ""))
    doc = await db.app_files.find_one({"appId": ctx.app_id, "path": path}, {"content": 1})
    before = (doc or {}).get("content", "")
    joiner = "" if not before or before.endswith("\n") or content.startswith("\n") else "\n"
    await write_file(ctx.app_id, path, before + joiner + content)
    return _tool_output(await _with_problems(ctx.app_id, f"Added {len(content)} chars to {path} "
                                             f"(now {len(before) + len(joiner) + len(content)} chars)."), f"Wrote {path}")


_LINE_NO_RE = re.compile(r"(?m)^ *\d+  ")


def _strip_line_numbers(text: str) -> str:
    """Undo read_file's "  12  " prefixes when the model copies them into an edit."""
    lines = [l for l in text.split("\n") if l.strip()]
    return _LINE_NO_RE.sub("", text) if lines and all(_LINE_NO_RE.match(l) for l in lines) else text


def locate_snippet(content: str, old: str):
    """Find `old` in `content`: exactly, then without copied line numbers, then ignoring whitespace.

    Returns (start, end, None) for a unique match, else (None, None, a message for the model).
    """
    candidates = [old]
    stripped = _strip_line_numbers(old)
    if stripped != old:
        candidates.append(stripped)
    for cand in candidates:
        count = content.count(cand)
        if count == 1:
            i = content.index(cand)
            return i, i + len(cand), None
        if count > 1:
            lines = sorted({content.count("\n", 0, m.start()) + 1 for m in re.finditer(re.escape(cand), content)})
            return None, None, (f"old_text matches {count} places (lines {', '.join(map(str, lines[:10]))}). "
                                "Include a few more surrounding lines so it matches exactly one.")
    tokens = stripped.split()
    if tokens:
        matches = list(re.finditer(r"\s+".join(map(re.escape, tokens)), content))
        if len(matches) == 1:
            return matches[0].start(), matches[0].end(), None
        if len(matches) > 1:
            return None, None, f"old_text matches {len(matches)} places. Include more surrounding lines."
    # Point the model at the closest text so its next try can succeed.
    file_lines, want = content.split("\n"), [l.strip() for l in stripped.strip().split("\n")]
    n, best, best_at = max(1, len(want)), 0.0, 0
    for i in range(0, max(1, len(file_lines) - n + 1)):
        score = difflib.SequenceMatcher(None, "\n".join(l.strip() for l in file_lines[i:i + n]), "\n".join(want)).quick_ratio()
        if score > best:
            best, best_at = score, i
    lo, hi = max(0, best_at - 2), min(len(file_lines), best_at + n + 2)
    near = "\n".join(f"{i + 1:4d}  {file_lines[i]}" for i in range(lo, hi))
    return None, None, ("old_text was not found in the file. The closest text is below; copy old_text exactly "
                        f"from it (without the line numbers), or use write_file for a bigger change.\n{near}")


async def _t_edit(ctx, args):
    path = clean_path(args.get("path", ""))
    doc = await db.app_files.find_one({"appId": ctx.app_id, "path": path})
    if not doc:
        return _tool_output(f"{path} does not exist.", f"{path} not found", ok=False)
    # One change (old_text, new_text), or several in one call (edits), so a change that touches many places
    # doesn't use up a builder turn's steps. They apply in order, all or none.
    edits = args.get("edits") if isinstance(args.get("edits"), list) else []
    if args.get("old_text"):
        edits = [{"old_text": args["old_text"], "new_text": args.get("new_text", "")}] + edits
    if not edits:
        raise ValueError("'old_text' (or 'edits') is required")
    content = doc["content"]
    for n, edit in enumerate(edits, 1):
        old, new = (edit or {}).get("old_text"), (edit or {}).get("new_text", "") or ""
        if not old:
            return _tool_output(f"Edit {n} has no old_text. Nothing was changed.", "Edit didn't match; retrying", ok=False)
        start, end, problem = locate_snippet(content, old)
        if problem:
            which = f"Edit {n} of {len(edits)}: " if len(edits) > 1 else ""
            done = " Nothing was changed; send the edits again with this one fixed." if len(edits) > 1 else ""
            return _tool_output(which + problem + done, "Edit didn't match; retrying", ok=False)
        if _strip_line_numbers(new) != new and _strip_line_numbers(old) != old:
            new = _strip_line_numbers(new)
        content = content[:start] + new + content[end:]
    await write_file(ctx.app_id, path, content)
    made = f" ({len(edits)} changes)" if len(edits) > 1 else ""
    return _tool_output(await _with_problems(ctx.app_id, f"Edited {path}{made}."), f"Edited {path}{made}")


async def _t_delete(ctx, args):
    path = clean_path(args.get("path", ""))
    ok = await delete_file(ctx.app_id, path)
    return _tool_output(f"Deleted {path}." if ok else f"{path} did not exist.", f"Deleted {path}", ok=ok)


async def _t_run(ctx, args):
    command = (args.get("command") or "").strip()
    if not command:
        raise ValueError("'command' is required")
    res = await sandbox.run_shell(command, await snapshot(ctx.app_id))
    body = format_run(res)
    ok = res.exit_code == 0 and not res.timed_out
    return _tool_output(body, f"`{command[:60]}` → " + ("ok" if ok else "timed out" if res.timed_out else f"exit {res.exit_code}"), ok=ok)


def format_run(res) -> str:
    parts = []
    if res.stdout:
        parts.append(f"stdout:\n{res.stdout}")
    if res.stderr:
        parts.append(f"stderr:\n{res.stderr}")
    parts.append("Timed out and was killed." if res.timed_out else f"exit code: {res.exit_code}")
    return "\n\n".join(parts)


async def _t_check(ctx, args):
    import media

    result = await check_preview(await snapshot(ctx.app_id), args.get("path") or "index.html", app_id=ctx.app_id)
    shot = await media.save_media(ctx.db, ctx.user_id, result["screenshot"], "image/jpeg", "screenshot",
                                  name="preview.jpg", conversation_id=ctx.conversation_id)
    errors = [l for l in result["logs"] if l.startswith(("[console.error]", "[uncaught", "[request failed]", "[http"))]
    body = (f"Title: {result['title']}\n\nConsole and network ({len(result['logs'])} entries):\n"
            + ("\n".join(result["logs"]) or "(none)") + f"\n\nVisible text:\n{result['text']}")
    summary = f"{len(errors)} error(s)" if errors else "No errors"
    return _tool_output(body, summary, ok=not errors, media=[shot])


async def _t_commit(ctx, args):
    result = await commit(ctx.app_id, args.get("message") or "Update", author="Krish AI")
    if not result:
        return _tool_output("Nothing to commit — no changes since the last version.", "No changes")
    return _tool_output(f"Committed version {result['id']}: {result['message']}", f"Saved version {result['id']}")


def register_tools(registry):
    path_param = {"type": "string", "description": "File path relative to the app root, e.g. index.html or src/app.js"}
    specs = [
        ("list_files", "List files", "List the app's files with sizes.", {}, [], _t_list),
        ("read_file", "Read file", "Read a file from the app with line numbers; for a large file pass start_line and "
         "end_line to read part of it.", {"path": path_param, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
         ["path"], _t_read),
        ("search_files", "Search files", "Find every line containing some text (case-insensitive) across the app's "
         "files, with file names and line numbers.", {"query": {"type": "string"}}, ["query"], _t_search),
        ("write_file", "Write file", "Create or overwrite a file in the app with the full new content.",
         {"path": path_param, "content": {"type": "string"}}, ["path", "content"], _t_write),
        ("append_file", "Write file", "Add content to the end of a file (creates it if missing). Use it to write a long "
         "file in parts: write_file with the first part, then append_file with each next part.",
         {"path": path_param, "content": {"type": "string"}}, ["path", "content"], _t_append),
        ("edit_file", "Edit file", "Replace an exact, unique snippet of text in a file (old_text with new_text). "
         "For several changes in the same file, pass them all at once in edits instead; they apply in order.",
         {"path": path_param, "old_text": {"type": "string"}, "new_text": {"type": "string"},
          "edits": {"type": "array", "description": "Several changes in this file, applied in order",
                    "items": {"type": "object", "properties": {"old_text": {"type": "string"},
                                                               "new_text": {"type": "string"}},
                              "required": ["old_text", "new_text"]}}},
         ["path"], _t_edit),
        ("delete_file", "Delete file", "Delete a file from the app.", {"path": path_param}, ["path"], _t_delete),
        ("run_command", "Terminal", "Run a shell command (sh) in a sandboxed copy of the app files: e.g. `node --test`, "
         "`python3 -m unittest`, `node script.js`. No network. File changes made by the command are not saved.",
         {"command": {"type": "string"}}, ["command"], _t_run),
        ("check_preview", "Check preview", "Open the app in a real browser: returns a screenshot, console logs, "
         "errors and failed requests. Use after UI changes.", {"path": {"type": "string", "description": "Page to open (default index.html)"}},
         [], _t_check),
        ("commit", "Save version", "Save the current files as a new version in the app's history (git commit).",
         {"message": {"type": "string"}}, ["message"], _t_commit),
    ]
    for name, label, desc, props, required, handler in specs:
        registry.register(Tool(name=name, label=label, description=desc,
                               parameters={"type": "object", "properties": props, "required": required},
                               handler=handler, scope="app",
                               available=(agent_browser.available if name == "check_preview" else (lambda: True))))


# ---------------------------------------------------------------- HTTP API
class AppIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    template: str = "blank"
    files: Optional[Dict[str, str]] = None  # start from these files instead of a template (e.g. code from a chat)


class AppPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)


class FileIn(BaseModel):
    content: str


class CommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=2000)


class GitHubIn(BaseModel):
    repo: str = Field(min_length=1, max_length=140)
    token: str = Field(default="", max_length=300)  # empty: use the GitHub connected in Settings > Connectors
    private: bool = True


class CommitIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


async def choose_style(app_id: str, request: str) -> Optional[str]:
    """Pick or keep the app's design style for this turn (design_themes.choose) and remember it on the app."""
    app = await db.apps.find_one({"id": app_id}, {"theme": 1})
    if not app:
        return None
    files = await snapshot(app_id)
    first = is_blank(files) or _starter(files)
    # Only the user's own words: not the code or errors that click-to-edit and auto-fix add after them.
    words = "" if re.match(r"\s*(Auto-fix:|The preview shows)", request or "") else (request or "").split("\n\n")[0]
    picked = re.search(r"(?im)^Design style:\s*(.+)$", request or "")  # the style chosen on the Apps page
    if picked:
        words = "Design style: " + picked.group(1) + "\n" + words
    theme = design_themes.choose(words, app.get("theme"), app_id, first)
    if theme and theme != app.get("theme"):
        await db.apps.update_one({"id": app_id}, {"$set": {"theme": theme}})
    return theme


def _starter(files: Dict[str, str]) -> bool:
    """Still exactly one of the starter templates (the instant start shown while the real app is written)."""
    own = {p: c for p, c in files.items() if not p.startswith((SAMPLE_DIR + "/", ASSET_DIR + "/")) and p != KIT_NAME}
    return any(own == {p: c for p, c in t.items() if p != KIT_NAME} for t in TEMPLATES.values())


def public_app(doc: dict) -> dict:
    pub = doc.get("published")
    return {
        "id": doc["id"], "name": doc["name"], "description": doc.get("description"),
        "conversationId": doc.get("conversationId"), "createdAt": doc["createdAt"], "updatedAt": doc["updatedAt"],
        "published": {"slug": pub["slug"], "url": f"/api/sites/{pub['slug']}/", "commitId": pub.get("commitId"),
                      "publishedAt": pub.get("publishedAt")} if pub else None,
        "github": doc.get("github"),
        "domain": doc.get("domain"),
        "theme": doc.get("theme"),
    }


@router.get("/apps")
async def list_apps(user_id: str = Depends(current_user_id)):
    docs = await db.apps.find({"userId": user_id}).sort("updatedAt", -1).to_list(500)
    return [public_app(d) for d in docs]


@router.post("/apps")
async def create_app(body: AppIn, user_id: str = Depends(current_user_id)):
    ts = _now()
    app_id = str(uuid.uuid4())
    conv = {"id": str(uuid.uuid4()), "userId": user_id, "title": f"App: {body.name.strip()}", "model": None,
            "projectId": None, "appId": app_id, "createdAt": ts, "updatedAt": ts}
    doc = {"id": app_id, "userId": user_id, "name": body.name.strip(), "description": (body.description or "").strip() or None,
           "conversationId": conv["id"], "published": None, "createdAt": ts, "updatedAt": ts}
    if body.files:
        if len(body.files) > MAX_FILES:
            raise HTTPException(status_code=400, detail=f"Too many files (max {MAX_FILES})")
        try:
            source = {clean_path(p): c for p, c in body.files.items()}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        label = "Create app from chat code"
    else:
        template = body.template if body.template in TEMPLATES else "blank"
        source, label = TEMPLATES[template], f"Create app from {template} template"
    await db.conversations.insert_one(conv)
    await db.apps.insert_one(doc)
    try:
        for path, content in source.items():
            await write_file(app_id, path, content)
    except ValueError as exc:
        await db.app_files.delete_many({"appId": app_id})
        await db.apps.delete_one({"id": app_id})
        await db.conversations.delete_one({"id": conv["id"]})
        raise HTTPException(status_code=400, detail=str(exc))
    await commit(app_id, label, author="Krish AI")
    return public_app(doc)


@router.get("/apps/{app_id}")
async def get_app(app_id: str, user_id: str = Depends(current_user_id)):
    app = await owned_app(app_id, user_id)
    files = await db.app_files.find({"appId": app_id}, {"content": 0}).sort("path", 1).to_list(MAX_FILES)
    contents = {f["path"]: f["content"] async for f in db.app_files.find({"appId": app_id})}
    sizes = {path: len(text.encode("utf-8")) for path, text in contents.items()}
    return {"app": public_app(app), "files": [{"path": f["path"], "size": sizes.get(f["path"], 0)} for f in files],
            "changes": await changed_paths(app_id), "fresh": is_blank(contents)}


def is_blank(files: Dict[str, str]) -> bool:
    """True while the app is still the empty starter: the builder shows its animated start screen instead."""
    return files == TEMPLATES["blank"]


@router.patch("/apps/{app_id}")
async def update_app(app_id: str, body: AppPatch, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    updates = {k: (v.strip() or None) for k, v in body.model_dump(exclude_none=True).items()}
    if updates:
        updates["updatedAt"] = _now()
        await db.apps.update_one({"id": app_id}, {"$set": updates})
    return public_app(await db.apps.find_one({"id": app_id}))


@router.delete("/apps/{app_id}")
async def delete_app(app_id: str, user_id: str = Depends(current_user_id)):
    app = await owned_app(app_id, user_id)
    await db.app_files.delete_many({"appId": app_id})
    await db.app_commits.delete_many({"appId": app_id})
    await appdata.delete_app_data(app_id)
    if app.get("conversationId"):
        await db.messages.delete_many({"conversationId": app["conversationId"]})
        await db.conversations.delete_one({"id": app["conversationId"]})
    await db.apps.delete_one({"id": app_id})
    return {"ok": True}


@router.get("/apps/{app_id}/files/{path:path}")
async def read_app_file(app_id: str, path: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    doc = await db.app_files.find_one({"appId": app_id, "path": path})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    return {"path": doc["path"], "content": doc["content"]}


@router.put("/apps/{app_id}/files/{path:path}")
async def save_app_file(app_id: str, path: str, body: FileIn, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    try:
        saved = await write_file(app_id, path, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"path": saved, "changes": await changed_paths(app_id)}


@router.delete("/apps/{app_id}/files/{path:path}")
async def remove_app_file(app_id: str, path: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    try:
        if not await delete_file(app_id, path):
            raise HTTPException(status_code=404, detail="File not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "changes": await changed_paths(app_id)}


@router.post("/apps/{app_id}/run")
async def run_app_command(app_id: str, body: CommandIn, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    started = time.monotonic()
    res = await sandbox.run_shell(body.command, await snapshot(app_id))
    return {"stdout": res.stdout, "stderr": res.stderr, "exitCode": res.exit_code, "timedOut": res.timed_out,
            "networkIsolated": res.network_isolated, "seconds": round(time.monotonic() - started, 2)}


@router.get("/apps/{app_id}/commits")
async def list_commits(app_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    docs = await db.app_commits.find({"appId": app_id}).sort([("createdAt", -1), ("seq", -1)]).to_list(500)
    return [public_commit(d) for d in docs]


@router.post("/apps/{app_id}/commits")
async def create_commit(app_id: str, body: CommitIn, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    result = await commit(app_id, body.message, author="You")
    if not result:
        raise HTTPException(status_code=400, detail="No changes to save")
    return result


@router.get("/apps/{app_id}/commits/{commit_id}/diff")
async def commit_diff(app_id: str, commit_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    if commit_id == "working":
        head = await head_commit(app_id)
        return unified_diff(await commit_files(head) if head else {}, await snapshot(app_id))
    target = await db.app_commits.find_one({"appId": app_id, "id": commit_id})
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")
    parent = await db.app_commits.find_one({"appId": app_id, "id": target["parent"]}) if target.get("parent") else None
    return unified_diff(await commit_files(parent) if parent else {}, await commit_files(target))


@router.post("/apps/{app_id}/commits/{commit_id}/restore")
async def restore_commit(app_id: str, commit_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    return {"commit": await restore(app_id, commit_id), "changes": await changed_paths(app_id)}


@router.get("/apps/{app_id}/export")
async def export_app(app_id: str, request: Request, git: bool = Query(True), auth: Optional[str] = Query(None)):
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    app = await owned_app(app_id, decode_token(token)["sub"])
    data = await export_zip(app, include_git=git)
    name = re.sub(r"[^\w\-]+", "-", app["name"]).strip("-").lower() or "app"
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})


@router.post("/apps/{app_id}/github")
async def push_to_github(app_id: str, body: GitHubIn, user_id: str = Depends(current_user_id)):
    app = await owned_app(app_id, user_id)
    head = await head_commit(app_id)
    message = f"{app['name']}: {head['message']}" if head else f"{app['name']} from Krish AI"
    token = body.token.strip()
    if not token:
        import connectors
        try:
            token = (await connectors.secret_for(user_id, "github"))["access"]
        except connectors.ConnectError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    try:
        result = await github_push.push(portable(await snapshot(app_id)), token, body.repo, message, private=body.private)
    except github_push.PushError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.apps.update_one({"id": app_id}, {"$set": {"github": {"repo": result["repo"], "url": result["url"], "pushedAt": _now()}}})
    return result


@router.get("/apps/{app_id}/preview-token")
async def get_preview_token(app_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    token = preview_token(app_id, user_id)
    return {"token": token, "url": f"/api/app-preview/{token}/"}


@router.post("/apps/{app_id}/publish")
async def publish_app(app_id: str, user_id: str = Depends(current_user_id)):
    app = await owned_app(app_id, user_id)
    await limits.require_publish(db, user_id)
    head = await commit(app_id, "Publish", author="You") or public_commit(await head_commit(app_id))
    slug = (app.get("published") or {}).get("slug") or (
        (re.sub(r"[^a-z0-9]+", "-", app["name"].lower()).strip("-")[:30] or "app") + "-" + secrets.token_hex(3))
    await db.apps.update_one({"id": app_id}, {"$set": {"published": {
        "slug": slug, "commitId": head["id"], "publishedAt": _now()}, "updatedAt": _now()}})
    return public_app(await db.apps.find_one({"id": app_id}))


@router.delete("/apps/{app_id}/publish")
async def unpublish_app(app_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    await db.apps.update_one({"id": app_id}, {"$set": {"published": None, "updatedAt": _now()}})
    return public_app(await db.apps.find_one({"id": app_id}))


@router.get("/app-preview/{token}")
async def preview_root(token: str):
    return RedirectResponse(f"/api/app-preview/{token}/")


@router.get("/sites/{slug}")
async def site_root(slug: str):
    return RedirectResponse(f"/api/sites/{slug}/")


@router.get("/app-preview/{token}/{path:path}")
async def serve_preview(token: str, path: str = ""):
    payload = _decode_preview(token)
    app = await db.apps.find_one({"id": payload["sub"], "userId": payload["uid"]})
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return _serve(await snapshot(app["id"]), path, bridge=True, cache="no-store", app_id=app["id"])


@router.get("/sites/{slug}/{path:path}")
async def serve_site(slug: str, path: str = ""):
    app = await db.apps.find_one({"published.slug": slug})
    if not app or not app.get("published"):
        return Response("This site is not published.", status_code=404, media_type="text/plain")
    version = await db.app_commits.find_one({"appId": app["id"], "id": app["published"]["commitId"]})
    return _serve(await commit_files(version), path, bridge=False, cache="public, max-age=60", app_id=app["id"])


# ------------------------------------------------------------------ next ideas and the prompt booster
# After a build the App Builder offers a few one-tap next steps. They come from what the app doesn't have yet,
# read from its files, so they are instant and cost no AI request.
_IDEAS = [
    (lambda c: "body.dark" not in c and "dark-mode" not in c and "darkmode" not in c and "theme" not in c,
     "Add a dark mode switch", "Add a dark mode switch in the header that remembers the choice."),
    (lambda c: "radha.auth" not in c and ("<form" in c or "cart" in c or "booking" in c),
     "Add sign up and login", "Add sign up and login with RADHA.auth, and show the user's name in the header when signed in."),
    (lambda c: "localstorage" not in c and "radha.db" not in c,
     "Remember data after refresh", "Save the app's data so it is still there after a page refresh."),
    (lambda c: "<form" in c and "radha.notify" not in c,
     "Email me form messages", "When someone sends a form, email it to me with RADHA.notify and show a thank-you message."),
    (lambda c: "search" not in c,
     "Add a search bar", "Add a search bar that filters the main list as I type."),
    (lambda c: "radha.ai" not in c,
     "Add an AI helper", "Add a small AI helper chat button (bottom right) that answers questions about this app with RADHA.ai."),
    (lambda c: "chart" not in c and ("<table" in c or "stat" in c or "total" in c),
     "Add charts", "Add a chart (Chart.js) that shows the main numbers visually."),
    (lambda c: "reveal" not in c and "fade-up" not in c and "@keyframes" not in c and "animation" not in c,
     "Add smooth animations", "Add smooth animations: sections fade in on scroll and buttons have hover effects."),
    (lambda c: "@media" not in c and "krish-ui.css" not in c and "tailwind" not in c,
     "Make it phone friendly", "Make the whole app look great on a phone."),
]
MAX_IDEAS = 4
NEW_LOOK_PROMPT = ("Give the app a new look in a different style. Keep all the content, pages and features exactly as "
                   "they are, and change only the design and motion.")


def next_ideas(files: Dict[str, str]) -> List[dict]:
    code = "\n".join(c for p, c in files.items() if p.endswith((".html", ".htm", ".js", ".mjs", ".css"))
                     and not p.startswith((SAMPLE_DIR + "/", ASSET_DIR + "/")) and p != KIT_NAME).lower()
    if not code:
        return []
    out = [{"label": label, "prompt": prompt} for test, label, prompt in _IDEAS if test(code)]
    if 'class="theme-' in code or "class='theme-" in code or " theme-" in code:
        # A Krish-designed app can always try another of the kit's styles (design_themes.py picks one it hasn't had).
        out = out[:MAX_IDEAS - 1] + [{"label": "Try a new look", "prompt": NEW_LOOK_PROMPT}]
    return out[:MAX_IDEAS]


@router.get("/apps/{app_id}/ideas")
async def app_ideas(app_id: str, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    return {"ideas": next_ideas(await snapshot(app_id))}


BOOST_SYSTEM = (
    "You turn a short app idea into a clear brief for an AI app builder. Keep everything the user said (names, "
    "colours, language, features) and add what a great version needs: who it is for, the screens or page "
    "sections, 5 to 8 concrete features that must work, realistic sample content, and the look (style, colours, "
    "mood). Write it as one short paragraph and then \"- \" bullets, under 140 words, in the same language as the "
    "request. The app's own text is English unless the user "
    "asked for another language, and never two languages side by side. Output only the brief: no intro, no questions, no code.")


class BoostIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/apps/boost")
async def boost_prompt(body: BoostIn, user_id: str = Depends(current_user_id)):
    """The builder's "Improve my prompt" button: one quick call that writes a fuller brief from a short ask."""
    from agent import llm as agent_llm, prompt_boost

    model = prompt_boost._model()
    if not model:
        raise HTTPException(status_code=503, detail="No AI model is set up to improve prompts")
    out = []

    async def run():
        async for ev in agent_llm.stream_completion(model, [{"role": "system", "content": BOOST_SYSTEM},
                                                            {"role": "user", "content": body.text}], []):
            if ev["type"] == "text":
                out.append(ev["text"])

    try:
        await asyncio.wait_for(run(), prompt_boost.TIMEOUT)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't improve the prompt: {str(exc)[:200]}")
    text = "".join(out).strip()
    if not text:
        raise HTTPException(status_code=502, detail="Couldn't improve the prompt. Try again.")
    return {"text": text}


# ------------------------------------------------------------------ open a GitHub repository as an app
class ImportIn(BaseModel):
    repo: str = Field(min_length=3, max_length=300)


@router.post("/apps/import")
async def import_github(body: ImportIn, user_id: str = Depends(current_user_id)):
    """Open an existing project from GitHub in the App Builder (public repos as is, private ones with the user's
    connected GitHub account). Vite and React projects run in the preview thanks to jsx_compile."""
    token = ""
    try:
        import connectors
        token = (await connectors.secret_for(user_id, "github"))["access"]
    except Exception:
        token = ""  # not connected: public repositories still open
    try:
        repo = await github_push.download(body.repo, token)
    except github_push.PushError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach GitHub: {str(exc)[:200]}")
    files = {}
    for path, content in repo["files"].items():
        try:
            files[clean_path(path)] = content
        except ValueError:
            continue
    files = {p: c for p, c in files.items() if len(c.encode("utf-8")) <= MAX_FILE_BYTES}
    if not files:
        raise HTTPException(status_code=400, detail="That repository has no code files the App Builder can open.")
    created = await create_app(AppIn(name=repo["name"][:80], description=(repo["description"] or f"Imported from {repo['url']}")[:500],
                                     files=files), user_id)
    await db.apps.update_one({"id": created["id"]}, {"$set": {"github": {"repo": repo["url"].split("github.com/")[-1],
                                                                          "url": repo["url"], "importedAt": _now()}}})
    return public_app(await db.apps.find_one({"id": created["id"]}))


# ------------------------------------------------------------------ instant edits (no AI)
# The preview's "Edit a part" can change words and colours directly: the text is replaced where it is written in
# the code (when it is there exactly once), and styles go into one <style id="krish-edits"> block in the page.
EDIT_STYLE_ID = "krish-edits"
_EDITABLE = (".html", ".htm", ".js", ".mjs", ".jsx", ".tsx", ".ts", ".vue", ".svelte")
_STYLE_PROPS = {"color", "background", "font-size", "font-weight", "border-radius", "padding", "text-align"}
_SAFE_VALUE = re.compile(r"^[#\w\s.%(),-]{1,60}$")
_SAFE_SELECTOR = re.compile(r"^[\w\s#.:>()\-\[\]=\"']{1,300}$")
_EDIT_BLOCK = re.compile(r'<style id="' + EDIT_STYLE_ID + r'">(.*?)</style>\n?', re.DOTALL)
_RULE = re.compile(r"\s*(.+?)\s*\{([^}]*)\}")


class QuickEditIn(BaseModel):
    kind: str = Field(pattern="^(text|style)$")
    old: Optional[str] = Field(default=None, max_length=2000)
    new: Optional[str] = Field(default=None, max_length=2000)
    selector: Optional[str] = Field(default=None, max_length=300)
    styles: Optional[Dict[str, str]] = None


def replace_text_once(files: Dict[str, str], old: str, new: str) -> Optional[tuple]:
    """(path, new content) when `old` is written exactly once in the app's code, else None."""
    old = old.strip()
    if not old:
        return None
    hits = [(p, c) for p, c in files.items() if p.endswith(_EDITABLE) and not p.startswith((SAMPLE_DIR + "/", ASSET_DIR + "/"))
            for _ in range(c.count(old))]
    if len(hits) != 1:
        return None
    path, content = hits[0]
    return path, content.replace(old, new.strip(), 1)


def add_styles(html: str, selector: str, styles: Dict[str, str]) -> str:
    """The page with `styles` set on `selector` in its krish-edits block (made when missing, rule merged when the
    selector already has one)."""
    m = _EDIT_BLOCK.search(html)
    rules = {}
    for rm in _RULE.finditer(m.group(1) if m else ""):
        props = {}
        for decl in rm.group(2).split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                props[k.strip()] = v.replace("!important", "").strip()
        rules[rm.group(1)] = props
    rules.setdefault(selector, {}).update(styles)
    css = "\n".join(f"{sel} {{ " + " ".join(f"{k}: {v} !important;" for k, v in props.items()) + " }"
                    for sel, props in rules.items())
    block = f'<style id="{EDIT_STYLE_ID}">\n{css}\n</style>\n'
    if m:
        return html[:m.start()] + block + html[m.end():]
    idx = html.lower().find("</head>")
    return html[:idx] + block + html[idx:] if idx >= 0 else block + html


@router.post("/apps/{app_id}/quick-edit")
async def quick_edit(app_id: str, body: QuickEditIn, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    files = await snapshot(app_id)
    if body.kind == "text":
        found = replace_text_once(files, body.old or "", body.new or "")
        if not found:
            raise HTTPException(status_code=409, detail="That text isn't written once in the code, so Krish will change it instead.")
        path, content = found
        await write_file(app_id, path, content)
        return {"path": path, "changes": await changed_paths(app_id)}
    styles = {k: v.strip() for k, v in (body.styles or {}).items() if k in _STYLE_PROPS and v and _SAFE_VALUE.match(v.strip())}
    selector = (body.selector or "").strip()
    if not styles or not _SAFE_SELECTOR.match(selector):
        raise HTTPException(status_code=400, detail="Pick a part of the page and a style to change.")
    page = "index.html" if "index.html" in files else next((p for p in files if p.endswith((".html", ".htm"))), None)
    if not page:
        raise HTTPException(status_code=400, detail="The app has no page to style.")
    await write_file(app_id, page, add_styles(files[page], selector, styles))
    return {"path": page, "changes": await changed_paths(app_id)}


# ------------------------------------------------------------------ custom domains
# A published app can answer on the owner's own domain: they point a CNAME at Krish AI's address, and the
# server's host check (site_for_host, used by a middleware in server.py) serves the site for that host.
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?!-)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")
_DOMAIN_CACHE: Dict[str, tuple] = {}
_DOMAIN_TTL = 60


class DomainIn(BaseModel):
    domain: str = Field(default="", max_length=253)


def clean_domain(text: str) -> str:
    d = re.sub(r"^https?://", "", (text or "").strip().lower()).split("/")[0].split(":")[0].rstrip(".")
    return d


def own_hosts() -> set:
    hosts = {"localhost", "127.0.0.1", "0.0.0.0", "testserver"}
    for value in (public_origin(), os.environ.get("FRONTEND_URL", ""), os.environ.get("BACKEND_URL", "")):
        host = urlparse(value).hostname if value else None
        if host:
            hosts.add(host.lower())
    hosts.update(h.strip().lower() for h in os.environ.get("APP_HOSTS", "").split(",") if h.strip())
    return hosts


@router.put("/apps/{app_id}/domain")
async def set_domain(app_id: str, body: DomainIn, user_id: str = Depends(current_user_id)):
    await owned_app(app_id, user_id)
    domain = clean_domain(body.domain)
    if not domain:
        await db.apps.update_one({"id": app_id}, {"$set": {"domain": None, "updatedAt": _now()}})
        _DOMAIN_CACHE.clear()
        return {"app": public_app(await db.apps.find_one({"id": app_id})), "target": None}
    if not _DOMAIN_RE.match(domain) or domain in own_hosts():
        raise HTTPException(status_code=400, detail="Use a domain you own, like shop.example.com.")
    taken = await db.apps.find_one({"domain": domain, "id": {"$ne": app_id}}, {"_id": 1})
    if taken:
        raise HTTPException(status_code=409, detail="That domain is already used by another app.")
    await db.apps.update_one({"id": app_id}, {"$set": {"domain": domain, "updatedAt": _now()}})
    _DOMAIN_CACHE.clear()
    return {"app": public_app(await db.apps.find_one({"id": app_id})),
            "target": urlparse(public_origin()).hostname}


async def site_for_host(host: str) -> Optional[dict]:
    """The published app answering on this custom domain, or None (cached for a minute)."""
    host = clean_domain(host)
    if not host or host in own_hosts():
        return None
    hit = _DOMAIN_CACHE.get(host)
    if hit and time.monotonic() - hit[0] < _DOMAIN_TTL:
        return hit[1]
    app = await db.apps.find_one({"domain": host, "published": {"$ne": None}})
    _DOMAIN_CACHE[host] = (time.monotonic(), app)
    return app


async def serve_domain(app: dict, path: str) -> Response:
    version = await db.app_commits.find_one({"appId": app["id"], "id": app["published"]["commitId"]})
    return _serve(await commit_files(version), path, bridge=False, cache="public, max-age=60", app_id=app["id"])
