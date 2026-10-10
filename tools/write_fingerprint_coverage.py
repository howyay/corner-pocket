"""Does the write-fingerprint proof still cover every table the migrations create?

``scripts/pool-write-fingerprint.sql`` prints one line per user-data table: the table
name, its row count, and an md5 over every row's ``xmin`` and content.  ``xmin`` is the
id of the transaction that last wrote the row, so any write changes the line - an INSERT,
a DELETE, even an UPDATE that rewrites identical values - while any number of reads leave
it byte-identical.  The before/after diff of two runs is how a read-only smoke is proven
to have written nothing (docs/postgres.md, "Proving a read wrote nothing").

The branch list is a hand copy of the schema, and SQL cannot read ``db/migrations``.  A
migration that creates a table therefore leaves the proof printing a complete-looking list
that silently omits it, and no other check notices: nothing under ``scripts/``, ``tools/``,
``tests/`` or ``.github/`` runs the file.

    .venv/bin/python tools/write_fingerprint_coverage.py

It reads the two texts, opens no database, and reports every table only one side has:

  * ``MISSING``   - db/migrations creates the table, the proof does not fingerprint it;
  * ``STALE``     - the proof fingerprints a table no migration creates;
  * ``UNUSED``    - a named exclusion that no longer matches a created table;
  * ``PROBLEM``   - a branch prints one name and reads another, two branches fingerprint
                    one table, the branches do not all use one expression, or the file is
                    not the shape this reader understands.

Exit status 0 means every created table is covered except the named exclusions.  The one
exclusion is the migration ledger ``schema_migrations``: one row per applied migration,
not operator data.  It is named in ``LEDGER`` with its reason, and an entry that stops
matching a created table is reported, so an exclusion cannot outlive its table.

``tests/test_write_fingerprint.py`` compares the same two files, so the suite fails on any
difference and this tool and the proof cannot drift apart.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import db

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "scripts" / "pool-write-fingerprint.sql"
MIGRATIONS = ROOT / "db" / "migrations"

#: Tables the proof must not fingerprint, mapped to the reason.  The ledger records which
#: migrations were applied; every other table under db/migrations is operator data.
LEDGER = {
    "schema_migrations": "the migration ledger (db/migrations/0001_schema_migrations.sql): "
                         "one row per applied migration, not operator data",
}

#: A branch head: the printed name, then - on the leading branch only - the column alias
#: the union orders by.
HEAD = re.compile(r"^(?:UNION ALL )?SELECT\s+'([A-Za-z_][A-Za-z0-9_]*)'(?:\s+AS\s+tbl)?")
#: A branch tail: the proof reads the table through the alias ``x``.
TAIL = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\s+x\s*$")
#: A column alias.  The leading branch of the shipped proof spells ``AS n`` and ``AS fp``
#: and the union branches spell neither: that names a column, it is not a second expression.
ALIAS = re.compile(r"\s+AS\s+[A-Za-z_][A-Za-z0-9_]*")
#: The line that closes the union.
TERMINATOR = re.compile(r"^ORDER BY 1;?$")
#: A migration's ``CREATE TABLE``, its name captured.  Unqualified, as db/migrations writes them.
CREATE = re.compile(r"^\s*CREATE TABLE\s+(?:IF NOT EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)")
#: Any mention of ``CREATE TABLE``, so a form this reader cannot parse is refused, not skipped.
CREATE_MENTION = re.compile(r"^\s*CREATE TABLE\b")


class ProofError(ValueError):
    """The proof file is not in the shape this reader understands."""


@dataclass(frozen=True)
class Branch:
    """One fingerprint branch: its line, the name it prints, the table it reads."""

    line: int
    label: str
    table: str
    body: str


@dataclass(frozen=True)
class Coverage:
    """The two readings and every difference between them."""

    branches: tuple
    created: dict
    files: tuple
    excluded: dict
    missing: tuple
    stale: tuple
    unused: tuple
    problems: tuple

    @property
    def covered(self) -> tuple:
        """The tables the proof fingerprints, in name order."""
        return tuple(sorted({branch.table for branch in self.branches}))

    @property
    def ok(self) -> bool:
        return not (self.missing or self.stale or self.unused or self.problems)


def label(path) -> str:
    """``path`` as a checkout-relative name when it is inside the checkout."""
    path = Path(path)
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def proof_branches(path=PROOF) -> tuple:
    """Every fingerprint branch of ``path``, in file order.

    The expression after the printed name must be the same in every branch, so the lines
    stay comparable with ``diff``; ``Branch.body`` is that expression with the printed
    name, the table and the column aliases taken out, which is what the comparison reads.
    """
    branches = []
    closed = False
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("--"):
            continue
        if TERMINATOR.match(text):
            closed = True
            continue
        head = HEAD.match(text)
        tail = TAIL.search(text)
        if head is None or tail is None:
            raise ProofError(f"{label(path)}:{number}: not a fingerprint branch: {text[:60]}")
        expression = ALIAS.sub("", text[head.end():tail.start()] + "FROM @ x")
        branches.append(Branch(number, head.group(1), tail.group(1), " ".join(expression.split())))
    if not closed:
        raise ProofError(f"{label(path)}: no '{TERMINATOR.pattern}' line; the union is not closed")
    if not branches:
        raise ProofError(f"{label(path)}: no fingerprint branch found")
    return tuple(branches)


def created_tables(directory=MIGRATIONS) -> tuple:
    """({table: "db/migrations/NNNN_name.sql:LINE"}, the migration file names in order)."""
    created = {}
    files = []
    for _, name, sql in db.migrations(Path(directory)):
        files.append(name)
        for number, line in enumerate(sql.splitlines(), 1):
            match = CREATE.match(line)
            if match:
                created[match.group(1)] = f"{label(directory)}/{name}.sql:{number}"
            elif CREATE_MENTION.match(line):
                raise ProofError(f"{label(directory)}/{name}.sql:{number}: a CREATE TABLE this "
                                 f"reader cannot parse: {line.strip()[:60]}")
    return created, tuple(files)


def stale_reason(table: str, excluded: dict) -> str:
    """Why a fingerprinted table is not one the migrations create."""
    if table in excluded:
        return f"the exclusion list covers it: {excluded[table]}"
    return "no migration creates this table"


def coverage(proof=PROOF, directory=MIGRATIONS, excluded=None) -> Coverage:
    """Compare the proof's branch list with the tables the migrations create.

    ``excluded`` maps a table name to the reason the proof must not cover it; the default
    is ``LEDGER``.  A difference is data, not an exception: the caller decides what to
    print and with which exit status.
    """
    excluded = dict(LEDGER if excluded is None else excluded)
    branches = proof_branches(proof)
    created, files = created_tables(directory)
    problems = []
    seen = {}
    for branch in branches:
        if branch.label != branch.table:
            problems.append(f"{label(proof)}:{branch.line}: prints '{branch.label}' but reads "
                            f"FROM {branch.table}")
        if branch.table in seen:
            problems.append(f"{label(proof)}:{branch.line}: {branch.table} is fingerprinted "
                            f"twice (also line {seen[branch.table]})")
        seen[branch.table] = branch.line
    bodies = {}
    for branch in branches:
        bodies.setdefault(branch.body, []).append(branch.line)
    if len(bodies) > 1:
        order = sorted(bodies, key=lambda body: bodies[body][0])
        problems.append(f"{label(proof)}: the branches do not all use one expression: line "
                        f"{bodies[order[0]][0]} reads {order[0]!r}, line {bodies[order[1]][0]} "
                        f"reads {order[1]!r}")
    wanted = {table: origin for table, origin in created.items() if table not in excluded}
    missing = tuple(sorted((table, origin) for table, origin in wanted.items()
                           if table not in seen))
    stale = tuple(sorted((branch.table, branch.line, stale_reason(branch.table, excluded))
                         for branch in branches if branch.table not in wanted))
    unused = tuple(sorted(table for table in excluded if table not in created))
    return Coverage(branches, created, files, excluded, missing, stale, unused, tuple(problems))


def by_file(created: dict, files: tuple) -> dict:
    """{migration file stem: how many tables it creates}, zero included."""
    counts = {name: 0 for name in files}
    for origin in created.values():
        stem = origin.rsplit("/", 1)[-1].split(".", 1)[0]
        counts[stem] = counts.get(stem, 0) + 1
    return counts


def report(proof=PROOF, directory=MIGRATIONS, excluded=None) -> tuple:
    """The full reading as text, and the exit status: 0 when the proof covers the schema."""
    result = coverage(proof, directory, excluded)
    files = by_file(result.created, result.files)
    schema = f"schema    {label(directory)}: {len(result.created)} CREATE TABLE in " \
             f"{len(result.files)} files"
    lines = [
        f"proof     {label(proof)}: {len(result.branches)} branches, {len(result.covered)} tables",
        schema + " (" + ", ".join(f"{name} {count}" for name, count in sorted(files.items())) + ")",
        f"covered   {' '.join(result.covered)}",
        "excluded  " + ("; ".join(f"{table}: {reason}" for table, reason
                                  in sorted(result.excluded.items())) or "nothing"),
    ]
    lines.extend(f"MISSING   {table} ({origin})" for table, origin in result.missing)
    lines.extend(f"STALE     {table} ({label(proof)}:{line}; {reason})"
                 for table, line, reason in result.stale)
    lines.extend(f"UNUSED    {table} is excluded but no migration creates it"
                 for table in result.unused)
    lines.extend(f"PROBLEM   {problem}" for problem in result.problems)
    if result.ok:
        lines.append(f"OK: {len(result.created) - len(result.excluded)} of "
                     f"{len(result.created)} created tables are fingerprinted; "
                     f"{len(result.excluded)} named exclusion(s)")
        return "\n".join(lines), 0
    lines.append(f"FAIL: {len(result.missing)} missing, {len(result.stale)} stale, "
                 f"{len(result.unused)} unused exclusion(s), {len(result.problems)} problem(s)")
    return "\n".join(lines), 1


def main() -> int:
    """Print the reading and return the exit status."""
    text, status = report()
    print(text)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
