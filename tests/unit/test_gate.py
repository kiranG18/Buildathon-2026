import pytest

from backend.core import clock
from backend.orchestrator.repo import enrollment
from backend.policy import gate
from tests.helpers import enrollment_of, scratch

pytestmark = pytest.mark.readonly


def base(db):
    """Dana Whitfield in C1: Live campaign, nothing sent yet, Marcus has quota."""
    return enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])


def result(db, e, **kw):
    g = gate.evaluate(db, e, kw.pop("ch", "email"), **kw)
    return g["dec"], g["reason"], {c["code"]: c["ok"] for c in g["cks"]}, g


def test_baseline_allows(seeded):
    with scratch() as db:
        dec, reason, checks, _ = result(db, base(db))
    assert dec == "allow" and reason == ""
    assert list(checks) == ["kill_switch", "campaign_live", "agent_enabled", "channel_enabled", "suppression", "claim", "frequency_cap", "rep_quota", "daily_cap", "approval_rule"]
    assert all(checks.values())


def test_check1_kill_switch_holds(seeded):
    with scratch() as db:
        db.x("update global_settings set kill_switch = true, kill_at = now() where id = 1")
        dec, reason, checks, _ = result(db, base(db))
    assert (dec, reason) == ("hold", "kill_switch") and not checks["kill_switch"]


def test_check2_paused_holds_and_draft_blocks(seeded):
    with scratch() as db:
        db.x("update campaigns set status = 'paused' where id = 'C1'")
        assert result(db, base(db))[:2] == ("hold", "campaign_paused")
        db.x("update campaigns set status = 'draft' where id = 'C1'")
        assert result(db, base(db))[:2] == ("block", "campaign_not_live")


def test_check3_agent_off_holds(seeded):
    with scratch() as db:
        db.x("update campaign_agents set enabled = false where campaign_id = 'C1' and agent_key = 'Writer'")
        assert result(db, base(db))[:2] == ("hold", "agent_paused")


def test_check4_channel_off_asks_for_replan(seeded):
    with scratch() as db:
        db.x("update channel_settings set enabled = false where campaign_id = 'C1' and channel = 'email'")
        assert result(db, base(db))[:2] == ("replan", "channel_paused")
        db.x("update channel_settings set enabled = true where campaign_id = 'C1' and channel = 'email'")
        db.x("update integrations set paused = true where key = 'gmail'")
        assert result(db, base(db))[:2] == ("replan", "channel_paused")


def test_check5_suppression_blocks(seeded):
    with scratch() as db:
        db.x("insert into suppression_list (id, kind, value, reason, added_by) values ('S-t', 'domain', 'ledgerline.com', 'test', 'test')")
        assert result(db, base(db))[:2] == ("block", "suppressed")


def test_check6_other_campaign_holds_claim(seeded):
    with scratch() as db:
        db.x("insert into contact_claims (prospect_id, campaign_id, status, priority) values ('dana-whitfield', 'C3', 'active', 50)")
        dec, reason, _, _ = result(db, base(db))
    assert (dec, reason) == ("defer", "claimed_by_other_campaign")


def test_check7_frequency_cap_defers_until_window_passes_but_replies_are_exempt(seeded):
    with scratch() as db:
        e = base(db)
        db.x("insert into messages (id, enrollment_id, prospect_id, campaign_id, channel, direction, body, created_at, status) values ('M-t', %s, 'dana-whitfield', 'C1', 'email', 'out', 'hi', %s, 'sent')",
             (e["id"], clock.now()))
        dec, reason, _, g = result(db, e)
        assert (dec, reason) == ("defer", "frequency_cap")
        assert g["until"] > clock.ms(clock.now())
        assert result(db, e, reply=True)[0] == "allow"


def test_check8_rep_quota_and_offboarded_rep(seeded):
    with scratch() as db:
        e = base(db)
        db.x("update users set rep_limit = 1 where id = 'U3'")
        other = enrollment_of("tomas-reyes", "C1")
        db.x("insert into messages (id, enrollment_id, prospect_id, campaign_id, channel, direction, body, status) values ('M-q', %s, 'tomas-reyes', 'C1', 'email', 'out', 'x', 'sent')", (other["id"],))
        assert result(db, e)[:2] == ("defer", "daily_cap")
        db.x("update users set active = false where id = 'U3'")
        assert result(db, e)[:2] == ("defer", "no_rep_available")


def test_check9_campaign_daily_cap(seeded):
    with scratch() as db:
        e = base(db)
        db.x("update campaigns set daily_send_cap = 2 where id = 'C1'")
        other = enrollment_of("tomas-reyes", "C1")
        for i in (1, 2):
            db.x("insert into messages (id, enrollment_id, prospect_id, campaign_id, channel, direction, body, status) values (%s, %s, 'tomas-reyes', 'C1', 'email', 'out', 'x', 'sent')", (f"M-c{i}", other["id"]))
        assert result(db, e)[:2] == ("defer", "daily_cap")


def test_check10_approval_rules(seeded):
    with scratch() as db:
        e = base(db)
        db.x("update campaigns set appr = '{\"first\": true, \"voice\": false, \"reply\": false}' where id = 'C1'")
        assert result(db, e)[:2] == ("needs_approval", "approval_rule")
        assert result(db, e, approved=True)[0] == "allow"
        db.x("update campaigns set appr = '{\"first\": false, \"voice\": true, \"reply\": false}' where id = 'C1'")
        assert result(db, e, ch="voice")[0] in ("needs_approval", "replan", "defer")


def test_responder_claims_accept_dronahq_string_items():
    from agents.models import ResponderResult

    r = ResponderResult.model_validate({"classification": "question", "next_action": "reply", "claims": ["F20125::Tessellate raised a Series B", "K-88::We integrate with Salesforce", {"text": "x", "source_type": "knowledge", "source_id": "K-1"}]})
    assert [(c.source_type, c.source_id) for c in r.claims] == [("prospect_fact", "F20125"), ("knowledge", "K-88"), ("knowledge", "K-1")]
    assert r.claims[0].text == "Tessellate raised a Series B"
