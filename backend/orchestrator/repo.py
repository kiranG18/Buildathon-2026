"""Database helpers used by the orchestrator. Every campaign-scoped function takes campaign_id explicitly."""

import random
import zlib
from datetime import datetime

from backend.core import clock
from backend.core.db import Db, J
from backend.core.errors import NotFound
from backend.orchestrator.defs import AGENT_META, AGENT_ROLE, JOB_AGENT


def now_ms() -> int:
    return clock.ms(clock.now())


def campaign(db: Db, campaign_id: str) -> dict:
    c = db.q1("select * from campaigns where id = %s", (campaign_id,))
    if not c:
        raise NotFound(f"Campaign {campaign_id} not found")
    c["agents"] = {r["agent_key"]: r["enabled"] for r in db.q("select agent_key, enabled from campaign_agents where campaign_id = %s", (campaign_id,))}
    c["channels"] = {r["channel"]: r["enabled"] for r in db.q("select channel, enabled from channel_settings where campaign_id = %s", (campaign_id,))}
    c["reps"] = [r["rep_id"] for r in db.q("select rep_id from rep_assignments where campaign_id = %s and active order by rep_id", (campaign_id,))]
    return c


def enrollment(db: Db, enrollment_id: str, for_update: bool = False) -> dict:
    e = db.q1(f"select * from enrollments where id = %s {'for update' if for_update else ''}", (enrollment_id,))
    if not e:
        raise NotFound(f"Enrollment {enrollment_id} not found")
    return e


def prospect(db: Db, prospect_id: str) -> dict:
    p = db.q1(
        "select p.*, c.name as company, c.domain, c.industry as ind, c.staff, c.stage, c.city from prospects p join companies c on c.id = p.company_id where p.id = %s",
        (prospect_id,),
    )
    if not p:
        raise NotFound(f"Prospect {prospect_id} not found")
    return p


def user(db: Db, user_id: str) -> dict | None:
    return db.q1("select * from users where id = %s", (user_id,))


def rep_for(db: Db, e: dict, c: dict) -> dict:
    rid = e["rep_id"] or (c["reps"][0] if c["reps"] else None)
    u = user(db, rid) if rid else None
    if u:
        return u
    return {"id": None, "name": "Unassigned", "role": "Rep", "active": False, "rep_limit": 0, "channels": [], "label": "", "hours": "", "tz": "PT"}


def first(name: str) -> str:
    return name.split(" ")[0]


def act(db: Db, e: dict | None, kind: str, text: str, *, cid: str | None = None, agent: str | None = None, run_id: str | None = None,
        msg_id: str | None = None, mode: str | None = None, quiet: bool = False, reason_code: str | None = None, at: datetime | None = None) -> str:
    aid = db.nid("A-")
    campaign_id = e["campaign_id"] if e else cid
    ts = at or clock.now()
    db.x(
        """insert into activity (id, ts, enrollment_id, prospect_id, campaign_id, kind, text, agent, run_id, msg_id, mode, quiet, reason_code)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (aid, ts, e["id"] if e else None, e["prospect_id"] if e else None, campaign_id, kind, text, agent, run_id, msg_id, mode, quiet, reason_code),
    )
    if campaign_id:
        db.x("update campaigns set last_activity = %s where id = %s", (ts, campaign_id))
    return aid


def channel_mode(db: Db, ch: str, prospect_id: str | None = None) -> str:
    """Live needs a switched-on integration, a registered adapter and, for email and SMS, a recipient on ALLOWED_RECIPIENTS. Anything else is a recorded sandbox send."""
    from backend.channels.adapters import is_allowed
    from backend.channels.base import REGISTRY
    from backend.orchestrator.defs import CH_INTEG

    row = db.q1("select mode from integrations where key = %s", (CH_INTEG.get(ch, ""),))
    if not (row and row["mode"] == "live" and ch in REGISTRY):
        return "sandbox"
    if prospect_id and ch in ("email", "sms"):
        p = db.q1("select email, phone from prospects where id = %s", (prospect_id,))
        if p and not is_allowed(p["email"] if ch == "email" else p["phone"]):
            return "sandbox"
    return "live"


def mk_msg(db: Db, e: dict, ch: str, direction: str, body: str, *, segs: list | None = None, **x) -> dict:
    """Insert a message. x may carry subject, status, run_id, kind, step_no, prompt_version, approved_by, classification,
    rule, sub, is_reply, is_ack, human, by_name, idempotency_key, at."""
    mid = db.nid("M-")
    at = x.pop("at", None) or clock.now()
    cols = {
        "id": mid, "enrollment_id": e["id"], "prospect_id": e["prospect_id"], "campaign_id": e["campaign_id"], "channel": ch, "direction": direction,
        "body": body, "segs": J(segs) if segs else None, "created_at": at, "mode": x.pop("mode", None) or channel_mode(db, ch, e["prospect_id"]), "status": x.pop("status", "sent"),
    }
    cols.update(x)
    names = ", ".join(cols)
    db.x(f"insert into messages ({names}) values ({', '.join(['%s'] * len(cols))})", list(cols.values()))
    return db.q1("select * from messages where id = %s", (mid,))


def enqueue(db: Db, e: dict, step: str, *, due: datetime | None = None, step_no: int | None = None, payload: dict | None = None) -> str:
    jid = db.nid("R-")
    now = clock.now()
    db.x(
        """insert into jobs (id, campaign_id, enrollment_id, prospect_id, agent, step, status, run_at, created_at, step_no, payload)
           values (%s,%s,%s,%s,%s,%s,'queued',%s,%s,%s,%s)""",
        (jid, e["campaign_id"], e["id"], e["prospect_id"], JOB_AGENT[step], step, due or now, now, step_no, J(payload) if payload else None),
    )
    return jid


def active_version(db: Db, campaign_id: str, role: str) -> int:
    r = db.q1("select version from prompt_versions where campaign_id = %s and agent_key = %s and status = 'active'", (campaign_id, role))
    return r["version"] if r else 1


def finish_job(db: Db, job: dict, *, summary: str, trace: dict, agent: str | None = None, cost: float | None = None, model: str | None = None,
               tokens_in: int | None = None, tokens_out: int | None = None, latency: float | None = None, status: str = "done",
               error: str | None = None, msg_id: str | None = None, provider: str | None = None, prompt_version: int | None = None,
               role: str | None = None, retrieved: list[str] | None = None) -> None:
    agent = agent or job["agent"]
    meta = AGENT_META[agent]
    r = random.Random(zlib.crc32(job["id"].encode()))
    role = role or AGENT_ROLE[agent]
    c = db.q1("select version from campaigns where id = %s", (job["campaign_id"],))
    pv = prompt_version if prompt_version is not None else active_version(db, job["campaign_id"], role)
    dur = latency if latency is not None else round(meta["dur"] * (0.8 + r.random() * 0.5), 1)
    cst = cost if cost is not None else round(meta["cost"] * (0.85 + r.random() * 0.3), 4)
    tin = tokens_in if tokens_in is not None else (0 if cst == 0 else round(1400 + r.random() * 2600))
    tout = tokens_out if tokens_out is not None else (0 if cst == 0 else round(120 + r.random() * 380))
    now = clock.now()
    db.x(
        "update jobs set status = %s, ended_at = %s, err = %s, msg_id = coalesce(%s, msg_id) where id = %s",
        (status, now, error, msg_id, job["id"]),
    )
    chunks = retrieved if retrieved is not None else list(trace.get("chunks", []))
    db.x(
        """insert into agent_runs (id, job_id, campaign_id, enrollment_id, agent_key, role, provider, model, prompt_version, campaign_version, retrieved_chunk_ids,
           summary, trace, input_snapshot, status, tokens_in, tokens_out, cost_usd, latency_s, error, is_replay, created_at)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (id) do update set summary = excluded.summary, trace = excluded.trace, status = excluded.status, error = excluded.error,
             prompt_version = excluded.prompt_version, cost_usd = excluded.cost_usd, tokens_in = excluded.tokens_in, tokens_out = excluded.tokens_out,
             latency_s = excluded.latency_s, created_at = excluded.created_at""",
        (job["id"], job["id"], job["campaign_id"], job["enrollment_id"], agent, role, provider or ("dronahq" if meta["host"] == "DronaHQ" else "direct"),
         model or meta["model"], pv, c["version"], chunks, summary, J(trace), J(trace.get("snapshot")) if trace.get("snapshot") else None, status, tin, tout,
         cst, dur, error, bool(job.get("is_replay")), now),
    )


def set_state(db: Db, e: dict, state: str, **fields) -> None:
    sets = ["state = %s"]
    vals: list = [state]
    for k, v in fields.items():
        sets.append(f"{k} = %s")
        vals.append(J(v) if isinstance(v, (dict, list)) and k in JSON_COLS else v)
    db.x(f"update enrollments set {', '.join(sets)} where id = %s", (*vals, e["id"]))
    e["state"] = state
    e.update(fields)


JSON_COLS = {"crit", "plan", "hold", "plan_hist", "meeting", "slots"}


def save_enr(db: Db, e: dict, **fields) -> None:
    sets, vals = [], []
    for k, v in fields.items():
        sets.append(f"{k} = %s")
        vals.append(J(v) if k in JSON_COLS and v is not None else v)
        e[k] = v
    if sets:
        db.x(f"update enrollments set {', '.join(sets)} where id = %s", (*vals, e["id"]))


def new_enrollment(db: Db, prospect_id: str, campaign_id: str, state: str = "new") -> dict:
    c = campaign(db, campaign_id)
    p = prospect(db, prospect_id)
    eid = db.nid("E")
    reps = c["reps"]
    rep = reps[0] if reps else None
    if len(reps) > 1:
        rep = "U5" if p["timezone"] in ("ET", "CT") and "U5" in reps else ("U3" if "U3" in reps else reps[0])
    db.x(
        "insert into enrollments (id, campaign_id, prospect_id, state, rep_id, created_at) values (%s,%s,%s,%s,%s,%s)",
        (eid, campaign_id, prospect_id, state, rep, clock.now()),
    )
    return enrollment(db, eid)
