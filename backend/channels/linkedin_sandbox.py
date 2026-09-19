"""LinkedIn runs as a labelled sandbox. Automating a real account breaks LinkedIn's terms, so there is no live adapter.
The sandbox simulates connection acceptance 24 hours after a connect note, and replies arrive through the reply simulator."""

from datetime import timedelta

from backend.core import clock
from backend.core.db import Db
from backend.orchestrator.repo import act, enrollment, prospect, save_enr


def simulate_acceptance(db: Db) -> int:
    cutoff = clock.now() - timedelta(hours=24)
    rows = db.q(
        """select distinct m.enrollment_id from messages m join campaigns c on c.id = m.campaign_id
           where c.status = 'live' and m.channel = 'linkedin' and m.direction = 'out' and m.status = 'sent' and m.kind = 'connect' and m.created_at < %s
           and not exists (select 1 from activity a where a.enrollment_id = m.enrollment_id and a.kind = 'linkedin_accept')""",
        (cutoff,),
    )
    for r in rows:
        e = enrollment(db, r["enrollment_id"])
        p = prospect(db, e["prospect_id"])
        save_enr(db, e, warm=True)
        act(db, e, "linkedin_accept", f"{p['full_name']} accepted the LinkedIn connection (SANDBOX)", agent="Guardian", mode="sandbox", quiet=True)
    return len(rows)
