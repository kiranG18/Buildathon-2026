"""Embeddings. A hosted API when EMBEDDINGS_API_KEY is set, else a deterministic local embedder.

The local embedder hashes unigrams and bigrams into 1536 signed buckets and normalises the vector.
It needs no network, so tests and `make reset` run offline. Retrieval also fuses full-text search,
so recall holds when the embedding call fails.
"""

import hashlib
import math
import re

import httpx

from backend.core.config import get_settings
from backend.core.logging import log

DIM = 1536
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "at", "with", "it", "as", "by", "be", "this", "that"}
_cache: dict[str, list[float]] = {}


class EmbeddingError(Exception):
    pass


def _bucket(token: str) -> tuple[int, float]:
    h = hashlib.blake2b(token.encode(), digest_size=8).digest()
    n = int.from_bytes(h, "big")
    return n % DIM, 1.0 if (n >> 40) & 1 else -1.0


def local_embed(text: str) -> list[float]:
    toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
    vec = [0.0] * DIM
    for i, t in enumerate(toks):
        b, s = _bucket(t)
        vec[b] += s
        if i + 1 < len(toks):
            b2, s2 = _bucket(t + "_" + toks[i + 1])
            vec[b2] += 0.5 * s2
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _remote(texts: list[str]) -> list[list[float]]:
    key = get_settings().embeddings_api_key
    r = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "text-embedding-3-small", "input": texts},
        timeout=20,
    )
    r.raise_for_status()
    return [d["embedding"] for d in r.json()["data"]]


def embed(texts: list[str]) -> list[list[float]]:
    """Return one vector per text. Raises EmbeddingError when the hosted API is configured and fails."""
    s = get_settings()
    if s.fail_embeddings:
        raise EmbeddingError("FAIL_EMBEDDINGS is set")
    keyed = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
    if not s.embeddings_api_key:
        return [local_embed(t) for t in texts]
    missing = [(k, t) for k, t in zip(keyed, texts, strict=True) if k not in _cache]
    if missing:
        try:
            vecs = _remote([t for _, t in missing])
        except Exception as e:  # httpx errors, bad payloads
            log().warning("embeddings api failed", extra={"event": "embeddings_fallback"})
            raise EmbeddingError(str(e)) from e
        for (k, _), v in zip(missing, vecs, strict=True):
            _cache[k] = v
    return [_cache[k] for k in keyed]


def vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
