"""Web research tools: search and page fetching.

Search uses Tavily when TAVILY_API_KEY is set, otherwise DuckDuckGo's HTML
endpoint (no key needed). Fetching guards against SSRF: only http(s), and every
hop of a redirect must resolve to a public address.
"""
import asyncio
import base64
import difflib
import ipaddress
import logging
import os
import re
import socket
from typing import List
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import httpx
import lxml.html

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; KrishAI-Agent/1.0)"
MAX_BYTES = 3 * 1024 * 1024
MAX_TEXT = 15_000
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class FetchError(Exception):
    pass


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("Only http and https URLs are allowed")
    host = parsed.hostname
    if not host:
        raise FetchError("URL has no host")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise FetchError(f"Could not resolve host {host}")
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise FetchError("Refusing to fetch a private or internal address")


async def _get(url: str) -> httpx.Response:
    """GET with manual redirect handling so each hop is checked."""
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await assert_public_url(url)
            async with client.stream("GET", url) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    continue
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                resp._content = b"".join(chunks)
                return resp
    raise FetchError("Too many redirects")


def html_to_text(html: str, base_url: str = "") -> dict:
    doc = lxml.html.fromstring(html)
    for bad in doc.xpath("//script|//style|//noscript|//svg|//iframe|//nav|//footer|//header|//form"):
        bad.drop_tree()
    title = (doc.findtext(".//title") or "").strip()
    main = doc.xpath("//main|//article")
    root = main[0] if main else doc
    lines = [ln.strip() for ln in root.text_content().splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    links = []
    for a in root.xpath(".//a[@href]")[:40]:
        label = " ".join(a.text_content().split())
        if label:
            links.append({"text": label[:80], "url": urljoin(base_url, a.get("href"))})
    return {"title": title, "text": text, "links": links}


async def fetch_page(url: str) -> dict:
    resp = await _get(url)
    ctype = resp.headers.get("content-type", "")
    body = resp.content.decode(resp.encoding or "utf-8", "replace")
    if "html" in ctype or body.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        page = html_to_text(body, str(resp.url))
    else:
        page = {"title": "", "text": body, "links": []}
    text = page["text"]
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + f"\n… [truncated {len(page['text']) - MAX_TEXT} chars]"
    return {"url": str(resp.url), "status": resp.status_code, "title": page["title"], "text": text, "links": page["links"][:20]}


def _ddg_real_url(href: str) -> str:
    # DuckDuckGo wraps results as //duckduckgo.com/l/?uddg=<encoded url>
    if "uddg=" in href:
        q = parse_qs(urlparse(href if "://" in href else "https:" + href).query)
        if q.get("uddg"):
            return unquote(q["uddg"][0])
    return href


def parse_ddg_html(html: str, limit: int) -> List[dict]:
    doc = lxml.html.fromstring(html)
    results = []
    for res in doc.xpath("//div[contains(@class,'result') and .//a[contains(@class,'result__a')]]"):
        a = res.xpath(".//a[contains(@class,'result__a')]")[0]
        snippet = res.xpath(".//*[contains(@class,'result__snippet')]")
        url = _ddg_real_url(a.get("href", ""))
        if not url.startswith("http") or "duckduckgo.com/y.js" in url:
            continue  # skip ads
        results.append({
            "title": " ".join(a.text_content().split()),
            "url": url,
            "snippet": " ".join(snippet[0].text_content().split()) if snippet else "",
        })
        if len(results) >= limit:
            break
    return results


def parse_ddg_lite(html: str, limit: int) -> List[dict]:
    doc = lxml.html.fromstring(html)
    results = []
    for a in doc.xpath("//a[contains(@class,'result-link')]"):
        url = _ddg_real_url(a.get("href", ""))
        if not url.startswith("http") or "duckduckgo.com/y.js" in url:
            continue
        row = a.getparent().getparent() if a.getparent() is not None else None
        snippet = ""
        if row is not None:
            nxt = row.getnext()
            cells = nxt.xpath(".//*[contains(@class,'result-snippet')]") if nxt is not None else []
            snippet = " ".join(cells[0].text_content().split()) if cells else ""
        results.append({"title": " ".join(a.text_content().split()), "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


# Search engines serve bot-looking clients a challenge page, so searches use a regular browser User-Agent.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0.0.0 Safari/537.36")


def _bing_real_url(href: str) -> str:
    # Bing sometimes wraps results as bing.com/ck/a?...&u=a1<base64 url>
    if "bing.com/ck/a" in href:
        u = parse_qs(urlparse(href).query).get("u", [""])[0]
        if u.startswith("a1"):
            try:
                raw = u[2:]
                return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
            except Exception:
                return href
    return href


def parse_bing_html(html: str, limit: int) -> List[dict]:
    doc = lxml.html.fromstring(html)
    results = []
    for li in doc.xpath("//li[contains(@class,'b_algo')]"):
        links = li.xpath(".//h2//a[@href]")
        if not links:
            continue
        url = _bing_real_url(links[0].get("href", ""))
        if not url.startswith("http"):
            continue
        snippet = li.xpath(".//*[contains(@class,'b_caption')]//p|.//p")
        results.append({"title": " ".join(links[0].text_content().split()), "url": url,
                        "snippet": " ".join(snippet[0].text_content().split()) if snippet else ""})
        if len(results) >= limit:
            break
    return results


async def _ddg(client: httpx.AsyncClient, query: str, limit: int) -> List[dict]:
    resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
    results = parse_ddg_html(resp.text, limit) if resp.status_code == 200 else []
    if not results:
        logger.warning("DuckDuckGo gave no results (HTTP %s)", resp.status_code)
    return results


async def _ddg_lite(client: httpx.AsyncClient, query: str, limit: int) -> List[dict]:
    resp = await client.post("https://lite.duckduckgo.com/lite/", data={"q": query})
    results = parse_ddg_lite(resp.text, limit) if resp.status_code == 200 else []
    if not results:
        logger.warning("DuckDuckGo lite gave no results (HTTP %s)", resp.status_code)
    return results


async def _bing(client: httpx.AsyncClient, query: str, limit: int) -> List[dict]:
    resp = await client.get("https://www.bing.com/search", params={"q": query, "setlang": "en"})
    results = parse_bing_html(resp.text, limit) if resp.status_code == 200 else []
    if not results:
        logger.warning("Bing gave no results (HTTP %s)", resp.status_code)
    return results


async def _wikipedia(client: httpx.AsyncClient, query: str, limit: int) -> List[dict]:
    resp = await client.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"})
    resp.raise_for_status()
    hits = resp.json().get("query", {}).get("search", [])
    return [{"title": h["title"], "url": "https://en.wikipedia.org/wiki/" + h["title"].replace(" ", "_"),
             "snippet": " ".join(lxml.html.fromstring(f"<p>{h.get('snippet') or ' '}</p>").text_content().split())}
            for h in hits]


async def search(query: str, limit: int = 6) -> List[dict]:
    """Web results from the first engine that answers: Tavily (with a key), DuckDuckGo, Bing, then Wikipedia."""
    limit = max(1, min(limit, 10))
    tavily_key = os.environ.get("TAVILY_API_KEY")
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0), follow_redirects=True,
                                 headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}) as client:
        if tavily_key:
            resp = await client.post("https://api.tavily.com/search", json={
                "api_key": tavily_key, "query": query, "max_results": limit, "search_depth": "basic",
            })
            resp.raise_for_status()
            return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")[:400]}
                    for r in resp.json().get("results", [])]
        last_error = None
        for engine in (_ddg, _ddg_lite, _bing, _wikipedia):
            try:
                results = await engine(client, query, limit)
            except Exception as exc:
                logger.warning("Search via %s failed: %s", engine.__name__, exc)
                last_error = exc
                continue
            if results:
                return results
        if last_error:
            raise last_error
        return []


# ------------------------------------------------------------ exchange rates
RATES_URL = "https://open.er-api.com/v6/latest/USD"  # free, no key
FALLBACK_RATES_URL = "https://api.frankfurter.app/latest?from=USD"
CURRENCY = re.compile(
    r"\b(dollar|dollars|usd|rupee|rupees|inr|euro|euros|eur|pound|pounds|gbp|yen|jpy|dirham|aed|riyal|sar|"
    r"yuan|cny|currency|exchange rate|forex|fx)\b",
    re.I,
)
COMMON_CODES = ["INR", "EUR", "GBP", "AED", "JPY", "CNY", "CAD", "AUD", "SGD", "SAR"]
_NAMES = {"rupee": "INR", "euro": "EUR", "pound": "GBP", "yen": "JPY", "dirham": "AED", "riyal": "SAR",
          "yuan": "CNY", "dollar": "USD"}
# The currency on the other side of "USD to X" / "X to USD", even when misspelled.
_PAIR = re.compile(r"\b(?:usd|dollars?)\s*(?:to|in|into|vs|->|=)\s*([a-z]{2,8})\b"
                   r"|\b([a-z]{2,8})\s*(?:to|in|into|vs|->|=)\s*(?:usd|dollars?)\b", re.I)


def resolve_currency(word: str, known) -> str:
    """The currency code a user meant: an exact code, a name like "rupee", or the closest code to a typo."""
    w = word.strip().upper()
    if w in known:
        return w
    for name, code in _NAMES.items():
        if w.lower().rstrip("s") == name:
            return code
    close = difflib.get_close_matches(w, COMMON_CODES, n=1, cutoff=0.5) or \
        difflib.get_close_matches(w, list(known), n=1, cutoff=0.6)
    return close[0] if close else ""


def pick_currencies(text: str, known) -> tuple:
    """(codes to show, notes about guessed typos) for a currency question."""
    wanted, notes = [], []
    for m in _PAIR.finditer(text):
        word = m.group(1) or m.group(2)
        code = resolve_currency(word, known)
        if code and code != "USD":
            wanted.append(code)
            if code != word.upper() and word.lower().rstrip("s") not in _NAMES:
                notes.append(f"'{word}' is not a currency code; it most likely means {code}.")
    wanted += [c for c in re.findall(r"\b[A-Z]{3}\b", text.upper()) if c in known and c != "USD"]
    wanted += [code for name, code in _NAMES.items() if name in text.lower() and code != "USD"]
    return list(dict.fromkeys(wanted + COMMON_CODES)), notes


async def _fetch_rates() -> dict:
    """USD rates from open.er-api.com, falling back to frankfurter.app (ECB rates). Both are free and keyless."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0), follow_redirects=True,
                                 headers={"User-Agent": USER_AGENT}) as client:
        try:
            resp = await client.get(RATES_URL)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rates"):
                return data
            logger.warning("open.er-api.com returned no rates: %s", str(data)[:200])
        except Exception as exc:
            logger.warning("open.er-api.com failed: %s", exc)
        resp = await client.get(FALLBACK_RATES_URL)
        resp.raise_for_status()
        data = resp.json()
        return {"rates": data.get("rates") or {}, "time_last_update_utc": f"{data.get('date', 'recently')} (ECB)"}


async def exchange_rates(text: str) -> str:
    """Live USD exchange rates relevant to the question, with notes on guessed typos."""
    data = await _fetch_rates()
    rates = data.get("rates") or {}
    codes, notes = pick_currencies(text, rates)
    lines = [f"1 USD = {rates[c]:,.4f} {c}" for c in codes if c in rates]
    if not lines:
        return ""
    updated = data.get("time_last_update_utc", "recently")
    out = f"Live exchange rates (updated {updated}):\n" + "\n".join(lines)
    if notes:
        out += "\n" + "\n".join(notes) + " Say which currency you assumed, then give its rate."
    return out
