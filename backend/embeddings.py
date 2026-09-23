"""Local embedding model (fastembed / ONNX) + cosine retrieval.

Runs fully on-box with no external API key. Vectors are stored in MongoDB and
scored in Python — appropriate for the per-project chunk volumes in V1 and for
a local MongoDB without Atlas Vector Search.
"""
from functools import lru_cache
from typing import List

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=MODEL_NAME)


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    vectors = list(_model().embed(texts))
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
