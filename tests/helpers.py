import time

from backend.core.db import tx
from backend.orchestrator.worker import Worker

MANAGER = {"id": "U2", "name": "Ava Chen", "role": "Manager"}
ADMIN = {"id": "U1", "name": "Nadia Frost", "role": "Admin"}


def enrollment_of(prospect_id: str, campaign_id: str) -> dict:
    with tx() as db:
        return db.q1("select * from enrollments where prospect_id = %s and campaign_id = %s", (prospect_id, campaign_id))


def run_worker(seconds: float = 6.0, until=None, campaign: str | None = None) -> int:
    """Tick the worker until `until()` is true or the time runs out. Returns the number of jobs run.

    A test that waits for a condition gets four times the time, so a slow CI runner does not fail it. It still stops as soon as the condition holds."""
    w = Worker(campaign_filter=campaign, threads=6)
    n = 0
    end = time.monotonic() + (seconds * 4 if until else seconds)
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


from contextlib import contextmanager  # noqa: E402


@contextmanager
def scratch():
    """A transaction that is always rolled back, so a test can change rows without reseeding."""
    with tx() as db:
        try:
            yield db
        finally:
            db.conn.rollback()


def make_ready(db, campaign_id: str, name: str, score: int) -> dict:
    """A qualified enrollment whose first email touch is due now, with its claim and a queued draft job."""
    import random

    from backend.conflicts.claims import create_claim
    from backend.orchestrator.handlers import dispatch_due
    from backend.orchestrator.repo import enrollment, new_enrollment, prospect, save_enr

    pr = discovery_make(db, name)
    e = new_enrollment(db, pr["id"], campaign_id)
    db.x("update prospects set facts = facts || rich, rich = '[]'::jsonb, researched = true where id = %s", (pr["id"],))
    plan = [{"day": 0, "ch": "email", "purpose": "intro", "reason": "test", "status": "pending", "due": clock_ms() - 1000, "cond": None}]
    save_enr(db, e, state="qualified", score=score, plan=plan)
    create_claim(db, pr["id"], campaign_id)
    dispatch_due(db, e)
    _ = random, prospect
    return enrollment(db, e["id"])


def discovery_make(db, name: str) -> dict:
    import random

    from backend.orchestrator import discovery

    return discovery.make_prospect(db, name, "CTO", f"{name} Labs", "C1", random.Random(3))


def clock_ms() -> int:
    from backend.core import clock

    return clock.ms(clock.now())
