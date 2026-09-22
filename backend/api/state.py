"""GET /state: the whole workspace in the shape the prototype UI reads (its `S` object).

Timestamps are millisecond epochs on the demo clock. Reps only see the campaigns they work on.
"""

import time

from fastapi import APIRouter, Depends

from backend.core import clock
from backend.core.config import get_settings
from backend.core.db import Db
from backend.core.security import User, current_user, db_dep

router = APIRouter()
ms = clock.ms

MAX_ACTS = 400
MAX_DONE_JOBS = 300


def _visible(db: Db, user: User) -> list[str] | None:
    if not user.is_rep:
        return None
    return [r["campaign_id"] for r in db.q("select campaign_id from rep_assignments where rep_id = %s and active", (user["id"],))]


def build_state(db: Db, user: User) -> dict:
    vis = _visible(db, user)
    vp: list = [] if vis is None else [vis]

    def where(col: str) -> str:
        return "" if vis is None else f"where {col} = any(%s)"

    gs = db.q1("select * from global_settings where id = 1")
    camps_rows = db.q(f"select * from campaigns {where('id')} order by id", vp)
    agents = {}
    for r in db.q("select campaign_id, agent_key, enabled from campaign_agents"):
        agents.setdefault(r["campaign_id"], {})[r["agent_key"]] = r["enabled"]
    chans = {}
    for r in db.q("select campaign_id, channel, enabled from channel_settings"):
        chans.setdefault(r["campaign_id"], {})[r["channel"]] = r["enabled"]
    reps = {}
    for r in db.q("select campaign_id, rep_id from rep_assignments where active order by rep_id"):
        reps.setdefault(r["campaign_id"], []).append(r["rep_id"])
    camps = [
        {
            "id": c["id"], "name": c["name"], "status": c["status"], "owner": c["owner_id"], "pausedBy": c["paused_by"], "pausedAt": ms(c["paused_at"]),
            "pausedHeld": c["paused_held"], "agents": agents.get(c["id"], {}), "chLimit": c["ch_limit"], "createdAt": ms(c["created_at"]), "version": c["version"],
            "parent": c["parent_id"], "thr": c["thr"], "icp": c["icp"], "personas": c["personas"], "geo": c["geo"], "objective": c["objective"],
            "signals": c["signals"], "order": c["seq_order"], "tone": c["tone"], "words": c["words"], "approval": c["approval_text"], "appr": c["appr"],
            "cap": c["daily_send_cap"], "reps": reps.get(c["id"], []), "priority": c["priority"], "channels": chans.get(c["id"], {}),
            "exclusions": c["exclusions"], "roles": c["roles"], "geoList": c["geo_list"], "last": ms(c["last_activity"]), "dryOk": c["dry_ok"], "tpl": c["tpl"],
            "refs": c["refs"],
        }
        for c in camps_rows
    ]
    users = [
        {"id": u["id"], "name": u["name"], "role": u["role"], "email": u["email"], "title": u["title"], "limit": u["rep_limit"], "hours": u["hours"],
         "tz": u["tz"], "channels": u["channels"], "active": u["active"], "label": u["label"]}
        for u in db.q("select * from users order by id")
    ]
    enr_rows = db.q(f"select * from enrollments {where('campaign_id')} order by id::text", vp)
    enr_rows.sort(key=lambda e: int(e["id"][1:]) if e["id"][1:].isdigit() else 0)
    enr = [
        {
            "id": e["id"], "pid": e["prospect_id"], "cid": e["campaign_id"], "st": e["state"], "score": e["score"], "crit": e["crit"], "plan": e["plan"],
            "rep": e["rep_id"], "created": ms(e["created_at"]), "lastTouch": ms(e["last_touch"]), "hold": e["hold"], "firstDue": ms(e["first_due"]),
            "reject": e["reject"], "warm": e["warm"], "slots": e["slots"], "meeting": e["meeting"], "wake": ms(e["wake"]), "reviewNote": e["review_note"],
            "hotCall": e["hot_call"], "deferNote": e["defer_note"], "planHist": e["plan_hist"], "note": e["note"],
        }
        for e in enr_rows
    ]
    pids = {e["pid"] for e in enr}
    suppressed = _suppressed_ids(db)
    people = {}
    for p in db.q("select p.*, c.name as company, c.domain, c.industry, c.staff, c.stage, c.city from prospects p join companies c on c.id = p.company_id"):
        if vis is not None and p["id"] not in pids:
            continue
        people[p["id"]] = {
            "id": p["id"], "name": p["full_name"], "first": p["first_name"], "title": p["title"], "company": p["company"], "domain": p["domain"],
            "ind": p["industry"], "staff": p["staff"], "stage": p["stage"], "city": p["city"], "region": p["region"], "email": p["email"],
            "linkedin": p["linkedin_url"], "phone": p["phone"], "tz": p["timezone"], "facts": p["facts"], "rich": p["rich"], "researched": p["researched"],
            "bio": p["bio"], "thin": p["thin"], "rej": p["rej"], "empty": p["is_empty"], "suppressed": p["id"] in suppressed,
        }
    msgs = [
        {
            "id": m["id"], "eid": m["enrollment_id"], "pid": m["prospect_id"], "cid": m["campaign_id"], "ch": m["channel"], "dir": m["direction"], "body": m["body"],
            "segs": m["segs"], "t": ms(m["created_at"]), "mode": m["mode"], "status": m["status"], "seed": m["is_seed"], "subject": m["subject"],
            "runId": m["run_id"], "kind": m["kind"], "stepNo": m["step_no"], "pv": m["prompt_version"], "approvedBy": m["approved_by"], "cls": m["classification"],
            "rule": m["rule"], "sub": m["sub"], "reply": m["is_reply"], "ack": m["is_ack"], "human": m["human"], "by": m["by_name"], "edited": m["edited"],
        }
        for m in db.q(f"select * from messages {where('campaign_id')} order by created_at, id", vp)
    ]
    acts = [
        {"id": a["id"], "t": ms(a["ts"]), "eid": a["enrollment_id"], "pid": a["prospect_id"], "cid": a["campaign_id"], "kind": a["kind"], "text": a["text"],
         "agent": a["agent"], "runId": a["run_id"], "msgId": a["msg_id"], "mode": a["mode"], "quiet": a["quiet"]}
        for a in db.q("select * from activity order by ts desc, seq desc limit %s", [MAX_ACTS if vis is None else MAX_ACTS * 3])
        if vis is None or a["campaign_id"] in vis
    ]
    jobs = _jobs(db, vis)
    approvals = [
        {"id": a["id"], "kind": a["kind"], "cid": a["campaign_id"], "eid": a["enrollment_id"], "t": ms(a["created_at"]), "status": a["status"],
         "runId": a["run_id"], "msgId": a["msg_id"], "stepNo": a["step_no"], "blocked": a["blocked"], "by": a["decided_by"], "at": ms(a["decided_at"]),
         "reason": a["reason"]}
        for a in db.q(f"select * from approvals {where('campaign_id')} order by created_at", vp)
    ]
    escal = [
        {"id": x["id"], "eid": x["enrollment_id"], "cid": x["campaign_id"], "reason": x["reason_code"], "rep": x["rep_id"], "t": ms(x["created_at"]),
         "status": x["status"], "msgId": x["msg_id"], "suggested": x["suggested"], "summary": x["summary"], "rule": x["rule"], "by": x["resolved_by"],
         "at": ms(x["resolved_at"])}
        for x in db.q(f"select * from escalations {where('campaign_id')} order by created_at", vp)
        if not user.is_rep or x["rep_id"] == user["id"]
    ]
    conflicts = [] if user.is_rep else [
        {"id": c["id"], "pid": c["prospect_id"], "cids": c["campaign_ids"], "rule": c["rule"], "winner": c["winner"], "status": c["status"], "code": c["code"],
         "decision": c["decision"], "t": ms(c["created_at"]), "by": c["resolved_by"]}
        for c in db.q("select * from conflicts order by created_at")
    ]
    meetings = [
        {"id": m["id"], "eid": m["enrollment_id"], "cid": m["campaign_id"], "pid": m["prospect_id"], "at": ms(m["slot_at"]), "rep": m["rep_id"], "label": m["label"]}
        for m in db.q(f"select * from meetings {where('campaign_id')} order by slot_at", vp)
    ]
    enr_ids = {e["id"] for e in enr}
    calls = [
        {"id": c["id"], "eid": c["enrollment_id"], "pid": c["prospect_id"], "at": ms(c["at"]), "dur": c["dur"], "disposition": c["disposition"], "mode": c["mode"],
         "runId": c["run_id"], "tr": c["transcript"], "summary": c["summary"]}
        for c in db.q("select * from calls order by at")
        if c["enrollment_id"] in enr_ids
    ]
    claims = {c["prospect_id"]: {"cid": c["campaign_id"], "since": ms(c["claimed_at"])} for c in db.q("select * from contact_claims where status = 'active'")}
    suppress = [] if user.is_rep else [
        {"id": s["id"], "kind": s["kind"], "value": s["value"], "reason": s["reason"], "by": s["added_by"], "at": ms(s["created_at"])}
        for s in db.q("select * from suppression_list order by created_at")
    ]
    prompts = [
        {"id": p["id"], "cid": p["campaign_id"], "role": p["agent_key"], "v": p["version"], "status": p["status"], "author": p["author_id"], "at": ms(p["created_at"]),
         "note": p["change_note"], "lines": p["lines"], "parent": p["parent_version"], "gold": p["gold"]}
        for p in db.q(f"select * from prompt_versions {where('campaign_id')} order by campaign_id, agent_key, version", vp)
    ]
    kb = _kb(db, vis)
    integ = {
        i["key"]: {"n": i["name"], "d": i["description"], "mode": i["mode"], "status": i["status"], "last": ms(i["last_check"]), "err": i["err"],
                   "canLive": i["can_live"], "paused": i["paused"]}
        for i in db.q("select * from integrations order by key")
    }
    settings = get_settings()
    crm_url = f"https://docs.google.com/spreadsheets/d/{settings.sheets_spreadsheet_id}/edit" if settings.sheets_enabled and settings.sheets_spreadsheet_id else None
    return {
        "now": ms(clock.now()),
        "user": {k: user[k] for k in ("id", "name", "role", "email")},
        "kill": {"at": ms(gs["kill_at"]), "by": gs["kill_by"]} if gs["kill_switch"] else None,
        "camps": camps, "users": users, "people": people, "enr": enr, "msgs": msgs, "acts": acts, "jobs": jobs, "approvals": approvals, "escal": escal,
        "conflicts": conflicts, "meetings": meetings, "calls": calls, "claims": claims, "suppress": suppress, "prompts": prompts, "kb": kb, "integ": integ,
        "hist": {}, "crmUrl": crm_url,
    }


def _suppressed_ids(db: Db) -> set[str]:
    rows = db.q(
        """select p.id from prospects p join companies c on c.id = p.company_id join suppression_list s
           on (s.kind = 'email' and lower(s.value) = lower(p.email)) or (s.kind = 'domain' and s.value = c.domain) or (s.kind = 'phone' and s.value = p.phone)"""
    )
    return {r["id"] for r in rows}


def _jobs(db: Db, vis: list[str] | None) -> list[dict]:
    cond = "" if vis is None else "and j.campaign_id = any(%s)"
    params: list = [] if vis is None else [vis]
    rows = db.q(
        f"""select j.*, r.model, r.prompt_version, r.campaign_version, r.summary, r.trace, r.tokens_in, r.tokens_out, r.cost_usd, r.latency_s, r.error as run_error
            from jobs j left join agent_runs r on r.id = j.id
            where (j.status <> 'done' or j.id in (select id from jobs where status = 'done' order by coalesce(ended_at, created_at) desc limit {MAX_DONE_JOBS})) {cond}
            order by j.created_at""",
        params,
    )
    out = []
    for j in rows:
        d = {
            "id": j["id"], "cid": j["campaign_id"], "eid": j["enrollment_id"], "pid": j["prospect_id"], "agent": j["agent"], "step": j["step"], "status": j["status"],
            "at": ms(j["created_at"]), "due": ms(j["run_at"]), "seed": j["is_seed"], "stepNo": j["step_no"], "msgId": j["msg_id"], "payload": j["payload"], "err": j["err"],
        }
        if j["is_replay"]:
            d["replay"] = True
        if j["started_at"]:
            d["start"] = ms(j["started_at"])
        if j["ended_at"]:
            d["end"] = ms(j["ended_at"])
        if j["trace"] is not None:
            d.update(model=j["model"], pv=j["prompt_version"], cv=j["campaign_version"], sum=j["summary"], tr=j["trace"], tin=j["tokens_in"], tout=j["tokens_out"],
                     cost=j["cost_usd"], dur=j["latency_s"])
        out.append(d)
    return out


def _kb(db: Db, vis: list[str] | None) -> dict:
    docs_rows = db.q("select * from knowledge_documents order by id")
    chunks = db.q("select id, document_id, content from knowledge_chunks order by id")
    by_doc: dict[str, list[str]] = {}
    for c in chunks:
        by_doc.setdefault(c["document_id"], []).append(c["id"])
    docs = [
        {"id": d["id"], "name": d["name"], "type": d["doc_type"], "scope": d["scope"], "chunks": by_doc.get(d["id"], []), "at": ms(d["ingested_at"])}
        for d in docs_rows
        if vis is None or d["scope"] == "global" or d["scope"] in vis
    ]
    keep = {k for d in docs for k in d["chunks"]}
    return {"docs": docs, "chunks": {c["id"]: {"id": c["id"], "doc": c["document_id"], "text": c["content"]} for c in chunks if c["id"] in keep}}


def signature(db: Db) -> str:
    """A hash of everything the UI shows, in one round trip so the page can poll it cheaply."""
    row = db.q1(
        """select md5(concat_ws('|',
            (select coalesce(max(seq), 0) from activity),
            (select count(*) from messages),
            (select md5(coalesce(string_agg(id || status, ',' order by id), '')) from jobs),
            (select md5(coalesce(string_agg(id || status, ',' order by id), '')) from approvals),
            (select md5(coalesce(string_agg(id || status, ',' order by id), '')) from escalations),
            (select md5(coalesce(string_agg(id || status || coalesce(winner, ''), ',' order by id), '')) from conflicts),
            (select md5(coalesce(string_agg(id || status || version::text || paused_held::text, ',' order by id), '')) from campaigns),
            (select md5(coalesce(string_agg(campaign_id || agent_key || enabled::text, ',' order by campaign_id, agent_key), '')) from campaign_agents),
            (select md5(coalesce(string_agg(campaign_id || channel || enabled::text, ',' order by campaign_id, channel), '')) from channel_settings),
            (select md5(coalesce(string_agg(id || status, ',' order by id), '')) from prompt_versions),
            (select md5(coalesce(string_agg(id || active::text || rep_limit::text, ',' order by id), '')) from users),
            (select md5(coalesce(string_agg(key || mode || paused::text || status, ',' order by key), '')) from integrations),
            (select count(*) || '-' || coalesce(max(ingested_at)::text, '') from knowledge_documents),
            (select count(*) from suppression_list),
            (select count(*) from enrollments),
            (select kill_switch::text || demo_clock_offset_hours::text from global_settings),
            (select md5(coalesce(string_agg(id || state || coalesce(score, 0)::text, ',' order by id), '')) from enrollments),
            (select md5(coalesce(string_agg(prospect_id || campaign_id, ',' order by prospect_id), '')) from contact_claims where status = 'active'),
            (select count(*) from meetings),
            (select count(*) || '-' || coalesce(max(disposition), '') from calls),
            (select count(*) from prospects),
            (select md5(coalesce(string_agg(campaign_id || rep_id || active::text, ',' order by campaign_id, rep_id), '')) from rep_assignments)
        )) as v"""
    )
    return row["v"]


_cache: dict[str, tuple[str, float, dict]] = {}
_sig_cache: tuple[float, str] | None = None
SIG_CACHE_TTL = 1.0


def get_cached_signature(db: Db) -> str:
    global _sig_cache
    now = time.monotonic()
    if _sig_cache and (now - _sig_cache[0]) < SIG_CACHE_TTL:
        return _sig_cache[1]
    sig = signature(db)
    _sig_cache = (now, sig)
    return sig


def invalidate_state_cache() -> None:
    global _cache, _sig_cache
    _cache.clear()
    _sig_cache = None


@router.get("/state")
def get_state(user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    """Rebuilding takes two dozen queries, so an unchanged workspace is served from memory after one cheap signature query."""
    cache_key = "manager" if not user.is_rep else user["id"]
    sig = get_cached_signature(db)
    hit = _cache.get(cache_key)
    if hit and hit[0] == sig:
        cached_out = hit[2]
        return {**cached_out, "now": ms(clock.now()), "user": {k: user[k] for k in ("id", "name", "role", "email")}}
    out = build_state(db, user)
    _cache[cache_key] = (sig, time.monotonic(), out)
    return out


@router.get("/state/sig")
def get_sig(user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    return {"sig": get_cached_signature(db), "now": ms(clock.now())}
