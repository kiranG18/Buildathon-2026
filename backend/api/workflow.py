from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.core import clock
from backend.core.config import get_settings
from backend.core.db import Db
from backend.core.errors import CadenceError, Forbidden, GateBlocked, NotFound, StateConflict
from backend.core.security import User, current_user, db_dep, require, webhook_guard
from backend.orchestrator import replay as replay_svc
from backend.orchestrator import replies
from backend.orchestrator.repo import campaign, enqueue, enrollment
from backend.policy import gate

router = APIRouter()
mgr = require("Admin", "Manager")


class ReplayBody(BaseModel):
    version: int


class SendBody(BaseModel):
    enrollment_id: str
    channel: str = "email"


class InboundBody(BaseModel):
    enrollment_id: str | None = None
    sender: str | None = None
    body: str
    external_id: str | None = None
    in_reply_to: str | None = None


class SimulateBody(BaseModel):
    enrollment_id: str
    channel: str = "email"
    body: str


def _vis(db: Db, user: User) -> list[str] | None:
    return [r["campaign_id"] for r in db.q("select campaign_id from rep_assignments where rep_id = %s and active", (user["id"],))] if user.is_rep else None


@router.get("/activity")
def activity(campaign_id: str | None = None, since_id: int = 0, limit: int = 50, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    vis = _vis(db, user)
    where, params = ["seq > %s", "not quiet"], [since_id]
    if campaign_id:
        where.append("campaign_id = %s")
        params.append(campaign_id)
    if vis is not None:
        where.append("campaign_id = any(%s)")
        params.append(vis)
    rows = db.q(f"select * from activity where {' and '.join(where)} order by seq desc limit %s", [*params, min(limit, 200)])
    items = [{"id": r["id"], "seq": r["seq"], "ts": clock.ms(r["ts"]), "campaign_id": r["campaign_id"], "enrollment_id": r["enrollment_id"], "agent_key": r["agent"],
              "event_type": r["kind"], "summary": r["text"], "reason_code": r["reason_code"]} for r in rows]
    return {"items": items, "last_id": max((r["seq"] for r in rows), default=since_id)}


@router.get("/agent-runs")
def agent_runs(campaign_id: str | None = None, status: str | None = None, agent: str | None = None, limit: int = 50, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    where, params = ["not r.is_replay"], []
    vis = _vis(db, user)
    for cond, val in (("r.campaign_id = %s", campaign_id), ("r.status = %s", status), ("r.agent_key = %s", agent)):
        if val:
            where.append(cond)
            params.append(val)
    if vis is not None:
        where.append("r.campaign_id = any(%s)")
        params.append(vis)
    rows = db.q(
        f"""select r.*, p.full_name from agent_runs r left join enrollments e on e.id = r.enrollment_id left join prospects p on p.id = e.prospect_id
            where {' and '.join(where)} order by r.created_at desc limit %s""", [*params, min(limit, 200)])
    counts = {x["status"]: x["n"] for x in db.q("select status, count(*) as n from jobs where not is_replay group by status")}
    return {"items": [{"id": r["id"], "ts": clock.ms(r["created_at"]), "campaign_id": r["campaign_id"], "agent_key": r["agent_key"], "prospect": r["full_name"], "summary": r["summary"],
                       "status": r["status"], "duration_ms": round(r["latency_s"] * 1000), "cost_usd": r["cost_usd"]} for r in rows],
            "counts": {"running": counts.get("running", 0), "queued": counts.get("queued", 0), "failed": counts.get("failed", 0)}}


@router.get("/agent-runs/{run_id}")
def agent_run(run_id: str, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    r = db.q1("select * from agent_runs where id = %s", (run_id,))
    if not r:
        raise NotFound("Agent run not found")
    vis = _vis(db, user)
    if vis is not None and r["campaign_id"] not in vis:
        raise Forbidden("Not your campaign")
    chunks = db.q("select c.id, d.name as label, c.content as text from knowledge_chunks c join knowledge_documents d on d.id = c.document_id where c.id = any(%s)", (r["retrieved_chunk_ids"],))
    tr = r["trace"]
    return {"agent": r["agent_key"], "provider": r["provider"], "model": r["model"], "prompt_version": {"id": f"{r['campaign_id']}-{r['role']}-v{r['prompt_version']}", "version": r["prompt_version"]},
            "campaign_version": r["campaign_version"], "retrieved_chunks": chunks, "input_summary": tr.get("input"), "output": tr.get("output"), "tokens_in": r["tokens_in"],
            "tokens_out": r["tokens_out"], "cost_usd": r["cost_usd"], "latency_ms": round(r["latency_s"] * 1000), "gate_decision": tr.get("gate"), "replay": r["is_replay"]}


@router.post("/agent-runs/{run_id}/replay")
def replay(run_id: str, body: ReplayBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return replay_svc.replay(db, run_id, body.version)


@router.post("/agent-runs/{run_id}/retry", status_code=202)
def retry(run_id: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    j = db.q1("select * from jobs where id = %s", (run_id,))
    if not j:
        raise NotFound("Job not found")
    if j["status"] != "failed":
        raise StateConflict("Only a failed job can be retried")
    db.x("delete from agent_runs where id = %s", (run_id,))
    db.x("update jobs set status = 'queued', err = null, run_at = %s, attempts = 0, ended_at = null where id = %s", (clock.now(), run_id))
    return {"job_id": run_id}


@router.post("/outreach/send", status_code=202)
def outreach_send(body: SendBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    """Ask the Guardian to authorize a send. A refusal comes back as a 409 with every check listed. An allow queues the next draft step."""
    e = enrollment(db, body.enrollment_id)
    g = gate.evaluate(db, e, body.channel)
    if g["dec"] in ("block", "hold", "defer", "replan"):
        raise GateBlocked(g["reason"], f"The Guardian refused this send: {g['reason']}", g["dec"], {"gate": g["cks"], "retry_at": g["until"]})
    step = next((i for i, s in enumerate(e["plan"] or []) if s["status"] == "pending"), None)
    if step is None:
        raise StateConflict("No pending step to send", code="no_pending_step")
    plan = e["plan"]
    plan[step]["queued"] = True
    from backend.orchestrator.repo import save_enr

    save_enr(db, e, plan=plan)
    return {"decision": g["dec"], "job_id": enqueue(db, e, "draft", step_no=step)}


@router.post("/inbound/{channel}")
def inbound(channel: str, body: InboundBody, _: None = Depends(webhook_guard), db: Db = Depends(db_dep)) -> dict:
    e = _find_enrollment(db, body)
    m = replies.ingest_reply(db, e, channel, body.body, external_id=body.external_id)
    return {"message_id": m["id"]}


@router.post("/demo/simulate-reply")
def simulate_reply(body: SimulateBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if not get_settings().demo_mode:
        raise CadenceError("Demo tools are off", code="demo_disabled", status=403)
    e = enrollment(db, body.enrollment_id)
    c = campaign(db, e["campaign_id"])
    if c["status"] in ("completed", "archived"):
        raise StateConflict("This campaign is closed")
    m = replies.ingest_reply(db, e, body.channel, body.body)
    return {"message_id": m["id"], "classification": m["classification"], "sub": m["sub"], "rule": m["rule"]}


def _find_enrollment(db: Db, body: InboundBody) -> dict:
    if body.enrollment_id:
        return enrollment(db, body.enrollment_id)
    row = db.q1(
        """select e.id from enrollments e join prospects p on p.id = e.prospect_id where lower(p.email) = lower(%s)
           order by (select count(*) from messages m where m.enrollment_id = e.id and m.direction = 'out') desc, e.created_at desc limit 1""", (body.sender or "",))
    if not row:
        raise NotFound("No enrollment matches that sender")
    return enrollment(db, row["id"])
