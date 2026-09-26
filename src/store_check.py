"""Check that the 0002 projection rows equal a fresh projection of the stored documents.

    PYTHONPATH=. .venv/bin/python -m src.store_check        # exit 0 = consistent

Since 0003 the documents in json_documents are the source of truth for the
operations and operator-record files, and the 0002 rows are a projection written
from them in the same transaction. This recomputes that projection from the stored
documents - into a throwaway schema, with the same writer code the store and the
import use - and compares it table by table with the live rows (every column but
the write timestamps). Any difference is printed and the exit code is 1.

The identity index and the face store have no document (their rows are the
store), so there is nothing to recompute for them. The event log is compared with
the document's last 500 events, which is what the document keeps.
"""
from __future__ import annotations

import json
import sys
import uuid

from src import db
from src.store_files import DATASETS, documents

# The rebuild copies each live table's definition (LIKE ... INCLUDING ALL): same
# columns, defaults, CHECKs and unique indexes; foreign keys are not copied, which
# is fine - the rebuilt rows are compared, not relied on.

SKIP_COLUMNS = {"updated_at"}          # set by the database at write time, not part of the data


def projections(docs: dict[str, str]):
    """(data set spec, parsed document) for every data set that has stored documents."""
    from src.store_import import SETS
    state = docs.get("out/corner-pocket/state.json")
    if state is not None:
        yield SETS["operations"], json.loads(state)
    seeds = docs.get("out/pid_seed.json")
    if seeds is not None:
        yield SETS["seeds"], json.loads(seeds)
    yield SETS["verdicts"], {ds: json.loads(docs[f"out/{scan}/annotations.json"])
                             for ds, scan in DATASETS.items() if f"out/{scan}/annotations.json" in docs}
    yield SETS["labels"], {path.split("/")[1]: json.loads(text) for path, text in docs.items()
                           if path.endswith("/labels.json")}
    yield SETS["anchors"], {path[len("out/pid_anchors_"):-len(".json")]: json.loads(text)
                            for path, text in docs.items() if path.startswith("out/pid_anchors_")}
    scans = {scan: ds for ds, scan in DATASETS.items()}
    corrections: dict = {}
    for path, text in docs.items():
        parts = path.split("/")
        if len(parts) == 5 and parts[2] == "frame_results" and parts[4] == "correction.json":
            corrections.setdefault(scans[parts[1]], {})[parts[3]] = json.loads(text)
    yield SETS["corrections"], corrections


def _rows(conn, schema: str, table: str) -> list[str]:
    columns = [r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
        "ORDER BY ordinal_position", (schema, table)).fetchall() if r[0] not in SKIP_COLUMNS]
    if table == "ops_events":
        query = (f'SELECT {", ".join(columns)} FROM (SELECT * FROM "{schema}".ops_events '
                 f'ORDER BY revision DESC LIMIT 500) last')
    else:
        query = f'SELECT {", ".join(columns)} FROM "{schema}"."{table}"'
    return sorted(repr(row) for row in conn.execute(query).fetchall())


class _Rollback(Exception):
    pass


def check(conn) -> list[str]:
    """Differences between the live projection and one rebuilt from the documents.

    The rebuild happens in a throwaway schema inside a transaction (a savepoint when
    the caller holds one) that is always rolled back, so the check leaves nothing
    behind and can run inside a store write to see exactly that write's state."""
    live = conn.execute("SELECT current_schema()").fetchone()[0]
    docs = documents(conn)
    scratch = f"store_check_{uuid.uuid4().hex[:12]}"
    tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s", (live,)).fetchall()]
    problems = []
    try:
        with conn.transaction():
            conn.execute(f"CREATE SCHEMA {scratch}")
            for table in tables:
                if table != "schema_migrations":
                    conn.execute(f'CREATE TABLE "{scratch}"."{table}" (LIKE "{live}"."{table}" INCLUDING ALL)')
            conn.execute(f"SET LOCAL search_path TO {scratch}")
            for spec, doc in projections(docs):
                spec.write(conn, doc)
                for table in spec.tables:
                    want, have = _rows(conn, scratch, table), _rows(conn, live, table)
                    if want != have:
                        missing = [r for r in want if r not in have][:2]
                        extra = [r for r in have if r not in want][:2]
                        problems.append(f"{table}: {len(have)} live rows vs {len(want)} from the documents; "
                                        f"missing {missing} extra {extra}")
            raise _Rollback
    except _Rollback:
        pass
    return problems


def main(argv=None) -> int:
    try:
        with db.connect() as conn:
            if conn.execute("SELECT to_regclass('json_documents')").fetchone()[0] is None:
                print("json_documents does not exist: apply the migrations first (python -m src.db)", file=sys.stderr)
                return 2
            problems = check(conn)
    except db.DatabaseNotConfigured as error:
        print(error, file=sys.stderr)
        return 2
    if problems:
        for problem in problems:
            print("MISMATCH  " + problem)
        return 1
    print("projection consistent with the stored documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
