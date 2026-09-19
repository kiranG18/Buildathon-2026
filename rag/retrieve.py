"""Hybrid retrieval: vector top 20 plus full-text top 20, merged by reciprocal rank fusion.

Every query filters on the campaign or the global scope. Text scraped from web pages never
builds the query: callers pass structured facts and the task only.
"""

import re
import time

from backend.core.db import Db
from backend.core.logging import log
from rag.embeddings import EmbeddingError, embed, vec_literal

K_RRF = 60
_WORD = re.compile(r"[A-Za-z0-9]{3,}")
_cache: dict[tuple, tuple[float, list[dict]]] = {}
CACHE_SECONDS = 600


def _or_query(query: str) -> str:
    words = sorted(set(w.lower() for w in _WORD.findall(query)))
    return " | ".join(words)


def search(
    db: Db,
    campaign_id: str,
    query: str,
    doc_types: list[str] | None = None,
    k: int = 4,
    use_cache: bool = True,
) -> list[dict]:
    key = (campaign_id, query, tuple(doc_types or ()), k)
    hit = _cache.get(key)
    if use_cache and hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    types_sql = "and doc_type = any(%s)" if doc_types else ""
    tparams = [doc_types] if doc_types else []
    fts: list[dict] = []
    tsq = _or_query(query)
    if tsq:
        fts = db.q(
            f"""select id, content, document_id, ts_rank(tsv, to_tsquery('english', %s)) as s
                from knowledge_chunks
                where (scope = 'global' or campaign_id = %s) {types_sql} and tsv @@ to_tsquery('english', %s)
                order by s desc limit 20""",
            (tsq, campaign_id, *tparams, tsq),
        )
    vec: list[dict] = []
    try:
        qv = embed([query])[0]
        vec = db.q(
            f"""select id, content, document_id, 1 - (embedding <=> %s::vector) as s
                from knowledge_chunks
                where (scope = 'global' or campaign_id = %s) and embedding is not null {types_sql}
                order by embedding <=> %s::vector limit 20""",
            (vec_literal(qv), campaign_id, *tparams, vec_literal(qv)),
        )
    except EmbeddingError:
        log().warning("retrieval fell back to full-text", extra={"event": "retrieval_fallback", "campaign_id": campaign_id})
    scores: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for lst in (vec, fts):
        for rank, r in enumerate(lst):
            scores[r["id"]] = scores.get(r["id"], 0.0) + 1.0 / (K_RRF + rank + 1)
            rows[r["id"]] = r
    docs = {d["id"]: d["name"] for d in db.q("select id, name from knowledge_documents")}
    out = [
        {"id": cid, "label": docs.get(rows[cid]["document_id"], cid), "text": rows[cid]["content"], "score": round(sc * K_RRF / 2, 4)}
        for cid, sc in sorted(scores.items(), key=lambda kv: -kv[1])[:k]
    ]
    _cache[key] = (time.monotonic(), out)
    return out


def clear_cache() -> None:
    _cache.clear()
