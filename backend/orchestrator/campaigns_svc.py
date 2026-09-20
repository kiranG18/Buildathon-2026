"""Campaign lifecycle: create, edit (each edit is a new version snapshot), pre-launch checklist, activate, complete, archive, duplicate, dry run."""

import random

from agents import writer
from agents.util import js_hash
from backend.core import clock
from backend.core.db import Db, J
from backend.core.errors import NotFound, StateConflict
from backend.orchestrator import discovery, prompts_svc
from backend.orchestrator.defs import AGENTS, CHANNELS, ROLES, static, tk
from backend.orchestrator.repo import act, active_version, campaign, enrollment, new_enrollment, prospect
from backend.policy import grounding

INTEG_OF = {"email": "gmail", "linkedin": "linkedin", "sms": "twilio", "voice": "voice"}


def snapshot(db: Db, c: dict, by: str, note: str) -> None:
    db.x(
        "insert into campaign_versions (campaign_id, version, config, changed_by, changed_at, note) values (%s,%s,%s,%s,%s,%s)",
        (c["id"], c["version"], J({k: c[k] for k in ("name", "objective", "thr", "daily_send_cap", "appr", "priority", "ch_limit")} | {"channels": c["channels"], "agents": c["agents"], "reps": c["reps"]}), by, clock.now(), note),
    )


def checklist(db: Db, campaign_id: str) -> list[dict]:
    c = campaign(db, campaign_id)
    docs = db.q("select doc_type from knowledge_documents where campaign_id = %s or scope = 'global'", (campaign_id,))
    n_chunks = db.q1("select count(*) as n from knowledge_chunks where campaign_id = %s or scope = 'global'", (campaign_id,))["n"]
    types = {d["doc_type"] for d in docs}
    integ_ok = {r["key"]: r["status"] == "ok" for r in db.q("select key, status from integrations")}
    ch_ok = [ch for ch, on in c["channels"].items() if on and integ_ok.get(INTEG_OF[ch])]
    reps = [r for r in db.q("select * from users where id = any(%s)", (c["reps"],)) if r["active"] and r["rep_limit"] > 0]
    roles_ok = {r["agent_key"] for r in db.q("select agent_key from prompt_versions where campaign_id = %s and status = 'active'", (campaign_id,))}
    return [
        {"name": "icp", "passed": bool(c["roles"] and c["geo_list"] and c["exclusions"]), "detail": "ICP has at least one role, one geography and one exclusion rule"},
        {"name": "prompts", "passed": all(r in roles_ok for r in ROLES), "detail": "Every enabled agent has an active prompt version"},
        {"name": "knowledge", "passed": n_chunks >= 8 and "case study" in types and "objections" in types,
         "detail": f"At least 8 knowledge chunks, including one case study and one objection ({n_chunks} now)"},
        {"name": "channel", "passed": bool(ch_ok), "detail": "At least one channel is enabled with a verified sender"},
        {"name": "reps", "passed": bool(reps), "detail": "At least one rep is assigned, with limits set"},
        {"name": "dry_run", "passed": bool(c["dry_ok"]), "detail": "A dry run on 3 sample prospects passed the grounding check"},
    ]


def volume_estimate(c: dict) -> dict:
    n = min(c["daily_send_cap"], sum(1 for v in c["channels"].values() if v) * 12)
    return {"touches_per_day": n, "model_cost_per_day": round(n * 0.056, 3)}


def _next_id(db: Db) -> str:
    row = db.q1("select coalesce(max(substr(id, 2)::int), 0) + 1 as n from campaigns where id ~ '^C[0-9]+$'")
    return f"C{row['n']}"


def attach_docs(db: Db, campaign_id: str, doc_ids: list[str]) -> None:
    """Copy documents (and their chunks, with embeddings) from other campaigns into this one. Copies keep origin_id so citations of the original id still verify."""
    db.x("delete from knowledge_documents where campaign_id = %s", (campaign_id,))
    for did in doc_ids:
        src = db.q1("select * from knowledge_documents where id = %s", (did,))
        if not src:
            continue
        new_id = f"{campaign_id}-{did}"
        db.x("insert into knowledge_documents (id, name, doc_type, scope, campaign_id, metadata, ingested_at) values (%s,%s,%s,%s,%s,%s,%s)",
             (new_id, src["name"], src["doc_type"], campaign_id, campaign_id, J(src["metadata"]), clock.now()))
        for ch in db.q("select * from knowledge_chunks where document_id = %s", (did,)):
            db.x(
                """insert into knowledge_chunks (id, document_id, campaign_id, origin_id, scope, doc_type, tags, content, embedding, token_count, citation_label)
                   select %s, %s, %s, coalesce(origin_id, id), %s, doc_type, tags, content, embedding, token_count, citation_label from knowledge_chunks where id = %s""",
                (db.nid("K-U"), new_id, campaign_id, campaign_id, ch["id"]),
            )


def create(db: Db, body: dict, by: dict) -> dict:
    cid = _next_id(db)
    thr = int(body.get("thr") or 70)
    tpl = body.get("tpl") or "C1"
    appr = {"first": bool(body.get("first")), "voice": body.get("voice", True), "reply": body.get("reply", True)}
    channels = {ch: bool((body.get("channels") or {}).get(ch)) for ch in CHANNELS}
    db.x(
        """insert into campaigns (id, name, owner_id, status, objective, icp, personas, geo, signals, seq_order, tone, words, approval_text, roles, geo_list, exclusions, refs, thr, appr,
           daily_send_cap, priority, ch_limit, version, created_at, tpl) values (%s,%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s,90,%s,%s,%s,%s,%s,%s,%s,%s,50,%s,1,%s,%s)""",
        (cid, body["name"].strip(), by["id"], body.get("objective", ""), body.get("icp") or body["name"], ", ".join(body.get("roles", [])), ", ".join(body.get("geo_list", [])),
         "Headcount, stage, hiring signals, stack fit", ", ".join(k.capitalize() for k, v in channels.items() if v), body.get("tone", ""),
         "Every first touch needs approval" if appr["first"] else "First touch autonomous", body.get("roles", []), body.get("geo_list", []), body.get("exclusions", []),
         body.get("refs", ""), thr, J(appr), int(body.get("daily_send_cap", 30)), J({"email": 40, "linkedin": 20, "sms": 10, "voice": 5}), clock.now(), tpl),
    )
    agents = body.get("agents") or {}
    for a in AGENTS:
        db.x("insert into campaign_agents (campaign_id, agent_key, enabled, provider) values (%s,%s,%s,%s)",
             (cid, a, agents.get(a, True), "dronahq" if a in ("Researcher", "Responder", "Caller") else "direct"))
    for ch, on in channels.items():
        db.x("insert into channel_settings (campaign_id, channel, enabled, daily_limit) values (%s,%s,%s,%s)", (cid, ch, on, {"email": 40, "linkedin": 20, "sms": 10, "voice": 5}[ch]))
    rep_ids = body.get("rep_ids") or [r["id"] for r in db.q("select id from users where role = 'Rep' and active order by id limit 1")]
    for r in rep_ids:
        db.x("insert into rep_assignments (rep_id, campaign_id) values (%s,%s)", (r, cid))
    c = campaign(db, cid)
    prompts_svc.seed_prompts(db, c, by["id"])
    doc_ids = body.get("doc_ids")
    if not doc_ids:
        doc_ids = [d["id"] for d in db.q("select id from knowledge_documents where campaign_id = %s", (tpl,))]
    attach_docs(db, cid, doc_ids)
    snapshot(db, c, by["name"], "Created as a Draft")
    act(db, None, "agent", f"{by['name']} created the draft campaign {c['name']}", cid=cid, agent="Manager")
    return {"id": cid, "status": "draft"}


EDITABLE = {"name": "name", "objective": "objective", "thr": "thr", "daily_send_cap": "daily_send_cap", "priority": "priority", "tone": "tone", "icp": "icp", "refs": "refs"}


def update(db: Db, campaign_id: str, body: dict, by: dict) -> dict:
    c = campaign(db, campaign_id)
    if c["status"] in ("completed", "archived"):
        raise StateConflict("A closed campaign is read-only")
    changed = []
    for k, col in EDITABLE.items():
        if k in body and body[k] is not None:
            db.x(f"update campaigns set {col} = %s where id = %s", (body[k], campaign_id))
            changed.append(k)
    if "appr" in body:
        db.x("update campaigns set appr = %s where id = %s", (J({**c["appr"], **body["appr"]}), campaign_id))
        changed.append("appr")
    if "ch_limit" in body:
        db.x("update campaigns set ch_limit = %s where id = %s", (J({**c["ch_limit"], **body["ch_limit"]}), campaign_id))
        for ch, v in body["ch_limit"].items():
            db.x("update channel_settings set daily_limit = %s where campaign_id = %s and channel = %s", (v, campaign_id, ch))
        changed.append("ch_limit")
    for k in ("roles", "geo_list", "exclusions"):
        if k in body:
            db.x(f"update campaigns set {k} = %s where id = %s", (body[k], campaign_id))
            changed.append(k)
    if "rep_ids" in body:
        db.x("update rep_assignments set active = false where campaign_id = %s", (campaign_id,))
        for r in body["rep_ids"]:
            db.x("insert into rep_assignments (rep_id, campaign_id, active) values (%s,%s,true) on conflict (rep_id, campaign_id) do update set active = true", (r, campaign_id))
        changed.append("reps")
    if "doc_ids" in body:
        attach_docs(db, campaign_id, body["doc_ids"])
        changed.append("knowledge")
    if not changed:
        return {"id": campaign_id, "version": c["version"]}
    db.x("update campaigns set version = version + 1, dry_ok = case when %s then false else dry_ok end where id = %s", (bool(set(changed) & {"roles", "geo_list", "exclusions", "knowledge", "tone"}), campaign_id))
    c2 = campaign(db, campaign_id)
    snapshot(db, c2, by["name"], "Changed " + ", ".join(changed))
    act(db, None, "agent", f"{by['name']} changed {', '.join(changed)} on {c['name']}. Campaign version {c2['version']}", cid=campaign_id, agent="Manager")
    return {"id": campaign_id, "version": c2["version"], "campaign_version_id": f"{campaign_id}-v{c2['version']}"}


def activate(db: Db, campaign_id: str, by: dict) -> dict:
    c = campaign(db, campaign_id)
    if c["status"] != "draft":
        raise StateConflict(f"Only a Draft can be activated. This one is {c['status']}", code="not_draft")
    checks = checklist(db, campaign_id)
    if not all(x["passed"] for x in checks):
        raise StateConflict("The pre-launch checklist has failing items", code="checklist_failed", extra={"checks": checks})
    db.x("update campaigns set status = 'live', version = greatest(version, 1) where id = %s", (campaign_id,))
    act(db, None, "resume", f"{by['name']} activated {c['name']}", cid=campaign_id, agent="Manager")
    for e in db.q("select * from enrollments where campaign_id = %s and state = 'new'", (campaign_id,)):
        from backend.orchestrator.repo import enqueue

        if not db.q1("select 1 as x from jobs where enrollment_id = %s and step = 'research'", (e["id"],)):
            enqueue(db, e, "research")
    return {"status": "live"}


def close(db: Db, campaign_id: str, by: dict, status: str) -> dict:
    c = campaign(db, campaign_id)
    allowed = {"completed": ("live", "paused"), "archived": ("completed", "draft", "paused", "live")}[status]
    if c["status"] not in allowed:
        raise StateConflict(f"A {c['status']} campaign cannot become {status}")
    db.x("update campaigns set status = %s where id = %s", (status, campaign_id))
    db.x("update jobs set status = 'cancelled' where campaign_id = %s and status = 'queued'", (campaign_id,))
    act(db, None, "stop", f"{by['name']} {'completed' if status == 'completed' else 'archived'} {c['name']}", cid=campaign_id, agent="Manager")
    return {"status": status}


def duplicate(db: Db, campaign_id: str, by: dict, name: str | None = None) -> dict:
    c = campaign(db, campaign_id)
    cid = _next_id(db)
    new_name = name or f"{c['name']}: Variant B"
    db.x(
        """insert into campaigns (id, name, owner_id, status, objective, icp, personas, geo, signals, seq_order, tone, words, approval_text, roles, geo_list, exclusions, refs, thr, appr,
           daily_send_cap, priority, ch_limit, version, parent_id, created_at, tpl)
           select %s, %s, %s, 'draft', objective, icp, personas, geo, signals, seq_order, tone, words, approval_text, roles, geo_list, exclusions, refs, thr, appr,
           daily_send_cap, priority, ch_limit, 1, id, %s, coalesce(tpl, id) from campaigns where id = %s""",
        (cid, new_name, by["id"], clock.now(), campaign_id),
    )
    for a, on in c["agents"].items():
        db.x("insert into campaign_agents (campaign_id, agent_key, enabled, provider) values (%s,%s,%s,'direct')", (cid, a, on))
    for ch, on in c["channels"].items():
        db.x("insert into channel_settings (campaign_id, channel, enabled, daily_limit) values (%s,%s,%s,%s)", (cid, ch, on, c["ch_limit"].get(ch, 0)))
    for r in c["reps"]:
        db.x("insert into rep_assignments (rep_id, campaign_id) values (%s,%s)", (r, cid))
    for p in db.q("select * from prompt_versions where campaign_id = %s and status = 'active'", (campaign_id,)):
        db.x("insert into prompt_versions (id, campaign_id, agent_key, version, status, author_id, created_at, change_note, lines) values (%s,%s,%s,1,'active',%s,%s,%s,%s)",
             (f"{cid}-{p['agent_key']}-v1", cid, p["agent_key"], by["id"], clock.now(), f"Copied from {campaign_id} v{p['version']}", J(p["lines"])))
    attach_docs(db, cid, [d["id"] for d in db.q("select id from knowledge_documents where campaign_id = %s", (campaign_id,))])
    snapshot(db, campaign(db, cid), by["name"], f"Duplicated from {campaign_id}")
    act(db, None, "agent", f"{by['name']} duplicated {c['name']} as {new_name}", cid=cid, agent="Manager")
    return {"id": cid, "parent_campaign_id": campaign_id, "name": new_name}


class _Rollback(Exception):
    pass


def dry_run(db: Db, campaign_id: str) -> dict:
    """Run the Writer and the grounding check on three sample prospects. Nothing is stored and no channel is attached."""
    c = campaign(db, campaign_id)
    key = discovery._key_for(c)
    results: list[dict] = []
    ok = True
    try:
        with db.conn.transaction():
            rng = random.Random(js_hash(campaign_id) + 9)
            for i, company in enumerate(static()["RESERVE"][key][:3]):
                name = f"Sample Prospect {campaign_id}{i + 1}"
                pr = discovery.make_prospect(db, name, (c["roles"] or ["CTO"])[0], company, key, rng)
                e = new_enrollment(db, pr["id"], campaign_id)
                p = prospect(db, pr["id"])
                db.x("update prospects set facts = facts || rich, rich = '[]'::jsonb where id = %s", (p["id"],))
                p = prospect(db, pr["id"])
                try:
                    d = writer.draft(db, enrollment(db, e["id"]), p, c, "intro", channel="email", version=active_version(db, campaign_id, "Writer"), rep_name="Sample Rep", now_ms=clock.ms(clock.now()))
                except writer.KnowledgeGap:
                    results.append({"agent": "Writer", "ok": False, "output_summary": "no knowledge to ground the draft. Attach a case study."})
                    ok = False
                    continue
                gc = grounding.check(db, d.comp, p, campaign_id)
                hallucinated = bool(gc["bad"]) or (d.generic_safe and any(x not in ("model_failure",) for x in d.failures))
                passed = not gc["bad"] and not hallucinated and bool(d.comp.get("claims"))
                ok = ok and passed
                if passed:
                    summary = d.comp["body"][:200]
                elif gc["bad"]:
                    summary = f"{len(gc['bad'])} claims without evidence: {', '.join(x['reason'] for x in gc['bad'][:2])}"
                elif d.generic_safe and d.failures:
                    summary = f"Draft failed: {'; '.join(d.failures)}"
                else:
                    summary = "Grounding check failed"
                results.append({"agent": "Writer", "ok": passed, "output_summary": summary})
            raise _Rollback
    except _Rollback:
        pass
    if not any(d["doc_type"] == "case study" for d in db.q("select doc_type from knowledge_documents where campaign_id = %s or scope = 'global'", (campaign_id,))):
        ok = False
        results.append({"agent": "Writer", "ok": False, "output_summary": "no customer result in the knowledge to ground the draft. Attach a case study."})
    db.x("update campaigns set dry_ok = %s where id = %s", (ok, campaign_id))
    return {"results": results, "grounding_passed": ok, "sample": results[0]["output_summary"] if results else ""}


def dashboard(db: Db, campaign_id: str) -> dict:
    from backend.analytics.rollups import funnel, stats
    from backend.orchestrator.controls import held_count

    c = campaign(db, campaign_id)
    jobs = {r["status"]: r["n"] for r in db.q("select status, count(*) as n from jobs where campaign_id = %s and not is_replay group by status", (campaign_id,))}
    held = held_count(db, campaign_id)
    return {
        "campaign": {"id": c["id"], "name": c["name"], "status": c["status"], "paused_by": c["paused_by"], "paused_at": clock.ms(c["paused_at"]), "held_jobs": held},
        "funnel": funnel(db, campaign_id),
        "stats": stats(db, campaign_id),
        "agents": {"running": jobs.get("running", 0), "queued": jobs.get("queued", 0), "held": held, "failed": jobs.get("failed", 0),
                   "pending_approvals": db.q1("select count(*) as n from approvals where campaign_id = %s and status = 'open'", (campaign_id,))["n"],
                   "escalations": db.q1("select count(*) as n from escalations where campaign_id = %s and status = 'open'", (campaign_id,))["n"]},
        "alerts": [{"type": "held_by_conflict", "count": db.q1("select count(*) as n from enrollments where campaign_id = %s and state = 'deferred'", (campaign_id,))["n"]}],
        "checklist": checklist(db, campaign_id) if c["status"] == "draft" else None,
        "volume": volume_estimate(c),
    }


__all__ = ["tk", "NotFound"]
