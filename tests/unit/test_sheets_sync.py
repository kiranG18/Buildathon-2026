"""Google Sheets CRM mirror: row shape and the never-crash contract when unconfigured."""

import pytest

from backend.core.config import get_settings
from backend.integrations import sheets
from tests.helpers import scratch


def test_rows_have_header_and_one_row_per_enrollment():
    with scratch() as db:
        rows = sheets._rows(db)
        total = db.q1("select count(*) as n from enrollments")["n"]
    assert rows[0] == sheets.HEADER
    assert len(rows) - 1 == total
    if total:
        assert len(rows[1]) == len(sheets.HEADER)


def test_sync_raises_cleanly_when_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "sheets_enabled", False)
    with scratch() as db, pytest.raises(sheets.SheetsUnavailable, match="SHEETS_ENABLED"):
        sheets.sync(db)


def test_sync_if_due_never_raises_when_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "sheets_enabled", False)
    with scratch() as db:
        sheets.sync_if_due(db)  # must not raise
