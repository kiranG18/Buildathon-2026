"""Prompt coach: reads the failing golden cases for a prompt version and saves an improved draft. It never activates anything.

Live mode asks Sonnet for the rewrite. Fake mode restores the campaign's default harness lines for the behaviour that failed.
"""

from pydantic import BaseModel

from agents import llm_client, runtime
from backend.core.db import Db
from backend.core.errors import AgentFailure, CadenceError
from backend.orchestrator import prompts_svc
from backend.orchestrator.repo import campaign
from evals import runner


class CoachResult(BaseModel):
    lines: list[str]
    note: str = ""


def suggest(db: Db, campaign_id: str, role: str, version: int, by: dict) -> dict:
    res = runner.run(db, campaign_id, role, version, record=False)
    failing = [r for r in res["results"] if not r["ok"]]
    if not failing:
        raise CadenceError(f"{role} v{version} passes every golden case, so there is nothing to improve", code="nothing_to_improve", status=409)
    current = db.q1("select lines from prompt_versions where campaign_id = %s and agent_key = %s and version = %s", (campaign_id, role, version))["lines"]
    c = campaign(db, campaign_id)
    lines = prompts_svc.default_lines(role, c)
    note = f"Coach draft from {len(failing)} failing golden cases"
    if runtime.live():
        summary = "\n".join(f"- expected {f['case']}, got {f['got']}: {f['note']}" for f in failing[:8])
        system = "You improve sales-agent prompts. Return a JSON object {\"lines\": [...], \"note\": \"...\"} with the full improved prompt as short lines. Keep every existing safety rule."
        user = "CURRENT PROMPT\n" + "\n".join(current) + "\n\nFAILING GOLDEN CASES\n" + summary
        try:
            out = llm_client.run(agent="coach", model=llm_client.SONNET, system=system, user=user, schema=CoachResult, key_inputs={"c": campaign_id, "r": role, "v": version})
            lines, note = out.parsed.lines, (out.parsed.note or note)
        except AgentFailure:
            pass
    problems = prompts_svc.lint("\n".join(lines))
    if problems:
        raise CadenceError("The coach draft failed the prompt lint: " + "; ".join(problems), code="lint_failed", status=422)
    saved = prompts_svc.save_version(db, campaign_id, role, "\n".join(lines), by, note, version)
    return {"version": saved["version"], "failing": len(failing), "note": note}
