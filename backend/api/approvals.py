from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.core import clock
from backend.core.db import Db
from backend.core.errors import Forbidden, NotFound
from backend.core.security import User, current_user, db_dep, require
from backend.orchestrator import replies
from backend.orchestrator.repo import enrollment
from backend.policy import gate

router = APIRouter()
mgr = require("Admin", "Manager")


class DecideBody(BaseModel):
    decision: str
    edited_body: str | None = None
    reason: str | None = None


class ResolveEscBody(BaseModel):
    note: str


class ReassignBody(BaseModel):
    replacement_rep_id: str


class ConflictBody(BaseModel):
    winner_campaign_id: str
    note: str | None = None


def _vis(db: Db, user: User) -> list[str] | None:
    return [r["campaign_id"] for r in db.q("select campaign_id from rep_assignments where rep_id = %s and active", (user["id"],))] if user.is_rep else None


@router.get("/approvals")
def list_approvals(status: str = "open", kind: str | None = None, campaign_id: str | None = None, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    where, params = ["a.status = %s"], [status]
    if kind:
        where.append("a.kind = %s")
        params.append(kind)
    if campaign_id:
        where.append("a.campaign_id = %s")
        params.append(campaign_id)
    vis = _vis(db, user)
    if vis is not None:
        where.append("a.campaign_id = any(%s)")
        params.append(vis)
    out = []
    for a in db.q(f"select a.*, p.full_name from approvals a join enrollments e on e.id = a.enrollment_id join prospects p on p.id = e.prospect_id where {' and '.join(where)} order by a.created_at", params):
        m = db.q1("select * from messages where id = %s", (a["msg_id"],)) if a["msg_id"] else None
        g = gate.evaluate(db, enrollment(db, a["enrollment_id"]), m["channel"], reply=m["is_reply"]) if m else None
        out.append({"id": a["id"], "kind": a["kind"], "campaign_id": a["campaign_id"], "prospect": a["full_name"], "draft": m["body"] if m else None,
                    "evidence": [s for s in (m["segs"] or []) if s.get("src")] if m else [], "gate_reasons": g["cks"] if g else [], "created_at": clock.ms(a["created_at"])})
    return out


@router.get("/approvals/{aid}/gate")
def approval_gate(aid: str, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    """The Guardian's checks for one open approval, fetched when someone opens it so /state stays cheap."""
    a = db.q1("select * from approvals where id = %s", (aid,))
    vis = _vis(db, user)
    if not a or (vis is not None and a["campaign_id"] not in vis):
        raise NotFound("Approval not found")
    m = db.q1("select channel, is_reply, kind from messages where id = %s", (a["msg_id"],)) if a["status"] == "open" and a["msg_id"] else None
    if not m:
        return {"gate": None}
    return {"gate": gate.evaluate(db, enrollment(db, a["enrollment_id"]), m["channel"], reply=m["is_reply"], pricing=m["kind"] == "pricing_answer")}


@router.post("/approvals/{aid}/decide")
def decide(aid: str, body: DecideBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if body.decision == "approve":
        return replies.approve_item(db, aid, user, body.edited_body)
    replies.reject_item(db, aid, user, body.reason or "Rejected")
    return {"ok": True}


@router.get("/escalations")
def list_escalations(status: str = "open", user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    rows = db.q("select x.*, p.full_name from escalations x join enrollments e on e.id = x.enrollment_id join prospects p on p.id = e.prospect_id where x.status = %s order by x.created_at", (status,))
    return [{"id": r["id"], "reason_code": r["reason_code"], "summary": r["summary"], "severity": r["severity"], "prospect": r["full_name"], "suggested_reply": r["suggested"],
             "status": r["status"], "rep_id": r["rep_id"]} for r in rows if not user.is_rep or r["rep_id"] == user["id"]]


@router.post("/escalations/{xid}/resolve")
def resolve_escalation(xid: str, body: ResolveEscBody, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    x = db.q1("select rep_id from escalations where id = %s", (xid,))
    if not x:
        raise NotFound("Escalation not found")
    if user.is_rep and x["rep_id"] != user["id"]:
        raise Forbidden("This escalation belongs to another rep")
    replies.resolve_escalation(db, xid, user, body.note)
    return {"status": "resolved"}


@router.post("/escalations/{xid}/reassign")
def reassign_escalation(xid: str, body: ReassignBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    rep = db.q1("select id from users where id = %s and role = 'Rep' and active", (body.replacement_rep_id,))
    if not rep:
        raise NotFound("Rep not found or offboarded")
    db.x("update escalations set rep_id = %s where id = %s", (rep["id"], xid))
    return {"rep_id": rep["id"]}


@router.get("/conflicts")
def list_conflicts(status: str = "open", user: User = Depends(mgr), db: Db = Depends(db_dep)) -> list[dict]:
    rows = db.q("select c.*, p.full_name from conflicts c join prospects p on p.id = c.prospect_id where c.status = %s order by c.created_at", (status,))
    return [{"id": r["id"], "prospect": r["full_name"], "campaigns": r["campaign_ids"], "type": "overlap", "rule_applied": r["rule"], "decision": r["decision"]} for r in rows]


@router.post("/conflicts/{cid}/resolve")
def resolve_conflict(cid: str, body: ConflictBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    replies.resolve_conflict(db, cid, user, body.winner_campaign_id)
    return {"status": "resolved", "winner": body.winner_campaign_id}
