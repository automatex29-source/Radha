"""A coding question that runs code keeps its question all the way to the answer. Offline, end to end.

The bug (Krish Basic, Nov 2026): "Write Python for Dijkstra ... and RUN it" ran the code, then answered
"How can I assist you today?". On the free model's small token budget the request after the code run was too
long, and trimming dropped the oldest messages first: the question itself, then the tool call, leaving a lone
tool result that harmony_safe removed. The model saw only the system prompt.

This test sends that exact prompt through the real chat endpoint (/api/conversations/{id}/stream) with Krish Basic
on Groq, the real system prompt, the real trimming and the real Python sandbox. Only the model is scripted, and it
behaves like the real one: without the question it greets; with it, it runs the code (first with a wrong test, as
the real model did, then fixed) and answers with the code, the real run output and an explanation.
"""
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROMPT = ("Write Python for Dijkstra shortest path and RUN it on this graph (undirected): A-B 4, A-C 2, C-B 1, "
          "B-D 5, C-D 8, D-E 3, B-E 10. Print the shortest path from A to E and its cost, and add 3 assert tests.")

CODE = '''import heapq

def dijkstra(graph, start):
    # graph: dict node -> list of (neighbor, weight)
    dist = {node: float("inf") for node in graph}
    prev = {node: None for node in graph}
    dist[start] = 0
    pq = [(0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if d != dist[u]:
            continue
        for v, w in graph[u]:
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev

def shortest_path(prev, start, end):
    path, cur = [], end
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path if path and path[0] == start else []

edges = [("A", "B", 4), ("A", "C", 2), ("C", "B", 1), ("B", "D", 5), ("C", "D", 8), ("D", "E", 3), ("B", "E", 10)]
graph = {}
for u, v, w in edges:
    graph.setdefault(u, []).append((v, w))
    graph.setdefault(v, []).append((u, w))

dist, prev = dijkstra(graph, "A")
path = shortest_path(prev, "A", "E")
print("Shortest path from A to E:", " -> ".join(path))
print("Cost:", dist["E"])

assert dist["C"] == 2
assert dist["D"] == DIST_D, f"Dist A->D expected DIST_D, got {dist['D']}"
assert shortest_path(prev, "A", "D") == ["A", "C", "B", "D"]
print("All 3 tests passed")
'''
# The real model's first test was wrong (it expected 7; A-C-B-D is 2 + 1 + 5 = 8), so the first run fails.
WRONG = CODE.replace("DIST_D", "7")
FIXED = CODE.replace("DIST_D", "8")
GREETING = "How can I assist you today?"


def _chunk(content=None, tool_calls=None, finish=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=None)


class _Stream:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        return self.chunks.pop(0)


def _call(code, n):
    fn = SimpleNamespace(name="run_python", arguments=json.dumps({"code": code}))
    return _Stream([_chunk(tool_calls=[SimpleNamespace(index=0, id=f"call_{n}", function=fn)], finish="tool_calls")])


def _text(text):
    return _Stream([_chunk(content=text, finish="stop")])


CHAT_CALLS = []


async def _model(**kw):
    """A stand-in for the model. Side jobs (titles, follow-up ideas) get a short reply; the chat itself is
    answered from what this request actually contains, like the real model."""
    messages = kw["messages"]
    tools = [t["function"]["name"] for t in kw.get("tools") or []]
    system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
    if "run_python" not in tools and not any(m.get("role") == "tool" for m in messages):
        return _text("Dijkstra in Python")  # a title or another small helper job
    CHAT_CALLS.append(kw)
    asked = any(m.get("role") == "user" and PROMPT in str(m.get("content")) for m in messages)
    if not asked:
        return _text(GREETING)  # what the real model said when the question had been trimmed away
    runs = [m for m in messages if m.get("role") == "tool"]
    if not runs:
        return _call(WRONG, 1)
    if "AssertionError" in runs[-1]["content"] and len(runs) == 1:
        return _call(FIXED, 2)
    out = runs[-1]["content"]
    assert "stdout:" in out and len(system) > 0
    stdout = out.split("stdout:\n", 1)[1].split("\n\nstderr:", 1)[0].strip()
    return _text(f"Here is the code:\n\n```python\n{FIXED}```\n\nOutput of the run:\n\n```\n{stdout}\n```\n\n"
                 "The shortest path is A -> C -> B -> D -> E with cost 11 (2 + 1 + 5 + 3). My first test expected "
                 "A to D to cost 7, but A-C-B-D is 2 + 1 + 5 = 8, so I fixed the test and ran it again.")


@pytest.fixture(scope="module")
def client():
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
    for key in ("GEMINI_API_KEY", "CEREBRAS_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                "LLM_GATEWAY_URL"):
        os.environ.pop(key, None)
    import motor.motor_asyncio
    import litellm
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    original = litellm.acompletion
    litellm.acompletion = _model
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    try:
        with TestClient(server.app) as c:
            token = c.post("/api/auth/register", json={"name": "Asha", "email": "asha-dijkstra@test.com",
                                                       "password": "secret1"}).json()["token"]
            c.headers["Authorization"] = f"Bearer {token}"
            yield c
    finally:
        litellm.acompletion = original


def test_dijkstra_prompt_runs_code_and_answers_the_question(client):
    CHAT_CALLS.clear()
    cid = client.post("/api/conversations", json={}).json()["id"]
    body = client.post(f"/api/conversations/{cid}/stream",
                       json={"content": PROMPT, "agent": True, "model": "krish-auto"}).text
    assert "event: error" not in body

    # Every request the chat made, before and after each code run, still carried the question.
    assert len(CHAT_CALLS) == 3, [c["model"] for c in CHAT_CALLS]
    for kw in CHAT_CALLS:
        assert any(m.get("role") == "user" and PROMPT in str(m.get("content")) for m in kw["messages"])
        assert kw["model"].startswith("groq/")  # Krish Basic on the free model, with its small budget

    answer = client.get(f"/api/conversations/{cid}").json()["messages"][-1]
    text = answer["content"]
    assert GREETING not in text
    assert "```python" in text and "def dijkstra" in text  # the code
    assert "Shortest path from A to E: A -> C -> B -> D -> E" in text and "Cost: 11" in text  # the real run output
    assert "All 3 tests passed" in text
    assert "fixed the test" in text  # and an explanation
