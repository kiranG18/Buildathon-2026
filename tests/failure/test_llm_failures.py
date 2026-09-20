"""LLM failure injection: every failure ends in a handled state, never a crash and never an auto-qualify."""

import json
from types import SimpleNamespace

import pytest

from agents import llm_client, qualifier, sequencer
from agents.models import Draft, QualifierResult, SequencerResult
from backend.core.config import get_settings
from backend.core.db import tx
from backend.core.errors import AgentFailure
from backend.orchestrator.repo import campaign, enrollment, prospect
from tests.helpers import enrollment_of, scratch

pytestmark = pytest.mark.readonly


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_mode", "live")
    yield
    llm_client.set_transport(None)


def scripted(*replies):
    calls = []

    def transport(model, system, user, temperature, max_tokens):
        calls.append((model, user))
        r = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(r, Exception):
            raise r
        return llm_client.RawReply(r, 100, 20)

    llm_client.set_transport(transport)
    return calls


VALID_QUAL = json.dumps({"criteria": [{"name": "x", "met": "yes", "evidence_fact_id": None}] * 5})


def run(schema=QualifierResult):
    return llm_client.run(agent="qualifier", model=llm_client.HAIKU, system="s", user="u", schema=schema, key_inputs={"k": 1})


def test_mo1_invalid_json_is_repaired_once(seeded, live):
    calls = scripted("not json", VALID_QUAL)
    res = run()
    assert res.repaired and len(calls) == 2 and res.cost > 0


def test_mo2_wrong_schema_repairs_once_then_fails(seeded, live):
    scripted(json.dumps({"claims": []}), json.dumps({"claims": []}))
    with pytest.raises(AgentFailure) as e:
        run(Draft)
    assert e.value.code == "invalid_output"


def test_mo5_markdown_fences_and_prose_are_stripped(seeded, live):
    scripted("Here you go:\n```json\n" + VALID_QUAL + "\n```\nHope that helps")
    assert not run().repaired


def test_mo6_an_empty_string_is_a_failure_never_a_success(seeded, live):
    scripted("", "")
    with pytest.raises(AgentFailure):
        run()


def test_lf1_timeouts_retry_twice_then_fail_cleanly(seeded, live):
    calls = scripted(llm_client.LLMUnavailable("timeout"))
    with pytest.raises(AgentFailure) as e:
        run()
    assert e.value.code == "llm_unavailable" and len(calls) == 3


def test_lf2_a_429_backs_off_and_recovers_on_retry(seeded, live):
    calls = scripted(llm_client.LLMUnavailable("429"), VALID_QUAL)
    assert run().parsed.criteria and len(calls) == 2


def test_a2_qualifier_never_qualifies_on_invalid_output(seeded, live):
    scripted("garbage", "garbage")
    with scratch() as db:
        e = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        j = qualifier.judge(db, e, prospect(db, e["prospect_id"]), campaign(db, "C1"))
    assert j.failed and all(x["st"] == "unk" for x in j.crit)
    assert qualifier.decide(qualifier.score(j.crit), 70, False) != "qualify"


def test_a6_sequencer_falls_back_to_the_default_sequence_when_the_channel_is_illegal(seeded, live):
    bad = json.dumps({"steps": [{"day": 0, "channel": "sms", "purpose": "sms", "rationale": "x"}], "rationale": ""})
    calls = scripted(bad, bad)
    with scratch() as db:
        e = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        out = sequencer.build_plan(db, e, prospect(db, e["prospect_id"]), campaign(db, "C1"), ["email", "linkedin"], 0)
    assert out.fallback and out.steps[0]["ch"] == "email" and len(calls) == 2
    assert "sequencer_fallback" in out.note


def test_sequencer_accepts_a_valid_plan_and_validates_order(seeded, live):
    good = json.dumps({"steps": [{"day": 0, "channel": "email", "purpose": "intro", "rationale": "Verified email"}, {"day": 3, "channel": "linkedin", "purpose": "connect", "rationale": "Silent"}]})
    scripted(good)
    with scratch() as db:
        e = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        out = sequencer.build_plan(db, e, prospect(db, e["prospect_id"]), campaign(db, "C1"), ["email", "linkedin"], 0)
    assert not out.fallback and [s["ch"] for s in out.steps] == ["email", "linkedin"]
    assert sequencer.validate(SequencerResult.model_validate_json(good), ["email"]) is not None


def test_a7_a_live_writer_regenerates_once_then_uses_the_generic_safe_variant(seeded, live):
    from agents import writer

    bad = json.dumps({"channel": "email", "subject": "Hi", "body": "Customers save huge amounts of time.", "claims": [{"text": "Customers save huge amounts of time.", "source_type": "knowledge", "source_id": "K-999"}]})
    calls = scripted(bad, bad)
    with scratch() as db:
        e = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        d = writer.draft(db, e, prospect(db, e["prospect_id"]), campaign(db, "C1"), "intro", channel="email", version=2, rep_name="Marcus Lee", now_ms=0)
    assert d.generic_safe and d.regenerated and len(calls) == 2
    assert all(c["src"].startswith("K") for c in d.comp["claims"])


def test_a8_a_live_writer_accepts_a_grounded_draft(seeded, live):
    from agents import writer
    from backend.policy import grounding

    body = "Hi Dana, Northbeam cut its internal-tool request backlog from 212 to 125 tickets in one quarter (41%). Worth 20 minutes?"
    ok = json.dumps({"channel": "email", "subject": "Backlog", "body": body, "claims": [{"text": "Northbeam cut its internal-tool request backlog from 212 to 125 tickets in one quarter (41%).", "source_type": "knowledge", "source_id": "K-207"}]})
    scripted(ok)
    with scratch() as db:
        e = enrollment(db, enrollment_of("dana-whitfield", "C1")["id"])
        p = prospect(db, e["prospect_id"])
        d = writer.draft(db, e, p, campaign(db, "C1"), "intro", channel="email", version=2, rep_name="Marcus Lee", now_ms=0)
        assert not d.generic_safe and not grounding.check(db, d.comp, p, "C1")["bad"]


def test_r4_a_draft_citing_an_unknown_chunk_or_an_unsourced_number_fails_grounding(seeded):
    from backend.policy import grounding

    with scratch() as db:
        p = prospect(db, "dana-whitfield")
        unknown = {"body": "x", "segs": [{"t": "x", "src": "K-999"}], "claims": [{"t": "x", "src": "K-999"}]}
        assert grounding.check(db, unknown, p, "C1")["bad"][0]["reason"] == "unknown_source"
        wrong = {"body": "y", "segs": [{"t": "Northbeam cut backlog by 73%", "src": "K-207"}], "claims": [{"t": "Northbeam cut backlog by 73%", "src": "K-207"}]}
        assert grounding.check(db, wrong, p, "C1")["bad"][0]["reason"].startswith("number_not_in_source")
        other = {"body": "z", "segs": [{"t": "Ringlet reviews every call", "src": "K-407"}], "claims": [{"t": "Ringlet reviews every call", "src": "K-407"}]}
        assert grounding.check(db, other, p, "C1")["bad"][0]["reason"] == "unknown_source"


def test_r2_retrieval_is_campaign_scoped_and_global_chunks_are_shared(seeded):
    from rag import retrieve

    with tx() as db:
        c1 = {h["id"] for h in retrieve.search(db, "C1", "voice script open the call permission", None, 10, use_cache=False)}
        c3 = {h["id"] for h in retrieve.search(db, "C3", "voice script open the call permission", None, 10, use_cache=False)}
        glob = {h["id"] for h in retrieve.search(db, "C1", "Helix Agents AI agent platform enterprise workflows", None, 10, use_cache=False)}
    assert "K-431" in c3 and "K-431" not in c1
    assert "K-001" in glob


def test_r3_embeddings_down_falls_back_to_full_text(seeded, monkeypatch):
    from rag import retrieve

    monkeypatch.setattr(get_settings(), "fail_embeddings", True)
    with tx() as db:
        hits = retrieve.search(db, "C2", "data residency India region", None, 3, use_cache=False)
    assert hits and hits[0]["id"] in ("K-312", "K-302")


def test_r1_ten_retrieval_queries_land_the_expected_chunk_in_the_top_three(seeded):
    from rag import retrieve

    cases = [("C1", "internal-tool backlog case study Northbeam", "K-207"), ("C1", "we are building this in-house objection", "K-211"), ("C2", "data residency where does customer data stay", "K-312"),
             ("C2", "RBI compliance regulated lender", "K-311"), ("C2", "audit trail every action logged", "K-313"), ("C3", "voice call opening permission", "K-431"),
             ("C3", "already use an incumbent competitor tool", "K-411"), ("C3", "Ringlet reviews every call case study", "K-407"), ("C1", "pricing discount human rep", "K-022"),
             ("C1", "opt-out suppression compliance rules", "K-041")]
    hits = 0
    with tx() as db:
        for cid, q, want in cases:
            top = [h["id"] for h in retrieve.search(db, cid, q, None, 3, use_cache=False)]
            hits += want in top
    assert hits >= 8, hits


class FakeHttpReply:
    def __init__(self, body: dict):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def test_gemini_provider_maps_the_model_role_asks_for_json_and_reads_usage(seeded, live, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "gemini")
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return FakeHttpReply({"candidates": [{"content": {"parts": [{"text": VALID_QUAL}]}}], "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30}})

    monkeypatch.setattr(llm_client, "_get_http_client", lambda: SimpleNamespace(post=fake_post))
    res = run()
    assert res.provider == "gemini" and res.model == llm_client.GEMINI_FAST and (res.tokens_in, res.tokens_out) == (120, 30)
    assert seen["url"].endswith(f"/models/{llm_client.GEMINI_FAST}:generateContent") and seen["headers"] == {"x-goog-api-key": "test-key"}
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json" and seen["body"]["systemInstruction"]["parts"][0]["text"] == "s"
    strong = llm_client.resolve_model(llm_client.SONNET)
    assert strong == llm_client.GEMINI_STRONG


def test_groq_takes_over_when_the_primary_provider_has_no_key(seeded, live, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(get_settings(), "llm_fallback_provider", "groq")
    monkeypatch.setattr(get_settings(), "llm_fallback_key", "groq-key")
    monkeypatch.setattr(get_settings(), "llm_fallback_model", "")
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return FakeHttpReply({"choices": [{"message": {"content": VALID_QUAL}}], "usage": {"prompt_tokens": 90, "completion_tokens": 25}})

    monkeypatch.setattr(llm_client, "_get_http_client", lambda: SimpleNamespace(post=fake_post))
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_: None)
    res = run()
    assert res.provider == "fallback" and seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"] == {"Authorization": "Bearer groq-key"} and seen["body"]["model"] == llm_client.GROQ_STRONG and seen["body"]["response_format"] == {"type": "json_object"}


def test_a_429_with_retry_after_waits_that_long_and_does_not_use_up_an_attempt(seeded, live, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "groq")
    monkeypatch.setattr(get_settings(), "groq_api_key", "k")
    waits, replies = [], []

    class Limited(Exception):
        pass

    def fake_post(url, headers=None, json=None, timeout=None):
        request = llm_client.httpx.Request("POST", url)
        if len(replies) < 4:
            replies.append(429)
            raise llm_client.httpx.HTTPStatusError("limited", request=request, response=llm_client.httpx.Response(429, headers={"retry-after": "3"}, request=request))
        replies.append(200)
        assert json["reasoning_effort"] == "low" and json["model"] == llm_client.GROQ_FAST
        return FakeHttpReply({"choices": [{"message": {"content": VALID_QUAL}}], "usage": {"prompt_tokens": 50, "completion_tokens": 20}})

    monkeypatch.setattr(llm_client, "_get_http_client", lambda: SimpleNamespace(post=fake_post))
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: waits.append(s))
    res = run()
    assert res.provider == "groq" and replies == [429, 429, 429, 429, 200] and waits == [3.0, 3.0, 3.0, 3.0]
