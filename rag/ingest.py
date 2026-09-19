import hashlib
from datetime import datetime
from pathlib import Path

from backend.core import clock
from backend.core.db import Db
from backend.core.logging import log
from rag.chunking import chunk_text, parse_frontmatter, tokens
from rag.embeddings import EmbeddingError, embed, vec_literal

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


def ingest_document(
    db: Db,
    *,
    doc_id: str,
    name: str,
    doc_type: str,
    scope: str,
    body: str,
    metadata: dict | None = None,
    source_path: str | None = None,
    at: datetime | None = None,
) -> list[str]:
    """Chunk, embed and upsert one document. Returns the chunk ids. Embedding failures leave vectors null."""
    campaign_id = None if scope == "global" else scope
    pieces = chunk_text(doc_type, body)
    ids = [pid or db.nid("K-U") for pid, _ in pieces]
    texts = [t for _, t in pieces]
    try:
        vecs: list[list[float] | None] = list(embed(texts))
    except EmbeddingError:
        log().warning("ingest without embeddings", extra={"event": "embeddings_fallback"})
        vecs = [None] * len(texts)
    from backend.core.db import J

    db.x(
        """insert into knowledge_documents (id, name, doc_type, scope, campaign_id, metadata, source_path, content_hash, ingested_at)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (id) do update set name = excluded.name, doc_type = excluded.doc_type, scope = excluded.scope,
             campaign_id = excluded.campaign_id, metadata = excluded.metadata, content_hash = excluded.content_hash,
             ingested_at = excluded.ingested_at""",
        (doc_id, name, doc_type, scope, campaign_id, J(metadata or {}), source_path, hashlib.sha1(body.encode()).hexdigest(), at or clock.now()),
    )
    db.x("delete from knowledge_chunks where document_id = %s", (doc_id,))
    tags = [str(v) for v in (metadata or {}).values() if isinstance(v, str)][:8]
    for cid, text, vec in zip(ids, texts, vecs, strict=True):
        db.x(
            """insert into knowledge_chunks (id, document_id, campaign_id, scope, doc_type, tags, content, embedding, token_count, citation_label)
               values (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
               on conflict (id) do update set document_id = excluded.document_id, campaign_id = excluded.campaign_id,
                 scope = excluded.scope, doc_type = excluded.doc_type, content = excluded.content,
                 embedding = excluded.embedding, token_count = excluded.token_count""",
            (cid, doc_id, campaign_id, scope, doc_type, tags, text, vec_literal(vec) if vec else None, tokens(text), f"{name} {cid}"),
        )
    return ids


def ingest_file(db: Db, path: Path, at: datetime | None = None) -> list[str]:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    return ingest_document(
        db,
        doc_id=meta.get("id") or path.stem,
        name=meta.get("name") or path.stem,
        doc_type=meta.get("doc_type", "playbook"),
        scope=meta.get("scope", "global"),
        body=body,
        metadata={k: v for k, v in meta.items() if k in ("industry", "persona", "channel", "scenario", "quality")},
        source_path=str(path.relative_to(KNOWLEDGE_DIR.parent)),
        at=at,
    )


def ingest_all(db: Db, at: datetime | None = None) -> int:
    n = 0
    for f in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        n += len(ingest_file(db, f, at))
    return n
