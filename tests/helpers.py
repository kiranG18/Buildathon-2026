import time

from backend.core.db import tx
from backend.orchestrator.worker import Worker

MANAGER = {"id": "U2", "name": "Ava Chen", "role": "Manager"}
ADMIN = {"id": "U1", "name": "Nadia Frost", "role": "Admin"}


def enrollment_of(prospect_id: str, campaign_id: str) -> dict:
    with tx() as db:
        return db.q1("select * from enrollments where prospect_id = %s and campaign_id = %s", (prospect_id, campaign_id))


def run_worker(seconds: float = 6.0, until=None, campaign: str | None = None) -> int:
    """Tick the worker until `until()` is true or the time runs out. Returns the number of jobs run."""
    w = Worker(campaign_filter=campaign, threads=6)
    n = 0
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        n += w.tick()
        if until and until():
            break
    w.pool.shutdown()
    return n


def activity_count(campaign_id: str) -> int:
    with tx() as db:
        return db.q1("select count(*) as n from activity where campaign_id = %s", (campaign_id,))["n"]


def import_prospects(campaign_id: str, n: int, prefix: str = "Test") -> None:
    from backend.orchestrator import discovery

    rows = [[f"{prefix} Person{i}{campaign_id}", "CTO", f"{prefix}Corp{i}{campaign_id}"] for i in range(n)]
    with tx() as db:
        discovery.import_rows(db, campaign_id, rows, MANAGER)
