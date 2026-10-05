"""Deep research: plan several searches, read the best pages, and write a cited report.

Everything runs inside one tool call so the chat model only sees a short summary:
  1. a small model call turns the question into a few focused search queries,
  2. the queries are searched and the top pages fetched in parallel,
  3. the passages most relevant to the question are picked from each page (no model call),
  4. one model call writes the report with numbered citations, saved as a PDF or Word file.

The source pack is sized to fit Groq's free per-minute token budget (see llm.lean).
"""
import asyncio
import json
import logging
import re
from typing import Awaitable, Callable, List, Optional

from . import llm, web

logger = logging.getLogger("radha.research")

MAX_QUERIES = 4
RESULTS_PER_QUERY = 5
FETCH_TIMEOUT = 25
_STOP = set("a an and are as at be by can do does for from how i in is it me my of on or should the this to "
            "vs what when where which who why will with you your best top compare comparison".split())

Ask = Callable[[str, str, int], Awaitable[str]]  # (model, prompt, max_tokens) -> text


def limits(model: str) -> dict:
    """How many sources, how much of each, and how long the report may be for this model."""
    if llm.lean(model):
        return {"sources": 6, "chars": 1500, "report_tokens": 2600}
    return {"sources": 10, "chars": 3500, "report_tokens": 6000}


def keywords(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9ऀ-ॿ]{3,}", text.lower()) if w not in _STOP]


def best_passages(text: str, terms: List[str], max_chars: int) -> str:
    """The paragraphs that mention the question's words most, kept in page order."""
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if len(p.strip()) > 60]
    if not paras:
        return text[:max_chars]
    terms = set(terms)
    scored = []
    for i, p in enumerate(paras):
        words = keywords(p)
        hits = sum(1 for w in words if w in terms)
        # Numbers (prices, dates, stats) are what reports need most.
        bonus = 0.5 * min(3, len(re.findall(r"\d", p)) // 3)
        scored.append((hits + bonus, i))
    keep, used = [], 0
    for score, i in sorted(scored, key=lambda s: (-s[0], s[1])):
        if score <= 0 and keep:
            break
        p = paras[i][:max_chars]
        if used + len(p) > max_chars and keep:
            continue
        keep.append(i)
        used += len(p)
        if used >= max_chars:
            break
    return "\n".join(paras[i] for i in sorted(keep))[:max_chars]


def parse_queries(text: str, question: str) -> List[str]:
    m = re.search(r"\[.*\]", text or "", re.S)
    queries = []
    if m:
        try:
            queries = [q for q in json.loads(m.group(0)) if isinstance(q, str) and q.strip()]
        except (ValueError, TypeError):
            queries = []
    if not queries:
        queries = [line.strip(" -*0123456789.\"") for line in (text or "").splitlines() if len(line.strip()) > 5]
    out = [question.strip()[:200]]
    for q in queries:
        q = q.strip()[:200]
        if q and q.lower() not in {o.lower() for o in out}:
            out.append(q)
    return out[:MAX_QUERIES]


async def default_ask(model: str, prompt: str, max_tokens: int) -> str:
    import litellm

    kwargs = {"model": llm.litellm_model(model), "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens, "timeout": 120}
    gw = llm.gateway()
    if gw:
        kwargs.update(model=f"openai/{model}", **gw)
    if model.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = "low"
    for attempt in range(4):
        try:
            resp = await litellm.acompletion(**kwargs)
            return resp.choices[0].message.content or ""
        except litellm.RateLimitError as exc:
            if attempt == 3 or "per day" in str(exc).lower():
                raise
            await asyncio.sleep(llm._retry_after(exc))
    return ""


def planner_model(model: str) -> str:
    # On Groq, plan with the small model so the writer keeps the big model's per-minute budget.
    return "openai/gpt-oss-20b" if llm.lean(model) and model.startswith("openai/gpt-oss") else model


async def plan(question: str, focus: str, model: str, ask: Ask) -> List[str]:
    prompt = (f"Break this research question into {MAX_QUERIES - 1} short, different web search queries that "
              "together cover it (facts, prices, comparisons, recent news, pros and cons). Reply with only a JSON "
              f"array of strings.\n\nQuestion: {question}" + (f"\nFocus: {focus}" if focus else ""))
    try:
        return parse_queries(await ask(planner_model(model), prompt, 400), question)
    except Exception as exc:
        logger.warning("research planning failed, searching the question only: %s", exc)
        return [question.strip()[:200]]


async def gather_sources(queries: List[str], terms: List[str], max_sources: int, max_chars: int,
                         search=web.search, fetch=web.fetch_page, search_timeout: Optional[float] = None,
                         fetch_timeout: float = FETCH_TIMEOUT) -> List[dict]:
    def one(q):
        return asyncio.wait_for(search(q, RESULTS_PER_QUERY), search_timeout) if search_timeout else search(q, RESULTS_PER_QUERY)
    results = await asyncio.gather(*(one(q) for q in queries), return_exceptions=True)
    # Round-robin across queries so every angle gets a source.
    lists = [r for r in results if isinstance(r, list)]
    picked, seen = [], set()
    for rank in range(RESULTS_PER_QUERY):
        for lst in lists:
            if rank < len(lst):
                r = lst[rank]
                url = (r.get("url") or "").split("#")[0]
                if url.startswith("http") and url not in seen:
                    seen.add(url)
                    picked.append(r)
    picked = picked[:max_sources + 3]  # a few spares for pages that fail to load

    async def load(r: dict) -> Optional[dict]:
        try:
            page = await asyncio.wait_for(fetch(r["url"]), fetch_timeout)
            text = best_passages(page.get("text") or "", terms, max_chars)
        except Exception as exc:
            logger.info("research: could not read %s: %s", r.get("url"), exc)
            text = ""
        if len(text) < 200:
            text = r.get("snippet") or ""
        if not text.strip():
            return None
        return {"title": (r.get("title") or r["url"])[:150], "url": r["url"], "text": text}

    loaded = await asyncio.gather(*(load(r) for r in picked))
    return [s for s in loaded if s][:max_sources]


def report_prompt(question: str, focus: str, sources: List[dict]) -> str:
    pack = "\n\n".join(f"[{i}] {s['title']} ({s['url']})\n{s['text']}" for i, s in enumerate(sources, 1))
    return (
        "You are a research analyst. Write a clear research report in Markdown answering the question, using ONLY "
        "the sources below. Cite facts with [n] after the sentence. Start with '# ' and a title, then these "
        "sections: '## Summary' (3-5 sentences with the direct answer), '## Key findings' (bullets), a comparison "
        "table when options, tools or prices are compared, '## Details', '## Recommendation', and '## Sources' "
        "(numbered list of title and URL). Say plainly where sources disagree or data is missing. Write in the "
        "same language as the question.\n\n"
        f"Question: {question}\n" + (f"Focus: {focus}\n" if focus else "") + f"\nSources:\n{pack}"
    )


def sources_section(sources: List[dict]) -> str:
    return "## Sources\n\n" + "\n".join(f"{i}. [{s['title']}]({s['url']})" for i, s in enumerate(sources, 1))


def summary_of(report: str, max_chars: int = 1500) -> str:
    m = re.search(r"##\s*Summary\s*\n(.*?)(?=\n##\s|\Z)", report, re.S | re.I)
    text = (m.group(1) if m else report).strip()
    return text[:max_chars]


async def run(question: str, model: str, focus: str = "", ask: Optional[Ask] = None,
              search=web.search, fetch=web.fetch_page) -> dict:
    """Returns {"title", "markdown", "summary", "sources", "queries"}."""
    ask = ask or default_ask
    lim = limits(model)
    queries = await plan(question, focus, model, ask)
    terms = keywords(question + " " + focus + " " + " ".join(queries))
    sources = await gather_sources(queries, terms, lim["sources"], lim["chars"], search, fetch)
    if not sources:
        raise RuntimeError("No web pages could be read for this question; try rephrasing it.")
    report = (await ask(model, report_prompt(question, focus, sources), lim["report_tokens"])).strip()
    if not report:
        raise RuntimeError("The model returned an empty report.")
    if not re.search(r"^##\s*Sources", report, re.M | re.I):
        report += "\n\n" + sources_section(sources)
    m = re.match(r"#\s+(.+)", report)
    title = m.group(1).strip() if m else question.strip()[:80]
    return {"title": title, "markdown": report, "summary": summary_of(report), "sources": sources,
            "queries": queries}
