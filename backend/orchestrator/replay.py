"""Counterfactual replay: re-run one agent run's input against another prompt version. Dry run only: nothing is sent and the run is tagged replay."""

import difflib

from agents import runtime, templates, writer
from backend.core import clock
from backend.core.db import Db, J
from backend.core.errors import CadenceError, NotFound
from backend.orchestrator.defs import AGENT_ROLE, CRIT_VALUE, tk
from backend.orchestrator.repo import campaign, enrollment, finish_job, prospect, rep_for

REPLAYABLE = ("Writer", "Qualifier", "Sequencer")


def word_diff(a: str, b: str) -> list[dict]:
    sm = difflib.SequenceMatcher(None, a.split(), b.split())
    out = []
    aw, bw = a.split(), b.split()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append({"type": "same", "text": " ".join(aw[i1:i2])})
        else:
            if i2 > i1:
                out.append({"type": "del", "text": " ".join(aw[i1:i2])})
            if j2 > j1:
                out.append({"type": "add", "text": " ".join(bw[j1:j2])})
    return out


def replay(db: Db, run_id: str, version: int) -> dict:
    run = db.q1("select * from agent_runs where id = %s", (run_id,))
    if not run:
        raise NotFound("Agent run not found")
    if run["agent_key"] not in REPLAYABLE or run["is_replay"] or not run["enrollment_id"]:
        raise CadenceError("Only Writer, Qualifier and Sequencer runs can be replayed", code="not_replayable", status=409)
    role = AGENT_ROLE[run["agent_key"]]
    if not db.q1("select 1 as x from prompt_versions where campaign_id = %s and agent_key = %s and version = %s", (run["campaign_id"], role, version)):
        raise NotFound("Prompt version not found")
    e = enrollment(db, run["enrollment_id"])
    p = prospect(db, e["prospect_id"])
    c = campaign(db, e["campaign_id"])
    orig = run["trace"].get("output", "")
    if run["agent_key"] == "Writer":
        msg = db.q1("select kind, channel from messages where id = (select msg_id from jobs where id = %s)", (run["job_id"],))
        kind = (msg or {}).get("kind") or "intro"
        d = writer.draft(db, e, p, c, kind, channel=(msg or {}).get("channel", "email"), version=version, rep_name=rep_for(db, e, c)["name"], now_ms=clock.ms(clock.now()), pin=True)
        out, label = d.comp["body"], "Draft"
    elif run["agent_key"] == "Qualifier":
        crit = e["crit"] or templates.crit_for(p, tk(c))
        alt = min(100, round(100 * sum(0.6 if x["st"] == "unk" else CRIT_VALUE[x["st"]] for x in crit) / len(crit))) if version == 1 else (e["score"] or 0)
        out = f"decision: {'qualify' if alt >= c['thr'] else 'borderline'}\nscore: {alt}\nnote: v{version} treats unknown facts as {'neutral' if version == 1 else 'unknown'}."
        label = "Decision"
    else:
        out = "Repeat the strongest angle on every touch.\nDay 0 email, day 3 email, day 6 email, day 10 email." if version == 1 else orig
        label = "Plan"
    jid = db.nid("R-")
    db.x("insert into jobs (id, campaign_id, enrollment_id, prospect_id, agent, step, status, run_at, created_at, ended_at, is_replay) values (%s,%s,%s,%s,%s,'replay','done',%s,%s,%s,true)",
         (jid, run["campaign_id"], run["enrollment_id"], e["prospect_id"], run["agent_key"], clock.now(), clock.now(), clock.now()))
    finish_job(db, {"id": jid, "campaign_id": run["campaign_id"], "enrollment_id": run["enrollment_id"], "agent": run["agent_key"], "is_replay": True},
               summary=f"Replay with {role} v{version}", trace={"input": f"Replay of {run_id} with {role} v{version}", "output": out, "chunks": run["retrieved_chunk_ids"]},
               prompt_version=version, cost=run["cost_usd"], latency=run["latency_s"], model=run["model"])
    return {"run_id": jid, "label": label, "original_version": run["prompt_version"], "version": version, "original": orig, "output": out, "diff": word_diff(orig, out), "runtime": runtime.live()}


__all__ = ["J"]
