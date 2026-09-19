"""Qualifier (ICP Fitment). Hard filters run in code before any call. The model judges criteria from supplied facts only.
Code computes the score and the decision, so the model never does arithmetic. A failed call never qualifies anyone.
"""

from dataclasses import dataclass, field

from agents import llm_client, runtime, templates
from agents.models import QualifierResult
from agents.prompting import render
from backend.core.db import Db
from backend.core.errors import AgentFailure
from backend.orchestrator.defs import CRIT_VALUE, KB_ICP, KB_ICP2, static, tk

MET = {"yes": "met", "partial": "part", "no": "no", "unknown": "unk"}


@dataclass
class Judgement:
    crit: list[dict]
    failed: bool = False
    error: str = ""
    chunks: list[str] = field(default_factory=list)
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float | None = None
    latency: float | None = None
    provider: str = "direct"
    prompt_version: int | None = None


def hard_reject(p: dict, c: dict) -> str | None:
    return (p.get("rej") or {}).get(tk(c))


def score(crit: list[dict]) -> int:
    return round(100 * sum(CRIT_VALUE[x["st"]] for x in crit) / len(crit))


def decide(sc: int, thr: int, no_facts: bool) -> str:
    """Score at or above the threshold qualifies. Within 20 below it is borderline for review. Lower rejects. No facts is always borderline."""
    if no_facts:
        return "borderline"
    if sc < thr - 20:
        return "reject"
    return "borderline" if sc < thr else "qualify"


def strict_prompt(lines: list[str]) -> bool:
    """Fake mode judges unknown facts as unknown only when the Qualifier prompt says so. A prompt that treats them as neutral inflates scores."""
    return any("as unknown" in line.lower() for line in lines)


def judge(db: Db, e: dict, p: dict, c: dict, version: int | None = None) -> Judgement:
    key = tk(c)
    b = runtime.bundle(db, c["id"], "Qualifier", version)
    if not runtime.live():
        crit = templates.crit_for(p, key)
        if not strict_prompt(b.agent):
            crit = [{**x, "st": "part" if x["st"] == "unk" else x["st"]} for x in crit]
        return Judgement(crit, chunks=[KB_ICP[key], KB_ICP2[key]] if key in KB_ICP else [], prompt_version=b.agent_version)
    from agents.memory import build

    hits = runtime.gather(db, c["id"], runtime.plan_query(p, "ideal customer profile qualification"), [(["icp"], 2), (["playbook"], 1)])
    labels = static()["CRIT"][key]
    schema = QualifierResult.model_json_schema()
    task = ("Judge each criterion using only the supplied facts. Answer 'unknown' when no fact speaks to it. "
            f"Return criteria in this order with these exact names: {labels}. Cite evidence_fact_id from the facts.")
    system, user = render(campaign_system=b.system, agent_prompt=b.agent, knowledge=hits, memory=build(db, e), task=task, schema=schema)
    try:
        res = llm_client.run(agent="qualifier", model=llm_client.HAIKU, system=system, user=user, schema=QualifierResult, prompt_version=b.agent_version,
                             key_inputs={"pid": p["id"], "cid": c["id"]})
    except AgentFailure as err:
        return Judgement([{"label": lab, "st": "unk", "ev": None} for lab in labels], failed=True, error=err.message, chunks=[h["id"] for h in hits], prompt_version=b.agent_version)
    by_name = {j.name.strip().lower(): j for j in res.parsed.criteria}
    fact_ids = {f["id"] for f in p["facts"]}
    crit = []
    for i, lab in enumerate(labels):
        j = by_name.get(lab.lower()) or (res.parsed.criteria[i] if i < len(res.parsed.criteria) else None)
        ev = j.evidence_fact_id if j and j.evidence_fact_id in fact_ids else None
        crit.append({"label": lab, "st": MET[j.met] if j else "unk", "ev": ev})
    r = res.parsed
    return Judgement(crit, chunks=[h["id"] for h in hits], model=res.model, tokens_in=res.tokens_in, tokens_out=res.tokens_out, cost=res.cost, latency=res.latency,
                     provider=res.provider, prompt_version=b.agent_version, error="; ".join(r.reasons)[:200])
