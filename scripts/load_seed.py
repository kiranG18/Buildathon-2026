"""Load the demo workspace from seed/prototype_state.json.

Every timestamp in the dump is a millisecond epoch on the prototype's timeline (T0). The loader shifts
them so T0 lands on the current demo time, which keeps the data fresh after every reset.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core import clock  # noqa: E402
from backend.core.config import get_settings  # noqa: E402
from backend.core.db import Db, J, migrate, tx  # noqa: E402
from backend.core.security import hash_password  # noqa: E402
from evals.runner import run_seeded  # noqa: E402
from rag.chunking import parse_frontmatter  # noqa: E402
from rag.ingest import KNOWLEDGE_DIR, ingest_file  # noqa: E402

DEMO_PASSWORD = "helix-demo"
ROLE_OF = {"Researcher": "Researcher", "Qualifier": "Qualifier", "Sequencer": "Strategy", "Writer": "Writer", "Responder": "Responder", "Caller": "Caller"}
PROVIDER = {"Researcher": "dronahq", "Responder": "dronahq", "Caller": "dronahq"}
TABLES = (
    "eval_runs eval_sets knowledge_chunks knowledge_documents suppression_list conflicts contact_claims calls meetings "
    "escalations approvals activity messages agent_runs jobs enrollments prospects companies prompt_versions rep_assignments "
    "channel_settings campaign_agents campaign_versions campaigns integrations users"
)
INTEG_KEY = {"gmail": "gmail", "linkedin": "linkedin", "twilio": "twilio", "voice": "voice", "agents": "agents", "llm": "llm", "embed": "embed"}


def load(now: datetime | None = None) -> dict:
    data = json.loads((ROOT / "seed" / "prototype_state.json").read_text(encoding="utf-8"))
    S, t0 = data["S"], data["T0"]
    now = now or datetime.now(UTC)
    delta = int(now.timestamp() * 1000) - t0

    def sh(v):
        return None if v is None else v + delta

    def ts(v):
        return None if v is None else datetime.fromtimestamp((v + delta) / 1000, tz=UTC)

    with tx(timeout_ms=0) as db:
        db.x(f"truncate {TABLES.replace(' ', ', ')} restart identity cascade")
        db.x("update global_settings set kill_switch = false, kill_at = null, kill_by = null, demo_clock_offset_hours = 0 where id = 1")
        clock.invalidate()
        with clock.freeze(now):
            _users(db, S)
            _integrations(db, S, ts)
            _campaigns(db, S, ts)
            _prompts(db, S, ts)
            _people(db, S)
            _enrollments(db, S, ts, sh)
            _messages(db, S, ts)
            _jobs(db, S, ts)
            _activity(db, S, ts)
            _misc(db, S, ts)
            _knowledge(db, S, ts)
            run_seeded(db)
            db.x("delete from jobs where prospect_id = 'dana-whitfield' and status = 'queued' and step = 'research'")
        db.x("select setval('id_seq', greatest(nextval('id_seq'), 20000))")
    counts = {k: len(S[k]) for k in ("camps", "users", "people", "enr", "msgs", "acts", "jobs", "approvals")}
    return counts


def _users(db: Db, S: dict) -> None:
    pw = hash_password(DEMO_PASSWORD)
    for u in S["users"]:
        db.x(
            "insert into users (id, name, role, email, password_hash, title, rep_limit, hours, tz, channels, active, label) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (u["id"], u["name"], u["role"], u["email"], pw, u["title"], u["limit"], u["hours"], u["tz"], u["channels"], u["active"], u["label"]),
        )


def _integrations(db: Db, S: dict, ts) -> None:
    cfg = get_settings()
    env_mode = {"gmail": cfg.channel_mode_email, "twilio": cfg.channel_mode_sms, "voice": cfg.channel_mode_voice, "linkedin": "sandbox"}
    for k, v in S["integ"].items():
        db.x(
            "insert into integrations (key, name, description, mode, status, last_check, err, can_live, paused) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (k, v["n"], v["d"], env_mode.get(k, v["mode"]), v["status"], ts(v["last"]), v["err"], v["canLive"], bool(v.get("paused"))),
        )


def _campaigns(db: Db, S: dict, ts) -> None:
    for c in S["camps"]:
        db.x(
            """insert into campaigns (id, name, owner_id, status, objective, icp, personas, geo, signals, seq_order, tone, words, approval_text,
               roles, geo_list, exclusions, thr, appr, daily_send_cap, priority, ch_limit, version, parent_id, paused_by, paused_at, created_at,
               last_activity, tpl) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (c["id"], c["name"], c["owner"], c["status"], c["objective"], c["icp"], c["personas"], c["geo"], c["signals"], c["order"], c["tone"],
             c["words"], c["approval"], c["roles"], c["geoList"], c["exclusions"], c["thr"], J(c["appr"]), c["cap"], c["priority"], J(c["chLimit"]),
             c["version"], c["parent"], c["pausedBy"], ts(c["pausedAt"]), ts(c["createdAt"]), ts(c.get("last")), c.get("tpl")),
        )
        for agent, on in c["agents"].items():
            db.x("insert into campaign_agents (campaign_id, agent_key, enabled, provider) values (%s,%s,%s,%s)", (c["id"], agent, on, PROVIDER.get(agent, "direct")))
        for ch, on in c["channels"].items():
            db.x("insert into channel_settings (campaign_id, channel, enabled, daily_limit) values (%s,%s,%s,%s)", (c["id"], ch, on, c["chLimit"][ch]))
        for r in c["reps"]:
            db.x("insert into rep_assignments (rep_id, campaign_id) values (%s,%s)", (r, c["id"]))
        db.x(
            "insert into campaign_versions (campaign_id, version, config, changed_by, changed_at, note) values (%s,%s,%s,%s,%s,%s)",
            (c["id"], c["version"], J({k: c[k] for k in ("name", "objective", "thr", "cap", "appr", "channels", "agents")}), c["owner"], ts(c["createdAt"]), "Seeded configuration"),
        )


def _prompts(db: Db, S: dict, ts) -> None:
    for p in S["prompts"]:
        db.x(
            "insert into prompt_versions (id, campaign_id, agent_key, version, status, author_id, created_at, change_note, lines, parent_version, gold) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (p["id"], p["cid"], p["role"], p["v"], p["status"], p["author"], ts(p["at"]), p["note"], J(p["lines"]), p["parent"], None),
        )


def _people(db: Db, S: dict) -> None:
    for p in S["people"].values():
        db.x(
            "insert into companies (id, name, domain, industry, staff, stage, city) values (%s,%s,%s,%s,%s,%s,%s) on conflict (id) do nothing",
            (p["domain"], p["company"], p["domain"], p["ind"], p["staff"], p["stage"], p["city"]),
        )
        db.x(
            """insert into prospects (id, company_id, full_name, first_name, title, email, phone, linkedin_url, region, timezone, facts, rich, researched,
               bio, thin, is_empty, rej, is_seed) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)""",
            (p["id"], p["domain"], p["name"], p["first"], p["title"], p["email"], p["phone"], p["linkedin"], p["region"], p["tz"], J(p["facts"]), J(p["rich"]),
             p["researched"], p["bio"], p["thin"], bool(p.get("empty")), J(p["rej"])),
        )


def _enrollments(db: Db, S: dict, ts, sh) -> None:
    for e in S["enr"]:
        plan = []
        for s in e["plan"]:
            s = dict(s)
            s["due"] = sh(s["due"])
            if s.get("doneAt"):
                s["doneAt"] = sh(s["doneAt"])
            plan.append(s)
        hold = e.get("hold")
        if hold and hold.get("until"):
            hold = {**hold, "until": sh(hold["until"])}
        hist = [{**h, "t": sh(h["t"])} for h in e.get("planHist", [])]
        meeting = e.get("meeting")
        if meeting:
            meeting = {**meeting, "t": sh(meeting.get("t") or meeting.get("at")), "label": meeting.get("label")}
        slots = [{**s, "t": sh(s["t"])} for s in e["slots"]] if e.get("slots") else None
        db.x(
            """insert into enrollments (id, campaign_id, prospect_id, state, score, crit, plan, rep_id, reject, review_note, defer_note, hold, plan_hist,
               meeting, slots, wake, warm, hot_call, first_due, last_touch, note, created_at, is_seed) values
               (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)""",
            (e["id"], e["cid"], e["pid"], e["st"], e["score"], J(e["crit"]) if e.get("crit") else None, J(plan), e["rep"], e.get("reject"), e.get("reviewNote"),
             e.get("deferNote"), J(hold) if hold else None, J(hist), J(meeting) if meeting else None, J(slots) if slots else None, ts(e.get("wake")),
             bool(e.get("warm")), bool(e.get("hotCall")), ts(e.get("firstDue")), ts(e.get("lastTouch")), e.get("note"), ts(e["created"])),
        )


def _messages(db: Db, S: dict, ts) -> None:
    for m in sorted(S["msgs"], key=lambda x: x["t"]):
        db.x(
            """insert into messages (id, enrollment_id, prospect_id, campaign_id, channel, direction, body, segs, created_at, mode, status, is_seed, subject,
               run_id, kind, step_no, prompt_version, approved_by, classification, rule, sub, is_reply, is_ack, human, by_name, edited)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (m["id"], m["eid"], m["pid"], m["cid"], m["ch"], m["dir"], m["body"], J(m["segs"]) if m.get("segs") else None, ts(m["t"]), "sandbox", m["status"],
             m.get("subject"), m.get("runId"), m.get("kind"), m.get("stepNo"), m.get("pv"), m.get("approvedBy"), m.get("cls"), m.get("rule"), m.get("sub"),
             bool(m.get("reply")), bool(m.get("ack")), bool(m.get("human")), m.get("by"), bool(m.get("edited"))),
        )


def _jobs(db: Db, S: dict, ts) -> None:
    for j in sorted(S["jobs"], key=lambda x: x["at"]):
        status = "queued" if j["status"] == "running" else j["status"]
        db.x(
            """insert into jobs (id, campaign_id, enrollment_id, prospect_id, agent, step, status, run_at, created_at, ended_at, step_no, payload, err, msg_id, is_seed)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)""",
            (j["id"], j["cid"], j["eid"], j["pid"], j["agent"], j["step"], status, ts(j["due"]), ts(j["at"]), ts(j.get("end")), j.get("stepNo"),
             J(j["payload"]) if j.get("payload") else None, j.get("err"), j.get("msgId")),
        )
        if j["status"] in ("done", "failed"):
            tr = j.get("tr") or {}
            db.x(
                """insert into agent_runs (id, job_id, campaign_id, enrollment_id, agent_key, role, provider, model, prompt_version, campaign_version, retrieved_chunk_ids,
                   summary, trace, status, tokens_in, tokens_out, cost_usd, latency_s, error, is_seed, created_at) values
                   (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s)""",
                (j["id"], j["id"], j["cid"], j["eid"], j["agent"], ROLE_OF.get(j["agent"], j["agent"]), PROVIDER.get(j["agent"], "direct"), j.get("model", ""),
                 j.get("pv"), j.get("cv"), tr.get("chunks", []), j.get("sum", ""), J(tr), j["status"], j.get("tin", 0), j.get("tout", 0), j.get("cost", 0),
                 j.get("dur", 0), j.get("err"), ts(j.get("end") or j["at"])),
            )


def _activity(db: Db, S: dict, ts) -> None:
    for a in sorted(S["acts"], key=lambda x: x["t"]):
        db.x(
            "insert into activity (id, ts, enrollment_id, prospect_id, campaign_id, kind, text, agent, run_id, msg_id, mode, quiet) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (a["id"], ts(a["t"]), a.get("eid"), a.get("pid"), a.get("cid"), a["kind"], a["text"], a.get("agent"), a.get("runId"), a.get("msgId"), "sandbox" if a.get("mode") else None, bool(a.get("quiet"))),
        )


def _misc(db: Db, S: dict, ts) -> None:
    for a in S["approvals"]:
        db.x(
            "insert into approvals (id, kind, campaign_id, enrollment_id, created_at, status, run_id, msg_id, step_no, blocked, decided_by, decided_at, reason) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (a["id"], a["kind"], a["cid"], a["eid"], ts(a["t"]), a["status"], a.get("runId"), a.get("msgId"), a.get("stepNo"), bool(a.get("blocked")), a.get("by"), ts(a.get("at")), a.get("reason")),
        )
    for x in S["escal"]:
        db.x(
            "insert into escalations (id, enrollment_id, campaign_id, reason_code, rep_id, created_at, status, msg_id, suggested, summary, rule, resolved_by, resolved_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (x["id"], x["eid"], x["cid"], x["reason"], x["rep"], ts(x["t"]), x["status"], x.get("msgId"), x["suggested"], x["summary"], x["rule"], x.get("by"), ts(x.get("at"))),
        )
    for c in S["conflicts"]:
        db.x(
            "insert into conflicts (id, prospect_id, campaign_ids, rule, winner, status, code, decision, created_at, resolved_by) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (c["id"], c["pid"], c["cids"], c["rule"], c["winner"], c["status"], c["code"], c["decision"], ts(c["t"]), c.get("by")),
        )
    for m in S["meetings"]:
        db.x("insert into meetings (id, enrollment_id, campaign_id, prospect_id, slot_at, rep_id, label) values (%s,%s,%s,%s,%s,%s,%s)", (m["id"], m["eid"], m["cid"], m["pid"], ts(m["at"]), m["rep"], m["label"]))
    for c in S["calls"]:
        db.x(
            "insert into calls (id, enrollment_id, prospect_id, at, dur, disposition, mode, run_id, transcript, summary) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (c["id"], c["eid"], c["pid"], ts(c["at"]), c["dur"], c["disposition"], "sandbox", c.get("runId"), J(c["tr"]), c["summary"]),
        )
    prio = {c["id"]: c["priority"] for c in S["camps"]}
    for pid, cl in S["claims"].items():
        db.x("insert into contact_claims (prospect_id, campaign_id, status, priority, claimed_at) values (%s,%s,'active',%s,%s)", (pid, cl["cid"], prio[cl["cid"]], ts(cl["since"])))
    for s in S["suppress"]:
        db.x("insert into suppression_list (id, kind, value, reason, added_by, created_at) values (%s,%s,%s,%s,%s,%s)", (s["id"], s["kind"], s["value"], s["reason"], s["by"], ts(s["at"])))


def _knowledge(db: Db, S: dict, ts) -> None:
    at_by_id = {d["id"]: ts(d["at"]) for d in S["kb"]["docs"]}
    for f in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        meta, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        ingest_file(db, f, at_by_id.get(meta.get("id")))


def main() -> None:
    applied = migrate()
    if applied:
        print("migrated", ", ".join(applied))
    print("loaded", load())


if __name__ == "__main__":
    main()
