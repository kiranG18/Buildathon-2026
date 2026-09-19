"""Contact claims, the priority ladder and resolve_claim. Deterministic code with no model in it.

One active claim per prospect is enforced by a partial unique index. The ladder picks a winner
between the campaign holding the claim and one that wants it. The first rung that separates them wins.
"""

from dataclasses import dataclass

from backend.core import clock
from backend.core.db import Db
from backend.orchestrator.defs import tk
from backend.orchestrator.repo import act, campaign, enqueue, prospect


@dataclass
class Decision:
    dec: str  # allow, block, defer
    code: str
    note: str


def is_suppressed(db: Db, p: dict) -> bool:
    row = db.q1(
        """select 1 as x from suppression_list where (kind = 'email' and lower(value) = lower(%s))
           or (kind = 'domain' and value = %s) or (kind = 'phone' and value = %s) limit 1""",
        (p["email"], p["domain"], p["phone"]),
    )
    return row is not None


def active_claim(db: Db, prospect_id: str) -> dict | None:
    return db.q1("select * from contact_claims where prospect_id = %s and status = 'active'", (prospect_id,))


def create_claim(db: Db, prospect_id: str, campaign_id: str) -> None:
    c = db.q1("select priority from campaigns where id = %s", (campaign_id,))
    db.x(
        "insert into contact_claims (prospect_id, campaign_id, status, priority, claimed_at) values (%s,%s,'active',%s,%s)",
        (prospect_id, campaign_id, c["priority"], clock.now()),
    )


def transfer_claim(db: Db, prospect_id: str, campaign_id: str) -> None:
    db.x("update contact_claims set status = 'lost' where prospect_id = %s and status = 'active'", (prospect_id,))
    create_claim(db, prospect_id, campaign_id)


def is_customer_campaign(c: dict) -> bool:
    return tk(c) == "C4"


def ladder(db: Db, holder_enr: dict, new_enr: dict, claim: dict) -> tuple[str | None, str]:
    """Return (winning campaign id or None for a tie, rule text)."""
    h, n = campaign(db, holder_enr["campaign_id"]), campaign(db, new_enr["campaign_id"])
    if db.q1("select 1 as x from messages where enrollment_id = %s and direction = 'in' limit 1", (holder_enr["id"],)):
        return h["id"], "Active conversation keeps the claim"
    if is_customer_campaign(n) and not is_customer_campaign(h):
        return n["id"], "Customer-relationship campaign outranks cold acquisition"
    if is_customer_campaign(h):
        return h["id"], "Customer-relationship campaign outranks cold acquisition"
    if h["priority"] != n["priority"]:
        return (h["id"] if h["priority"] > n["priority"] else n["id"]), "Higher campaign priority"
    hs, ns = holder_enr["score"], new_enr["score"]
    if hs is not None and ns is not None and hs != ns:
        return (h["id"] if hs > ns else n["id"]), f"Higher ICP score ({max(hs, ns)} vs {min(hs, ns)})"
    if claim["claimed_at"] != new_enr["created_at"]:
        return h["id"], "Earlier claim wins"
    return None, "Exact tie on priority, score and claim time"


def add_conflict(db: Db, prospect_id: str, cids: list[str], rule: str, winner: str | None, status: str, code: str, decision: str) -> None:
    if db.q1("select 1 as x from conflicts where prospect_id = %s and campaign_ids = %s and status <> 'resolved'", (prospect_id, cids)):
        return
    db.x(
        "insert into conflicts (id, prospect_id, campaign_ids, rule, winner, status, code, decision, created_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (db.nid("X-"), prospect_id, cids, rule, winner, status, code, decision, clock.now()),
    )


def resolve_claim(db: Db, e: dict) -> Decision:
    """Runs at qualification and again inside every send. Returns allow, defer or block."""
    p = prospect(db, e["prospect_id"])
    if is_suppressed(db, p):
        return Decision("block", "suppressed", "On the suppression list")
    claim = active_claim(db, p["id"])
    if claim is None:
        create_claim(db, p["id"], e["campaign_id"])
        return Decision("allow", "claim_ok", "Claim created for this campaign")
    if claim["campaign_id"] == e["campaign_id"]:
        return Decision("allow", "claim_ok", "This campaign holds the claim")
    holder = db.q1("select * from enrollments where prospect_id = %s and campaign_id = %s", (p["id"], claim["campaign_id"]))
    winner, rule = ladder(db, holder, e, claim)
    cids = [claim["campaign_id"], e["campaign_id"]]
    if winner is None:
        add_conflict(db, p["id"], cids, rule, None, "open", "conflict_tie", f"Tie. {claim['campaign_id']} keeps the claim until a manager decides.")
        return Decision("defer", "conflict_tie", f"Tie between {cids[0]} and {cids[1]}: a manager decides")
    if winner == e["campaign_id"]:
        transfer_claim(db, p["id"], e["campaign_id"])
        for other in db.q("select * from enrollments where prospect_id = %s and campaign_id <> %s", (p["id"], e["campaign_id"])):
            cancel_pending_steps(db, other, f"Claim moved to {e['campaign_id']}")
        add_conflict(db, p["id"], cids, rule, e["campaign_id"], "logged", "claimed_by_other_campaign", f"{e['campaign_id']} takes the claim. {claim['campaign_id']} steps stop.")
        return Decision("allow", "claim_ok", "Claim moved here: " + rule)
    add_conflict(db, p["id"], cids, rule, claim["campaign_id"], "open", "claimed_by_other_campaign", f"{claim['campaign_id']} keeps the claim. {e['campaign_id']} waits.")
    return Decision("defer", "claimed_by_other_campaign", f"{claim['campaign_id']} holds the claim: {rule}")


def cancel_pending_steps(db: Db, e: dict, why: str, cancel_jobs: bool = False) -> None:
    from backend.core.db import J

    plan = e["plan"] or []
    changed = False
    for s in plan:
        if s.get("status") == "pending":
            s["status"], s["reason"], changed = "cancelled", why, True
    if changed:
        db.x("update enrollments set plan = %s where id = %s", (J(plan), e["id"]))
        e["plan"] = plan
    if cancel_jobs:
        db.x("update jobs set status = 'cancelled' where enrollment_id = %s and status = 'queued' and step = 'draft'", (e["id"],))


def release_claim(db: Db, e: dict, why: str) -> None:
    claim = active_claim(db, e["prospect_id"])
    if not claim or claim["campaign_id"] != e["campaign_id"]:
        return
    db.x("update contact_claims set status = 'released' where id = %s", (claim["id"],))
    other = db.q1("select * from enrollments where prospect_id = %s and campaign_id <> %s and state = 'deferred'", (e["prospect_id"], e["campaign_id"]))
    if other:
        db.x("update enrollments set state = 'qualified', defer_note = null where id = %s", (other["id"],))
        p = prospect(db, other["prospect_id"])
        act(db, other, "conflict", f"Claim released ({why}). {p['full_name']} rechecks in {other['campaign_id']}")
        enqueue(db, other, "plan")
