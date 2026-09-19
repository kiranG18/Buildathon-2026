"""ProspectMemory: everything an agent may know about one enrollment, keyed by enrollment and never by channel.

A LinkedIn reply therefore changes what the email step says next. The builder keeps to a 3,000-token budget:
older messages collapse into a rolling summary line.
"""

from backend.core.db import Db
from backend.orchestrator.repo import campaign, prospect, rep_for

TOKEN_BUDGET = 3000


def approx_tokens(obj) -> int:
    return int(len(str(obj).split()) * 1.35)


def build(db: Db, enrollment: dict) -> dict:
    c = campaign(db, enrollment["campaign_id"])
    p = prospect(db, enrollment["prospect_id"])
    rep = rep_for(db, enrollment, c)
    msgs = db.q(
        "select channel, direction, subject, body, status, kind, created_at from messages where enrollment_id = %s and status <> 'rejected' order by created_at desc limit 40",
        (enrollment["id"],),
    )
    touches = [{"channel": m["channel"], "kind": m["kind"], "at": m["created_at"].isoformat()} for m in msgs if m["direction"] == "out" and m["status"] == "sent"][:5]
    last8 = [{"channel": m["channel"], "direction": m["direction"], "body": m["body"][:600]} for m in msgs[:8]][::-1]
    older = msgs[8:]
    summary = f"{len(older)} earlier messages omitted." if older else ""
    mem = {
        "prospect": {"name": p["full_name"], "title": p["title"], "company": p["company"], "industry": p["ind"], "staff": p["staff"], "stage": p["stage"], "region": p["region"]},
        "facts": [{"id": f["id"], "statement": f["text"], "source_url": f["url"], "confidence": f["conf"]} for f in p["facts"] if f["conf"] != "Low"],
        "enrollment": {"state": enrollment["state"], "icp_score": enrollment["score"], "channel_plan": enrollment["plan"]},
        "last_touches": touches,
        "messages": last8,
        "summary": summary,
        "campaign": {"objective": c["objective"], "tone": c["tone"], "words": c["words"], "rep": rep["name"]},
    }
    while approx_tokens(mem) > TOKEN_BUDGET and mem["messages"]:
        mem["messages"].pop(0)
        mem["summary"] = "Earlier messages collapsed into this summary."
    return mem
