"""Sequencer (Outreach Strategy and Follow-up). Code lists the legal channels first. The model picks among them and gives a reason.
Code validates the pick. An invalid pick retries once, then falls back to the campaign's default sequence (sequencer_fallback).
"""

from dataclasses import dataclass, field

from agents import llm_client, runtime, templates
from agents.models import SequencerResult
from agents.prompting import render
from backend.core.db import Db
from backend.core.errors import AgentFailure
from backend.orchestrator.defs import CHANNELS, KB_PLAY, static, tk

DAY = 86_400_000


@dataclass
class PlanOut:
    steps: list[dict]
    fallback: bool = False
    note: str = ""
    chunks: list[str] = field(default_factory=list)
    model: str = ""
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None
    latency: float | None = None
    prompt_version: int | None = None


def validate(result: SequencerResult, allowed: list[str]) -> str | None:
    if not result.steps:
        return "the plan has no steps"
    for s in result.steps:
        if s.channel not in CHANNELS or s.channel not in allowed:
            return f"channel {s.channel} is not in allowed_channels {allowed}"
    days = [s.day for s in result.steps]
    if days != sorted(days):
        return "steps must be in day order"
    return None


def build_plan(db: Db, e: dict, p: dict, c: dict, allowed: list[str], t0_ms: float, replan_reason: str | None = None) -> PlanOut:
    key = tk(c)
    default = templates.build_default_plan(key, allowed, t0_ms)
    chunks = [KB_PLAY[key]] if key in KB_PLAY else []
    if not runtime.live():
        return PlanOut(default, chunks=chunks)
    from agents.memory import build

    b = runtime.bundle(db, c["id"], "Strategy")
    hits = runtime.gather(db, c["id"], runtime.plan_query(p, "sequence rules channel order"), [(["playbook"], 2)])
    seq = static()["SEQ"][key]
    task = (f"Plan the touch sequence. allowed_channels={allowed}. Default sequence: {seq}. "
            + (f"Replan because: {replan_reason}. " if replan_reason else "")
            + "Return steps in day order. Each step needs a one sentence rationale. Use only allowed channels.")
    system, user = render(campaign_system=b.system, agent_prompt=b.agent, knowledge=hits, memory=build(db, e), task=task, schema=SequencerResult.model_json_schema())
    err_hint = ""
    tin = tout = 0
    cost = 0.0
    for _attempt in range(2):
        try:
            res = llm_client.run(agent="sequencer", model=llm_client.SONNET, system=system, user=user + err_hint, schema=SequencerResult, prompt_version=b.agent_version,
                                 key_inputs={"eid": e["id"], "allowed": allowed, "why": replan_reason or ""})
        except AgentFailure as ex:
            return PlanOut(default, True, f"sequencer_fallback: {ex.message}", chunks, prompt_version=b.agent_version)
        tin, tout, cost = tin + res.tokens_in, tout + res.tokens_out, cost + res.cost
        problem = validate(res.parsed, allowed)
        if problem is None:
            steps = [{"day": s.day, "ch": s.channel, "purpose": s.purpose, "reason": s.rationale, "status": "pending", "due": t0_ms + s.day * DAY, "cond": None}
                     for s in res.parsed.steps]
            return PlanOut(steps, chunks=[h["id"] for h in hits] or chunks, model=res.model, tokens_in=tin, tokens_out=tout, cost=cost, latency=res.latency,
                           prompt_version=b.agent_version)
        err_hint = f"\n\nYour last plan was rejected: {problem}. Fix it."
    return PlanOut(default, True, "sequencer_fallback: invalid channel or order after retry", chunks, tokens_in=tin, tokens_out=tout, cost=cost, prompt_version=b.agent_version)
