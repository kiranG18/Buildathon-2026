"""Calendly client: real availability for the two proposed meeting slots, and webhook signature
verification for the booking confirmation. Same shape as `apollo.py`: an injectable transport for
tests, a typed unavailable exception, a short timeout. `agents/util.py:slots_for` falls back to the
deterministic fake slots whenever this raises or CALENDLY_MODE is not "live" — a Calendly outage
never blocks a send.
"""

import hashlib
import hmac
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from backend.core.config import get_settings
from backend.core.logging import log

BASE = "https://api.calendly.com"
TIMEOUT_S = 10
SIGNATURE_TOLERANCE_S = 300

Transport = Callable[[str, str, dict], dict]
_transport: Transport | None = None


class CalendlyUnavailable(Exception):
    """Not configured, timeout, or non-2xx. Callers must fall back to the fake slots, never crash the send."""


def set_transport(fn: Transport | None) -> None:
    global _transport
    _transport = fn


def _get(path: str, params: dict) -> dict:
    s = get_settings()
    if not s.calendly_api_token:
        raise CalendlyUnavailable("CALENDLY_API_TOKEN is not set")
    if _transport is not None:
        return _transport("GET", path, params)
    try:
        with httpx.Client(timeout=TIMEOUT_S) as c:
            r = c.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {s.calendly_api_token}"}, params=params)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        log().warning("calendly call failed", extra={"event": "calendly_fallback", "status": type(e).__name__})
        raise CalendlyUnavailable(f"calendly request failed: {type(e).__name__}") from e


def available_times(now_ms: float, days: int = 6) -> list[dict]:
    """Two open real slots on different weekdays, starting tomorrow. Mirrors agents/util.py:slots_for's shape."""
    s = get_settings()
    if not s.calendly_event_type_uri:
        raise CalendlyUnavailable("CALENDLY_EVENT_TYPE_URI is not set")
    start = datetime.fromtimestamp(now_ms / 1000, tz=UTC) + timedelta(days=1)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=min(max(days, 1), 6))
    data = _get("/event_type_available_times", {
        "event_type": s.calendly_event_type_uri,
        "start_time": start.isoformat().replace("+00:00", "Z"),
        "end_time": end.isoformat().replace("+00:00", "Z"),
    })
    out: list[dict] = []
    seen_days: set[str] = set()
    for slot in data.get("collection", []):
        if slot.get("status") != "available":
            continue
        t = datetime.fromisoformat(slot["start_time"].replace("Z", "+00:00"))
        day_key = t.strftime("%Y-%m-%d")
        if day_key in seen_days:
            continue
        seen_days.add(day_key)
        out.append({"t": int(t.timestamp() * 1000), "label": t.strftime("%a %-d %b, %H:%M"), "url": slot["scheduling_url"]})
        if len(out) >= 2:
            break
    if len(out) < 2:
        raise CalendlyUnavailable("fewer than 2 open slots in the window")
    return out


def verify_signature(payload: bytes, header: str | None, signing_key: str) -> bool:
    """`Calendly-Webhook-Signature: t=<unix ts>,v1=<hex hmac>` over `f"{t}.{payload}"`, HMAC-SHA256 with the signing key."""
    if not header or not signing_key:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    t, v1 = parts.get("t"), parts.get("v1")
    if not t or not v1:
        return False
    if abs(time.time() - int(t)) > SIGNATURE_TOLERANCE_S:
        return False
    signed = f"{t}.{payload.decode()}".encode()
    expected = hmac.new(signing_key.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)
