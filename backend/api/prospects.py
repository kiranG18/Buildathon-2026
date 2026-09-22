from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.core import clock
from backend.core.db import Db
from backend.core.errors import Forbidden, NotFound
from backend.core.security import User, current_user, db_dep, require
from backend.orchestrator import replies
from backend.orchestrator.repo import enqueue, enrollment

router = APIRouter()
mgr = require("Admin", "Manager")


class StopBody(BaseModel):
    reason: str = "Stopped by a person"


class RunBody(BaseModel):
    step: str = "research"


class ReplyBody(BaseModel):
    text: str


def _visible_campaigns(db: Db, user: User) -> list[str] | None:
    if not user.is_rep:
        return None
    return [r["campaign_id"] for r in db.q("select campaign_id from rep_assignments where rep_id = %s and active", (user["id"],))]


@router.get("/prospects")
def list_prospects(campaign_id: str | None = None, state: str | None = None, q: str | None = None, limit: int = 50, cursor: int = 0,
                   user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    where, params = ["true"], []
    vis = _visible_campaigns(db, user)
    if vis is not None:
        where.append("e.campaign_id = any(%s)")
        params.append(vis)
    if campaign_id:
        where.append("e.campaign_id = %s")
        params.append(campaign_id)
    if state:
        where.append("e.state = %s")
        params.append(state)
    if q:
        where.append("(p.full_name ilike %s or c.name ilike %s or p.title ilike %s)")
        params += [f"%{q}%"] * 3
    rows = db.q(
        f"""select e.id, e.campaign_id, e.state, e.score, e.last_touch, p.id as pid, p.full_name, p.title, c.name as company from enrollments e
            join prospects p on p.id = e.prospect_id join companies c on c.id = p.company_id where {' and '.join(where)}
            order by e.id limit %s offset %s""",
        [*params, limit, cursor],
    )
    items = [{"id": r["pid"], "enrollment_id": r["id"], "name": r["full_name"], "title": r["title"], "company": r["company"],
              "campaigns": [{"id": r["campaign_id"], "state": r["state"], "icp_score": r["score"]}], "last_touch": clock.ms(r["last_touch"])} for r in rows]
    return {"items": items, "next_cursor": cursor + limit if len(rows) == limit else None}


@router.get("/prospects/{pid}")
def prospect_detail(pid: str, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    p = db.q1("select p.*, c.name as company from prospects p join companies c on c.id = p.company_id where p.id = %s", (pid,))
    if not p:
        raise NotFound("Prospect not found")
    vis = _visible_campaigns(db, user)
    enrs = [e for e in db.q("select * from enrollments where prospect_id = %s", (pid,)) if vis is None or e["campaign_id"] in vis]
    if not enrs:
        raise Forbidden("This prospect belongs to campaigns you do not work on")
    ids = [e["id"] for e in enrs]
    timeline = db.q("select id, channel, direction, subject, body, status, mode, created_at, run_id from messages where enrollment_id = any(%s) order by created_at", (ids,))
    return {
        "profile": {"id": p["id"], "name": p["full_name"], "title": p["title"], "company": p["company"], "email": p["email"], "phone": p["phone"]},
        "facts": p["facts"],
        "enrollments": [{"id": e["id"], "campaign_id": e["campaign_id"], "state": e["state"], "score": e["score"]} for e in enrs],
        "timeline": [{**m, "created_at": clock.ms(m["created_at"])} for m in timeline],
        "plan": {e["id"]: e["plan"] for e in enrs},
        "icp_scorecard": {e["id"]: e["crit"] for e in enrs},
        "conflicts": db.q("select id, campaign_ids, rule, decision, status from conflicts where prospect_id = %s", (pid,)),
    }


@router.post("/enrollments/{eid}/stop")
def stop(eid: str, body: StopBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    replies.stop_prospect(db, enrollment(db, eid), user)
    return {"state": "stopped"}


@router.post("/enrollments/{eid}/escalate")
def escalate(eid: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    replies.escalate_manually(db, enrollment(db, eid), user)
    return {"state": "escalated"}


class ReassignBody(BaseModel):
    replacement_rep_id: str


@router.post("/enrollments/{eid}/reassign")
def reassign(eid: str, body: ReassignBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    rep = db.q1("select id from users where id = %s and role = 'Rep' and active", (body.replacement_rep_id,))
    if not rep:
        raise NotFound("Rep not found or offboarded")
    e = enrollment(db, eid)
    db.x("update enrollments set rep_id = %s where id = %s", (rep["id"], eid))
    # A rep only sees a campaign's enrollments once assigned to that campaign, regardless of who owns any one of them.
    db.x(
        "insert into rep_assignments (rep_id, campaign_id, active) values (%s,%s,true) on conflict (rep_id, campaign_id) do update set active = true",
        (rep["id"], e["campaign_id"]),
    )
    return {"rep_id": rep["id"]}


@router.post("/enrollments/{eid}/run", status_code=202)
def run_now(eid: str, body: RunBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    e = enrollment(db, eid)
    if body.step not in ("research", "qualify", "plan"):
        raise NotFound("Unknown step")
    return {"job_id": enqueue(db, e, body.step)}


@router.post("/enrollments/{eid}/reply")
def human_reply(eid: str, body: ReplyBody, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    e = enrollment(db, eid)
    vis = _visible_campaigns(db, user)
    if vis is not None and e["campaign_id"] not in vis:
        raise Forbidden("Not your thread")
    m = replies.human_send(db, e, user, body.text.strip())
    return {"message_id": m["id"]}


@router.post("/enrollments/{eid}/linkedin-reply")
def linkedin_reply(eid: str, body: ReplyBody, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    """A rep pastes a reply they received on LinkedIn. It takes the same path as a Gmail or SMS reply."""
    e = enrollment(db, eid)
    vis = _visible_campaigns(db, user)
    if vis is not None and e["campaign_id"] not in vis:
        raise Forbidden("Not your thread")
    m = replies.ingest_reply(db, e, "linkedin", body.text.strip())
    return {"message_id": m["id"], "classification": m["classification"], "sub": m["sub"], "rule": m["rule"]}
