"""Google Sheets CRM mirror: one-way push of every enrollment (prospect x campaign) to a spreadsheet tab.

Auth is a service account JWT bearer flow (RS256, signed with the service account's own private key),
never an OAuth consent screen - no human sign-in needed once the sheet is shared with the service account's
email. The access token is cached in memory and refreshed a minute before it expires.

Sync is a full overwrite of the tab (clear then write), not a diff - simplest thing that cannot drift out
of sync, and the enrollment table is small enough that this stays fast and cheap on quota.
"""

import json
import threading
import time

import httpx
import jwt

from backend.core.config import get_settings
from backend.core.db import Db
from backend.core.logging import log

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - not a secret, a public endpoint
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
TIMEOUT_S = 15

HEADER = ["Prospect", "Title", "Company", "Email", "Phone", "LinkedIn", "Region", "Campaign", "Stage", "Score", "Rep", "Last touch", "Meeting", "Note", "DEMO"]

_lock = threading.Lock()
_token: str | None = None
_token_exp = 0.0
_last_sync = 0.0


class SheetsUnavailable(Exception):
    """Not configured, auth failed, or the API returned a non-2xx. Callers must never crash on this."""


def _access_token() -> str:
    global _token, _token_exp
    with _lock:
        if _token and time.time() < _token_exp - 60:
            return _token
        raw = get_settings().sheets_service_account_json
        if not raw:
            raise SheetsUnavailable("SHEETS_SERVICE_ACCOUNT_JSON is not set")
        try:
            creds = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SheetsUnavailable(f"SHEETS_SERVICE_ACCOUNT_JSON is not valid JSON: {exc}") from exc
        now = int(time.time())
        claims = {
            "iss": creds["client_email"],
            "scope": SHEETS_SCOPE,
            "aud": TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        }
        assertion = jwt.encode(claims, creds["private_key"], algorithm="RS256")
        try:
            with httpx.Client(timeout=TIMEOUT_S) as c:
                r = c.post(TOKEN_URL, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
        except httpx.HTTPError as exc:
            raise SheetsUnavailable(f"token request failed: {exc}") from exc
        if r.status_code != 200:
            raise SheetsUnavailable(f"token request returned {r.status_code}: {r.text[:200]}")
        body = r.json()
        _token = body["access_token"]
        _token_exp = time.time() + body.get("expires_in", 3600)
        return _token


def _rows(db: Db) -> list[list[str]]:
    rows = db.q(
        """select p.full_name, p.title, c.name as company, p.email, p.phone, p.linkedin_url, p.region,
                  cp.name as campaign, e.state, e.score, u.name as rep, e.last_touch, e.meeting, e.note, e.is_seed
           from enrollments e
           join prospects p on p.id = e.prospect_id
           join companies c on c.id = p.company_id
           join campaigns cp on cp.id = e.campaign_id
           left join users u on u.id = e.rep_id
           order by cp.name, e.last_touch desc nulls last, p.full_name"""
    )
    out = [HEADER]
    for r in rows:
        out.append(
            [
                r["full_name"],
                r["title"],
                r["company"],
                r["email"],
                r["phone"],
                r["linkedin_url"],
                r["region"],
                r["campaign"],
                r["state"],
                str(r["score"]) if r["score"] is not None else "",
                r["rep"] or "",
                r["last_touch"].isoformat() if r["last_touch"] else "",
                "yes" if r["meeting"] else "",
                r["note"] or "",
                "DEMO" if r["is_seed"] else "",
            ]
        )
    return out


def sync(db: Db) -> int:
    """Overwrite the configured tab with every enrollment. Returns the row count written. Raises SheetsUnavailable on failure."""
    settings = get_settings()
    if not settings.sheets_enabled:
        raise SheetsUnavailable("SHEETS_ENABLED is off")
    sid = settings.sheets_spreadsheet_id
    if not sid:
        raise SheetsUnavailable("SHEETS_SPREADSHEET_ID is not set")
    token = _access_token()
    values = _rows(db)
    tab = settings.sheets_sheet_name
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=TIMEOUT_S) as c:
        clear = c.post(f"{base}/{tab}:clear", headers=headers)
        if clear.status_code != 200:
            raise SheetsUnavailable(f"clear returned {clear.status_code}: {clear.text[:200]}")
        put = c.put(
            f"{base}/{tab}!A1",
            headers=headers,
            params={"valueInputOption": "RAW"},
            json={"values": values},
        )
        if put.status_code != 200:
            raise SheetsUnavailable(f"update returned {put.status_code}: {put.text[:200]}")
    return len(values) - 1


def sync_if_due(db: Db) -> None:
    """Called from the worker's maintenance tick. Rate-limited to SHEETS_SYNC_SECONDS. Never raises."""
    global _last_sync
    settings = get_settings()
    if not settings.sheets_enabled:
        return
    if time.monotonic() - _last_sync < settings.sheets_sync_seconds:
        return
    _last_sync = time.monotonic()
    try:
        n = sync(db)
        log().info("sheets sync ok", extra={"event": "sheets_sync", "rows": n})
    except SheetsUnavailable as exc:
        log().warning("sheets sync skipped", extra={"event": "sheets_sync_failed", "reason": str(exc)[:200]})
    except Exception:
        log().exception("sheets sync failed", extra={"event": "sheets_sync_failed"})
