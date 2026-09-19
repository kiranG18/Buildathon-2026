"""Inbound polling. Gmail replies are matched to the right enrollment by the Message-ID we stored on the outbound message, then handed to ingest_reply."""

from datetime import datetime, timedelta

from backend.channels.base import REGISTRY
from backend.core import clock
from backend.core.db import Db
from backend.core.errors import ChannelError
from backend.core.logging import log
from backend.orchestrator.repo import enrollment

_last_poll: dict[str, datetime] = {}
POLL_EVERY = timedelta(seconds=30)


def match_enrollment(db: Db, item: dict) -> dict | None:
    ids = [i for i in ([item.get("in_reply_to")] + (item.get("references") or "").split()) if i]
    if ids:
        row = db.q1("select enrollment_id from messages where rfc_message_id = any(%s) and direction = 'out' order by created_at desc limit 1", (ids,))
        if row:
            return enrollment(db, row["enrollment_id"])
    return None


def process_email(db: Db, item: dict) -> bool:
    from backend.orchestrator.replies import ingest_reply

    if db.q1("select 1 as x from messages where external_id = %s", (item["external_id"],)):
        return False
    e = match_enrollment(db, item)
    if e is None:
        log().info("inbound email did not match an enrollment", extra={"event": "inbound_unmatched"})
        return False
    ingest_reply(db, e, "email", item["body"], external_id=item["external_id"], rfc_message_id=item.get("rfc_id"))
    return True


def poll_all(db: Db) -> int:
    """Poll each registered adapter at most every 30 seconds. Returns the number of replies ingested."""
    n = 0
    now = clock.now()
    for name, adapter in list(REGISTRY.items()):
        if name != "email" or now - _last_poll.get(name, now - POLL_EVERY * 2) < POLL_EVERY:
            continue
        since = _last_poll.get(name, now - timedelta(minutes=10))
        _last_poll[name] = now
        try:
            for item in adapter.poll_inbound(since - timedelta(minutes=2)):
                n += process_email(db, item)
        except ChannelError as exc:
            log().warning("inbound poll failed", extra={"event": "poll_failed", "reason_code": exc.code})
    return n
