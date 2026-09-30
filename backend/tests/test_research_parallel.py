"""Deep research tool and parallel tool calls; offline, with fake search, pages and model."""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import Tool, ToolContext, ToolOutput, ToolRegistry, run_agent, research  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def test_parse_queries_keeps_question_first_and_dedupes():
    qs = research.parse_queries('Sure: ["cheap hosting india", "Render pricing", "render pricing", "x"]',
                                "Best hosting for a small app?")
    assert qs[0] == "Best hosting for a small app?"
    assert qs[1:] == ["cheap hosting india", "Render pricing", "x"][:research.MAX_QUERIES - 1]
    assert research.parse_queries("", "q only") == ["q only"]


def test_best_passages_prefers_relevant_paragraphs():
    text = "\n".join(["Cookie banner and navigation links for the whole website here."] * 5
                     + ["Render free tier pricing is $0 per month for 750 instance hours in 2026."])
    out = research.best_passages(text, research.keywords("render pricing free tier"), 200)
    assert "750 instance hours" in out


def test_run_builds_cited_report_from_sources():
    searched, prompts = [], []

    async def search(q, n):
        searched.append(q)
        return [{"title": f"Page {q}", "url": f"https://example.com/{abs(hash(q))}", "snippet": "snip"}]

    async def fetch(url):
        return {"text": "Groq offers a free tier with rate limits of 8000 tokens per minute for models.\n" * 3}

    async def ask(model, prompt, max_tokens):
        prompts.append((model, prompt, max_tokens))
        if len(prompts) == 1:
            return '["groq free tier limits", "groq pricing 2026"]'
        return "# Groq free tier\n\n## Summary\nGroq is free with limits [1].\n\n## Key findings\n- 8000 TPM [1]"

    result = run(research.run("Is Groq free?", "openai/gpt-oss-120b", ask=ask, search=search, fetch=fetch))
    assert searched[0] == "Is Groq free?" and len(searched) == 3
    assert prompts[0][0] == "openai/gpt-oss-20b"  # planning uses the small model on Groq
    assert "[1]" in prompts[1][1] and "8000 tokens" in prompts[1][1]
    assert result["title"] == "Groq free tier"
    assert result["summary"].startswith("Groq is free")
    assert "## Sources" in result["markdown"] and "https://example.com/" in result["markdown"]


def test_lean_source_pack_fits_groq_budget():
    lim = research.limits("openai/gpt-oss-120b")
    sources = [{"title": "t" * 150, "url": "https://example.com/" + "p" * 80, "text": "x" * lim["chars"]}
               for _ in range(lim["sources"])]
    prompt_tokens = len(research.report_prompt("q" * 300, "f" * 100, sources)) / 3
    assert prompt_tokens + lim["report_tokens"] < 7700


def test_tool_calls_in_one_step_run_in_parallel():
    async def slow(ctx, args):
        await asyncio.sleep(0.3)
        return ToolOutput(content=f"done {args['n']}")

    reg = ToolRegistry().register(Tool(name="slow", description="", parameters={}, handler=slow))
    turns = [{"tool_calls": [{"id": f"c{i}", "name": "slow", "arguments": json.dumps({"n": i})} for i in range(3)]},
             {"text": ["ok"]}]
    seen = []

    async def llm(model, messages, tools):
        seen.append(messages)
        turn = turns[len(seen) - 1]
        for t in turn.get("text", []):
            yield {"type": "text", "text": t}
        if turn.get("tool_calls"):
            yield {"type": "tool_calls", "calls": turn["tool_calls"]}

    async def go():
        return [e async for e in run_agent(llm, reg, ToolContext(None, "u"), "m", [])]

    t0 = time.monotonic()
    events = run(go())
    assert time.monotonic() - t0 < 0.8
    assert [e["type"] for e in events][:3] == ["tool_start"] * 3
    tool_msgs = [m for m in seen[1] if m["role"] == "tool"]
    assert [m["content"] for m in tool_msgs] == ["done 0", "done 1", "done 2"]


def test_browser_calls_stay_in_order():
    order = []

    async def browser(ctx, args):
        order.append(("start", args["n"]))
        await asyncio.sleep(0.05 if args["n"] == 0 else 0)
        order.append(("end", args["n"]))
        return ToolOutput(content="ok")

    reg = ToolRegistry().register(Tool(name="browser", description="", parameters={}, handler=browser))
    turns = [{"tool_calls": [{"id": f"c{i}", "name": "browser", "arguments": json.dumps({"n": i})} for i in range(2)]},
             {"text": ["ok"]}]
    count = []

    async def llm(model, messages, tools):
        count.append(1)
        turn = turns[len(count) - 1]
        for t in turn.get("text", []):
            yield {"type": "text", "text": t}
        if turn.get("tool_calls"):
            yield {"type": "tool_calls", "calls": turn["tool_calls"]}

    async def go():
        return [e async for e in run_agent(llm, reg, ToolContext(None, "u"), "m", [])]

    run(go())
    assert order == [("start", 0), ("end", 0), ("start", 1), ("end", 1)]
