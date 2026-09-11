"""
Embedding provider abstraction: embedding_service.embed(text) -> list[float]

Ships with a lightweight local hashing-based embedder so RAG works out of
the box without an external API key. Swap EMBEDDING_PROVIDER=openai (or any
other provider you wire in) once you have a key, without touching
rag_service.py.
"""
import hashlib
import math
from flask import current_app

LOCAL_DIM = 256


def _local_embed(text: str):
    """Deterministic bag-of-hashed-tokens embedding. Good enough for small
    knowledge bases; replace with a real embedding API for production scale."""
    vec = [0.0] * LOCAL_DIM
    tokens = text.lower().split()
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % LOCAL_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str):
    provider = current_app.config.get("EMBEDDING_PROVIDER", "local")
    if provider == "local":
        return _local_embed(text)
    # Placeholder for future providers (OpenAI, Cohere, etc.) - implement and
    # branch here without changing any caller.
    return _local_embed(text)


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
