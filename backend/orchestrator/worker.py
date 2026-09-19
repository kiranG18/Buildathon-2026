"""The worker loop. Claims due jobs from the jobs table with FOR UPDATE SKIP LOCKED and runs them.

Fair share: every Live campaign gets its own claim query, capped at 3 running jobs, so one busy campaign cannot starve the others.
A campaign that is Paused (or whose agent is off, or under the kill switch) matches no claim query, which is why pausing A never stops B or C.
A job-level try/except records failures and never kills the loop.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from backend.channels import inbound, linkedin_sandbox
from backend.core import clock
from backend.core.config import get_settings
from backend.core.db import Db, tx
from backend.core.errors import ChannelError
from backend.core.logging import log
from backend.orchestrator import handlers
from backend.orchestrator.repo import act, campaign, enrollment

PER_CAMPAIGN_CAP = 3
POLL_SECONDS = 2.0
RETRY_MINUTES = (0.5, 2, 10)
STALE_RUNNING = timedelta(minutes=3)


class Worker:
    def __init__(self, campaign_filter: str | None = None, threads: int = 8):
        self.campaign_filter = campaign_filter or get_settings().worker_campaign_id or None
        self.pool = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="job")
        self.stop_event = threading.Event()
        self.rr = 0
        self.last_maintenance = 0.0

    # --- claiming ---------------------------------------------------------------------------------------------------------

    def claim(self) -> list[dict]:
        claimed: list[dict] = []
        with tx() as db:
            if db.q1("select kill_switch from global_settings where id = 1")["kill_switch"]:
                return claimed
            now = clock.now()
            live = [r["id"] for r in db.q("select id from campaigns where status = 'live' order by id")]
            if self.campaign_filter:
                live = [c for c in live if c == self.campaign_filter]
            if not live:
                return claimed
            self.rr = (self.rr + 1) % len(live)
            for cid in live[self.rr :] + live[: self.rr]:
                running = db.q1("select count(*) as n from jobs where campaign_id = %s and status = 'running'", (cid,))["n"]
                room = PER_CAMPAIGN_CAP - running
                if room <= 0:
                    continue
                rows = db.q(
                    """select j.* from jobs j left join campaign_agents a on a.campaign_id = j.campaign_id and a.agent_key = j.agent
                       left join enrollments e on e.id = j.enrollment_id
                       where j.campaign_id = %s and j.status = 'queued' and j.run_at <= %s and coalesce(a.enabled, true)
                       order by coalesce(e.score, 0) desc, j.run_at, j.created_at limit %s for update of j skip locked""",
                    (cid, now, room),
                )
                for j in rows:
                    db.x("update jobs set status = 'running', started_at = %s, attempts = attempts + 1 where id = %s", (now, j["id"]))
                    j["attempts"] += 1
                    claimed.append(j)
        return claimed

    # --- running ----------------------------------------------------------------------------------------------------------

    def run_one(self, job: dict) -> None:
        t0 = time.monotonic()
        try:
            with tx() as db:
                fresh = db.q1("select * from jobs where id = %s", (job["id"],))
                if fresh["status"] != "running":
                    return
                handlers.run_job(db, fresh)
                left = db.q1("select status from jobs where id = %s", (job["id"],))
                if left["status"] == "running":
                    db.x("update jobs set status = 'queued' where id = %s", (job["id"],))
            log().info("job done", extra={"job_id": job["id"], "campaign_id": job["campaign_id"], "agent": job["agent"], "duration_ms": int((time.monotonic() - t0) * 1000)})
        except Exception as exc:  # one job failing must never stop the loop
            log().exception("job failed", extra={"job_id": job["id"], "campaign_id": job["campaign_id"], "agent": job["agent"]})
            self.record_failure(job, exc)

    def record_failure(self, job: dict, exc: Exception) -> None:
        msg = f"{type(exc).__name__}: {str(exc)[:240]}"
        try:
            with tx() as db:
                if isinstance(exc, ChannelError) and exc.extra.get("channel"):
                    self.count_channel_failure(db, exc.extra["channel"], str(exc))
                attempts = job["attempts"]
                if attempts < 3:
                    delay = RETRY_MINUTES[min(attempts - 1, len(RETRY_MINUTES) - 1)]
                    db.x("update jobs set status = 'queued', err = %s, run_at = %s where id = %s", (msg, clock.now() + timedelta(minutes=delay), job["id"]))
                    return
                db.x("update jobs set status = 'failed', err = %s, ended_at = %s where id = %s", (msg, clock.now(), job["id"]))
                if job["enrollment_id"]:
                    e = enrollment(db, job["enrollment_id"])
                    c = campaign(db, e["campaign_id"])
                    rep = c["reps"][0] if c["reps"] else None
                    db.x("insert into escalations (id, enrollment_id, campaign_id, reason_code, rep_id, created_at, summary, rule, created_by_agent) values (%s,%s,%s,'agent_failure',%s,%s,%s,%s,%s)",
                         (db.nid("ES-"), e["id"], e["campaign_id"], rep, clock.now(), f"{job['agent']} failed three times on a {job['step']} step: {msg}", "job failed after 3 attempts", job["agent"]))
                    act(db, e, "gate", f"{job['agent']} job failed after 3 attempts: {msg[:80]}", run_id=job["id"], agent="Guardian", reason_code="agent_failure")
        except Exception:
            log().exception("could not record job failure", extra={"job_id": job["id"]})

    @staticmethod
    def count_channel_failure(db: Db, channel: str, message: str) -> None:
        """Three consecutive send failures put the channel in error, which raises an alert on Command Center."""
        from backend.channels.base import CH_KEY

        row = db.q1("update integrations set fail_count = fail_count + 1 where key = %s returning fail_count, name", (CH_KEY[channel],))
        if row and row["fail_count"] >= 3:
            db.x("update integrations set status = 'error', err = %s, last_check = %s where key = %s", (message[:200], clock.now(), CH_KEY[channel]))
            act(db, None, "channel", f"{row['name']} is degraded after {row['fail_count']} failed sends", agent="Guardian", reason_code="channel_degraded")

    # --- maintenance ------------------------------------------------------------------------------------------------------

    def maintenance(self) -> None:
        if time.monotonic() - self.last_maintenance < 5:
            return
        self.last_maintenance = time.monotonic()
        with tx() as db:
            db.x("update jobs set status = 'queued' where status = 'running' and started_at < %s", (clock.now() - STALE_RUNNING,))
            for r in db.q("select id from campaigns where status = 'live'"):
                if self.campaign_filter and r["id"] != self.campaign_filter:
                    continue
                handlers.scan_due(db, r["id"])
            _watchdogs(db)
            inbound.poll_all(db)
            linkedin_sandbox.simulate_acceptance(db)

    def run_batch(self, jobs: list[dict]) -> None:
        """One campaign's claimed jobs run in claim order (best ICP score first), so the scarce daily slots go to the best prospects."""
        for j in jobs:
            self.run_one(j)

    def tick(self) -> int:
        self.maintenance()
        jobs = self.claim()
        by_campaign: dict[str, list[dict]] = {}
        for j in jobs:
            by_campaign.setdefault(j["campaign_id"], []).append(j)
        futures = [self.pool.submit(self.run_batch, batch) for batch in by_campaign.values()]
        for f in futures:
            f.result()
        return len(jobs)

    def run_forever(self) -> None:
        log().info("worker started", extra={"event": "worker_start"})
        while not self.stop_event.is_set():
            try:
                n = self.tick()
            except Exception:
                log().exception("worker tick failed")
                n = 0
            if not n:
                self.stop_event.wait(POLL_SECONDS)

    def stop(self) -> None:
        self.stop_event.set()


def _watchdogs(db: Db) -> None:
    """Voice calls that never posted an outcome become unknown_outcome plus an escalation after 10 minutes."""
    from backend.orchestrator import dronahq

    dronahq.sweep_awaiting_outcome(db)


def start_embedded() -> Worker:
    w = Worker()
    threading.Thread(target=w.run_forever, name="worker", daemon=True).start()
    return w
