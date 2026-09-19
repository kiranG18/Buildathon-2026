"""Funnel, reply, cost and comparison metrics computed from messages, meetings and agent_runs. Every number carries campaign_id."""

from datetime import datetime

from backend.core.db import Db
from backend.orchestrator.defs import STAGES, STATE_STAGE


def funnel(db: Db, campaign_id: str) -> list[dict]:
    states = [r["state"] for r in db.q("select state from enrollments where campaign_id = %s", (campaign_id,))]
    out, prev = [], None
    for i, name in enumerate(STAGES):
        n = sum(1 for s in states if STATE_STAGE.get(s, 0) >= i and not (s == "new" and i > 0))
        out.append({"stage": name.lower(), "count": n, "conversion": None if prev is None else (round(n / prev, 3) if prev else 0)})
        prev = n
    return out


def stats(db: Db, campaign_id: str | None = None, since: datetime | None = None) -> dict:
    cf = "" if campaign_id is None else "and campaign_id = %s"
    p = [] if campaign_id is None else [campaign_id]
    sf = "" if since is None else "and created_at >= %s"
    sp = [] if since is None else [since]
    prospects = db.q1(f"select count(*) as n from enrollments where true {cf}", p)["n"]
    touches = db.q1(f"select count(*) as n from messages where direction = 'out' and status = 'sent' and not is_reply and kind is distinct from 'call' {cf} {sf}", [*p, *sp])["n"]
    contacted = db.q1(f"select count(distinct enrollment_id) as n from messages where direction = 'out' and status = 'sent' and not is_reply and kind is distinct from 'call' {cf} {sf}", [*p, *sp])["n"]
    replies = db.q1(f"select count(distinct enrollment_id) as n from messages where direction = 'in' {cf} {sf}", [*p, *sp])["n"]
    pos = db.q1(f"select count(distinct enrollment_id) as n from messages where direction = 'in' and classification in ('positive', 'book') {cf} {sf}", [*p, *sp])["n"]
    meetings = db.q1(f"select count(*) as n from meetings where true {cf}", p)["n"]
    qualified = sum(1 for r in db.q(f"select state from enrollments where true {cf}", p) if STATE_STAGE.get(r["state"], 0) >= 2)
    cost = db.q1(f"select coalesce(sum(cost_usd), 0) as c from agent_runs where status = 'done' and not is_replay {cf} {sf}", [*p, *sp])["c"]
    return {
        "prospects": prospects, "touches": touches, "contacted": contacted, "replies": replies, "positive_replies": pos, "meetings": meetings, "qualified": qualified,
        "cost_usd": round(cost, 4),
        "reply_rate": round(replies / contacted, 4) if contacted else 0.0,
        "positive_reply_rate": round(pos / contacted, 4) if contacted else 0.0,
        "meeting_rate": round(meetings / contacted, 4) if contacted else 0.0,
        "cost_per_prospect": round(cost / prospects, 4) if prospects else 0.0,
        "cost_per_qualified": round(cost / qualified, 4) if qualified else 0.0,
        "cost_per_conversation": round(cost / replies, 4) if replies else 0.0,
    }


def by_agent(db: Db, campaign_id: str | None = None) -> list[dict]:
    cf = "" if campaign_id is None else "and campaign_id = %s"
    rows = db.q(
        f"""select agent_key, count(*) as runs, coalesce(sum(cost_usd), 0) as cost, coalesce(avg(latency_s), 0) as lat,
            avg(case when status = 'failed' then 1.0 else 0.0 end) as fail from agent_runs where not is_replay {cf} group by agent_key order by agent_key""",
        [] if campaign_id is None else [campaign_id],
    )
    return [{"agent_key": r["agent_key"], "runs": r["runs"], "cost_usd": round(r["cost"], 4), "avg_latency_ms": round(r["lat"] * 1000), "failure_rate": round(float(r["fail"]), 3)} for r in rows]


def prompt_versions(db: Db, campaign_id: str | None, agent: str | None) -> list[dict]:
    where, params = ["true"], []
    if campaign_id:
        where.append("v.campaign_id = %s")
        params.append(campaign_id)
    if agent:
        where.append("v.agent_key = %s")
        params.append(agent)
    rows = db.q(
        f"""select v.id, v.campaign_id, v.agent_key, v.version, v.gold, count(r.id) as runs, coalesce(avg(r.cost_usd), 0) as cost
            from prompt_versions v left join agent_runs r on r.campaign_id = v.campaign_id and r.role = v.agent_key and r.prompt_version = v.version and not r.is_replay
            where {' and '.join(where)} group by v.id order by v.campaign_id, v.agent_key, v.version""",
        params,
    )
    return [{"version_id": r["id"], "campaign_id": r["campaign_id"], "agent_key": r["agent_key"], "version": r["version"], "golden_score": (r["gold"] or [None, None])[1],
             "runs": r["runs"], "cost_per_run": round(r["cost"], 4)} for r in rows]
