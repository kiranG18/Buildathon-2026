"""Pydantic output models for the six agents. Their JSON Schemas are exported to agents/schemas/ for DronaHQ Structured Output."""

from typing import Literal

from pydantic import BaseModel, Field

Channel = Literal["email", "linkedin", "sms", "voice"]


class Fact(BaseModel):
    id: str
    category: str = "company"
    statement: str
    source_url: str
    confidence: float = Field(ge=0, le=1)


class PainHypothesis(BaseModel):
    text: str
    supporting_fact_ids: list[str] = []


class ResearchResult(BaseModel):
    facts: list[Fact] = []
    trigger_events: list[str] = []
    pain_hypotheses: list[PainHypothesis] = []
    gaps: list[str] = []


class CriterionJudgment(BaseModel):
    name: str
    met: Literal["yes", "partial", "no", "unknown"]
    evidence_fact_id: str | None = None


class QualifierResult(BaseModel):
    """The model judges each criterion. Code turns the judgements into a score and a decision."""

    criteria: list[CriterionJudgment]
    reasons: list[str] = []
    missing_info: list[str] = []


class PlanStep(BaseModel):
    day: int = Field(ge=0, le=30)
    channel: Channel
    purpose: Literal["intro", "connect", "message", "value_add", "nudge", "breakup", "call_offer", "meeting_ask", "sms"]
    rationale: str


class SequencerResult(BaseModel):
    steps: list[PlanStep]
    rationale: str = ""


class Claim(BaseModel):
    text: str
    source_type: Literal["prospect_fact", "knowledge"]
    source_id: str


class Draft(BaseModel):
    channel: Channel = "email"
    subject: str | None = None
    body: str
    claims: list[Claim] = []
    cta: str = ""
    omitted_personalisation_reason: str | None = None


class ResponderResult(BaseModel):
    classification: Literal[
        "interested", "meeting_request", "objection", "question", "not_now", "not_interested", "unsubscribe", "out_of_office", "wrong_person", "other"
    ]
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    objection_type: str | None = None
    next_action: Literal["reply", "book_meeting", "escalate", "nurture", "stop"]
    reply_draft: str = ""
    claims: list[Claim] = []
    slots_offered: list[str] = []
    escalation_reason: str | None = None
    summary_update: str = ""
    confidence: float = Field(default=0.8, ge=0, le=1)


class CallOutcome(BaseModel):
    transcript: list[dict] = []
    recording_url: str | None = None
    disposition: Literal["connected_interested", "callback", "not_interested", "voicemail", "wrong_number", "escalate"]
    objections: list[str] = []
    next_step: str = ""
    booked_slot: str | None = None
    structured_answers: dict = {}


MODELS = {
    "researcher": ResearchResult,
    "qualifier": QualifierResult,
    "sequencer": SequencerResult,
    "writer": Draft,
    "responder": ResponderResult,
    "caller": CallOutcome,
}


def flatten_schema(schema: dict) -> dict:
    """Inline $defs so tools that reject $ref (DronaHQ Structured Output) accept the schema."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)
