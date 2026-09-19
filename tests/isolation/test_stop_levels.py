"""The four stop levels stay inside their scope: pausing an agent or a channel in one campaign never touches the others (I4, I5)."""

from backend.core.db import tx
from backend.orchestrator import controls
from tests.helpers import MANAGER, enrollment_of, import_prospects, run_worker


def sent_by_agent(campaign_id: str, agent: str) -> int:
    with tx() as db:
        return db.q1("select count(*) as n from jobs where campaign_id = %s and agent = %s and status = 'done'", (campaign_id, agent))["n"]


def test_i4_pausing_the_writer_in_c1_leaves_the_writer_running_in_c3(seeded):
    import_prospects("C1", 12, prefix="Stop")
    import_prospects("C3", 12, prefix="Stop")
    with tx() as db:
        controls.toggle_agent(db, "C1", "Writer", MANAGER, enabled=False)
    run_worker(6)
    with tx() as db:
        controls.advance_clock(db, 2)
    before = {c: sent_by_agent(c, "Writer") for c in ("C1", "C3")}
    run_worker(8)
    after = {c: sent_by_agent(c, "Writer") for c in ("C1", "C3")}
    assert after["C3"] > before["C3"]
    assert after["C1"] == before["C1"]
    with tx() as db:
        held = controls.held_count(db, "C1")
    assert held > 0


def test_i5_pausing_linkedin_in_c1_leaves_linkedin_on_in_c3(seeded):
    with tx() as db:
        controls.toggle_channel(db, "C1", "linkedin", MANAGER, enabled=False)
    with tx() as db:
        rows = {r["campaign_id"]: r["enabled"] for r in db.q("select campaign_id, enabled from channel_settings where channel = 'linkedin'")}
    assert rows["C1"] is False and rows["C3"] is True and rows["C2"] is True
    assert enrollment_of("tomas-reyes", "C1")["plan"]
