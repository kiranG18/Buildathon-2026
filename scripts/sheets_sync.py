"""One-off runner for MA-15: push the current CRM mirror to Google Sheets right now and print the result.

Run with `python -m scripts.sheets_sync` after SHEETS_ENABLED, SHEETS_SPREADSHEET_ID and
SHEETS_SERVICE_ACCOUNT_JSON are set (locally in .env, or on the host).
"""

import sys

from backend.core.config import get_settings
from backend.core.db import tx
from backend.integrations import sheets


def main() -> int:
    try:
        with tx() as db:
            n = sheets.sync(db)
    except sheets.SheetsUnavailable as exc:
        print(f"Sync failed: {exc}")
        return 1
    print(f"Synced {n} rows to tab '{get_settings().sheets_sheet_name}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
