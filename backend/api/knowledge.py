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
    name: str
    doc_type: str
    scope: str
    text: str


@router.post("/knowledge/search")
def search(body: SearchBody, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    if user.is_rep and not db.q1("select 1 as x from rep_assignments where rep_id = %s and campaign_id = %s and active", (user["id"], body.campaign_id)):
        raise CadenceError("This campaign belongs to other reps", code="forbidden", status=403)
    return retrieve.search(db, body.campaign_id, body.query, body.doc_types, min(body.k, 10), use_cache=False)


@router.post("/knowledge/documents", status_code=201)
def upload(body: UploadBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if body.scope != "global" and not db.q1("select 1 as x from campaigns where id = %s", (body.scope,)):
        raise NotFound("Campaign not found")
    doc_id = db.nid("DU")
    ids = ingest.ingest_document(db, doc_id=doc_id, name=body.name.strip(), doc_type=body.doc_type, scope=body.scope, body=body.text)
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
