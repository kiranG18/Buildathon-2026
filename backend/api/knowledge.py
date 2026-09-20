from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.core import clock
from backend.core.db import Db
from backend.core.errors import CadenceError, NotFound
from backend.core.security import User, current_user, db_dep, require
from rag import ingest, retrieve

router = APIRouter()
mgr = require("Admin", "Manager")


class SearchBody(BaseModel):
    campaign_id: str
    query: str
    doc_types: list[str] | None = None
    k: int = 4


class UploadBody(BaseModel):
    name: str = "Untitled Document"
    doc_type: str = "case study"
    scope: str = "global"
    text: str = ""


@router.get("/knowledge/documents")
def list_documents(user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    docs_rows = db.q("select * from knowledge_documents order by ingested_at desc, id")
    chunks = db.q("select id, document_id from knowledge_chunks order by id")
    by_doc: dict[str, list[str]] = {}
    for c in chunks:
        by_doc.setdefault(c["document_id"], []).append(c["id"])
    return [
        {"id": d["id"], "name": d["name"], "doc_type": d["doc_type"], "scope": d["scope"], "campaign_id": d["campaign_id"], "chunks": by_doc.get(d["id"], []), "ingested_at": clock.ms(d["ingested_at"])}
        for d in docs_rows
    ]


@router.get("/knowledge/search")
def search_get(query: str, campaign_id: str = "C1", k: int = 4, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    return retrieve.search(db, campaign_id, query, None, min(k, 10), use_cache=False)


@router.post("/knowledge/search")
def search(body: SearchBody, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    if user.is_rep and not db.q1("select 1 as x from rep_assignments where rep_id = %s and campaign_id = %s and active", (user["id"], body.campaign_id)):
        raise CadenceError("This campaign belongs to other reps", code="forbidden", status=403)
    return retrieve.search(db, body.campaign_id, body.query, body.doc_types, min(body.k, 10), use_cache=False)


@router.post("/knowledge/documents", status_code=201)
def upload(body: UploadBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    raw_scope = (body.scope or "global").strip()
    if raw_scope.lower() in ("undefined", "null", "none", "", "global"):
        scope = "global"
    elif db.q1("select 1 as x from campaigns where id = %s", (raw_scope,)):
        scope = raw_scope
    else:
        scope = "global"
    name = (body.name or "Untitled Document").strip()
    doc_type = (body.doc_type or "case study").lower().strip()
    text = (body.text or "").strip()
    if not text:
        raise CadenceError("Document text cannot be empty", code="validation_error")
    doc_id = db.nid("DU")
    ids = ingest.ingest_document(db, doc_id=doc_id, name=name, doc_type=doc_type, scope=scope, body=text)
    retrieve.clear_cache()
    return {"id": doc_id, "chunks": ids}


@router.post("/knowledge/documents/{did}/reingest")
def reingest(did: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    d = db.q1("select * from knowledge_documents where id = %s", (did,))
    if not d:
        raise NotFound("Document not found")
    rows = db.q("select id, content from knowledge_chunks where document_id = %s order by id", (did,))
    body = "\n\n".join(f"<!-- {r['id']} -->\n{r['content']}" for r in rows)
    ingest.ingest_document(db, doc_id=did, name=d["name"], doc_type=d["doc_type"], scope=d["scope"], body=body, at=clock.now())
    retrieve.clear_cache()
    return {"chunks": len(rows)}


@router.delete("/knowledge/documents/{did}")
def delete(did: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if not db.x("delete from knowledge_documents where id = %s", (did,)):
        raise NotFound("Document not found")
    retrieve.clear_cache()
    return {"ok": True}
