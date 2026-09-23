"""Web research tools: search and page fetching.

Search uses Tavily when TAVILY_API_KEY is set, otherwise DuckDuckGo's HTML
endpoint (no key needed). Fetching guards against SSRF: only http(s), and every
hop of a redirect must resolve to a public address.
"""
import asyncio
import ipaddress
import os
import socket
from typing import List
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import httpx
import lxml.html

USER_AGENT = "Mozilla/5.0 (compatible; RADHA-Agent/1.0; +https://automatex.ai)"
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


async def search(query: str, limit: int = 6) -> List[dict]:
    limit = max(1, min(limit, 10))
    tavily_key = os.environ.get("TAVILY_API_KEY")
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        if tavily_key:
            resp = await client.post("https://api.tavily.com/search", json={
                "api_key": tavily_key, "query": query, "max_results": limit, "search_depth": "basic",
            })
            resp.raise_for_status()
            return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")[:400]}
                    for r in resp.json().get("results", [])]
        resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
        resp.raise_for_status()
        return parse_ddg_html(resp.text, limit)
