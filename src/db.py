"""PostgreSQL access for Corner Pocket: one connection helper and a tiny migration runner.

The database is optional.  It is configured by exactly one environment variable,
POOL_DATABASE_URL (kept in ~/.config/pool/postgres.env, mode 600 -- see
docs/postgres.md).  Without it nothing here connects, and the JSON files stay the
store.  No ORM: plain psycopg 3, plain SQL.

  with connect() as conn:                 # autocommit; closed when the block ends
      with conn.transaction():            # BEGIN ... COMMIT, ROLLBACK if it raises
          conn.execute("...")

  with transaction() as conn:             # one connection, one transaction
      conn.execute("...")

Migrations are db/migrations/NNNN_name.sql, applied in version order by migrate()
and recorded in schema_migrations (created by 0001 itself).  A run takes an
advisory lock and applies every pending file in one transaction, so it is
idempotent, safe to race, and all-or-nothing.  A migration file must not contain
BEGIN/COMMIT, and an applied file must never be edited: its checksum is recorded
and a changed file is refused.  Apply from the shell with `python -m src.db`.

Nothing here formats the connection string into a message: the password in it
must never reach a log.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

ENV = "POOL_DATABASE_URL"
MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migrations"
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_LOCK = 0x706F6F6C  # advisory lock key ('pool') serialising concurrent migrate() runs


class DatabaseNotConfigured(RuntimeError):
    pass


def database_url() -> str:
    url = os.environ.get(ENV)
    if not url:
        raise DatabaseNotConfigured(
            f"{ENV} is not set, so the Postgres backend is off. Load it with "
            f"`set -a; . ~/.config/pool/postgres.env; set +a` (docs/postgres.md).")
    return url


def connect(url: str | None = None):
    """An autocommit psycopg connection; use it as a context manager so it closes."""
    url = url or database_url()
    import psycopg  # imported here so the JSON-only code paths never need the driver
    return psycopg.connect(url, autocommit=True, connect_timeout=5)


@contextmanager
def transaction(url: str | None = None):
    """One connection, one transaction: commits when the block ends, rolls back if it raises."""
    with connect(url) as conn, conn.transaction():
        yield conn


def migrations(directory: Path = MIGRATIONS) -> list[tuple[int, str, str]]:
    """(version, name, sql) for every migration file, in version order."""
    found: dict[int, tuple[int, str, str]] = {}
    for path in sorted(directory.glob("*.sql")):
        m = _NAME.match(path.name)
        if not m:
            raise ValueError(f"migration file must be named NNNN_name.sql: {path.name}")
        version = int(m.group(1))
        if version in found:
            raise ValueError(f"two migrations share version {version:04d}: {found[version][1]}, {path.stem}")
        found[version] = (version, path.stem, path.read_text())
    return [found[v] for v in sorted(found)]


def migrate(conn, directory: Path = MIGRATIONS) -> list[int]:
    """Apply every pending migration in order, in one transaction; returns the versions applied now."""
    applied: list[int] = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK,))
        done: dict[int, str] = {}
        if conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0]:
            done = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())
        for version, name, sql in migrations(directory):
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if version in done:
                if done[version] != checksum:
                    raise RuntimeError(f"migration {name} changed after it was applied; add a new migration instead")
                continue
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                         (version, name, checksum))
            applied.append(version)
    return applied


if __name__ == "__main__":
    try:
        with connect() as conn:
            applied = migrate(conn)
            print(f"{conn.info.host}:{conn.info.port}/{conn.info.dbname}: applied {applied or 'nothing'}")
            for name, at in conn.execute("SELECT name, applied_at FROM schema_migrations ORDER BY version"):
                print(f"  {name}  {at:%Y-%m-%d %H:%M:%S %z}")
    except DatabaseNotConfigured as e:
        sys.exit(str(e))
