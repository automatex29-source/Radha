"""Unit tests for the agent runtime, tool registry, sandbox and web helpers.

These run offline with a scripted fake model; no server or API keys needed.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import Tool, ToolContext, ToolOutput, ToolRegistry, run_agent  # noqa: E402
from agent import sandbox, web  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def scripted_llm(turns):
    """A fake stream_fn: each call replays the next scripted turn."""
    calls = []

    async def stream_fn(model, messages, tools):
        calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        turn = turns[len(calls) - 1]
        for chunk in turn.get("text", []):
            yield {"type": "text", "text": chunk}
        if turn.get("tool_calls"):
            yield {"type": "tool_calls", "calls": turn["tool_calls"]}

    stream_fn.calls = calls
    return stream_fn


def echo_registry():
    async def echo(ctx, args):
        return ToolOutput(content=f"echo:{args['msg']}", summary="echoed")

    async def boom(ctx, args):
        raise RuntimeError("kaboom")

    params = {"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]}
    return (ToolRegistry()
            .register(Tool("echo", "Echo", params, echo))
            .register(Tool("boom", "Fails", {"type": "object", "properties": {}}, boom))
            .register(Tool("hidden", "Unavailable", {"type": "object"}, echo, available=lambda: False)))


async def collect(gen):
    return [ev async for ev in gen]


class TestAgentRuntime:
    def test_plain_answer_without_tools(self):
        llm = scripted_llm([{"text": ["Hi", " there"]}])
        events = run(collect(run_agent(llm, echo_registry(), ToolContext(None, "u"), "m", [{"role": "user", "content": "hi"}])))
        assert [e["text"] for e in events] == ["Hi", " there"]
        assert len(llm.calls) == 1

    def test_tool_call_then_answer(self):
        llm = scripted_llm([
            {"text": ["Checking."], "tool_calls": [{"id": "c1", "name": "echo", "arguments": '{"msg": "ping"}'}]},
            {"text": ["Got ping."]},
        ])
        msgs = [{"role": "user", "content": "go"}]
        events = run(collect(run_agent(llm, echo_registry(), ToolContext(None, "u"), "m", msgs)))
        types = [e["type"] for e in events]
        assert types == ["text", "text", "tool_start", "tool_end", "text"]
        end = events[3]
        assert end["ok"] and end["output"] == "echo:ping" and end["summary"] == "echoed"
        # Second model call sees the assistant tool call and the tool result.
        second = llm.calls[1]["messages"]
        assert second[-2]["tool_calls"][0]["function"]["name"] == "echo"
        assert second[-1] == {"role": "tool", "tool_call_id": "c1", "content": "echo:ping"}

    def test_tool_errors_are_returned_to_model(self):
        llm = scripted_llm([
            {"tool_calls": [
                {"id": "a", "name": "boom", "arguments": "{}"},
                {"id": "b", "name": "echo", "arguments": "not json"},
                {"id": "c", "name": "hidden", "arguments": "{}"},
            ]},
            {"text": ["done"]},
        ])
        events = run(collect(run_agent(llm, echo_registry(), ToolContext(None, "u"), "m", [])))
        ends = [e for e in events if e["type"] == "tool_end"]
        assert [e["ok"] for e in ends] == [False, False, False]
        assert "kaboom" in ends[0]["output"]
        assert "invalid JSON" in ends[1]["output"]
        assert "unknown or unavailable" in ends[2]["output"]

    def test_unavailable_tools_not_offered(self):
        names = [s["function"]["name"] for s in echo_registry().schemas()]
        assert names == ["echo", "boom"]

    def test_step_limit_forces_final_answer(self):
        loop_call = {"tool_calls": [{"id": "x", "name": "echo", "arguments": '{"msg": "again"}'}]}
        from agent import runtime
        turns = [loop_call] * (runtime.MAX_STEPS - 1) + [{"text": ["final"]}]
        llm = scripted_llm(turns)
        events = run(collect(run_agent(llm, echo_registry(), ToolContext(None, "u"), "m", [])))
        assert events[-1] == {"type": "text", "text": "final"}
        assert llm.calls[-1]["tools"] == []  # last step withholds tools

    def test_use_tools_false_sends_no_tools(self):
        llm = scripted_llm([{"text": ["ok"]}])
        run(collect(run_agent(llm, echo_registry(), ToolContext(None, "u"), "m", [], use_tools=False)))
        assert llm.calls[0]["tools"] == []


class TestSandbox:
    def test_runs_code_and_captures_files(self):
        res = run(sandbox.run_python('print("hello")\nopen("out.csv", "w").write("a,b\\n1,2\\n")'))
        assert res.exit_code == 0 and res.stdout.strip() == "hello"
        assert [(a.name, a.data) for a in res.artifacts] == [("out.csv", b"a,b\n1,2\n")]

    def test_reports_errors(self):
        res = run(sandbox.run_python("raise ValueError('bad')"))
        assert res.exit_code != 0 and "ValueError: bad" in res.stderr

    def test_no_network_when_isolation_available(self):
        if not sandbox.network_isolation_available():
            pytest.skip("host does not allow network namespaces")
        code = ("import socket\ntry:\n    socket.create_connection(('1.1.1.1', 80), timeout=3)\n    print('OPEN')\n"
                "except OSError:\n    print('BLOCKED')")
        assert run(sandbox.run_python(code)).stdout.strip() == "BLOCKED"

    def test_memory_limit(self):
        res = run(sandbox.run_python("x = bytearray(4 * 1024 ** 3)"))
        assert res.exit_code != 0 and "MemoryError" in res.stderr

    def test_wall_timeout(self, monkeypatch):
        monkeypatch.setattr(sandbox, "WALL_SECONDS", 2)
        res = run(sandbox.run_python("import time\ntime.sleep(30)"))
        assert res.timed_out and res.exit_code is None


class TestWeb:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/", "http://localhost:8001/api/", "http://169.254.169.254/latest/meta-data",
        "http://10.1.2.3/", "http://192.168.0.1/", "http://[::1]/", "file:///etc/passwd", "ftp://example.com/",
    ])
    def test_blocks_internal_and_non_http(self, url):
        with pytest.raises(web.FetchError):
            run(web.assert_public_url(url))

    def test_parses_duckduckgo_results_and_skips_ads(self):
        html = """
        <div class="result results_links"><a class="result__a" href="//duckduckgo.com/y.js?ad=1">Ad</a></div>
        <div class="result results_links web-result">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Flibrary%2Fasyncio.html&rut=x">asyncio docs</a>
          <a class="result__snippet">Asynchronous I/O  library.</a>
        </div>
        <div class="result"><a class="result__a" href="https://example.org/b">Second</a></div>
        """
        results = web.parse_ddg_html(html, 5)
        assert results == [
            {"title": "asyncio docs", "url": "https://docs.python.org/3/library/asyncio.html", "snippet": "Asynchronous I/O library."},
            {"title": "Second", "url": "https://example.org/b", "snippet": ""},
        ]

    def test_html_to_text_strips_chrome(self):
        page = web.html_to_text(
            "<html><head><title>T</title><script>evil()</script></head><body><nav>menu</nav>"
            "<main><h1>Head</h1><p>Body text</p><a href='/x'>Link</a></main></body></html>",
            "https://site.test/page")
        assert page["title"] == "T"
        assert "evil" not in page["text"] and "menu" not in page["text"]
        assert "Head" in page["text"] and "Body text" in page["text"]
        assert page["links"] == [{"text": "Link", "url": "https://site.test/x"}]
