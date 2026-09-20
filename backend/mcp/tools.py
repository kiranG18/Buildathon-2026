"""The seven tools DronaHQ agents call over MCP. Each opens its own transaction and returns plain JSON.

Agents never send anything through these tools. They read knowledge and the timeline, save sourced research,
propose and book slots, raise escalations and record a classification. Every send still passes the policy gate.
"""

from agents.models import ResearchResult, ResponderResult
from agents.util import slots_for
from backend.core import clock
from backend.core.db import J, tx
from backend.core.errors import NotFound
from backend.orchestrator import replies
from backend.orchestrator.repo import act, campaign, enrollment, prospect, rep_for
from rag import retrieve

CONF_LABEL = [(0.85, "High"), (0.6, "Medium"), (0.0, "Low")]


def search_knowledge(campaign_id: str, query: str, doc_types: list[str] | None = None, k: int = 4) -> list[dict]:
    with tx() as db:
        campaign(db, campaign_id)
        return retrieve.search(db, campaign_id, query, doc_types, min(max(k, 1), 8))


def get_timeline_in(db, enrollment_id: str, limit: int = 20) -> dict:
    e = enrollment(db, enrollment_id)
    p = prospect(db, e["prospect_id"])
    msgs = db.q("select channel, direction, subject, body, status, created_at from messages where enrollment_id = %s and status <> 'rejected' order by created_at desc limit %s", (enrollment_id, min(limit, 50)))
    return {
        "facts": [{"id": f["id"], "statement": f["text"], "source_url": f["url"], "confidence": f["conf"]} for f in p["facts"]],
        "messages": [{"channel": m["channel"], "direction": m["direction"], "subject": m["subject"], "body": m["body"][:800], "at": clock.ms(m["created_at"])} for m in reversed(msgs)],
        "plan": e["plan"],
        "summary": f"State {e['state']}, ICP score {e['score']}, {len(msgs)} messages.",
    }


def get_timeline(enrollment_id: str, limit: int = 20) -> dict:
    with tx() as db:
        return get_timeline_in(db, enrollment_id, limit)


def save_research_in(db, enrollment_id: str, result: dict) -> dict:
    """Store sourced facts. Facts under 0.5 confidence, or without a source URL, are dropped and reported as gaps."""
    r = ResearchResult.model_validate(result)
    e = enrollment(db, enrollment_id)
    p = prospect(db, e["prospect_id"])
    have = {f["id"] for f in p["facts"]}
    have_text = {f["text"] for f in p["facts"]}
    new = []
    for f in r.facts:
        if f.confidence < 0.5 or not f.source_url or f.statement in have_text or f.id in have:
            continue
        label = next(lab for cut, lab in CONF_LABEL if f.confidence >= cut)
        src = f.category if f.category in ("about", "careers", "docs", "blog", "rbi", "news", "annual", "product", "linkedin") else "about"
        new.append({"id": f.id, "text": f.statement, "src": src, "conf": label, "url": f.source_url})
    facts = [*p["facts"], *new]
    rich = [x for x in p["rich"] if x["id"] not in {n["id"] for n in new}]
    db.x("update prospects set facts = %s, rich = %s, researched = true where id = %s", (J(facts), J(rich), p["id"]))
    db.x("insert into research_callbacks (enrollment_id, run_id, facts_saved) values (%s,%s,%s) on conflict do nothing", (enrollment_id, db.nid("RC-"), len(new)))
    act(db, e, "research", f"DronaHQ Researcher saved {len(new)} sourced facts for {p['full_name']} through MCP", agent="Researcher", reason_code="mcp_save_research")
    return {"saved_facts": len(new), "gaps": r.gaps}


def save_research(enrollment_id: str, result: dict) -> dict:
    with tx() as db:
        return save_research_in(db, enrollment_id, result)


def propose_slots(enrollment_id: str, days: int = 5) -> list[dict]:
    with tx() as db:
        enrollment(db, enrollment_id)
        return [{"start": s["t"], "label": s["label"]} for s in slots_for(clock.ms(clock.now()))]


def book_meeting(enrollment_id: str, slot_start: int) -> dict:
    with tx() as db:
        e = enrollment(db, enrollment_id)
        slot = next((s for s in slots_for(clock.ms(clock.now())) if s["t"] == slot_start), None)
        if slot is None:
            raise NotFound("That slot is not open. Call propose_slots first.")
        replies.book_meeting(db, e, slot, "Responder")
        row = db.q1("select id from meetings where enrollment_id = %s order by slot_at desc limit 1", (enrollment_id,))
        return {"meeting_id": row["id"], "status": "booked"}


def create_escalation(enrollment_id: str, reason_code: str, summary: str, suggested_reply: str = "") -> dict:
    with tx() as db:
        e = enrollment(db, enrollment_id)
        c = campaign(db, e["campaign_id"])
        rep = rep_for(db, e, c)
        xid = db.nid("ES-")
        db.x("insert into escalations (id, enrollment_id, campaign_id, reason_code, rep_id, created_at, suggested, summary, rule, created_by_agent) values (%s,%s,%s,%s,%s,%s,%s,%s,'raised by an agent through MCP','Responder')",
             (xid, enrollment_id, e["campaign_id"], reason_code, rep["id"], clock.now(), suggested_reply, summary))
        db.x("update enrollments set state = 'escalated' where id = %s", (enrollment_id,))
        act(db, e, "handoff", f"Agent escalated {prospect(db, e['prospect_id'])['full_name']} to {rep['name']}: {reason_code}", agent="Responder", reason_code=reason_code)
        return {"escalation_id": xid}


def set_classification(enrollment_id: str, classification: str, next_action: str, confidence: float = 0.8, sentiment: str = "neutral", objection_type: str | None = None,
                       reply_draft: str = "", claims: list[str] | None = None, slots_offered: list[str] | None = None, escalation_reason: str | None = None, summary_update: str = "") -> dict:
    """Record the hosted Responder's whole decision for one inbound reply. The worker resumes on it and the policy gate still checks every send."""
    decision = ResponderResult.model_validate({
        "classification": classification, "next_action": next_action, "confidence": confidence, "sentiment": sentiment, "objection_type": objection_type or None,
        "reply_draft": reply_draft, "claims": claims or [], "slots_offered": slots_offered or [], "escalation_reason": escalation_reason or None, "summary_update": summary_update,
    })
    with tx() as db:
        enrollment(db, enrollment_id)
        db.x("insert into responder_decisions (enrollment_id, decision) values (%s,%s)", (enrollment_id, J(decision.model_dump())))
        return {"ok": True, "classification": decision.classification, "next_action": decision.next_action}
