"""Inbound replies, approvals, escalations and conflict overrides.

ingest_reply is the single inbound function: Gmail polling, the Twilio webhook, the reply simulator and the voice post-webhook all call it.
Unsubscribe, out-of-office and bounce rules run before any model call.
"""

from agents import responder, runtime, templates, writer
from agents.util import f_d, f_dt, slots_for
from backend.channels import base as channels
from backend.conflicts.claims import cancel_pending_steps, release_claim, transfer_claim
from backend.core import clock
from backend.core.db import Db, J
from backend.core.errors import NotFound, StateConflict
from backend.orchestrator.defs import CH_NAME, ESC_LABEL, D, tk
from backend.orchestrator.handlers import _mk_trace, _requeue_later, allowed_channels, send_step
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

CLS_LABEL = {"positive": "positive", "book": "accepts a slot", "objection": "objection", "not_now": "not now", "unsubscribe": "opt-out", "ooo": "out of office",
             "escalate": "needs a human", "question": "question", "not_interested": "not interested"}
OBJECTION_MAP = {
    "inhouse": ("obj_inhouse", ["K-211", "K-208"]), "residency": ("obj_residency", ["K-312", "K-313"]), "competitor": ("obj_competitor", ["K-412"]),
    "budget": ("obj_budget", ["K-212"]), "pricing": ("pricing_answer", ["K-021", "K-022"]),
}
CASE_CHUNK = {"C1": "K-207", "C2": "K-307", "C3": "K-407"}


def cancel_all_pending(db: Db, e: dict, why: str) -> None:
    e = enrollment(db, e["id"])
    cancel_pending_steps(db, e, why, cancel_jobs=True)


def add_suppression(db: Db, kind: str, value: str, reason: str, by: str) -> None:
    db.x(
        "insert into suppression_list (id, kind, value, reason, added_by, created_at) values (%s,%s,%s,%s,%s,%s) on conflict (kind, value) do nothing",
        (db.nid("S-"), kind, value, reason, by, clock.now()),
    )


def book_meeting(db: Db, e: dict, slot: dict, by_agent: str) -> None:
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    rep = rep_for(db, e, c)
    save_enr(db, e, meeting={"t": slot["t"], "label": slot["label"]})
    set_state(db, e, "meeting")
    db.x("insert into meetings (id, enrollment_id, campaign_id, prospect_id, slot_at, rep_id, label, source) values (%s,%s,%s,%s,%s,%s,%s,%s)",
         (db.nid("MT-"), e["id"], e["campaign_id"], p["id"], clock.from_ms(slot["t"]), rep["id"], slot["label"], by_agent))
    act(db, e, "meeting", f"Meeting booked with {p['full_name']}: {slot['label']}", agent=by_agent)
    release_claim(db, e, "meeting booked")


def ingest_reply(db: Db, e: dict, ch: str, text: str, *, external_id: str | None = None, rfc_message_id: str | None = None) -> dict:
    db.lock("enr:" + e["id"])
    e = enrollment(db, e["id"])
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    rep = rep_for(db, e, c)
    now_ms = clock.ms(clock.now())
    key = tk(c)
    rd = responder.read(db, e, p, c, text)
    cls, sub = rd.cls, rd.sub
    if rd.escalate_low_confidence:
        cls, sub = "escalate", "human_request"
    inm = mk_msg(db, e, ch, "in", text, classification=cls, rule=rd.rule, sub=sub, external_id=external_id, rfc_message_id=rfc_message_id)
    save_enr(db, e, warm=True)
    act(db, e, "reply", f"{p['full_name']} replied on {CH_NAME[ch]}: {CLS_LABEL[cls]}", msg_id=inm["id"], mode=inm["mode"], agent="Guardian")

    def job(compose: str, label: str, chunks: list[str], **x) -> str:
        payload = {"ch": ch, "compose": compose, "label": label, "chunks": chunks, "cls": {"cls": cls, "sub": sub, "rule": rd.rule}, "inbound": inm["id"],
                   "input": f'Inbound on {CH_NAME[ch]}: "{text}". Classified by {rd.rule}.', **x}
        if rd.llm and rd.reply_draft:
            payload["llm_draft"] = {"body": rd.reply_draft, "claims": rd.claims, "cost": rd.cost, "tin": rd.tokens_in, "tout": rd.tokens_out, "model": rd.model, "pv": rd.prompt_version}
        return enqueue(db, e, "reply", payload=payload)

    if cls == "ooo":
        save_enr(db, e, note="Out of office reply. Sequence waits.")
        return inm
    cancel_all_pending(db, e, "Superseded by an inbound reply")
    e = enrollment(db, e["id"])
    if cls == "unsubscribe":
        add_suppression(db, "email", p["email"], f"Replied to opt out on {CH_NAME[ch]}", "Guardian")
        for x in db.q("select * from enrollments where prospect_id = %s", (p["id"],)):
            set_state(db, x, "opted_out")
            cancel_all_pending(db, x, "Opted out")
        db.x("update contact_claims set status = 'released' where prospect_id = %s and status = 'active'", (p["id"],))
        job("unsub", "Opt-out confirmed", ["K-041"], ack=True)
    elif cls == "escalate":
        set_state(db, e, "escalated")
        slot = slots_for(now_ms)[0]["label"]
        suggested = templates.ESC_SUGGEST[sub].format(f=p["first_name"], slot=slot)
        db.x("insert into escalations (id, enrollment_id, campaign_id, reason_code, rep_id, created_at, msg_id, suggested, summary, rule) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
             (db.nid("ES-"), e["id"], c["id"], sub, rep["id"], clock.now(), inm["id"], suggested, f'{p["full_name"]} ({p["title"]}, {p["company"]}) wrote: "{text}"', rd.rule))
        job("escalate", "Escalated to " + first(rep["name"]), ["K-022"], ack=True)
    elif cls == "not_interested":
        set_state(db, e, "stopped", reject="Replied that they are not interested")
        release_claim(db, e, "not interested")
    elif cls == "positive" or (cls == "book" and not e["slots"]):
        set_state(db, e, "replied_pos")
        save_enr(db, e, slots=slots_for(now_ms))
        job("slots", "Two slots offered", [])
        if c["channels"].get("voice") and c["appr"].get("voice") and key == "C3" and e["hot_call"]:
            plan_call(db, e)
    elif cls == "book":
        idx = 1 if _has(text, ("second", "2nd", "later", "tuesday", "wednesday")) else 0
        slot = e["slots"][idx] if len(e["slots"]) > idx else e["slots"][0]
        book_meeting(db, e, slot, "Responder")
        job("confirm", "Meeting confirmed", [])
    elif cls == "objection":
        set_state(db, e, "replied_obj")
        if sub == "case":
            m = ("case_study", [CASE_CHUNK.get(key, "K-207")])
        else:
            m = OBJECTION_MAP.get(sub or "budget", OBJECTION_MAP["budget"])
        job(m[0], f"Objection answered: {sub}", m[1], pricing=sub == "pricing")
    elif cls == "not_now":
        wake = clock.now() + 90 * D_TD
        set_state(db, e, "replied_notnow", wake=wake)
        job("notnow", f"Wake date set {f_d(clock.ms(wake))}", ["K-213"])
    else:
        set_state(db, e, "replied_obj")
        job("answer_q", "Clarifying question", ["K-001"])
    return inm


def _has(text: str, words: tuple[str, ...]) -> bool:
    t = text.lower()
    return any(w in t for w in words)


from datetime import timedelta  # noqa: E402

D_TD = timedelta(milliseconds=D)


def send_reply(db: Db, job: dict) -> None:
    e = enrollment(db, job["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    rep = rep_for(db, e, c)
    pl = job["payload"]
    ch = pl["ch"]
    key = tk(c)
    db.lock("prospect:" + p["id"])
    now_ms = clock.ms(clock.now())
    comp = templates.compose(pl["compose"], p={**p, "facts": p["facts"]}, tkey=key, rep_name=rep["name"], ver=runtime.template_version(db, c["id"], active_version(db, c["id"], "Writer")), now_ms=now_ms,
                             meeting=e["meeting"], wake_ms=clock.ms(e["wake"]) if e["wake"] else None)
    comp["allow_uncited_numbers"] = True
    ld = pl.get("llm_draft")
    if ld:
        segs, missing = writer.segs_from_claims(ld["body"], ld["claims"])
        llm_comp = {"ch": ch, "subject": comp["subject"], "segs": segs, "body": ld["body"], "claims": [s for s in segs if s.get("src")] + [{**m, "src": "?"} for m in missing]}
        if not grounding.check(db, llm_comp, p, c["id"])["bad"]:
            comp = llm_comp
    comp["ch"] = ch
    ack = bool(pl.get("ack"))
    g = gate.evaluate(db, e, ch, reply=True, pricing=bool(pl.get("pricing")), approved=bool(pl.get("approved")), ack=ack)
    if ack and g["dec"] in ("block", "defer", "replan"):
        g = {**g, "dec": "allow", "reason": ""}
    if g["dec"] == "hold":
        _requeue_later(db, job)
        return
    tr = {"input": pl["input"], "output": comp["body"], "chunks": pl["chunks"], "gate": g, "claims": comp["claims"], "segs": comp["segs"], "cls": pl["cls"]}
    kw = {}
    if ld:
        kw = dict(model=ld.get("model"), tokens_in=ld.get("tin"), tokens_out=ld.get("tout"), cost=ld.get("cost"), prompt_version=ld.get("pv"))
    if g["dec"] in ("block", "defer", "replan"):
        finish_job(db, job, summary=f"Reply not sent: {g['reason']}", trace=tr, **kw)
        act(db, e, "gate", f"Guardian held the reply to {p['full_name']}: {g['reason']}", run_id=job["id"], agent="Guardian", reason_code=g["reason"])
        return
    if g["dec"] == "needs_approval":
        m = mk_msg(db, e, ch, "out", comp["body"], segs=comp["segs"], subject=comp["subject"], status="pending", run_id=job["id"], is_reply=True, kind=pl["compose"])
        finish_job(db, job, summary="Reply drafted, waiting for approval", trace=tr, msg_id=m["id"], **kw)
        db.x("insert into approvals (id, kind, campaign_id, enrollment_id, created_at, status, run_id, msg_id) values (%s,'reply',%s,%s,%s,'open',%s,%s)",
             (db.nid("AP-"), c["id"], e["id"], clock.now(), job["id"], m["id"]))
        act(db, e, "draft", f"Responder drafted a reply to {p['full_name']}. Waiting for approval", run_id=job["id"], agent="Responder", msg_id=m["id"])
        return
    key_ = f"{e['id']}:reply:{pl.get('inbound', job['id'])}:{pl['compose']}"
    from psycopg import errors as pgerr

    try:
        with db.conn.transaction():
            m = mk_msg(db, e, ch, "out", comp["body"], segs=comp["segs"], subject=comp["subject"], run_id=job["id"], is_reply=True, kind=pl["compose"], is_ack=ack,
                       idempotency_key=key_, gate_decision="allow")
            channels.send_message(db, m, p)
    except pgerr.UniqueViolation:
        finish_job(db, job, summary="Duplicate reply prevented", trace=tr, **kw)
        return
    finish_job(db, job, summary=f"Replied on {CH_NAME[ch]}: {pl['label']}", trace=tr, msg_id=m["id"], **kw)
    act(db, e, "send", f"Responder replied to {p['full_name']} on {CH_NAME[ch]}", run_id=job["id"], agent="Responder", msg_id=m["id"], mode=m["mode"])


# --- calls ----------------------------------------------------------------------------------------------------------------

CALL_SCRIPT = lambda p, rep: [  # noqa: E731
    ["Caller", 0, f"Hi {p['first_name']}, this is the Helix Agents assistant calling for {first(rep['name'])}. Is now a bad time for two minutes?"],
    ["Prospect", 6, "No, go ahead."],
    ["Caller", 9, "You replied about call QA. Are you still reviewing calls by hand?", "Question"],
    ["Prospect", 15, "Yes, we sample about ten percent. It does not scale.", "Objection"],
    ["Caller", 24, f"Ringlet moved to agents and now reviews every call. {first(rep['name'])} can walk you through it. Would the first slot work?"],
    ["Prospect", 34, "What does it cost?", "Pricing"],
    ["Caller", 38, f"I cannot quote pricing on a call. {first(rep['name'])} covers it in the session."],
    ["Prospect", 45, "Fine, book it.", "Positive"],
]


def plan_call(db: Db, e: dict) -> None:
    if db.q1("select 1 as x from approvals where enrollment_id = %s and kind = 'voice' and status = 'open'", (e["id"],)):
        return
    p = prospect(db, e["prospect_id"])
    jid = enqueue(db, e, "call")
    job = db.q1("select * from jobs where id = %s", (jid,))
    db.x("update jobs set agent = 'Sequencer', status = 'running' where id = %s", (jid,))
    finish_job(db, {**job, "agent": "Sequencer"}, agent="Sequencer", summary="Plan: voice call, hot reply", cost=0.0,
               trace={"input": "Reply was warm, ICP score high, voice allowed for this campaign.",
                      "output": "Next action: voice call by Caller.\nreason: hot reply, working hours, phone on file.\nCampaign rule: every voice call needs approval.", "chunks": ["K-441", "K-431"]})
    db.x("insert into approvals (id, kind, campaign_id, enrollment_id, created_at, status, run_id) values (%s,'voice',%s,%s,%s,'open',%s)",
         (db.nid("AP-"), e["campaign_id"], e["id"], clock.now(), jid))
    set_state(db, e, "awaiting_voice")
    act(db, e, "plan", f"Sequencer planned a voice call to {p['full_name']}. Waiting for approval", run_id=jid, agent="Sequencer")


def record_call(db: Db, e: dict, *, sandbox: bool, disposition: str = "connected_interested", transcript: list | None = None, summary: str | None = None,
                duration: str = "00:52", at=None, recording_url: str | None = None) -> str:
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    rep = rep_for(db, e, c)
    jid = enqueue(db, e, "call")
    job = db.q1("select * from jobs where id = %s", (jid,))
    finish_job(db, job, summary="Call connected, interested" if disposition == "connected_interested" else f"Call ended: {disposition}",
               trace={"input": "Briefing fetched from the pre-call webhook: facts, thread, objective.", "output": f"disposition: {disposition}\nnext: book meeting", "chunks": ["K-431", "K-432"]},
               latency=52, cost=0.11)
    tr = transcript or CALL_SCRIPT(p, rep)
    summ = summary or (f"{p['first_name']} samples about ten percent of calls and wants full coverage. Asked about price, which the Caller deferred to {first(rep['name'])}. Agreed to book a call.")
    cid = db.nid("CL-")
    db.x("insert into calls (id, enrollment_id, prospect_id, at, dur, disposition, mode, run_id, transcript, summary, recording_url) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
         (cid, e["id"], p["id"], at or clock.now(), duration, disposition, "sandbox" if sandbox else "live", jid, J(tr), summ, recording_url))
    mk_msg(db, e, "voice", "out", f"Voice call, {duration}. {summ}", run_id=jid, mode="sandbox" if sandbox else "live", kind="call")
    act(db, e, "call", f"Call with {p['full_name']} {'connected' if disposition == 'connected_interested' else disposition}. Disposition: {disposition.replace('connected_', '')}", run_id=jid, agent="Caller",
        mode="sandbox" if sandbox else "live")
    return cid


# --- approvals ------------------------------------------------------------------------------------------------------------

def approve_item(db: Db, approval_id: str, by: dict, edit: str | None = None) -> dict:
    a = db.q1("select * from approvals where id = %s for update", (approval_id,))
    if not a:
        raise NotFound("Approval not found")
    if a["status"] != "open":
        raise StateConflict("This approval was already decided")
    e = enrollment(db, a["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    now = clock.now()
    if a["kind"] == "borderline":
        db.x("update approvals set status = 'approved', decided_by = %s, decided_at = %s where id = %s", (by["name"], now, a["id"]))
        act(db, e, "approval", f"{by['name']} approved {p['full_name']} after review", agent="Manager")
        from backend.orchestrator.handlers import _qualify_or_defer

        _qualify_or_defer(db, e, p, e["score"] or 0, None)
        return {"ok": True, "msg": f"{p['full_name']} qualified. The Sequencer will plan next."}
    if a["kind"] == "voice":
        db.x("update approvals set status = 'approved', decided_by = %s, decided_at = %s where id = %s", (by["name"], now, a["id"]))
        integ = db.q1("select mode from integrations where key = 'voice'")
        from backend.orchestrator import voice

        sandbox = integ["mode"] != "live"
        _, awaiting = voice.place_call(db, e, sandbox=sandbox)
        if awaiting:
            return {"ok": True, "msg": "Call placed (LIVE). The outcome arrives from DronaHQ Voice when the call ends."}
        e = enrollment(db, e["id"])
        if e["state"] != "meeting":
            slot = slots_for(clock.ms(now))[0]
            book_meeting(db, e, slot, "Caller")
        return {"ok": True, "msg": f"Call placed (SANDBOX). {p['first_name']} agreed to a meeting."}
    m = db.q1("select * from messages where id = %s", (a["msg_id"],))
    if m["segs"] and any(s.get("src") == "?" for s in m["segs"]) and not (edit and edit != m["body"]):
        return {"ok": False, "msg": "The verifier blocked this draft. Edit the unsupported claim before you approve."}
    if edit and edit != m["body"]:
        db.x("update messages set body = %s, segs = null, edited = true where id = %s", (edit, m["id"]))
        m["body"], m["segs"] = edit, None
    gate.lock_quota(db, e)
    g = gate.evaluate(db, e, m["channel"], approved=True, reply=m["is_reply"])
    if g["dec"] not in ("allow", "needs_approval"):
        return {"ok": False, "msg": f"Approval kept open. Guardian holds the send: {g['reason']}."}
    db.x("update approvals set status = 'approved', decided_by = %s, decided_at = %s where id = %s", (by["name"], now, a["id"]))
    mode = db.q1("select mode from integrations where key = %s", ({"email": "gmail", "linkedin": "linkedin", "sms": "twilio", "voice": "voice"}[m["channel"]],))["mode"]
    db.x("update messages set status = 'sent', created_at = %s, mode = %s, approved_by = %s where id = %s", (now, mode, by["name"], m["id"]))
    m = db.q1("select * from messages where id = %s", (m["id"],))
    channels.send_message(db, m, p)
    if m["step_no"] is not None and e["plan"] and len(e["plan"]) > m["step_no"]:
        plan = e["plan"]
        plan[m["step_no"]].update(status="done", doneAt=clock.ms(now), msgId=m["id"], queued=False)
        save_enr(db, e, plan=plan)
    save_enr(db, e, last_touch=now)
    if e["state"] in ("awaiting_approval", "qualified"):
        set_state(db, e, "contacted")
    act(db, e, "send", f"{CH_NAME[m['channel']]} to {p['full_name']} sent after approval by {by['name']}", msg_id=m["id"], mode=m["mode"], agent="Guardian")
    return {"ok": True, "msg": f"Approved. {CH_NAME[m['channel']]} sent ({m['mode'].upper()})."}


def reject_item(db: Db, approval_id: str, by: dict, reason: str) -> None:
    a = db.q1("select * from approvals where id = %s for update", (approval_id,))
    if not a:
        raise NotFound("Approval not found")
    e = enrollment(db, a["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    db.x("update approvals set status = 'rejected', decided_by = %s, decided_at = %s, reason = %s where id = %s", (by["name"], clock.now(), reason, a["id"]))
    if a["msg_id"]:
        db.x("update messages set status = 'rejected' where id = %s", (a["msg_id"],))
    if a["kind"] == "borderline":
        set_state(db, e, "rejected", reject="Rejected in review: " + reason)
    elif a["kind"] == "voice":
        set_state(db, e, "replied_pos")
    elif a["kind"] == "first_touch":
        set_state(db, e, "stopped", reject="Draft rejected: " + reason)
        cancel_all_pending(db, e, "Draft rejected")
        release_claim(db, enrollment(db, e["id"]), "draft rejected")
    act(db, e, "approval", f"{by['name']} rejected {a['kind'].replace('_', ' ')} for {p['full_name']}: {reason}", agent="Manager")


def resolve_escalation(db: Db, esc_id: str, by: dict, text: str) -> None:
    x = db.q1("select * from escalations where id = %s for update", (esc_id,))
    if not x:
        raise NotFound("Escalation not found")
    e = enrollment(db, x["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    inbound = db.q1("select channel from messages where id = %s", (x["msg_id"],)) if x["msg_id"] else None
    ch = inbound["channel"] if inbound else "email"
    db.x("update escalations set status = 'resolved', resolved_by = %s, resolved_at = %s where id = %s", (by["name"], clock.now(), x["id"]))
    m = mk_msg(db, e, ch, "out", text, human=True, by_name=by["name"], is_reply=True, status="sent")
    channels.send_message(db, m, p)
    set_state(db, e, "replied_pos", note="Handled by " + by["name"])
    act(db, e, "handoff", f"{by['name']} replied to {p['full_name']} and closed the escalation", msg_id=m["id"], mode=m["mode"], agent="Rep")


def resolve_conflict(db: Db, conflict_id: str, by: dict, campaign_id: str) -> None:
    x = db.q1("select * from conflicts where id = %s for update", (conflict_id,))
    if not x:
        raise NotFound("Conflict not found")
    if campaign_id not in x["campaign_ids"]:
        raise StateConflict("That campaign is not part of this conflict")
    p = prospect(db, x["prospect_id"])
    lose = next(c for c in x["campaign_ids"] if c != campaign_id)
    win_e = db.q1("select * from enrollments where prospect_id = %s and campaign_id = %s", (p["id"], campaign_id))
    lose_e = db.q1("select * from enrollments where prospect_id = %s and campaign_id = %s", (p["id"], lose))
    db.x("update conflicts set status = 'resolved', winner = %s, resolved_by = %s, decision = %s where id = %s",
         (campaign_id, by["name"], f"{by['name']} gave {p['full_name']} to {campaign_id}", x["id"]))
    transfer_claim(db, p["id"], campaign_id)
    if lose_e:
        cancel_all_pending(db, lose_e, "Claim given to " + campaign_id)
        if lose_e["state"] in ("qualified", "contacted"):
            set_state(db, lose_e, "deferred", defer_note="Claim given to " + campaign_id)
    if win_e and win_e["state"] == "deferred":
        set_state(db, win_e, "qualified", defer_note=None)
        enqueue(db, win_e, "plan")
    act(db, win_e, "conflict", f"{by['name']} gave {p['full_name']} to {campaign_id} (manual override)", agent="Manager")


def stop_prospect(db: Db, e: dict, by: dict) -> None:
    p = prospect(db, e["prospect_id"])
    set_state(db, e, "stopped", reject="Stopped by " + by["name"])
    cancel_all_pending(db, e, "Stopped by a person")
    release_claim(db, enrollment(db, e["id"]), "stopped")
    act(db, e, "stop", f"{by['name']} stopped {p['full_name']} in {e['campaign_id']}", agent="Manager")


def escalate_manually(db: Db, e: dict, by: dict) -> None:
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    rep = rep_for(db, e, c)
    set_state(db, e, "escalated")
    cancel_all_pending(db, e, "Escalated to a rep")
    last_in = db.q1("select id from messages where enrollment_id = %s and direction = 'in' order by created_at desc limit 1", (e["id"],))
    any_msg = last_in or db.q1("select id from messages where enrollment_id = %s order by created_at limit 1", (e["id"],))
    slot = slots_for(clock.ms(clock.now()))[0]["label"]
    db.x("insert into escalations (id, enrollment_id, campaign_id, reason_code, rep_id, created_at, msg_id, suggested, summary, rule) values (%s,%s,%s,'human_request',%s,%s,%s,%s,%s,'manual escalation')",
         (db.nid("ES-"), e["id"], c["id"], rep["id"], clock.now(), any_msg["id"] if any_msg else None,
          f"Hi {p['first_name']}, {first(by['name'])} asked me to take over. Do you have 15 minutes {slot}?", f"{by['name']} escalated {p['full_name']} manually."))
    act(db, e, "handoff", f"{by['name']} escalated {p['full_name']} to {rep['name']}", agent="Manager")


def human_send(db: Db, e: dict, by: dict, text: str) -> dict:
    p = prospect(db, e["prospect_id"])
    last = db.q1("select channel from messages where enrollment_id = %s and direction = 'in' order by created_at desc limit 1", (e["id"],))
    ch = last["channel"] if last else "email"
    m = mk_msg(db, e, ch, "out", text, human=True, by_name=by["name"], is_reply=True)
    channels.send_message(db, m, p)
    act(db, e, "handoff", f"{by['name']} replied to {p['full_name']} on {CH_NAME[ch]}", msg_id=m["id"], mode=m["mode"], agent="Rep")
    return m


__all__ = ["allowed_channels", "_mk_trace", "send_step", "f_dt", "ESC_LABEL", "NotFound"]
