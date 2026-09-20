"""DronaHQ agent provider. The worker triggers hosted agents through their Webhook triggers and falls back to the direct provider on any failure.

Researcher: the agent saves its facts through the save_research MCP tool. The worker resumes on that callback, or after 90 seconds
reruns the step on the direct provider (activity: provider_fallback). Responder: expects a structured ResponderResult in the response.
Voice: a live call posts to the Voice agent, and the post-call webhook (POST /voice/outcome) records the result.
"""

import json
import time
from datetime import timedelta

import httpx
from pydantic import ValidationError

from agents import researcher, runtime
from agents.models import ResearchResult, ResponderResult
from agents.responder import Reading
from agents.util import strip_fences
from backend.core import clock
from backend.core.config import get_settings
from backend.core.db import Db
from backend.core.logging import log
from backend.orchestrator.repo import act

POST_TIMEOUT_S = 110.0
WAIT_SECONDS = 40.0
RESPONDER_WAIT_SECONDS = 20.0
POLL_SECONDS = 1.0
_transport: httpx.BaseTransport | None = None


def set_transport(t: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = t


def enabled(agent: str) -> bool:
    s = get_settings()
    provider = {"Researcher": s.agent_provider_researcher, "Responder": s.agent_provider_responder, "Caller": s.agent_provider_caller}.get(agent, "direct")
    url = {"Researcher": s.dronahq_researcher_webhook_url, "Responder": s.dronahq_responder_webhook_url}.get(agent, s.dronahq_voice_agent_id)
    return provider == "dronahq" and bool(url)


def agent_result(body) -> dict | None:
    """The agent's result: a top-level output or result, or the last JSON object in the text steps of a Standard reply."""
    if not isinstance(body, dict):
        return None
    for key in ("output", "result"):
        if isinstance(body.get(key), dict):
            return body[key]
    steps = body.get("response")
    if isinstance(steps, list):
        for item in reversed(steps):
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    obj = json.loads(strip_fences(item.get("text", "")))
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    return obj
    return body


def _post(url: str, payload: dict, timeout: float = POST_TIMEOUT_S) -> httpx.Response:
    headers = {"api-key": get_settings().dronahq_api_key} if get_settings().dronahq_api_key else {}
    with httpx.Client(transport=_transport, timeout=timeout) as client:
        return client.post(url, json=payload, headers=headers)


def _bundle_payload(db: Db, campaign_id: str, role: str) -> dict:
    b = runtime.bundle(db, campaign_id, role)
    return {"campaign_system_prompt": "\n".join(b.system), "agent_prompt": "\n".join(b.agent), "prompt_version_id": f"{campaign_id}-{role}-v{b.agent_version}"}


def _fallback(db: Db, e: dict, p: dict, why: str) -> researcher.Research:
    act(db, e, "gate", f"DronaHQ Researcher unavailable ({why}). The step reran on the direct provider", agent="Guardian", reason_code="provider_fallback")
    log().warning("dronahq researcher fallback", extra={"event": "provider_fallback", "reason_code": why})
    return researcher.research(p)


def research(db: Db, e: dict, p: dict, c: dict) -> researcher.Research:
    from backend.mcp import tools

    payload = {
        "run_id": db.nid("run_"), "agent": "researcher", "enrollment_id": e["id"], "campaign_id": c["id"],
        "prompt_bundle": _bundle_payload(db, c["id"], "Researcher"),
        "context": {"prospect": {"name": p["full_name"], "title": p["title"], "company": p["company"], "domain": p["domain"], "linkedin": p["linkedin_url"]},
                    "facts": [{"id": f["id"], "statement": f["text"], "source_url": f["url"]} for f in p["facts"]], "checklist": []},
        "output_schema": ResearchResult.model_json_schema(),
    }
    started = db.q1("select clock_timestamp() as t")["t"]
    parsed = None
    try:
        r = _post(get_settings().dronahq_researcher_webhook_url, payload)
        r.raise_for_status()
        try:
            result = agent_result(r.json())
            parsed = ResearchResult.model_validate(result) if result else None
        except (ValueError, ValidationError):
            parsed = None
    except httpx.TimeoutException:
        log().warning("dronahq researcher slow", extra={"event": "webhook_slow"})
    except httpx.HTTPError as exc:
        return _fallback(db, e, p, type(exc).__name__)
    def saved_through_mcp():
        return db.q1("select facts_saved from research_callbacks where enrollment_id = %s and saved_at >= %s order by saved_at desc limit 1", (e["id"], started))

    row = saved_through_mcp()
    if row:
        return researcher.Research([], parsed.gaps if parsed else [], "dronahq", f" DronaHQ agent saved {row['facts_saved']} sourced facts through MCP.")
    if parsed is not None and parsed.facts:
        saved = tools.save_research_in(db, e["id"], parsed.model_dump())
        return researcher.Research([], parsed.gaps, "dronahq", f" DronaHQ agent returned {saved['saved_facts']} sourced facts.")
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        row = saved_through_mcp()
        if row:
            return researcher.Research([], [], "dronahq", f" DronaHQ agent saved {row['facts_saved']} sourced facts through MCP.")
        time.sleep(POLL_SECONDS)
    return _fallback(db, e, p, f"no callback in {int(WAIT_SECONDS)} seconds")


def respond(db: Db, e: dict, p: dict, c: dict, text: str) -> Reading | None:
    """Ask the hosted Responder to read a reply. Returns None on any failure so the caller uses its own rules and model."""
    from backend.mcp.tools import get_timeline_in

    payload = {"run_id": db.nid("run_"), "agent": "responder", "enrollment_id": e["id"], "campaign_id": c["id"], "prompt_bundle": _bundle_payload(db, c["id"], "Responder"),
               "context": {"inbound": text, "timeline": get_timeline_in(db, e["id"])}, "output_schema": ResponderResult.model_json_schema()}
    started = db.q1("select clock_timestamp() as t")["t"]

    def unavailable(why: str) -> None:
        act(db, e, "gate", f"DronaHQ Responder unavailable ({why}). The reply used the direct provider", agent="Guardian", reason_code="provider_fallback")

    def submitted() -> ResponderResult | None:
        row = db.q1("select decision from responder_decisions where enrollment_id = %s and saved_at >= %s order by saved_at desc limit 1", (e["id"], started))
        return ResponderResult.model_validate(row["decision"]) if row else None

    parsed = None
    try:
        r = _post(get_settings().dronahq_responder_webhook_url, payload)
        r.raise_for_status()
        try:
            parsed = ResponderResult.model_validate(agent_result(r.json()) or {})
        except (ValueError, ValidationError):
            parsed = None
    except httpx.TimeoutException:
        log().warning("dronahq responder slow", extra={"event": "webhook_slow"})
    except httpx.HTTPError as exc:
        unavailable(type(exc).__name__)
        return None
    parsed = submitted() or parsed
    deadline = time.monotonic() + RESPONDER_WAIT_SECONDS
    while parsed is None and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        parsed = submitted()
    if parsed is None:
        unavailable("no decision submitted")
        return None
    from agents.responder import LLM_TO_INTERNAL, OBJECTION_SUB

    if parsed.classification == "objection":
        cls, sub = "objection", OBJECTION_SUB.get((parsed.objection_type or "").lower().split()[0] if parsed.objection_type else "", "budget")
    else:
        cls, sub = LLM_TO_INTERNAL.get(parsed.classification, ("question", None))[0], None
    return Reading(cls, sub, f"DronaHQ Responder: {parsed.classification}", True, parsed.reply_draft, [{"t": x.text, "src": x.source_id} for x in parsed.claims],
                   confidence=parsed.confidence, escalate_low_confidence=parsed.confidence < 0.6)


def trigger_call(db: Db, e: dict, p: dict) -> bool:
    """Start a live call through DronaHQ's outbound dispatch API. False when telephony is not configured or the dispatch is refused, so the caller stays in sandbox."""
    s = get_settings()
    if not (s.dronahq_api_key and s.dronahq_voice_agent_id and s.dronahq_voice_from_number and p["phone"]):
        return False
    payload = {"destination_phonenumber": [p["phone"]], "source_phone_number": s.dronahq_voice_from_number, "agent_id": s.dronahq_voice_agent_id, "agent_overrides": {}}
    try:
        r = _post(s.dronahq_voice_call_url, payload, timeout=15)
        r.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log().warning("dronahq voice dispatch failed", extra={"event": "voice_dispatch_failed", "reason_code": type(exc).__name__})
        return False


def sweep_awaiting_outcome(db: Db) -> None:
    """A call whose post-webhook never arrives becomes unknown_outcome plus an escalation after 10 minutes."""
    from backend.orchestrator.repo import campaign, enrollment, rep_for

    cutoff = clock.now() - timedelta(minutes=10)
    for call in db.q("select * from calls where disposition = 'awaiting_outcome' and at < %s", (cutoff,)):
        e = enrollment(db, call["enrollment_id"])
        c = campaign(db, e["campaign_id"])
        rep = rep_for(db, e, c)
        db.x("update calls set disposition = 'unknown_outcome', summary = 'No outcome arrived from the voice agent within 10 minutes.' where id = %s", (call["id"],))
        db.x("insert into escalations (id, enrollment_id, campaign_id, reason_code, rep_id, created_at, summary, rule, created_by_agent) values (%s,%s,%s,'unknown_outcome',%s,%s,%s,'voice post-webhook missing','Caller')",
             (db.nid("ES-"), e["id"], e["campaign_id"], rep["id"], clock.now(), "A call was placed but no outcome was recorded. Check the DronaHQ Voice trace."))
        act(db, e, "call", "Call outcome never arrived: unknown_outcome, escalated to the rep", agent="Caller", reason_code="unknown_outcome")
