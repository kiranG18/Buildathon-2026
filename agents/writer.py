"""Writer (Personalisation and Email). The only unit that writes customer-facing outreach text.

Fake mode renders the deterministic templates. Live mode retrieves campaign knowledge, asks the model for a Draft with claims[],
then the grounding check in code decides. One regeneration with the failure list, then the generic_safe variant.
"""

import re
from dataclasses import dataclass, field

from agents import llm_client, runtime, templates
from agents.models import Draft
from agents.prompting import render
from backend.core.db import Db
from backend.core.errors import AgentFailure
from backend.orchestrator.defs import tk
from backend.policy import grounding

NO_GROUND_KINDS = {"slots", "confirm", "notnow", "call_offer"}


class KnowledgeGap(Exception):
    """Retrieval returned nothing, so no draft may exist."""


@dataclass
class DraftOut:
    comp: dict
    chunks: list[str] = field(default_factory=list)
    generic_safe: bool = False
    regenerated: bool = False
    failures: list[str] = field(default_factory=list)
    model: str = ""
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None
    latency: float | None = None
    prompt_version: int | None = None


def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", s)
    s = re.sub(r"[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]", " ", s)
    return s.strip()


def segs_from_claims(body: str, claims: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split the body around each claim so the evidence panel can mark cited sentences. Returns (segs, claims_not_found_in_body)."""
    clean_body = _clean_text(body)
    segs: list[dict] = []
    missing: list[dict] = []
    rest = clean_body
    for cl in claims:
        t = _clean_text(cl.get("t", ""))
        if not t:
            continue
        i = rest.find(t)
        match_len = len(t)
        if i < 0:
            i = rest.lower().find(t.lower())
        if i < 0:
            clean_t = t.strip(" \t\n\r.,;:!?\"'()[]{}")
            if clean_t:
                i = rest.find(clean_t)
                if i < 0:
                    i = rest.lower().find(clean_t.lower())
                if i >= 0:
                    match_len = len(clean_t)
        if i < 0:
            missing.append(cl)
            continue
        if i:
            segs.append({"t": rest[:i]})
        matched_text = rest[i : i + match_len]
        segs.append({"t": matched_text, "src": cl["src"]})
        rest = rest[i + match_len :]
    if rest:
        segs.append({"t": rest})
    return segs, missing


def _comp_from_draft(d: Draft, channel: str) -> dict:
    body = _clean_text(d.body)
    claims = [{"t": _clean_text(c.text), "src": c.source_id} for c in d.claims]
    segs, missing = segs_from_claims(body, claims)
    subject = _clean_text(d.subject) if channel == "email" else None
    comp = {"ch": channel, "subject": subject, "segs": segs, "body": body, "claims": [s for s in segs if s.get("src")]}
    comp["claims"] += [{**m, "src": "?"} for m in missing]
    return comp


def draft(db: Db, e: dict, p: dict, c: dict, kind: str, *, channel: str, version: int, rep_name: str, now_ms: float, pin: bool = False) -> DraftOut:
    key = tk(c)

    def template(facts_override: list | None = None) -> dict:
        pp = {**p, "facts": p["facts"] if facts_override is None else facts_override}
        comp = templates.compose(kind, p=pp, tkey=key, rep_name=rep_name, ver=runtime.template_version(db, c["id"], version), now_ms=now_ms, meeting=e.get("meeting"))
        comp["allow_uncited_numbers"] = kind in NO_GROUND_KINDS
        return comp

    if not runtime.live():
        comp = template()
        return DraftOut(comp, chunks=sorted({x["src"] for x in comp["claims"] if x["src"].startswith("K")}), prompt_version=version)

    from agents.memory import build

    b = runtime.bundle(db, c["id"], "Writer", version if pin else None)
    hits = runtime.gather(
        db, c["id"], runtime.plan_query(p, f"{kind} {channel}"),
        [(["case study"], 2), (["examples"], 2), (["overview", "product"], 1), (["brand"], 1), (["compliance"], 1)],
    )
    if not hits:
        raise KnowledgeGap(f"No knowledge retrieved for {c['id']} {kind}")
    limits = {"email": f"subject up to 7 words, body up to {c['words']} words", "linkedin": "up to 300 characters", "sms": "up to 160 characters, name the sender, include opt-out"}[channel]
    task = (f"Write one {channel} message, purpose '{kind}'. Limits: {limits}. One personal hook from the highest-confidence fact, one proof point from a knowledge block, one CTA. "
            "Crucial: claims[].text must be copied verbatim from body. Every proof point must use ONLY case studies and metrics provided in KNOWLEDGE, never invent customer names or percentages. "
            "For every claim, set source_id to the exact fact id (e.g. F...) or knowledge id (e.g. K-...) from which it was taken. "
            "If no fact supports personalisation, leave the hook out and say why in omitted_personalisation_reason.")
    system, user = render(campaign_system=b.system, agent_prompt=b.agent, knowledge=hits, memory=build(db, e), task=task, schema=Draft.model_json_schema())
    chunk_ids = [h["id"] for h in hits]
    tin = tout = 0
    cost = 0.0
    failures: list[str] = []
    regenerated = False
    hint = ""
    for _attempt in range(2):
        try:
            res = llm_client.run(agent="writer", model=llm_client.SONNET, system=system, user=user + hint, schema=Draft, temperature=0.3, prompt_version=b.agent_version,
                                 key_inputs={"eid": e["id"], "kind": kind, "channel": channel})
        except AgentFailure:
            failures.append("model_failure")
            break
        tin, tout, cost = tin + res.tokens_in, tout + res.tokens_out, cost + res.cost
        comp = _comp_from_draft(res.parsed, channel)
        gc = grounding.check(db, comp, p, c["id"])
        problem = grounding.length_problem(comp, channel, c["words"])
        if not gc["bad"] and not problem:
            return DraftOut(comp, chunk_ids, regenerated=regenerated, failures=[], model=res.model, tokens_in=tin, tokens_out=tout, cost=cost,
                            latency=res.latency, prompt_version=b.agent_version)
        failures = [f"{x['reason']}: {x['t'][:60]}" for x in gc["bad"]] + ([problem] if problem else [])
        hint = "\n\nYour last draft failed checks: " + "; ".join(failures) + ". Regenerate without those problems."
        regenerated = True
    comp = template(facts_override=[])
    comp["claims"] = [x for x in comp["claims"] if x["src"].startswith("K")]
    return DraftOut(comp, chunk_ids, generic_safe=True, regenerated=regenerated, failures=failures, tokens_in=tin, tokens_out=tout, cost=cost, prompt_version=b.agent_version)
