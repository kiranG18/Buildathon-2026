import hashlib
import json

from backend.core.db import tx
from backend.orchestrator import controls
from tests.helpers import MANAGER, enrollment_of, import_prospects, run_worker


def fingerprint(campaign_id: str) -> str:
    with tx() as db:
        rows = {
            "campaign": db.q1("select id, name, status, objective, thr, appr, daily_send_cap, priority, version from campaigns where id = %s", (campaign_id,)),
            "prompts": db.q("select * from prompt_versions where campaign_id = %s order by id", (campaign_id,)),
            "agents": db.q("select * from campaign_agents where campaign_id = %s order by agent_key", (campaign_id,)),
            "channels": db.q("select * from channel_settings where campaign_id = %s order by channel", (campaign_id,)),
        }
    return hashlib.sha1(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()


def test_f1_f2_create_campaign_then_activation_needs_the_checklist(seeded, client, auth):
    h = auth()
    body = {"name": "UK Fintech CTOs", "objective": "Book a call", "icp": "UK fintech, 100+ staff", "roles": ["CTO"], "geo_list": ["United Kingdom"], "exclusions": ["Agencies"],
            "tone": "Concise and technical, peer to peer", "channels": {"email": True}, "rep_ids": ["U3"], "tpl": "C1"}
    r = client.post("/campaigns", headers=h, json=body)
    assert r.status_code == 201
    cid = r.json()["id"]
    assert r.json()["status"] == "draft"
    with tx() as db:
        assert db.q1("select count(*) as n from jobs where campaign_id = %s", (cid,))["n"] == 0
    no = client.post(f"/campaigns/{cid}/activate", headers=h)
    assert no.status_code == 409 and no.json()["error"]["code"] == "checklist_failed"
    failing = {c["name"] for c in no.json()["error"]["checks"] if not c["passed"]}
    assert failing == {"knowledge", "dry_run"}
    with tx() as db:
        docs = [d["id"] for d in db.q("select id from knowledge_documents where campaign_id = 'C1'")]
    assert client.patch(f"/campaigns/{cid}", headers=h, json={"doc_ids": docs}).status_code == 200
    dry = client.post(f"/campaigns/{cid}/dry-run", headers=h).json()
    assert dry["grounding_passed"] is True and len(dry["results"]) == 3
    with tx() as db:
        assert db.q1("select count(*) as n from prospects where full_name like 'Sample Prospect%%'")["n"] == 0
    ok = client.post(f"/campaigns/{cid}/activate", headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "live"


def test_f4_pause_and_resume_report_held_and_requeued_jobs(seeded, client, auth):
    h = auth()
    p = client.post("/campaigns/C1/pause", headers=h).json()
    assert p["status"] == "paused" and p["held_jobs"] > 0
    assert client.post("/campaigns/C1/pause", headers=h).status_code == 409
    r = client.post("/campaigns/C1/resume", headers=h).json()
    assert r["status"] == "live" and r["requeued_jobs"] == p["held_jobs"]


def test_f5_i2_prompt_versions_are_stamped_rolled_back_and_isolated(seeded, client, auth):
    h = auth()
    before = {c: fingerprint(c) for c in ("C2", "C3")}
    saved = client.post("/campaigns/C1/prompts", headers=h, json={"agent_key": "Writer", "body": "Write the message for the channel in a warm, direct tone.\nCite one source id per claim.", "note": "v3 test"})
    assert saved.status_code == 201 and saved.json()["version"] == 3
    act = client.post(f"/prompts/{saved.json()['id']}/activate", headers=h).json()
    assert act["previous_version_id"] == "C1-Writer-v2"
    with tx() as db:
        active = db.q("select version from prompt_versions where campaign_id = 'C1' and agent_key = 'Writer' and status = 'active'")
    assert [a["version"] for a in active] == [3]
    e = enrollment_of("dana-whitfield", "C1")
    from backend.orchestrator.repo import enqueue, enrollment

    with tx() as db:
        enqueue(db, enrollment(db, e["id"]), "research")
    run_worker(6, until=lambda: enrollment_of("dana-whitfield", "C1")["plan"] != [], campaign="C1")
    roll = client.post("/prompts/C1-Writer-v2/activate", headers=h, json={"rollback": True})
    assert roll.status_code == 200
    with tx() as db:
        assert db.q1("select version from prompt_versions where campaign_id = 'C1' and agent_key = 'Writer' and status = 'active'")["version"] == 2
        assert db.q1("select count(*) as n from activity where reason_code = 'prompt_rollback'")["n"] == 1
    assert {c: fingerprint(c) for c in ("C2", "C3")} == before


def test_f9_offboarding_lists_affected_campaigns_and_defers_until_reassigned(seeded, client, auth):
    h = auth("admin@helix.demo")
    r = client.post("/reps/U3/offboard", headers=h, json={})
    assert r.status_code == 200
    assert set(r.json()["affected"]["campaigns"]) == {"C1", "C3"}
    from backend.orchestrator.repo import enrollment
    from backend.policy import gate

    with tx() as db:
        g = gate.evaluate(db, enrollment(db, enrollment_of("dana-whitfield", "C1")["id"]), "email")
    assert (g["dec"], g["reason"]) == ("defer", "no_rep_available")
    assert client.post("/reps/U3/reassign", headers=h, json={"replacement_rep_id": "U5"}).status_code == 200
    with tx() as db:
        e = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        assert e["rep_id"] == "U5"
        assert gate.evaluate(db, e, "email")["reason"] != "no_rep_available"


def test_f10_daily_cap_defers_the_third_send(seeded):
    from backend.orchestrator.repo import enrollment
    from backend.policy import gate

    with tx() as db:
        used = gate.sent_today(db, "C1")
        db.x("update campaigns set daily_send_cap = %s where id = 'C1'", (used + 2,))
        e = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        assert gate.evaluate(db, e, "email")["dec"] == "allow"
        other = enrollment_of("tomas-reyes", "C1")
        for i in range(2):
            db.x("insert into messages (id, enrollment_id, prospect_id, campaign_id, channel, direction, body, status) values (%s,%s,'tomas-reyes','C1','linkedin','out','x','sent')", (f"M-cap{i}", other["id"]))
        g = gate.evaluate(db, e, "email")
    assert (g["dec"], g["reason"]) == ("defer", "daily_cap")


def test_f11_pausing_linkedin_replans_touches_onto_email_with_a_reason(seeded, client, auth):
    r = client.put("/campaigns/C1/channels/linkedin", headers=auth(), json={"enabled": False})
    assert r.status_code == 200 and r.json()["replanned"] == 8
    e = enrollment_of("tomas-reyes", "C1")
    moved = [s for s in e["plan"] if s.get("replanned")]
    assert moved and moved[0]["ch"] == "email" and "LinkedIn is off" in moved[0]["reason"]
    assert e["plan_hist"] and e["plan_hist"][-1]["why"].startswith("LinkedIn turned off")
    with tx() as db:
        assert db.q1("select count(*) as n from activity where kind = 'replan' and not quiet and text like 'Replanned %% prospects%%'")["n"] == 1


def test_f12_kill_switch_holds_every_campaign_and_resume_restores_their_own_state(seeded, client, auth):
    h = auth()
    client.post("/campaigns/C2/pause", headers=h)
    assert client.post("/kill-switch", headers=h, json={"active": True}).json()["active"] is True
    import_prospects("C1", 6)
    n = run_worker(2)
    assert n == 0
    client.post("/kill-switch", headers=h, json={"active": False})
    s = {c["id"]: c["status"] for c in client.get("/state", headers=h).json()["camps"]}
    assert s["C1"] == "live" and s["C2"] == "paused" and s["C3"] == "live"
    assert run_worker(3) > 0
    assert MANAGER["id"] == "U2" and controls


def test_rep_cannot_pause_or_flip_the_kill_switch_and_managers_cannot_reset(seeded, client, auth):
    rep, mgr = auth("marcus@helix.demo"), auth()
    assert client.post("/campaigns/C1/pause", headers=rep).status_code == 403
    assert client.post("/kill-switch", headers=rep, json={"active": True}).status_code == 403
    assert client.post("/demo/reset", headers=mgr).status_code == 403
    assert client.get("/campaigns/C2", headers=rep).status_code == 403
    assert client.get("/campaigns/C1", headers=rep).status_code == 200


def test_analytics_numbers_equal_database_counts(seeded, client, auth):
    rows = {r["campaign_id"]: r for r in client.get("/analytics/campaigns", headers=auth()).json()}
    with tx() as db:
        for cid in ("C1", "C2", "C3"):
            assert rows[cid]["prospects"] == db.q1("select count(*) as n from enrollments where campaign_id = %s", (cid,))["n"]
            assert rows[cid]["meetings"] == db.q1("select count(*) as n from meetings where campaign_id = %s", (cid,))["n"]
            assert rows[cid]["touches"] == db.q1("select count(*) as n from messages where campaign_id = %s and direction = 'out' and status = 'sent' and not is_reply and kind is distinct from 'call'", (cid,))["n"]
            cost = db.q1("select coalesce(sum(cost_usd), 0) as c from agent_runs where campaign_id = %s and status = 'done' and not is_replay", (cid,))["c"]
            assert abs(rows[cid]["cost_usd"] - cost) < 0.001
    assert rows["C1"]["cost_per_prospect"] > 0
