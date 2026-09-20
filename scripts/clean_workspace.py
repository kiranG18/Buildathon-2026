"""Empty the workspace of records while keeping its configuration.

Removes prospects, companies, enrollments, messages, calls, meetings, approvals, escalations, jobs, agent runs, activity, claims, conflicts, suppression entries
and agent callbacks. Keeps users, campaigns and their prompt versions, agents, channels, knowledge, evals, integrations and global settings, and puts the demo clock
back to real time. It runs against the database in DATABASE_URL: `python scripts/clean_workspace.py --yes`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.db import Db, tx  # noqa: E402

RECORDS = ("jobs", "agent_runs", "messages", "activity", "approvals", "escalations", "meetings", "calls", "contact_claims", "conflicts", "suppression_list",
           "research_callbacks", "responder_decisions", "enrollments", "prospects", "companies")


def clean(db: Db) -> dict[str, int]:
    before = {t: db.q1(f"select count(*) as n from {t}")["n"] for t in RECORDS}
    db.x(f"truncate {', '.join(RECORDS)}")
    db.x("update campaigns set paused_held = 0, dry_ok = false, last_activity = now()")
    db.x("update global_settings set demo_clock_offset_hours = 0, kill_switch = false, kill_at = null, kill_by = null where id = 1")
    return before


def main() -> None:
    if "--yes" not in sys.argv:
        sys.exit("This deletes every prospect, message, call and activity row. Run again with --yes to continue.")
    with tx() as db:
        removed = clean(db)
    for table, n in removed.items():
        print(f"{table}: removed {n}")


if __name__ == "__main__":
    main()
