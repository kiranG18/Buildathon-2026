"""Job handlers for the enrollment state machine: research, qualify, plan, draft, reply.

Each handler runs inside one transaction supplied by the worker. Agents never send anything: every send passes the policy gate,
takes a per-prospect advisory lock, and writes under an idempotency key, so a retry or a race cannot double-send.
"""

import time
from datetime import timedelta

from psycopg import errors as pgerr

from agents import qualifier as qual
from agents import researcher, templates, writer
from agents import sequencer as seq
from agents.util import f_d, f_dt
from backend.channels import base as channels
from backend.conflicts.claims import cancel_pending_steps, release_claim, resolve_claim
from backend.core import clock
from backend.core.config import get_settings
from backend.core.db import Db, J
from backend.core.errors import ChannelError
from backend.orchestrator import defs
from backend.orchestrator.defs import CH_INTEG, CH_NAME, KB_ICP, KB_ICP2, MIN, H, tk
from backend.orchestrator.repo import (
    act,
    active_version,
    campaign,
    enqueue,
    enrollment,
    finish_job,
    first,
    mk_msg,
    prospect,
    rep_for,
    save_enr,
    set_state,
)
from backend.policy import gate, grounding


def _sleep_latency() -> None:
    ms = get_settings().fake_latency_ms
    if ms:
        time.sleep(ms / 1000)


def run_job(db: Db, job: dict) -> None:
    fn = STEPS.get(job["step"])
    if fn is None:
        raise ValueError(f"unknown step {job['step']}")
    fn(db, job)


def _requeue_later(db: Db, job: dict, minutes: int = 1) -> None:
    db.x("update jobs set status = 'queued', run_at = %s where id = %s", (clock.now() + timedelta(minutes=minutes), job["id"]))


# --- research -------------------------------------------------------------------------------------------------------------

def do_research(db: Db, job: dict) -> None:
    e = enrollment(db, job["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    from backend.orchestrator import dronahq

    res = dronahq.research(db, e, p, c) if dronahq.enabled("Researcher") else researcher.research(p)
    p = prospect(db, e["prospect_id"])
    if res.provider == "direct" and not p["researched"]:
        facts = [*p["facts"], *res.new_facts]
        db.x("update prospects set facts = %s, rich = %s, researched = true where id = %s", (J(facts), J([]), p["id"]))
        p["facts"] = facts
    n = len(res.new_facts)
    summary = "No sources matched. 0 facts saved" if p["is_empty"] and not p["facts"] else f"Saved {n} new fact{'' if n == 1 else 's'}, {len(p['facts'])} on file"
    set_state(db, e, "researched")
    trace = {"input": f"{p['full_name']}, {p['title']}, {p['company']}. Tools: web search, enrichment, URL parser.", "output": summary + "." + res.note, "chunks": [],
             "facts": [f["id"] for f in p["facts"]], "gaps": res.gaps}
    finish_job(db, job, summary=summary, trace=trace, provider=res.provider)
    act(db, e, "research", f"Researcher: {summary.lower()} for {p['full_name']}", run_id=job["id"], agent="Researcher")
    enqueue(db, e, "qualify")


# --- qualify --------------------------------------------------------------------------------------------------------------

def do_qualify(db: Db, job: dict) -> None:
    e = enrollment(db, job["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    key = tk(c)
    icp_chunk = KB_ICP.get(key, "K-101")
    rej = qual.hard_reject(p, c)
    if rej:
        crit = templates.crit_for(p, key)
        set_state(db, e, "rejected", reject=rej, score=None, crit=crit)
        finish_job(db, job, summary="Rule reject: " + rej, cost=0.0, trace={"input": "Hard exclusion rules for " + c["name"],
                   "output": f"decision: reject\nreason: {rej}\nModel calls: 0. Rules reject before any model runs.", "chunks": [icp_chunk]})
        act(db, e, "qualify", f"Rejected {p['full_name']} ({p['company']}): {rej}", run_id=job["id"], agent="Qualifier")
        return
    _sleep_latency()
    j = qual.judge(db, e, p, c)
    crit = j.crit
    sc = qual.score(crit) if qual.runtime.live() else templates.score_of(c["id"], p["id"], crit)
    no_facts = bool(p["is_empty"] and not p["facts"])
    dec = "borderline" if j.failed else qual.decide(sc, c["thr"], no_facts)
    miss = [x["label"] for x in crit if x["st"] == "unk"]
    out = (f"decision: {dec}\nscore: {sc}\nreasons: " + "; ".join(f"{x['label']} {({'met': 'met', 'part': 'partial', 'unk': 'unknown', 'no': 'not met'})[x['st']]}" for x in crit)
           + f"\nmissing: {'; '.join(miss) or 'none'}" + (f"\nagent_failure: {j.error}" if j.failed else ""))
    finish_job(db, job, summary=f"Score {sc}, {dec}" + (" (agent_failure)" if j.failed else ""), trace={"input": f"Facts on file: {len(p['facts'])}. Threshold {c['thr']}.", "output": out,
               "chunks": j.chunks or [icp_chunk, KB_ICP2.get(key, "K-102")]}, model=j.model or None, tokens_in=j.tokens_in or None, tokens_out=j.tokens_out or None,
               cost=j.cost, latency=j.latency, provider=j.provider, prompt_version=j.prompt_version)
    if dec == "reject":
        set_state(db, e, "rejected", reject=f"Score {sc} is below the review band", score=sc, crit=crit)
        act(db, e, "qualify", f"Rejected {p['full_name']}: score {sc}", run_id=job["id"], agent="Qualifier")
        return
    if dec == "borderline":
        note = ("The Qualifier could not return a valid answer, so a person makes the call." if j.failed
                else "No facts found, so the Qualifier will not guess." if no_facts
                else f"{len(miss)} of {len(crit)} criteria have no evidence yet, so a person makes the call.")
        set_state(db, e, "borderline", score=sc, crit=crit, review_note=note)
        db.x("insert into approvals (id, kind, campaign_id, enrollment_id, created_at, status, run_id) values (%s,'borderline',%s,%s,%s,'open',%s)",
             (db.nid("AP-"), c["id"], e["id"], clock.now(), job["id"]))
        act(db, e, "qualify", f"{p['full_name']} needs review: score {sc}, {note.lower()}", run_id=job["id"], agent="Qualifier")
        return
    set_state(db, e, "researched", score=sc, crit=crit)
    _qualify_or_defer(db, e, p, sc, job["id"])


def _qualify_or_defer(db: Db, e: dict, p: dict, sc: int, run_id: str | None) -> None:
    decision = resolve_claim(db, e)
    if decision.dec == "block":
        set_state(db, e, "stopped", reject="Suppressed")
        return
    if decision.dec == "defer":
        set_state(db, e, "deferred", defer_note=decision.note)
        act(db, e, "conflict", f"{p['full_name']} qualified in {e['campaign_id']} at {sc}. Deferred: {decision.note}", run_id=run_id, agent="Qualifier")
        return
    set_state(db, e, "qualified")
    act(db, e, "qualify", f"Qualified {p['full_name']} at {sc}", run_id=run_id, agent="Qualifier")
    enqueue(db, e, "plan")


# --- plan -----------------------------------------------------------------------------------------------------------------

def allowed_channels(db: Db, e: dict, c: dict) -> list[str]:
    rep = rep_for(db, e, c)
    paused = {r["key"] for r in db.q("select key from integrations where paused")}
    return [ch for ch in defs.CHANNELS if c["channels"].get(ch) and CH_INTEG[ch] not in paused and ch in (rep["channels"] or [])]


def do_plan(db: Db, job: dict) -> None:
    e = enrollment(db, job["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    now = clock.ms(clock.now())
    allowed = allowed_channels(db, e, c)
    t0 = clock.ms(e["first_due"]) if e["first_due"] else now + MIN
    _sleep_latency()
    out = seq.build_plan(db, e, p, c, allowed, t0)
    save_enr(db, e, plan=out.steps)
    kept = [s for s in out.steps if s["status"] != "skipped"]
    txt = "\n".join(f"Day {s['day']}: {CH_NAME[s['ch']]} {s['purpose']}{' (skipped)' if s['status'] == 'skipped' else ''}\n  reason: {s['reason']}" for s in out.steps)
    if out.fallback:
        txt += f"\n{out.note}"
    finish_job(db, job, summary="Plan: " + ", ".join(f"{CH_NAME[s['ch']]} d{s['day']}" for s in kept),
               trace={"input": f"allowed_channels: {', '.join(allowed)}. Sequence default: {c['seq_order']}.", "output": txt, "chunks": out.chunks},
               model=out.model or None, tokens_in=out.tokens_in, tokens_out=out.tokens_out, cost=out.cost, latency=out.latency, prompt_version=out.prompt_version)
    act(db, e, "plan", f"Planned {len(kept)} touches for {p['full_name']}", run_id=job["id"], agent="Sequencer")
    if out.fallback:
        act(db, e, "plan", f"sequencer_fallback for {p['full_name']}: default sequence used", agent="Sequencer", reason_code="sequencer_fallback", quiet=True)
    dispatch_due(db, e)


def dispatch_due(db: Db, e: dict) -> None:
    e = enrollment(db, e["id"])
    plan = e["plan"] or []
    now = clock.ms(clock.now())
    changed = False
    has_inbound = db.q1("select 1 as x from messages where enrollment_id = %s and direction = 'in' limit 1", (e["id"],)) is not None
    open_gate_approval = db.q1("select 1 as x from approvals where enrollment_id = %s and status = 'open' and kind <> 'borderline' limit 1", (e["id"],)) is not None
    for i, s in enumerate(plan):
        if s["status"] != "pending" or s["due"] > now or s.get("queued"):
            continue
        if s.get("cond") == "engaged" and not has_inbound:
            continue
        if s.get("cond") == "warm" and not has_inbound and not e["warm"]:
            s["status"], s["reason"], changed = "skipped", "SMS stays off until the prospect is warm", True
            continue
        if e["state"] not in defs.ACTIVE_STATES or open_gate_approval:
            continue
        s["queued"], changed = True, True
        enqueue(db, e, "draft", due=clock.from_ms(s["due"]), step_no=i)
    if changed:
        save_enr(db, e, plan=plan)


def scan_due(db: Db, campaign_id: str | None = None) -> None:
    sql = """select e.* from enrollments e join campaigns c on c.id = e.campaign_id
             where c.status = 'live' and e.state in ('qualified', 'contacted') and jsonb_array_length(e.plan) > 0"""
    rows = db.q(sql + (" and e.campaign_id = %s" if campaign_id else ""), (campaign_id,) if campaign_id else ())
    for e in rows:
        sent = db.q1("select count(*) as n from messages where enrollment_id = %s and direction = 'out' and not is_reply and status = 'sent'", (e["id"],))["n"]
        open_left = any(s["status"] == "pending" for s in e["plan"])
        if e["state"] == "contacted" and sent >= 4 and open_left:
            cancel_pending_steps(db, e, "Four touches without a reply")
            release_claim(db, e, "sequence exhausted")
            p = prospect(db, e["prospect_id"])
            set_state(db, e, "stopped", reject="Sequence exhausted after four touches")
            act(db, e, "stop", f"Stopped {p['full_name']}: four touches without a reply")
            continue
        dispatch_due(db, e)


# --- draft and send -------------------------------------------------------------------------------------------------------

def _mk_trace(job: dict, st: dict, p: dict, comp: dict, gc: dict, g: dict, wv: int, step_no: int, extra: dict | None = None) -> dict:
    tr = {"input": f"Step {step_no + 1}: {CH_NAME[st['ch']]} {st['purpose']}. Facts on file: {len(p['facts'])}. Writer prompt v{wv}.", "output": comp["body"],
          "chunks": sorted({x["src"] for x in comp["claims"] if x["src"].startswith("K")}), "claims": comp["claims"], "segs": comp["segs"], "gate": g,
          "grounded": {"total": gc["total"], "bad": len(gc["bad"])}}
    tr.update(extra or {})
    return tr


def do_draft(db: Db, job: dict) -> None:
    e = enrollment(db, job["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    plan = e["plan"]
    step_no = job["step_no"]
    st = plan[step_no]
    if db.q1("select 1 as x from approvals where enrollment_id = %s and status = 'open' and kind <> 'borderline' and step_no is distinct from %s limit 1", (e["id"], step_no)):
        st["queued"] = False
        save_enr(db, e, plan=plan)
        db.x("update jobs set status = 'cancelled' where id = %s", (job["id"],))
        return
    db.lock("prospect:" + p["id"])
    wv = active_version(db, c["id"], "Writer")
    rep = rep_for(db, e, c)
    now_ms = clock.ms(clock.now())
    _sleep_latency()
    try:
        d = writer.draft(db, e, p, c, st["purpose"], channel=st["ch"], version=wv, rep_name=rep["name"], now_ms=now_ms)
    except writer.KnowledgeGap as gap:
        finish_job(db, job, summary="Blocked: knowledge_gap", trace={"input": f"Step {step_no + 1}", "output": str(gap), "chunks": []})
        db.x("insert into escalations (id, enrollment_id, campaign_id, reason_code, rep_id, created_at, summary, rule, created_by_agent) values (%s,%s,%s,'knowledge_gap',%s,%s,%s,%s,'Writer')",
             (db.nid("ES-"), e["id"], c["id"], rep["id"], clock.now(), f"No knowledge found to ground a {st['purpose']} for {p['full_name']}", "retrieval returned nothing"))
        act(db, e, "gate", f"Writer found no knowledge for {p['full_name']}: knowledge_gap escalation", run_id=job["id"], agent="Writer", reason_code="knowledge_gap")
        return
    comp = d.comp
    gc = grounding.check(db, comp, p, c["id"])
    same_day = any(i != step_no and s["status"] == "done" and s["day"] == st["day"] for i, s in enumerate(plan))
    g = gate.evaluate(db, e, st["ch"], same_day=same_day)
    if g["dec"] == "replan":
        al = allowed_channels(db, e, c)
        if st["ch"] != "email" and "email" in al:
            st["reason"] = f"{CH_NAME[st['ch']]} is paused, so this touch moved to email"
            st["ch"] = "email"
            if st["purpose"] in ("connect", "message"):
                st["purpose"] = "nudge"
            d = writer.draft(db, e, p, c, st["purpose"], channel="email", version=wv, rep_name=rep["name"], now_ms=now_ms)
            comp = d.comp
            gc = grounding.check(db, comp, p, c["id"])
            g = gate.evaluate(db, e, "email", same_day=same_day)
            save_enr(db, e, plan=plan)
        else:
            st["status"], st["reason"] = "skipped", "No allowed channel for this step"
            save_enr(db, e, plan=plan)
            finish_job(db, job, summary="Skipped: no allowed channel", trace={"input": f"Step {step_no + 1}", "output": "No channel available.", "chunks": [], "gate": g})
            return
    extra = {"regenerated": d.regenerated, "generic_safe": d.generic_safe, "failures": d.failures}
    kw = dict(model=d.model or None, tokens_in=d.tokens_in, tokens_out=d.tokens_out, cost=d.cost, latency=d.latency, prompt_version=wv, role="Writer")

    def trace() -> dict:
        return _mk_trace(job, st, p, comp, gc, g, wv, step_no, extra)

    if g["dec"] == "hold":
        _requeue_later(db, job)
        return
    kind = "voice" if st["ch"] == "voice" else "first_touch"
    if gc["bad"] and g["dec"] not in ("block", "defer"):
        m = mk_msg(db, e, st["ch"], "out", comp["body"], segs=comp["segs"], subject=comp["subject"], status="pending", run_id=job["id"], kind=st["purpose"], step_no=step_no, prompt_version=wv)
        finish_job(db, job, summary="Verifier blocked the draft", trace=trace(), msg_id=m["id"], **kw)
        db.x("insert into approvals (id, kind, campaign_id, enrollment_id, created_at, status, run_id, msg_id, step_no, blocked) values (%s,%s,%s,%s,%s,'open',%s,%s,%s,true)",
             (db.nid("AP-"), kind, c["id"], e["id"], clock.now(), job["id"], m["id"], step_no))
        if e["state"] == "qualified":
            set_state(db, e, "awaiting_approval")
        act(db, e, "gate", f"Verifier blocked a Writer draft for {p['full_name']}: a claim has no evidence. A person must edit it", run_id=job["id"], agent="Guardian", msg_id=m["id"], reason_code="grounding_failed")
        return
    if g["dec"] == "block":
        finish_job(db, job, summary="Blocked: " + g["reason"], trace=trace(), **kw)
        st["status"] = "blocked"
        save_enr(db, e, plan=plan)
        act(db, e, "gate", f"Guardian blocked {CH_NAME[st['ch']]} to {p['full_name']}: {g['reason']}", run_id=job["id"], agent="Guardian", reason_code=g["reason"])
        return
    if g["dec"] == "defer":
        finish_job(db, job, summary="Deferred: " + g["reason"], trace=trace(), **kw)
        until = g["until"] or now_ms + 6 * H
        st["due"], st["queued"] = until, True
        save_enr(db, e, plan=plan, hold={"code": g["reason"], "until": g["until"]})
        act(db, e, "gate", f"Guardian deferred {CH_NAME[st['ch']]} to {p['full_name']}: {g['reason']}{', until ' + f_dt(g['until']) if g['until'] else ''}", run_id=job["id"], agent="Guardian", reason_code=g["reason"])
        enqueue(db, e, "draft", due=clock.from_ms(until), step_no=step_no)
        return
    if g["dec"] == "needs_approval":
        m = mk_msg(db, e, st["ch"], "out", comp["body"], segs=comp["segs"], subject=comp["subject"], status="pending", run_id=job["id"], kind=st["purpose"], step_no=step_no, prompt_version=wv)
        finish_job(db, job, summary="Drafted, waiting for approval", trace=trace(), msg_id=m["id"], **kw)
        db.x("insert into approvals (id, kind, campaign_id, enrollment_id, created_at, status, run_id, msg_id, step_no) values (%s,%s,%s,%s,%s,'open',%s,%s,%s)",
             (db.nid("AP-"), kind, c["id"], e["id"], clock.now(), job["id"], m["id"], step_no))
        if e["state"] == "qualified":
            set_state(db, e, "awaiting_approval")
        act(db, e, "draft", f"Writer drafted a {CH_NAME[st['ch']]} {st['purpose']} for {p['full_name']}. Waiting for approval", run_id=job["id"], agent="Writer", msg_id=m["id"])
        return
    send_step(db, e, p, c, job, st, step_no, comp, trace, wv, kw)


def send_step(db: Db, e: dict, p: dict, c: dict, job: dict | None, st: dict, step_no: int, comp: dict, trace, wv: int, kw: dict, approved_by: str | None = None) -> dict | None:
    """Write the outbound message under its idempotency key, hand it to the channel, and advance the enrollment."""
    key = f"{e['id']}:{step_no}:{st['ch']}"
    try:
        with db.conn.transaction():
            m = mk_msg(db, e, st["ch"], "out", comp["body"], segs=comp["segs"], subject=comp["subject"], run_id=job["id"] if job else None, kind=st["purpose"], step_no=step_no,
                       prompt_version=wv, approved_by=approved_by, idempotency_key=key, gate_decision="allow")
            channels.send_message(db, m, p)
    except pgerr.UniqueViolation:
        if job:
            finish_job(db, job, summary="Duplicate send prevented", trace=trace(), **kw)
        return None
    except ChannelError as err:
        raise err
    st["status"], st["doneAt"], st["msgId"], st["queued"] = "done", clock.ms(clock.now()), m["id"], False
    save_enr(db, e, plan=e["plan"], last_touch=clock.now(), hold=None)
    if e["state"] in ("qualified", "awaiting_approval"):
        set_state(db, e, "contacted")
    if job:
        finish_job(db, job, summary=f"Sent {CH_NAME[st['ch']]} {st['purpose']}" + (" (approved)" if approved_by else ""), trace=trace(), msg_id=m["id"], **kw)
    act(db, e, "send", f"{CH_NAME[st['ch']]} {st['purpose']} sent to {p['full_name']}", run_id=job["id"] if job else None, agent="Writer", msg_id=m["id"], mode=m["mode"])
    return m


# --- reply ----------------------------------------------------------------------------------------------------------------

def do_reply(db: Db, job: dict) -> None:
    from backend.orchestrator.replies import send_reply

    send_reply(db, job)


STEPS = {"research": do_research, "qualify": do_qualify, "plan": do_plan, "draft": do_draft, "reply": do_reply}

__all__ = ["run_job", "scan_due", "dispatch_due", "allowed_channels", "STEPS", "f_d", "first"]
