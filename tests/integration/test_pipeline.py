from backend.core.db import tx
from backend.orchestrator import controls
from backend.orchestrator.repo import enqueue, enrollment
from tests.helpers import MANAGER, activity_count, enrollment_of, import_prospects, run_worker


def test_dana_runs_from_discovered_to_sent_and_stamps_prompt_version(seeded):
    e = enrollment_of("dana-whitfield", "C1")
    assert e["state"] == "new"
    with tx() as db:
        enqueue(db, enrollment(db, e["id"]), "research")
    run_worker(8, until=lambda: enrollment_of("dana-whitfield", "C1")["plan"] != [])
    e = enrollment_of("dana-whitfield", "C1")
    assert e["state"] == "qualified" and e["score"] >= 70
    assert len(e["plan"]) == 4 and e["plan"][0]["ch"] == "email"
    with tx() as db:
        facts = db.q1("select facts from prospects where id = 'dana-whitfield'")["facts"]
        controls.advance_clock(db, 1)
    assert len(facts) >= 3
    run_worker(8, until=lambda: enrollment_of("dana-whitfield", "C1")["state"] == "contacted")
    e = enrollment_of("dana-whitfield", "C1")
    assert e["state"] == "contacted"
    with tx() as db:
        m = db.q1("select * from messages where enrollment_id = %s and direction = 'out' order by created_at desc limit 1", (e["id"],))
        run = db.q1("select * from agent_runs where id = %s", (m["run_id"],))
    assert m["kind"] == "intro" and m["status"] == "sent" and m["mode"] == "sandbox"
    assert run["agent_key"] == "Writer" and run["prompt_version"] == 2
    assert any(s.get("src") for s in m["segs"])


def test_draft_campaign_refuses_a_send(client, auth):
    with tx() as db:
        e = db.q1("select id from enrollments where campaign_id = 'C4' limit 1")
    r = client.post("/outreach/send", headers=auth(), json={"enrollment_id": e["id"], "channel": "email"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "campaign_not_live"
    assert any(c["code"] == "campaign_live" and not c["ok"] for c in r.json()["error"]["gate"])
    with tx() as db:
        assert db.q1("select count(*) as n from messages where campaign_id = 'C4' and direction = 'out'")["n"] == 0


def test_pause_isolation_three_campaigns(seeded):
    for cid in ("C1", "C2", "C3"):
        import_prospects(cid, 60, prefix="Iso")
    with tx() as db:
        controls.advance_clock(db, 2)
    run_worker(1)
    with tx() as db:
        controls.pause_campaign(db, "C2", MANAGER)
    before = {c: activity_count(c) for c in ("C1", "C2", "C3")}
    with tx() as db:
        queued_c2 = db.q1("select count(*) as n from jobs where campaign_id = 'C2' and status = 'queued'")["n"]
    assert queued_c2 > 0, "the paused campaign must still hold work so the test proves it is held"
    run_worker(5)
    after = {c: activity_count(c) for c in ("C1", "C2", "C3")}
    assert after["C1"] > before["C1"] and after["C3"] > before["C3"]
    assert after["C2"] == before["C2"]
    with tx() as db:
        assert db.q1("select count(*) as n from jobs where campaign_id = 'C2' and status = 'running'")["n"] == 0
        assert db.q1("select count(*) as n from jobs where campaign_id = 'C2' and status = 'queued'")["n"] >= queued_c2
    with tx() as db:
        out = controls.resume_campaign(db, "C2", MANAGER)
    assert out["requeued_jobs"] >= queued_c2
    run_worker(4)
    assert activity_count("C2") > after["C2"]
