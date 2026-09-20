"""Hunter.io Email Finder: given a real name and a real company domain, a real email with Hunter's own
confidence score and verification status. Same shape as apollo.py: injectable transport for tests, a
typed unavailable exception, one retry on 429/5xx. Callers must treat a miss/failure as "no email found",
never crash - the caller falls back to a clearly-labelled sandbox address, never a guessed one.
"""

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from backend.core.config import get_settings
from backend.core.logging import log

BASE = "https://api.hunter.io/v2"
TIMEOUT_S = 15
RETRIES = 1


class HunterUnavailable(Exception):
    """No key, timeout, 429 or non-2xx. Callers must fall back, never crash the request."""


@dataclass
class HunterEmail:
    email: str
    confidence: int
    verification_status: str


Transport = Callable[[dict], dict]
_transport: Transport | None = None


def set_transport(fn: Transport | None) -> None:
    global _transport
    _transport = fn


def _get(params: dict) -> dict:
    key = get_settings().hunter_api_key
    if not key:
        raise HunterUnavailable("HUNTER_API_KEY is not set")
    if _transport is not None:
        return _transport(params)
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            with httpx.Client(timeout=TIMEOUT_S) as c:
                r = c.get(f"{BASE}/email-finder", params={**params, "api_key": key})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            last = e
            if e.response.status_code not in (429, 500, 502, 503, 504) or attempt == RETRIES:
                break
        except httpx.HTTPError as e:
            last = e
            if attempt == RETRIES:
                break
    log().warning("hunter call failed", extra={"event": "hunter_fallback", "status": type(last).__name__ if last else "unknown"})
    raise HunterUnavailable(f"hunter request failed: {type(last).__name__ if last else 'unknown'}") from last


def find_email(first_name: str, last_name: str, domain: str) -> HunterEmail | None:
    """The real (or best Hunter can verify) email for a named person at a domain. None on a clean miss."""
    data = _get({"domain": domain, "first_name": first_name, "last_name": last_name})
    d = (data or {}).get("data") or {}
    email = d.get("email")
    if not email:
        return None
    return HunterEmail(email=email, confidence=int(d.get("score") or 0), verification_status=(d.get("verification") or {}).get("status", "unknown"))
