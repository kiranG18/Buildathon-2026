import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.core.config import get_settings

MIGRATIONS = Path(__file__).resolve().parents[2] / "database" / "migrations"

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def J(value: Any) -> Jsonb:
    return Jsonb(value)


def pool() -> ConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ConnectionPool(
                get_settings().database_url,
                min_size=1,
                max_size=24,
                kwargs={"row_factory": dict_row, "options": "-c statement_timeout=5000"},
                open=False,
                timeout=10,
            )
            _pool.open(wait=True, timeout=15)
    return _pool


def close_pool() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None


class Db:
    """One transaction. Every helper takes positional %s parameters."""

    def __init__(self, conn):
        self.conn = conn

    def q(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def q1(self, sql: str, params: tuple | list = ()) -> dict | None:
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def x(self, sql: str, params: tuple | list = ()) -> int:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def nid(self, prefix: str) -> str:
        row = self.q1("select nextval('id_seq') as n")
        return f"{prefix}{row['n']}"

    def lock(self, key: str) -> None:
        self.x("select pg_advisory_xact_lock(hashtext(%s))", (key,))


@contextmanager
def tx(timeout_ms: int | None = None) -> Iterator[Db]:
    with pool().connection() as conn:
        if timeout_ms is not None:
            conn.execute(f"set local statement_timeout = {int(timeout_ms)}")
        yield Db(conn)


def migrate(reset: bool = False) -> list[str]:
    applied: list[str] = []
    with pool().connection() as conn:
        if reset:
            conn.execute("drop schema public cascade")
            conn.execute("create schema public")
            conn.commit()
        conn.execute("create table if not exists schema_migrations (name text primary key, applied_at timestamptz default now())")
        done = {r["name"] for r in conn.execute("select name from schema_migrations").fetchall()}
        conn.commit()
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
            conn.commit()
            applied.append(f.name)
    return applied
