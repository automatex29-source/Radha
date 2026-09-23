"""Browser automation for the agent: a real headless Chromium per conversation.

The model drives it with simple actions (open, click, type, press, scroll,
back, read, wait). After each action it gets the page title/URL, visible text
and a numbered list of interactive elements to target by `ref`, and the user
sees a screenshot. Every request the page makes goes through the same SSRF
guard as fetch_url, so the browser can't reach internal addresses.

Needs `pip install playwright` and `playwright install chromium` on the server.
Disable with BROWSER_TOOL=0.
"""
import asyncio
import importlib.util
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urlparse

from . import web

IDLE_SECONDS = 600
MAX_SESSIONS = 12
NAV_TIMEOUT_MS = 30_000
ACTION_TIMEOUT_MS = 8_000
MAX_TEXT = 6_000
MAX_ELEMENTS = 80
VIEWPORT = {"width": 1280, "height": 800}

_SNAPSHOT_JS = """
(maxElements) => {
  document.querySelectorAll('[data-radha-ref]').forEach(e => e.removeAttribute('data-radha-ref'));
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, summary, [role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [contenteditable=true]';
  const out = [];
  let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || style.visibility === 'hidden' || style.display === 'none') continue;
    if (r.bottom < 0 || r.top > innerHeight * 3) continue;
    n += 1;
    el.setAttribute('data-radha-ref', String(n));
    const tag = el.tagName.toLowerCase();
    const kind = el.getAttribute('role') || (tag === 'input' ? `input[${el.type}]` : tag === 'a' ? 'link' : tag);
    const label = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || el.name || el.title || '')
      .replace(/\\s+/g, ' ').trim().slice(0, 80);
    const href = tag === 'a' ? el.getAttribute('href') : null;
    out.push({ ref: n, kind, label, href: href && href.length < 120 ? href : null,
               inView: r.top < innerHeight && r.bottom > 0 });
    if (out.length >= maxElements) break;
  }
  return { title: document.title, url: location.href,
           text: (document.body ? document.body.innerText : '').replace(/\\n{3,}/g, '\\n\\n'),
           elements: out, scrollY: scrollY, scrollMax: document.documentElement.scrollHeight - innerHeight };
}
"""


class BrowserError(Exception):
    pass


def available() -> bool:
    return os.environ.get("BROWSER_TOOL", "1") != "0" and importlib.util.find_spec("playwright") is not None


@dataclass
class _Session:
    context: object
    page: object
    last_used: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class BrowserManager:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._sessions: Dict[str, _Session] = {}
        self._launch_lock = asyncio.Lock()

    async def _ensure_browser(self):
        async with self._launch_lock:
            if self._browser and self._browser.is_connected():
                return self._browser
            try:
                from playwright.async_api import async_playwright

                self._pw = self._pw or await async_playwright().start()
                self._browser = await self._pw.chromium.launch(
                    headless=True, executable_path=os.environ.get("BROWSER_EXECUTABLE_PATH") or None)
            except Exception as exc:
                raise BrowserError(f"Could not start the browser ({exc}). Run `playwright install chromium` on the server.")
            return self._browser

    async def _guard(self, route, allowed: Dict[str, bool]):
        url = route.request.url
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return await route.continue_() if parsed.scheme in ("data", "blob") else await route.abort("blockedbyclient")
        host = parsed.hostname or ""
        if host not in allowed:
            try:
                await web.assert_public_url(url)
                allowed[host] = True
            except web.FetchError:
                allowed[host] = False
        if allowed[host]:
            await route.continue_()
        else:
            await route.abort("blockedbyclient")

    async def _expire(self):
        now = time.monotonic()
        stale = [k for k, s in self._sessions.items() if now - s.last_used > IDLE_SECONDS]
        if len(self._sessions) - len(stale) >= MAX_SESSIONS:
            by_age = sorted(self._sessions, key=lambda k: self._sessions[k].last_used)
            stale += by_age[: len(self._sessions) - MAX_SESSIONS + 1]
        for key in set(stale):
            await self.close(key)

    async def session(self, key: str) -> _Session:
        await self._expire()
        sess = self._sessions.get(key)
        if sess:
            sess.last_used = time.monotonic()
            return sess
        browser = await self._ensure_browser()
        context = await browser.new_context(viewport=VIEWPORT, accept_downloads=False, locale="en-US",
                                            user_agent=web.USER_AGENT.replace("compatible; ", "X11; Linux x86_64; "))
        allowed: Dict[str, bool] = {}
        await context.route("**/*", lambda route: self._guard(route, allowed))
        page = await context.new_page()
        page.set_default_timeout(ACTION_TIMEOUT_MS)
        sess = _Session(context=context, page=page)
        self._sessions[key] = sess
        return sess

    async def close(self, key: str):
        sess = self._sessions.pop(key, None)
        if sess:
            try:
                await sess.context.close()
            except Exception:
                pass

    async def shutdown(self):
        for key in list(self._sessions):
            await self.close(key)
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = self._pw = None

    async def act(self, key: str, action: str, args: dict) -> dict:
        sess = await self.session(key)
        async with sess.lock:
            page = sess.page
            if action == "open":
                url = (args.get("url") or "").strip()
                if not url:
                    raise BrowserError("'url' is required for open")
                if "://" not in url:
                    url = "https://" + url
                await web.assert_public_url(url)
                await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            elif action in ("click", "type"):
                target = self._locator(page, args)
                if action == "click":
                    await target.click()
                else:
                    await target.fill(str(args.get("text") or ""))
                    if args.get("submit"):
                        await target.press("Enter")
            elif action == "press":
                await page.keyboard.press(str(args.get("key") or "Enter"))
            elif action == "scroll":
                delta = VIEWPORT["height"] * 0.8 * (-1 if args.get("direction") == "up" else 1)
                await page.mouse.wheel(0, delta)
            elif action == "back":
                await page.go_back(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            elif action == "wait":
                await page.wait_for_timeout(min(float(args.get("seconds") or 2), 10) * 1000)
            elif action not in ("read", "screenshot"):
                raise BrowserError(f"Unknown action '{action}'")
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            snap = await page.evaluate(_SNAPSHOT_JS, MAX_ELEMENTS)
            shot = await page.screenshot(type="jpeg", quality=60)
            snap["screenshot"] = shot
            snap["full_text"] = action == "read"
            return snap

    @staticmethod
    def _locator(page, args: dict):
        if args.get("ref") is not None:
            return page.locator(f'[data-radha-ref="{int(args["ref"])}"]').first
        if args.get("selector"):
            return page.locator(str(args["selector"])).first
        if args.get("text"):
            return page.get_by_text(str(args["text"]), exact=False).first
        raise BrowserError("Give a 'ref' from the element list (or a 'selector')")


def describe(snap: dict) -> str:
    limit = 15_000 if snap.get("full_text") else MAX_TEXT
    text = snap.get("text") or ""
    if len(text) > limit:
        text = text[:limit] + f"\n… [{len(snap['text']) - limit} more chars — use action 'read' or 'scroll']"
    lines = []
    for el in snap.get("elements", []):
        extra = f" → {el['href']}" if el.get("href") else ""
        flag = "" if el.get("inView") else " (below)"
        lines.append(f"[{el['ref']}] {el['kind']} \"{el['label']}\"{extra}{flag}")
    scroll = f"Scroll: {int(snap.get('scrollY', 0))}/{max(int(snap.get('scrollMax', 0)), 0)}px"
    return (f"URL: {snap['url']}\nTitle: {snap['title']}\n{scroll}\n\nInteractive elements (use ref):\n"
            + ("\n".join(lines) or "(none)") + f"\n\nVisible text:\n{text}")


manager = BrowserManager()
