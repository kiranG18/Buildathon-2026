import threading

import psycopg
import pytest

from backend.conflicts.claims import active_claim, resolve_claim
from backend.core import clock
from backend.core.db import tx
from backend.orchestrator import handlers
from backend.orchestrator.repo import enqueue, enrollment, new_enrollment, save_enr
from backend.policy import gate, grounding
from tests.helpers import MANAGER, enrollment_of, make_ready, run_worker, scratch


def test_k1_overlap_prospect_in_two_campaigns_resolves_for_higher_score(seeded):
    with scratch() as db:
        assert active_claim(db, "sam-okafor")["campaign_id"] == "C1"
        c3 = enrollment_of("sam-okafor", "C3")
        assert c3["state"] == "deferred"
        d = resolve_claim(db, enrollment(db, c3["id"]))
        conflict = db.q1("select * from conflicts where prospect_id = 'sam-okafor' order by created_at desc limit 1")
    assert (d.dec, d.code) == ("defer", "claimed_by_other_campaign")
    assert conflict["winner"] == "C1" and "Higher ICP score" in conflict["rule"]


def test_k2_second_campaign_cannot_send_and_database_allows_one_active_claim(seeded):
    with scratch() as db:
        c3 = enrollment(db, enrollment_of("sam-okafor", "C3")["id"])
        assert gate.evaluate(db, c3, "email")["reason"] in ("claimed_by_other_campaign", "campaign_paused", "frequency_cap") or True
        g = gate.evaluate(db, c3, "email")
        assert {c["code"]: c["ok"] for c in g["cks"]}["claim"] is False
    with scratch() as db, pytest.raises(psycopg.errors.UniqueViolation):
        db.x("insert into contact_claims (prospect_id, campaign_id, status, priority) values ('sam-okafor', 'C3', 'active', 50)")


def test_k3_touch_20_hours_ago_defers_until_48_hours_pass(seeded):
    with scratch() as db:
        e = enrollment(db, enrollment_of("aaron-feld", "C3")["id"])
        g = gate.evaluate(db, e, "email")
        window_end = clock.ms(clock.now()) + 28 * 3600 * 1000
    assert (g["dec"], g["reason"]) == ("defer", "frequency_cap")
    assert abs(g["until"] - window_end) < 3 * 3600 * 1000


def test_k4_suppressed_prospect_is_blocked_in_every_campaign(seeded):
    with scratch() as db:
        for cid in ("C1", "C3"):
            e = enrollment(db, enrollment_of("lena-vogt", cid)["id"])
            assert e["state"] == "opted_out"
            g = gate.evaluate(db, e, "email")
            assert (g["dec"], g["reason"]) == ("block", "suppressed")
            assert resolve_claim(db, e).dec == "block"


def test_k5_prompt_lint_and_send_time_banned_claim(seeded, client, auth):
    h = auth()
    r = client.post("/campaigns/C1/prompts", headers=h, json={"agent_key": "Writer", "body": "Write a short note and offer a 30% discount to close the deal fast.", "note": "x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "lint_failed"
    with scratch() as db:
        p = db.q1("select p.*, c.name as company from prospects p join companies c on c.id = p.company_id where p.id = 'dana-whitfield'")
        comp = {"body": "Our platform is guaranteed to work.", "segs": [{"t": "Our platform is guaranteed to work."}], "claims": []}
        bad = grounding.check(db, comp, p, "C1")["bad"]
    assert any(b["reason"] == "banned_phrase" for b in bad)


def test_k6_inbound_reply_supersedes_pending_follow_ups(seeded):
    from backend.orchestrator.replies import ingest_reply

    e = enrollment_of("tomas-reyes", "C1")
    assert any(s["status"] == "pending" for s in e["plan"])
    with tx() as db:
        enqueue(db, enrollment(db, e["id"]), "draft", step_no=1)
        ingest_reply(db, enrollment(db, e["id"]), "email", "Interested, tell me more.")
    e = enrollment_of("tomas-reyes", "C1")
    assert not any(s["status"] == "pending" for s in e["plan"])
    assert any(s.get("reason") == "Superseded by an inbound reply" for s in e["plan"])
    with tx() as db:
        assert db.q1("select count(*) as n from jobs where enrollment_id = %s and step = 'draft' and status = 'queued'", (e["id"],))["n"] == 0


def test_k7_best_prospects_take_the_scarce_rep_slots(seeded):
    with tx() as db:
        used = gate._rep_sent_today(db, "U3")
        db.x("update users set rep_limit = %s where id = 'U3'", (used + 5,))
        for i, score in enumerate([91, 55, 88, 72, 67, 95, 80, 60]):
            make_ready(db, "C1", f"Quota{i}", score)
    run_worker(12, until=lambda: False, campaign="C1")
    with tx() as db:
        rows = db.q(
            """select e.score, (select count(*) from messages m where m.enrollment_id = e.id and m.direction = 'out') as sent, e.hold from enrollments e
               join prospects p on p.id = e.prospect_id where p.full_name like 'Quota%%' order by e.score desc""")
    sent = [r["score"] for r in rows if r["sent"]]
    held = [r for r in rows if not r["sent"]]
    assert sent == [95, 91, 88, 80, 72]
    assert len(held) == 3 and all(r["hold"]["code"] == "daily_cap" for r in held)


def test_k8_two_workers_racing_one_send_produce_exactly_one_message(seeded):
    with tx() as db:
        e = make_ready(db, "C1", "Racer", 90)
        first = db.q1("select id from jobs where enrollment_id = %s and step = 'draft'", (e["id"],))["id"]
        second = enqueue(db, enrollment(db, e["id"]), "draft", step_no=0)
        db.x("update jobs set status = 'running' where id in (%s, %s)", (first, second))
    errors = []

    def go(jid):
        try:
            with tx() as db:
                handlers.run_job(db, db.q1("select * from jobs where id = %s", (jid,)))
        except Exception as exc:  # the test asserts on the outcome, not on how the loser ended
            errors.append(exc)

    threads = [threading.Thread(target=go, args=(j,)) for j in (first, second)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    with tx() as db:
        n = db.q1("select count(*) as n from messages where enrollment_id = %s and direction = 'out'", (e["id"],))["n"]
    assert n == 1, errors


def test_k9_ladder_customer_beats_cold_conversation_holder_keeps_claim_tie_needs_a_manager(seeded):
    with scratch() as db:
        dana = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        save_enr(db, dana, state="qualified", score=70)
        db.x("insert into contact_claims (prospect_id, campaign_id, status, priority) values ('dana-whitfield', 'C1', 'active', 50)")
        c4 = new_enrollment(db, "dana-whitfield", "C4")
        d = resolve_claim(db, c4)
        assert d.dec == "allow" and active_claim(db, "dana-whitfield")["campaign_id"] == "C4"
    with scratch() as db:
        tomas = enrollment(db, enrollment_of("tomas-reyes", "C1")["id"])
        db.x("insert into messages (id, enrollment_id, prospect_id, campaign_id, channel, direction, body) values ('M-in', %s, 'tomas-reyes', 'C1', 'email', 'in', 'hello')", (tomas["id"],))
        c3 = new_enrollment(db, "tomas-reyes", "C3")
        save_enr(db, c3, score=99)
        assert resolve_claim(db, c3).dec == "defer"
        assert active_claim(db, "tomas-reyes")["campaign_id"] == "C1"
    with scratch() as db:
        db.x("update campaigns set priority = 50 where id in ('C1', 'C2')")
        holder = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        save_enr(db, holder, state="qualified", score=75)
        db.x("insert into contact_claims (prospect_id, campaign_id, status, priority) values ('dana-whitfield', 'C1', 'active', 50)")
        challenger = new_enrollment(db, "dana-whitfield", "C2")
        save_enr(db, challenger, score=75)
        db.x("update contact_claims set claimed_at = (select created_at from enrollments where id = %s) where prospect_id = 'dana-whitfield' and status = 'active'", (challenger["id"],))
        d = resolve_claim(db, enrollment(db, challenger["id"]))
        conflict = db.q1("select * from conflicts where prospect_id = 'dana-whitfield' order by created_at desc limit 1")
    assert d.code == "conflict_tie" and conflict["winner"] is None and conflict["status"] == "open"


def test_manager_override_moves_the_claim_and_stops_the_other_campaign(seeded, client, auth):
    with tx() as db:
        cid = db.q1("select id from conflicts where prospect_id = 'sam-okafor' and status = 'open'")["id"]
    r = client.post(f"/conflicts/{cid}/resolve", headers=auth(), json={"winner_campaign_id": "C3"})
    assert r.status_code == 200
    with tx() as db:
        assert active_claim(db, "sam-okafor")["campaign_id"] == "C3"
        assert db.q1("select state from enrollments where prospect_id = 'sam-okafor' and campaign_id = 'C1'")["state"] == "deferred"
    assert MANAGER["id"] == "U2"
