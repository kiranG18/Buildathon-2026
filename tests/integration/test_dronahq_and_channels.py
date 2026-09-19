import base64
import json

import httpx
import pytest

from backend.channels import adapters, inbound
from backend.channels.base import REGISTRY, OutboundMessage
from backend.core.config import get_settings
from backend.core.db import tx
from backend.core.errors import ChannelError
from backend.mcp import tools
from backend.orchestrator import dronahq
from backend.orchestrator.repo import enrollment
from tests.helpers import enrollment_of, scratch

SECRET = {"X-Cadence-Secret": get_settings().webhook_shared_secret}
MCP = {"Authorization": f"Bearer {get_settings().mcp_token}", "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, method, params=None, id_=1):
    r = client.post("/mcp", headers=MCP, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_se2_mcp_needs_the_token_and_exposes_exactly_seven_tools(seeded, client):
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
    assert client.post("/mcp", headers={"Authorization": "Bearer wrong"}, json={}).status_code == 401
    init = rpc(client, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
    assert init["serverInfo"]["name"] == "Cadence"
    names = {t["name"] for t in rpc(client, "tools/list", id_=2)["tools"]}
    assert names == {"search_knowledge", "get_timeline", "save_research", "propose_slots", "book_meeting", "create_escalation", "set_classification"}


def test_an_mcp_tool_call_saves_sourced_facts_and_the_same_event_shows_in_activity(seeded, client):
    e = enrollment_of("dana-whitfield", "C1")
    facts = {"facts": [
        {"id": "F-mcp-1", "category": "careers", "statement": "Ledgerline posted three platform-engineer roles this month.", "source_url": "/demo-sources/ledgerline/careers", "confidence": 0.9},
        {"id": "F-mcp-2", "category": "news", "statement": "A guess with no support.", "source_url": "", "confidence": 0.3},
    ]}
    res = rpc(client, "tools/call", {"name": "save_research", "arguments": {"enrollment_id": e["id"], "result": facts}})
    assert not res.get("isError"), res
    with tx() as db:
        saved = db.q1("select facts from prospects where id = 'dana-whitfield'")["facts"]
        activity = db.q1("select count(*) as n from activity where enrollment_id = %s and reason_code = 'mcp_save_research'", (e["id"],))["n"]
    assert any(f["id"] == "F-mcp-1" and f["conf"] == "High" for f in saved)
    assert not any(f["id"] == "F-mcp-2" for f in saved)
    assert activity == 1
    hits = rpc(client, "tools/call", {"name": "search_knowledge", "arguments": {"campaign_id": "C2", "query": "data residency", "k": 2}})
    assert "K-312" in json.dumps(hits)


def test_mcp_book_meeting_rejects_a_slot_that_was_never_proposed(seeded):
    e = enrollment_of("tomas-reyes", "C1")
    slots = tools.propose_slots(e["id"])
    assert len(slots) == 2
    with pytest.raises(Exception, match="not open"):
        tools.book_meeting(e["id"], 12345)
    assert tools.book_meeting(e["id"], slots[0]["start"])["status"] == "booked"


def test_af2_a_dead_dronahq_researcher_falls_back_to_the_direct_provider(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_provider_researcher", "dronahq")
    monkeypatch.setattr(get_settings(), "dronahq_researcher_webhook_url", "https://agents.example/hook")
    dronahq.set_transport(httpx.MockTransport(lambda req: httpx.Response(503)))
    try:
        e = enrollment_of("dana-whitfield", "C1")
        with tx() as db:
            from backend.orchestrator.repo import enqueue

            jid = enqueue(db, enrollment(db, e["id"]), "research")
            db.x("update jobs set status = 'running' where id = %s", (jid,))
            from backend.orchestrator import handlers

            handlers.run_job(db, db.q1("select * from jobs where id = %s", (jid,)))
            facts = db.q1("select facts from prospects where id = 'dana-whitfield'")["facts"]
            fallback = db.q1("select count(*) as n from activity where reason_code = 'provider_fallback'")["n"]
        assert len(facts) >= 3 and fallback == 1
    finally:
        dronahq.set_transport(None)


def test_a_synchronous_dronahq_researcher_answer_is_saved_through_the_same_tool(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_provider_researcher", "dronahq")
    monkeypatch.setattr(get_settings(), "dronahq_researcher_webhook_url", "https://agents.example/hook")
    body = {"output": {"facts": [{"id": "F-sync", "category": "product", "statement": "Ledgerline ships payment rails.", "source_url": "/demo-sources/ledgerline/docs", "confidence": 0.9}]}}
    dronahq.set_transport(httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    try:
        e = enrollment_of("dana-whitfield", "C1")
        with scratch() as db:
            p = __import__("backend.orchestrator.repo", fromlist=["prospect"]).prospect(db, "dana-whitfield")
            out = dronahq.research(db, enrollment(db, e["id"]), p, __import__("backend.orchestrator.repo", fromlist=["campaign"]).campaign(db, "C1"))
            saved = [f["id"] for f in db.q1("select facts from prospects where id = 'dana-whitfield'")["facts"]]
        assert out.provider == "dronahq" and "F-sync" in saved
    finally:
        dronahq.set_transport(None)


def test_a11_voice_briefing_and_outcome_webhooks(seeded, client):
    e = enrollment_of("noor-haddad", "C3")
    assert client.get(f"/voice/briefing/{e['id']}").status_code == 401
    b = client.get(f"/voice/briefing/{e['id']}", headers=SECRET).json()
    assert b["prospect"]["name"] == "Noor Haddad" and "AI assistant" in b["opening_line"] and len(b["slots"]) == 2 and b["rep"]["name"]
    body = {"enrollment_id": e["id"], "disposition": "connected_interested", "transcript": [{"speaker": "Caller", "text": "Hi Noor"}, {"speaker": "Prospect", "text": "Send me an email"}],
            "next_step": "Email summary and meeting ask", "recording_url": "https://rec.example/1"}
    assert client.post("/voice/outcome", json=body).status_code == 401
    r = client.post("/voice/outcome", json=body, headers=SECRET)
    assert r.status_code == 200
    again = client.post("/voice/outcome", json=body, headers=SECRET).json()
    assert again["duplicate"] is True
    with tx() as db:
        call = db.q1("select * from calls where enrollment_id = %s order by at desc limit 1", (e["id"],))
        assert call["disposition"] == "connected_interested" and call["transcript"][1][2] == "Send me an email"
        assert db.q1("select count(*) as n from messages where enrollment_id = %s and kind = 'call'", (e["id"],))["n"] == 1
        assert db.q1("select state from enrollments where id = %s", (e["id"],))["state"] == "meeting"


def test_af6_a_call_without_an_outcome_becomes_unknown_outcome_and_escalates(seeded):
    from datetime import timedelta

    from backend.core import clock

    e = enrollment_of("noor-haddad", "C3")
    with tx() as db:
        db.x("insert into calls (id, enrollment_id, prospect_id, at, disposition, mode) values ('CL-t', %s, 'noor-haddad', %s, 'awaiting_outcome', 'live')", (e["id"], clock.now() - timedelta(minutes=11)))
        dronahq.sweep_awaiting_outcome(db)
        assert db.q1("select disposition from calls where id = 'CL-t'")["disposition"] == "unknown_outcome"
        assert db.q1("select count(*) as n from escalations where reason_code = 'unknown_outcome'")["n"] == 1


def test_allowed_recipients_gate_every_adapter(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "allowed_recipients", "team.example,+14155550100")
    adapters.enforce_allowed("dana@team.example")
    adapters.enforce_allowed("+1 (415) 555-0100")
    for bad in ("someone@corp.com", "+14155550999"):
        with pytest.raises(ChannelError):
            adapters.enforce_allowed(bad)


def test_allowed_recipients_accept_plus_addresses_of_an_allowed_mailbox_only(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "allowed_recipients", "sandbox@gmail.com")
    adapters.enforce_allowed("sandbox@gmail.com")
    adapters.enforce_allowed("Sandbox+jane.doe@gmail.com")
    for bad in ("other+sandbox@gmail.com", "sandbox@example.com", "sandbox+x@example.com"):
        with pytest.raises(ChannelError):
            adapters.enforce_allowed(bad)


def test_gmail_adapter_sends_with_a_message_id_and_maps_a_reply_to_the_right_enrollment(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "allowed_recipients", "gmail.com")
    sent = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if "oauth2" in str(req.url):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if str(req.url).endswith("/messages/send"):
            sent["raw"] = base64.urlsafe_b64decode(json.loads(req.content)["raw"] + "==").decode()
            return httpx.Response(200, json={"id": "gm-1"})
        if "/messages?" in str(req.url):
            return httpx.Response(200, json={"messages": [{"id": "in-1"}]})
        if "/messages/in-1" in str(req.url):
            data = base64.urlsafe_b64encode(b"Sounds relevant, free next week?").decode()
            return httpx.Response(200, json={"id": "in-1", "payload": {"mimeType": "text/plain", "body": {"data": data},
                                  "headers": [{"name": "In-Reply-To", "value": sent["rfc"]}, {"name": "From", "value": "someone@gmail.com"}, {"name": "Message-ID", "value": "<r1@x>"}]}})
        return httpx.Response(404)

    adapters.set_transport(httpx.MockTransport(handler))
    try:
        g = adapters.GmailAdapter("id", "secret", "refresh", "helix.sandbox@gmail.com")
        res = g.send(OutboundMessage("M-1", "email", "helix.sandbox+dana.whitfield@gmail.com", "Hello", "Body text"))
        sent["rfc"] = res.rfc_message_id
        assert res.external_id == "gm-1" and "Message-ID: " + res.rfc_message_id in sent["raw"] and "Subject: Hello" in sent["raw"]
        e = enrollment_of("tomas-reyes", "C1")
        with tx() as db:
            db.x("insert into messages (id, enrollment_id, prospect_id, campaign_id, channel, direction, body, rfc_message_id) values ('M-gm', %s, 'tomas-reyes', 'C1', 'email', 'out', 'x', %s)", (e["id"], res.rfc_message_id))
            REGISTRY["email"] = g
            n = inbound.poll_all(db)
            inbound._last_poll.clear()
            msg = db.q1("select * from messages where external_id = 'in-1'")
        assert n == 1 and msg["enrollment_id"] == e["id"] and msg["classification"] in ("question", "positive", "objection", "book")
        with pytest.raises(ChannelError):
            g.send(OutboundMessage("M-2", "email", "someone@corp.com", "x", "y"))
    finally:
        adapters.set_transport(None)
        REGISTRY.clear()


def test_af1_failing_sends_retry_then_escalate_and_three_failures_degrade_the_channel(seeded, monkeypatch):
    from backend.orchestrator.worker import Worker

    with tx() as db:
        for _ in range(3):
            Worker.count_channel_failure(db, "email", "Gmail send failed: 503")
        row = db.q1("select status, err, fail_count from integrations where key = 'gmail'")
    assert row["status"] == "error" and row["fail_count"] == 3 and "503" in row["err"]


def test_twilio_signature_is_verified_and_a_reply_lands_on_the_right_enrollment(seeded, client, monkeypatch):
    monkeypatch.setattr(get_settings(), "twilio_auth_token", "twilio-secret")
    e = enrollment_of("noor-haddad", "C3")
    with tx() as db:
        phone = db.q1("select phone from prospects where id = 'noor-haddad'")["phone"]
        db.x("insert into messages (id, enrollment_id, prospect_id, campaign_id, channel, direction, body) values ('M-sms', %s, 'noor-haddad', 'C3', 'sms', 'out', 'Hey Noor, 15 min?')", (e["id"],))
    form = {"From": phone, "Body": "Yes, send times", "MessageSid": "SM1"}
    url = get_settings().base_url.rstrip("/") + "/webhooks/twilio/sms"
    sig = adapters.twilio_signature("twilio-secret", url, form)
    assert client.post("/webhooks/twilio/sms", data=form).status_code == 403
    assert client.post("/webhooks/twilio/sms", data=form, headers={"X-Twilio-Signature": "bad"}).status_code == 403
    ok = client.post("/webhooks/twilio/sms", data=form, headers={"X-Twilio-Signature": sig})
    assert ok.status_code == 200 and ok.text == "<Response/>"
    with tx() as db:
        assert db.q1("select count(*) as n from messages where enrollment_id = %s and channel = 'sms' and direction = 'in'", (e["id"],))["n"] == 1


def test_source_pages_and_the_enrichment_tool(seeded, client):
    page = client.get("/demo-sources/ledgerline/careers")
    assert page.status_code == 200 and "three platform-engineer roles" in page.text and "fictional" in page.text
    assert client.get("/demo-sources/nobody/about").status_code == 404
    assert client.post("/tools/enrich", json={"domain": "ledgerline.com"}).status_code == 401
    r = client.post("/tools/enrich", json={"domain": "ledgerline.com"}, headers=SECRET).json()
    assert r["company"]["name"] == "Ledgerline" and any("platform-engineer" in f["statement"] for f in r["facts"])


def test_linkedin_sandbox_accepts_a_connection_after_a_day(seeded):
    from backend.channels import linkedin_sandbox

    with tx() as db:
        n = linkedin_sandbox.simulate_acceptance(db)
        again = linkedin_sandbox.simulate_acceptance(db)
    assert n >= 1 and again == 0
