"""Demo clock. now() is real UTC plus an offset stored in global_settings.

Advancing the clock moves every run_at and due calculation, so a six-day
sequence plays in about a minute. freeze() pins now() for seeding and tests.
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

_frozen: ContextVar[datetime | None] = ContextVar("clock_frozen", default=None)
_cache = {"at": 0.0, "hours": 0.0}


def _offset_hours() -> float:
    from backend.core.db import tx

    t = time.monotonic()
    if t - _cache["at"] > 1.0:
        with tx() as db:
            row = db.q1("select demo_clock_offset_hours as h from global_settings where id = 1")
        _cache.update(at=t, hours=float(row["h"]) if row else 0.0)
    return _cache["hours"]


def invalidate() -> None:
    _cache["at"] = 0.0


def now() -> datetime:
    f = _frozen.get()
    if f is not None:
        return f
    return datetime.now(UTC) + timedelta(hours=_offset_hours())


@contextmanager
def freeze(at: datetime):
    token = _frozen.set(at)
    try:
        yield
    finally:
        _frozen.reset(token)


def set_frozen(at: datetime | None) -> None:
    _frozen.set(at)


def ms(dt: datetime | None) -> int | None:
    return None if dt is None else int(dt.timestamp() * 1000)


def from_ms(value: float | int | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value / 1000, tz=UTC)
