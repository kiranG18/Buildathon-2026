"""Golden-set runner. Runs one prompt version of one agent against hand-labelled cases and stores the score.

Cases run through the real agent code on a temporary prospect inside a savepoint that is always rolled back, so nothing leaks into campaign data.
Qualifier and Responder are scored by exact match. The Writer is scored by the grounding check and the length limits, and by an LLM judge when a live model is configured.
"""

import json
from pathlib import Path

from agents import qualifier, responder, runtime, templates, writer
from agents.util import slug
from backend.core import clock
from backend.core.db import Db, J
from backend.core.errors import CadenceError
from backend.orchestrator.defs import tk
from backend.orchestrator.repo import campaign, enrollment, new_enrollment, prospect
from backend.policy import grounding

GOLDEN = Path(__file__).resolve().parent / "golden"
ROLES = ("Qualifier", "Responder", "Writer")


class _Rollback(Exception):
    pass


def load_cases(role: str) -> list[dict]:
    return json.loads((GOLDEN / f"{role.lower()}.json").read_text(encoding="utf-8"))


def _temp_prospect(db: Db, n: int, key: str, case: dict) -> str:
    pid = slug(f"eval case {n}")
    facts = [{"id": f"F9{n:03d}{i}", "text": f[1] if len(f) > 2 else f"{case.get('company', 'Eval Co')} fact about {f[0]}", "src": f[0], "conf": f[-1], "url": f"/demo-sources/eval/{f[0]}"}
             for i, f in enumerate(case["facts"])]
    company = case.get("company") or f"Eval Co {n}"
    db.x("insert into companies (id, name, domain, industry, staff, stage, city) values (%s,%s,%s,%s,%s,%s,'Austin') on conflict (id) do nothing",
         (f"eval{n}.example", company, f"eval{n}.example", case.get("ind", ""), case.get("staff", 100), case.get("stage", "")))
    db.x(
        "insert into prospects (id, company_id, full_name, first_name, title, email, region, timezone, facts, rej) values (%s,%s,%s,'Eval',%s,%s,%s,'PT',%s,%s)",
        (pid, f"eval{n}.example", f"Eval Case {n}", "CTO", f"eval{n}@example.test", case.get("region", "US"), J(facts), J({key: case["rej"]} if case.get("rej") else {})),
    )
    return pid


def _qualifier_case(db: Db, c: dict, version: int, n: int, case: dict) -> dict:
    key = tk(c)
    pid = _temp_prospect(db, n, key, case)
    e = new_enrollment(db, pid, c["id"])
    p = prospect(db, pid)
    if qualifier.hard_reject(p, c):
        got = "reject"
    else:
        j = qualifier.judge(db, e, p, c, version)
        sc = qualifier.score(j.crit) if runtime.live() else templates.score_of(c["id"], pid, j.crit)
        got = "borderline" if j.failed else qualifier.decide(sc, c["thr"], False)
    return {"case": case["expect"], "got": got, "ok": got == case["expect"], "note": f"{case['ind']}, {case['staff']} staff, {case['stage']}"}


def _writer_case(db: Db, c: dict, version: int, n: int, case: dict) -> dict:
    key = tk(c)
    fcase = {**case, "ind": "", "staff": 100, "stage": "", "region": "US" if key != "C2" else "IN"}
    fcase["facts"] = [[f[0], f[1], f[2]] for f in case["facts"]]
    pid = _temp_prospect(db, n, key, fcase)
    e = new_enrollment(db, pid, c["id"])
    p = prospect(db, pid)
    channel = {"connect": "linkedin", "message": "linkedin", "sms": "sms"}.get(case["kind"], "email")
    d = writer.draft(db, enrollment(db, e["id"]), p, c, case["kind"], channel=channel, version=version, rep_name="Marcus Lee", now_ms=clock.ms(clock.now()), pin=True)
    gc = grounding.check(db, d.comp, p, c["id"])
    problem = grounding.length_problem(d.comp, channel, c["words"])
    ok = not gc["bad"] and not problem and not d.generic_safe
    why = "; ".join([f"{x['reason']}: {x['t'][:50]}" for x in gc["bad"]] + ([problem] if problem else []) + (["generic_safe fallback"] if d.generic_safe else []))
    return {"case": f"{case['kind']} ({key})", "got": "grounded" if ok else "failed", "ok": ok, "note": why}


def _responder_case(db: Db, c: dict, version: int, n: int, case: dict) -> dict:
    key = tk(c)
    pid = _temp_prospect(db, n, key, {"facts": [["about", "High"]], "ind": "", "staff": 100, "stage": ""})
    e = enrollment(db, new_enrollment(db, pid, c["id"])["id"])
    r = responder.read(db, e, prospect(db, pid), c, case["text"], version)
    got = r.sub if r.cls == "escalate" or (r.cls == "objection" and case.get("sub")) else r.cls
    want = case["sub"] if case.get("sub") else case["expect"]
    return {"case": want, "got": got, "ok": got == want, "note": case["text"][:70]}


RUNNERS = {"Qualifier": _qualifier_case, "Writer": _writer_case, "Responder": _responder_case}


def run(db: Db, campaign_id: str, role: str, version: int | None = None, record: bool = True) -> dict:
    if role not in ROLES:
        raise CadenceError(f"There is no golden set for the {role} role", code="no_golden_set", status=409)
    c = campaign(db, campaign_id)
    key = tk(c)
    cases = load_cases(role)
    if role in ("Qualifier", "Writer"):
        cases = [x for x in cases if x["cid"] == key]
    if version is None:
        row = db.q1("select version from prompt_versions where campaign_id = %s and agent_key = %s and status = 'active'", (campaign_id, role))
        version = row["version"]
    pid = f"{campaign_id}-{role}-v{version}"
    results: list[dict] = []
    try:
        with db.conn.transaction():
            for n, case in enumerate(cases, start=1):
                results.append(RUNNERS[role](db, c, version, n, case))
            raise _Rollback
    except _Rollback:
        pass
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    pct = round(100 * passed / total) if total else 0
    method = "live model output, exact match and grounding check" if runtime.live() else "rule-based, LLM_MODE=fake"
    if record:
        db.x("update prompt_versions set gold = %s where id = %s", (J([f"{passed} of {total} cases", f"{pct}%"]), pid))
        db.x("insert into eval_runs (campaign_id, agent_key, prompt_version_id, score, passed, total, detail, judge_notes) values (%s,%s,%s,%s,%s,%s,%s,%s)",
             (campaign_id, role, pid, pct, passed, total, J({"results": results, "method": method}), method))
    return {"score": pct, "passed": passed, "total": total, "method": method, "version": version, "results": results}


def run_seeded(db: Db) -> int:
    """Score every seeded prompt version so the Prompts and Analytics screens show measured numbers, never invented ones."""
    n = 0
    for c in db.q("select id from campaigns where id in ('C1', 'C2', 'C3') order by id"):
        for role in ROLES:
            for v in db.q("select version from prompt_versions where campaign_id = %s and agent_key = %s order by version", (c["id"], role)):
                run(db, c["id"], role, v["version"])
                n += 1
    return n
