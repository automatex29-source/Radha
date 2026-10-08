"""Local embedding model (fastembed / ONNX) + cosine retrieval.

Runs fully on-box with no external API key. Vectors are stored in MongoDB and
scored in Python — appropriate for the per-project chunk volumes in V1 and for
a local MongoDB without Atlas Vector Search.
"""
import asyncio
import logging
import os
import re
import time
from functools import lru_cache
from typing import List

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384


SMALL_SERVER_MB = 1024  # below this the model (~400MB while embedding) would get the server killed mid-upload
BATCH_SIZE = 16  # fastembed's default of 256 chunks at once costs hundreds of MB more at its peak


def _memory_limit_mb():
    """The container's memory limit in MB, or None when there isn't one we can read."""
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            raw = open(path).read().strip()
        except OSError:
            continue
        if raw.isdigit() and int(raw) < 1 << 60:
            return int(raw) // (1024 * 1024)
    return None


def _enabled() -> bool:
    """EMBEDDINGS=1/0 decides; otherwise on, except on small servers (e.g. Render's free 512MB plan).

    Files are still read and found by keyword search when it is off.
    """
    setting = os.environ.get("EMBEDDINGS", "").strip().lower()
    if setting in ("0", "false", "off", "no"):
        return False
    if setting in ("1", "true", "on", "yes"):
        return True
    limit = _memory_limit_mb()
    return limit is None or limit >= SMALL_SERVER_MB


ENABLED = _enabled()

_RETRY_AFTER = 600  # seconds to wait before trying to load a model that failed to load
_failed_at = 0.0


def _model():
    global _failed_at
    if _failed_at and time.monotonic() - _failed_at < _RETRY_AFTER:
        raise RuntimeError("Embedding model unavailable")
    try:
        return _load()
    except Exception:
        _failed_at = time.monotonic()
        raise


@lru_cache(maxsize=1)
def _load():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=MODEL_NAME)


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    if not ENABLED:
        raise RuntimeError("Embedding model is off on this server")
    vectors = list(_model().embed(texts, batch_size=BATCH_SIZE))
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]


def cosine_rank(query_vec: List[float], candidates: List[dict], top_k: int = 5, threshold: float = 0.3):
    """candidates: list of {..., 'embedding': [...]}. Returns top_k with 'score' added."""
    if not candidates:
        return []
    q = np.array(query_vec, dtype=np.float32)
    q_norm = np.linalg.norm(q) or 1.0
    scored = []
    for c in candidates:
        if not c.get("embedding"):
            continue
        v = np.array(c["embedding"], dtype=np.float32)
        denom = (np.linalg.norm(v) or 1.0) * q_norm
        score = float(np.dot(q, v) / denom)
        if score >= threshold:
            scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, c in scored[:top_k]:
        item = {k: v for k, v in c.items() if k != "embedding"}
        item["score"] = round(score, 4)
        out.append(item)
    return out


_WORD = re.compile(r"\w{3,}", re.UNICODE)


def keyword_rank(query: str, candidates: List[dict], top_k: int = 5):
    """Fallback ranking by shared words, for when the embedding model is unavailable."""
    words = {w.lower() for w in _WORD.findall(query)}
    scored = []
    for c in candidates:
        text = c["text"].lower()
        hits = sum(1 for w in words if w in text)
        if hits:
            scored.append((hits / max(1, len(words)), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{**{k: v for k, v in c.items() if k != "embedding"}, "score": round(s, 4)} for s, c in scored[:top_k]]


async def rank(query: str, candidates: List[dict], top_k: int = 5, threshold: float = 0.2):
    """Chunks most related to the query: by meaning when possible, else by shared words."""
    try:
        if not ENABLED:
            ranked = []
        else:
            qvec = await asyncio.to_thread(embed_query, query)
            ranked = cosine_rank(qvec, candidates, top_k=top_k, threshold=threshold)
    except Exception:
        logging.getLogger("radha.embeddings").exception("Embedding the question failed; using keyword search")
        ranked = []
    if len(ranked) < top_k:
        seen = {c["id"] for c in ranked}
        extra = [c for c in candidates if c["id"] not in seen and not c.get("embedding")]
        ranked += keyword_rank(query, extra, top_k - len(ranked))
    return ranked
