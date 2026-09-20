"""Voice calls. A live call goes to the DronaHQ Voice agent and waits for its post-call webhook. Without telephony the same recording path plays a scripted outcome, labelled SANDBOX."""

from agents.util import slots_for
from backend.core import clock
from backend.core.db import Db, J
from backend.core.errors import NotFound
from backend.orchestrator import dronahq
from backend.orchestrator.repo import act, campaign, enrollment, mk_msg, prospect, rep_for, set_state

DISPOSITIONS = ("connected_interested", "callback", "not_interested", "voicemail", "wrong_number", "escalate")


def place_call(db: Db, e: dict, *, sandbox: bool) -> tuple[str, bool]:
    """Returns (call id, awaiting_outcome). Live calls are awaiting until the post-call webhook arrives."""
    from backend.orchestrator.replies import record_call

    p = prospect(db, e["prospect_id"])
    if not sandbox and dronahq.enabled("Caller") and dronahq.trigger_call(db, e, p):
        cid = db.nid("CL-")
        db.x("insert into calls (id, enrollment_id, prospect_id, at, dur, disposition, mode, summary) values (%s,%s,%s,%s,'00:00','awaiting_outcome','live','Call placed. Waiting for the DronaHQ Voice post-call webhook.')",
             (cid, e["id"], p["id"], clock.now()))
        act(db, e, "call", f"Call to {p['full_name']} placed on DronaHQ Voice. Waiting for the outcome", agent="Caller", mode="live")
        return cid, True
    return record_call(db, e, sandbox=True), False


def briefing(db: Db, enrollment_id: str) -> dict:
    from rag import retrieve

    e = enrollment(db, enrollment_id)
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    rep = rep_for(db, e, c)
    chunks = retrieve.search(db, c["id"], "voice call opening discovery questions objection handling", ["voice script", "objections"], 4)
    hist = db.q("select channel, direction, body from messages where enrollment_id = %s and status = 'sent' order by created_at desc limit 4", (enrollment_id,))
    first = p["first_name"]
    return {
        "enrollment_id": enrollment_id,
        "prospect": {"name": p["full_name"], "title": p["title"], "company": p["company"]},
        "facts": [f["text"] for f in p["facts"][:3]],
        "history_summary": " ".join(f"[{m['channel']} {m['direction']}] {m['body'][:160]}" for m in reversed(hist)),
        "objective": c["objective"],
        "opening_line": f"Hi {first}, this is the Helix Agents assistant calling for {rep['name'].split()[0]}. I am an AI assistant. Is now a bad time for two minutes?",
        "allowed_claims": [f["text"] for f in p["facts"]] + [k["text"] for k in chunks if k["id"] in ("K-407", "K-307", "K-207")],
        "objection_snippets": [{"id": k["id"], "text": k["text"]} for k in chunks],
        "rep": {"name": rep["name"]},
        "slots": [{"start": s["t"], "label": s["label"]} for s in slots_for(clock.ms(clock.now()))],
    }


def outcome_from_dronahq(db: Db, payload: dict) -> dict:
    """Translate DronaHQ's post-call payload into our outcome shape.

    The enrollment id comes back from our briefing (context.pre_webhook), or as a custom value, or from the number that was dialled.
    The transcript is one text with Agent and Customer lines. A disposition sent as structured data wins. Otherwise no customer speech is a voicemail and anything else is a callback for the rep."""
    body = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    call = body.get("call_data") or {}
    extra = {**(body.get("dynamic_variables") or {}), **(body.get("custom_payload") or {}), **((body.get("context") or {}).get("pre_webhook") or {})}
    structured = next((body[k] for k in ("structured_data", "structured_output") if isinstance(body.get(k), dict)), {})
    eid = extra.get("enrollment_id") or structured.get("enrollment_id")
    if not eid:
        dialled = "".join(ch for ch in str((call.get("destination_number") or {}).get("number", "")) if ch.isdigit())
        for row in db.q("select c.enrollment_id, p.phone from calls c join prospects p on p.id = c.prospect_id where c.disposition = 'awaiting_outcome' order by c.at desc"):
            if dialled and "".join(ch for ch in row["phone"] if ch.isdigit()) == dialled:
                eid = row["enrollment_id"]
                break
    if not eid:
        raise NotFound("The call cannot be matched to an enrollment")
    raw = body.get("transcript") or ""
    lines = list(raw) if isinstance(raw, list) else []
    if isinstance(raw, str):
        for ln in raw.splitlines():
            who, sep, text = ln.partition(":")
            if sep and text.strip():
                lines.append({"speaker": "Caller" if who.strip().lower() in ("agent", "assistant", "ai") else "Prospect", "text": text.strip()})
    disposition = structured.get("disposition")
    if disposition not in DISPOSITIONS:
        spoke = any(x.get("speaker") == "Prospect" for x in lines)
        disposition = "voicemail" if call.get("answered_by_voicemail") or not spoke else "callback"
    return {"enrollment_id": eid, "transcript": lines, "recording_url": body.get("recording_url"), "disposition": disposition, "objections": structured.get("objections") or [],
            "next_step": structured.get("next_step") or "", "booked_slot": structured.get("booked_slot") or None, "structured_answers": structured}


def ingest_outcome(db: Db, enrollment_id: str, outcome: dict) -> dict:
    """The DronaHQ post-call webhook. Idempotent: a retried webhook for the same call returns the stored result."""
    from backend.orchestrator.replies import book_meeting, cancel_all_pending, record_call

    e = enrollment(db, enrollment_id)
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    rep = rep_for(db, e, c)
    disp = outcome["disposition"]
    transcript = [[t.get("speaker", "Caller"), int(t.get("t", i * 6)), t.get("text", "")] for i, t in enumerate(outcome.get("transcript", []))]
    summary = outcome.get("next_step") or f"Call ended: {disp}."
    pending = db.q1("select * from calls where enrollment_id = %s and disposition = 'awaiting_outcome' order by at desc limit 1", (enrollment_id,))
    if pending:
        db.x("update calls set disposition = %s, transcript = %s, summary = %s, recording_url = %s, objections = %s, structured = %s, dur = %s where id = %s",
             (disp, J(transcript), summary, outcome.get("recording_url"), J(outcome.get("objections", [])), J(outcome.get("structured_answers", {})), "02:00", pending["id"]))
        call_id = pending["id"]
        mk_msg(db, e, "voice", "out", f"Voice call, 02:00. {summary}", run_id=None, mode="live", kind="call")
        act(db, e, "call", f"Call with {p['full_name']} ended. Disposition: {disp}", agent="Caller", mode="live")
    else:
        dup = db.q1("select id from calls where enrollment_id = %s and disposition = %s and recording_url is not distinct from %s", (enrollment_id, disp, outcome.get("recording_url")))
        if dup:
            return {"ok": True, "call_id": dup["id"], "duplicate": True}
        call_id = record_call(db, e, sandbox=False, disposition=disp, transcript=transcript or None, summary=summary, recording_url=outcome.get("recording_url"))
    e = enrollment(db, enrollment_id)
    if disp == "connected_interested":
        slots = slots_for(clock.ms(clock.now()))
        want = outcome.get("booked_slot")
        slot = next((s for s in slots if want and (str(s["t"]) == str(want) or s["label"] == want)), slots[0])
        if e["state"] != "meeting":
            book_meeting(db, e, slot, "Caller")
    elif disp == "not_interested":
        set_state(db, e, "stopped", reject="Not interested on the call")
        cancel_all_pending(db, e, "Not interested on the call")
    elif disp == "escalate":
        db.x("insert into escalations (id, enrollment_id, campaign_id, reason_code, rep_id, created_at, summary, rule, created_by_agent) values (%s,%s,%s,'human_request',%s,%s,%s,'raised by the voice agent','Caller')",
             (db.nid("ES-"), e["id"], e["campaign_id"], rep["id"], clock.now(), f"{p['full_name']} needs a human after the call: {summary}"))
        set_state(db, e, "escalated")
    return {"ok": True, "call_id": call_id}
