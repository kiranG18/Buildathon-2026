"""Start-up step for a fresh deployment: apply migrations and load the demo workspace when the database is empty."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.db import migrate, tx  # noqa: E402
from scripts.load_seed import load  # noqa: E402


def main() -> None:
    applied = migrate()
    if applied:
        print("migrated", ", ".join(applied))
    with tx() as db:
        empty = db.q1("select count(*) as n from campaigns")["n"] == 0
    if empty:
        print("empty database, loading the demo workspace:", load())
    else:
        print("database already holds a workspace")


if __name__ == "__main__":
    main()
