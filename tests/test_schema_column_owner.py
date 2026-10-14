"""Hold the column names of the shipped schema and of the importer together.

``db/migrations/0002_user_data.sql`` declares the columns of the user-data
tables.  ``src/store_import.py`` spells many of the same names a second time,
inside its ``INSERT INTO <table> (...)`` and ``SELECT ... FROM <table>``
statements.  SQL cannot import Python, so the two spellings are two copies of
one list.

A rename on either side is the cost.  The importer names a column the schema
does not declare, or the schema declares a column that no statement reads or
writes.  Every case that would catch such a rename opens a database:
``tests/test_store_import.py:20`` holds
``HAVE_DB = bool(os.environ.get(db.ENV))``, its import cases carry
``@unittest.skipUnless(HAVE_DB, ...)`` at ``tests/test_store_import.py:53``, and
``src/db.py:34`` holds ``ENV = "POOL_DATABASE_URL"``.  A default run leaves that
variable unset, so it runs none of them.

This module reads text only.  It opens no database, and it needs none:

1. it parses each ``CREATE TABLE`` block of the migration into
   ``{table: {column: line}}``;
2. it parses each ``INSERT INTO <table> (...)`` and each
   ``SELECT <columns> FROM <table>`` of the importer, with the line of each
   statement;
3. one case holds every named column to the schema;
4. one case holds every declared column of a written table to a statement, or
   to the explicit ``DELIBERATELY_UNUSED`` map of this module;
5. one case pins the numbers of the scan, so a reworded statement cannot make
   the guard pass in silence;
6. one case runs the report helper over a planted text and reads the report;
7. one case reads the UPDATE statements and the ``ON CONFLICT`` clauses, whose
   column names stand outside a plain name list.

The scan reads plain statement texts.  A statement that holds a subquery or a
computed expression is left out of the column check: only a plain name list is
proof of a column name.  The skipped texts are measured and pinned by the case
``test_the_scan_leaves_out_only_the_measured_statements``, so a statement cannot
leave the check in silence.

The scope follows the tables of migration 0002.  The importer writes to 17
tables and reads from 16 of them.  ``json_documents`` belongs to migration 0003
and is read only, so no case of this module names it: its declaration lives in
another file, and this module does not read that declaration.

Run: ``./scripts/pool-test.sh python test_schema_column_owner``
"""
from __future__ import annotations

import ast
import re
import unittest
from dataclasses import dataclass
from pathlib import Path

#: The repository root, from this file's own path.
ROOT = Path(__file__).resolve().parents[1]

#: The schema that declares the columns, and the importer that names them.
SCHEMA_PATH = "db/migrations/0002_user_data.sql"
IMPORTER_PATH = "src/store_import.py"

#: The words that start a table constraint, not a column definition.
CONSTRAINT_WORDS = ("PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CHECK", "CONSTRAINT")

#: The migration of the scan, with the words and the line numbers of the later
#: migrations.  A later migration can add a column to a table of migration 0002:
#: ``db/migrations/0003_json_documents.sql:32`` adds
#: ``identity_clusters.has_face_samples``.  The scan reads the two lines here,
#: because the importer states that column with the columns of the base table.
LATER_MIGRATIONS = ("db/migrations/0003_json_documents.sql", "db/migrations/0004_imported_datasets.sql")

#: The words of a table-scoped ALTER, with the table and the added column.
ALTER_RE = re.compile(r"^\s*ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+ADD\s+COLUMN\s+([A-Za-z_][A-Za-z0-9_]*)",
                      re.I)
#: The head of a CREATE TABLE block.
CREATE_RE = re.compile(r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)", re.I)
#: The first name of a column definition line.
COLUMN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s")
#: One column name, without a quote, a cast or an expression.
PLAIN_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: The head of an INSERT statement, with its column list.
INSERT_RE = re.compile(r"^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)", re.I | re.S)
#: The head of a SELECT statement, with its column list and its table.  The
#: column list holds no bracket, so a subquery is not a column list.
SELECT_RE = re.compile(r"^\s*SELECT\s+([^()]+?)\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)", re.I | re.S)
#: The head of an UPDATE statement, with its table.
UPDATE_RE = re.compile(r"^\s*UPDATE\s+([A-Za-z_][A-Za-z0-9_]*)\s+SET\s", re.I | re.S)
#: A column of the SET clause of an UPDATE, and a column of an ON CONFLICT clause.
SET_RE = re.compile(r"(?:^|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
EXCLUDED_RE = re.compile(r"\bEXCLUDED\.([A-Za-z_][A-Za-z0-9_]*)", re.I)

#: The columns of a written table that no statement of the importer names, each
#: one with the measured reason.  The key is ``(table, column)``.
DELIBERATELY_UNUSED = {
    ("ball_labels", "OR"):
        "a parser artifact: the name stands in the second line of the CHECK rule of 'label'",
    ("ball_labels", "updated_at"):
        "the database fills the default now(); the importer reads the file, not a change time",
    ("face_embeddings", "id"):
        "the identity column generates the key on insert, so no statement names it",
    ("identity_clusters", "updated_at"):
        "the database fills the default now(); no statement of the importer reads it",
    ("pocket_anchors", "updated_at"):
        "the database fills the default now(); the operator route writes the anchor row",
}

#: The numbers the scan measured on the tree of round 103.  Each one guards a
#: different silence: a lost file, a lost statement, a lost column.
TABLES_MEASURED = 17          # the CREATE TABLE blocks of the migration
COLUMNS_MEASURED = 114        # the column definitions those blocks declare
STATEMENTS_MEASURED = 36      # the INSERT and SELECT statements of the importer
INSERT_STATEMENTS_MEASURED = 17   # the statements that write a row
SELECT_STATEMENTS_MEASURED = 19   # the statements that read a row
WRITTEN_TABLES_MEASURED = 17  # the tables an INSERT writes
READ_TABLES_MEASURED = 16     # the tables a SELECT reads
SKIPPED_MEASURED = 2          # the plain statements whose table is outside migration 0002
NAMED_COLUMNS_MEASURED = 69  # the distinct columns the kept statements name
UPDATE_STATEMENTS_MEASURED = 2    # the UPDATE statements of the importer
UPDATE_LINES = (221, 225)         # the line of each UPDATE statement

#: The two ``json_documents`` SELECT statements of the importer, with the line of
#: each one.  The table belongs to migration 0003, so the scan skips the two.
SKIPPED_LINES = (715, 718)
MISSING_TABLE_NAME = "json_documents"


@dataclass(frozen=True)
class Statement:
    """One INSERT or SELECT statement of the importer, with its site."""

    kind: str                 # "INSERT" or "SELECT"
    path: str                 # "src/store_import.py"
    line: int                 # the first line of the statement text
    table: str                # the table the statement names
    columns: tuple            # the column names of the statement, in order
    text: str                 # the words of the statement, one space between them


def source_lines(relative: str) -> list:
    """The lines of one file of the repository, without their line ends."""
    return (ROOT / relative).read_text(encoding="utf-8").splitlines()


def line_text(text: str, line: int) -> str:
    """The exact text of one line of a text, without its line end.

    The reports of this module name the offender line by this text, so a writer
    opens the line the report names.  The text, not the file, is the input: a
    case can hand the report a planted text that stands in no file.
    """
    lines = text.splitlines()
    return lines[line - 1] if 0 < line <= len(lines) else ""


def schema_columns(relative: str = SCHEMA_PATH) -> dict:
    """``{table: {column: line}}`` from each CREATE TABLE block of one migration.

    Only a column definition line counts.  The words of ``CONSTRAINT_WORDS``
    start a table constraint, and a line that starts with ``)`` ends the block.
    """
    tables: dict = {}
    table = None
    for number, text in enumerate(source_lines(relative), start=1):
        head = CREATE_RE.match(text)
        if head:
            table = head.group(1)
            tables[table] = {}
            continue
        if table is None:
            continue
        words = text.strip()
        if words.startswith(")"):
            table = None
            continue
        if not words or words.startswith("--"):
            continue
        if words.upper().startswith(CONSTRAINT_WORDS):
            continue
        name = COLUMN_RE.match(words)
        if name:
            tables[table][name.group(1)] = number
    return tables


def added_columns() -> dict:
    """``{(table, column): "path:line"}`` of each column the later migrations declare.

    A later migration can add a column to a table of migration 0002, and it can
    declare a table of its own.  The map holds the declaration of each such
    column, and the name of its own site.  A column of this map is declared, so
    the column check accepts it and the skipped statements find their table.
    """
    added: dict = {}
    for relative in LATER_MIGRATIONS:
        for table, columns in schema_columns(relative).items():
            for column, number in columns.items():
                added.setdefault((table, column), f"{relative}:{number}")
        for number, text in enumerate(source_lines(relative), start=1):
            head = ALTER_RE.match(text)
            if head:
                added.setdefault((head.group(1), head.group(2)), f"{relative}:{number}")
    return added


def string_groups(text: str) -> list:
    """The adjacent string literals of a module, one group per statement.

    Python joins the parts of one statement into one value, and the parts of two
    statements stay apart.  The walk keeps the group, so the first line of a
    statement is the site this module reports.
    """
    tree = ast.parse(text)
    nodes = [node for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    nodes.sort(key=lambda node: (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset))
    groups: list = []
    group: list = []
    for node in nodes:
        if group and (node.lineno, node.col_offset) == (group[-1].end_lineno, group[-1].end_col_offset):
            group.append(node)
        else:
            if group:
                groups.append(group)
            group = [node]
    if group:
        groups.append(group)
    return groups


def name_list(text: str) -> tuple:
    """The plain column names of a comma-separated list, or an empty tuple.

    The reader refuses a name list that holds a quote, a cast or an expression:
    such a text is not proof of a column name.
    """
    names = tuple(part.strip().strip('"') for part in text.split(",") if part.strip())
    if names and all(PLAIN_NAME_RE.match(name) for name in names):
        return names
    return ()


def statements(source: str, tables: set) -> tuple:
    """``([Statement], [(line, words)])`` for the INSERT and SELECT statements.

    A statement whose table the schema does not declare waits in the second
    list.  The cases below read that list: a name cannot leave the check in
    silence.
    """
    kept: list = []
    outside: list = []
    for group in string_groups(source):
        words = " ".join("".join(node.value for node in group).split())
        line = group[0].lineno
        head = INSERT_RE.match(words)
        if head:
            kind, table, text = "INSERT", head.group(1), head.group(2)
        else:
            head = SELECT_RE.match(words)
            if not head:
                continue
            kind, table, text = "SELECT", head.group(2), head.group(1)
        if table not in tables:
            outside.append((line, words))
            continue
        columns = name_list(text)
        if not columns:
            continue
        kept.append(Statement(kind, IMPORTER_PATH, line, table, columns, words))
    return kept, outside


def named_columns(found: list) -> dict:
    """``{table: {column: [site]}}`` for each column the statements name."""
    names: dict = {}
    for statement in found:
        for column in statement.columns:
            names.setdefault(statement.table, {}).setdefault(column, []).append(
                f"{statement.path}:{statement.line}")
    return names


def violations(found: list, tables: dict, added: dict, text: str) -> list:
    """The report of each column a statement names and no migration declares.

    The schema is migration 0002 plus the declarations of the later migrations.
    A column of the second set is declared, so it is no violation.  The text
    holds the lines the report quotes.
    """
    report = []
    for statement in found:
        columns = tables.get(statement.table)
        if columns is None:
            continue
        for column in statement.columns:
            if column in columns or (statement.table, column) in added:
                continue
            report.append(
                f"{statement.path}:{statement.line}: {line_text(text, statement.line)}"
                f"  <- the statement names {column} and {SCHEMA_PATH} does not declare it for "
                f"{statement.table}")
    return report


def unaccounted(found: list, tables: dict) -> list:
    """The report of each declared column of a written table that no statement names.

    A written table is a table an INSERT statement names.  A column of such a
    table must stand in a statement, or in ``DELIBERATELY_UNUSED`` with a reason.
    """
    written = sorted({statement.table for statement in found if statement.kind == "INSERT"})
    named = named_columns(found)
    report = []
    for table in written:
        for column, number in sorted(tables.get(table, {}).items(), key=lambda pair: pair[1]):
            if column in named.get(table, {}) or (table, column) in DELIBERATELY_UNUSED:
                continue
            report.append(f"{SCHEMA_PATH}:{number} ({table}.{column})")
    return report


def undeclared_tables(outside: list, added: dict) -> list:
    """The report of each skipped statement whose table no migration declares.

    A statement of a table outside the schema of the scan is not proof of a
    broken row, so it is no violation of the column check.  The case of the
    skipped statements reads this list: a statement of a table that no migration
    of the repository declares would reach no check at all, and that is the one
    silence this helper refuses.
    """
    declared = {table for table, _ in added}
    return [f"{IMPORTER_PATH}:{line}: {words}" for line, words in outside
            if _first_table(words) not in declared]


def _first_table(words: str) -> str:
    """The table a statement names, without the schema of the scan."""
    head = INSERT_RE.match(words)
    if head:
        return head.group(1)
    head = SELECT_RE.match(words)
    return head.group(2) if head else ""


def updated_columns(tables: dict, added: dict, text: str) -> tuple:
    """``([line], [report])`` for the UPDATE statements of a module.

    An UPDATE names a column in its SET clause, and an upsert names a column
    after ``EXCLUDED.``.  Neither text is a plain name list, so the scan above
    leaves both alone.  This helper closes that hole: it reads the two forms and
    reports each name that no migration declares.
    """
    lines: list = []
    report: list = []
    for group in string_groups(text):
        words = " ".join("".join(node.value for node in group).split())
        head = UPDATE_RE.match(words)
        if not head:
            continue
        table = head.group(1)
        line = group[0].lineno
        lines.append(line)
        for column in sorted(set(SET_RE.findall(words.split("SET", 1)[1])
                                 + EXCLUDED_RE.findall(words))):
            if column in tables.get(table, {}) or (table, column) in added:
                continue
            report.append(f"{IMPORTER_PATH}:{line}: {line_text(text, line)}"
                          f"  <- the statement names {column} and {SCHEMA_PATH} does not declare it "
                          f"for {table}")
    return lines, report


class TheColumnsStandInBothFiles(unittest.TestCase):
    """The two copies of the column names, read as text."""

    def setUp(self):
        self.tables = schema_columns()
        self.added = added_columns()
        self.source = (ROOT / IMPORTER_PATH).read_text(encoding="utf-8")
        self.found, self.outside = statements(self.source, set(self.tables))

    def test_every_column_the_importer_names_is_declared(self):
        """Each column of each statement stands in migration 0002 or in a later ALTER."""
        report = violations(self.found, self.tables, self.added, self.source)
        self.assertEqual([], report,
                         "the importer names a column that no migration declares; a writer must "
                         "read this list as 'path:line: the line text  <- the name':\n"
                         + "\n".join(report))

    def test_no_written_column_of_an_update_escapes_the_schema(self):
        """Each column of an UPDATE or of an ON CONFLICT stands in a migration.

        The scan above reads a plain name list only, so an UPDATE and an upsert
        leave it.  This case reads the two forms of the module.  The count of the
        UPDATE statements is pinned, so a new UPDATE cannot enter in silence.
        """
        lines, report = updated_columns(self.tables, self.added, self.source)
        self.assertEqual(UPDATE_STATEMENTS_MEASURED, len(lines),
                         f"the module holds {len(lines)} UPDATE statements, not "
                         f"{UPDATE_STATEMENTS_MEASURED}: {lines}")
        self.assertEqual(list(UPDATE_LINES), lines,
                         "the UPDATE statements moved, so this case reads another site")
        self.assertEqual([], report,
                         "an UPDATE or an upsert names a column that no migration declares:\n"
                         + "\n".join(report))

    def test_every_declared_column_of_a_written_table_is_accounted_for(self):
        """Each column of a written table stands in a statement, or in the map with a reason."""
        report = unaccounted(self.found, self.tables)
        self.assertEqual([], report,
                         "a column of a written table reaches no statement, so no reader and no "
                         "writer names it.  Name it in a statement, or add it to "
                         "DELIBERATELY_UNUSED with the reason it stays empty:\n"
                         + "\n".join(report))

    def test_each_deliberately_unused_entry_names_a_real_column(self):
        """No entry of the map outlives its column, and each entry states a reason."""
        for (table, column), reason in sorted(DELIBERATELY_UNUSED.items()):
            with self.subTest(column=f"{table}.{column}"):
                self.assertTrue(column in self.tables.get(table, {}) or (table, column) in self.added,
                                f"the map names {table}.{column}, and no migration declares it")
                self.assertGreaterEqual(len(reason.split()), 4,
                                        f"the reason of {table}.{column} is too short to judge")

    def test_the_scan_leaves_out_only_the_measured_statements(self):
        """Each statement the scan leaves out names a table of a later migration.

        The statement leaves the column check, because migration 0002 does not
        declare its table.  That is safe only when a later migration declares the
        table, and this case holds that condition.
        """
        report = undeclared_tables(self.outside, self.added)
        self.assertEqual([], report,
                         "a statement names a table that no migration of the repository declares, "
                         "so no case of this module holds its columns:\n"
                         + "\n".join(report))
        self.assertEqual([MISSING_TABLE_NAME], sorted({_first_table(words) for _, words in self.outside}),
                         "the statements outside the scan changed table")
        self.assertEqual(list(SKIPPED_LINES), [line for line, _ in self.outside],
                         "the lines of the statements outside the scan changed, so a statement "
                         "entered or left the check in silence")

    def test_a_planted_offender_is_reported_with_its_file_and_line(self):
        """The report names the file, the line and the text of a planted violation.

        The planted text stands in no file of the repository: the report reads
        the line from the text it was given, so it names the planted line.
        """
        planted = ('"""A planted module: one statement that names a column no schema declares."""\n'
                   'import connection\n'
                   'def planted(conn):\n'
                   '    conn.execute("INSERT INTO planted_table (kept_name, planted_name) "\n'
                   '                 "VALUES (%s, %s)")\n')
        line = 4
        offender = '    conn.execute("INSERT INTO planted_table (kept_name, planted_name) "'
        self.assertEqual(offender, planted.splitlines()[line - 1],
                         "the planted text moved, so this case reads another line")
        statement = Statement("INSERT", "planted_module.py", line, "planted_table",
                              ("kept_name", "planted_name"), "INSERT INTO planted_table")
        report = violations([statement], {"planted_table": {"kept_name": 1}}, {}, planted)
        self.assertEqual(1, len(report), f"the report holds {len(report)} offenders, not one")
        self.assertIn(f"planted_module.py:{line}: {offender}", report[0],
                      "the report drops the file, the line or the text of the offender")
        self.assertIn("the statement names planted_name", report[0],
                      "the report drops the name of the offending column")
        self.assertNotIn(str(ROOT), report[0],
                         "the report of a planted text names the repository root")

    def test_the_scan_measures_the_numbers_of_this_round(self):
        """Pin the numbers, so a lost file or a reworded statement cannot pass.

        Each number holds one meaning: the tables of the migration, the columns
        those tables declare, the INSERT and the SELECT statements the scan
        reads, the written and the read tables, the statements outside the scan,
        and the distinct columns the statements name.
        """
        self.assertEqual(TABLES_MEASURED, len(self.tables),
                         f"the migration declares {len(self.tables)} tables, not {TABLES_MEASURED}")
        self.assertEqual(COLUMNS_MEASURED, sum(len(columns) for columns in self.tables.values()),
                         f"the migration declares {sum(len(c) for c in self.tables.values())} columns, "
                         f"not {COLUMNS_MEASURED}")
        self.assertEqual(STATEMENTS_MEASURED, len(self.found),
                         f"the scan reads {len(self.found)} statements, not {STATEMENTS_MEASURED}")
        self.assertEqual(INSERT_STATEMENTS_MEASURED,
                         sum(1 for statement in self.found if statement.kind == "INSERT"),
                         "the scan reads another number of INSERT statements")
        self.assertEqual(SELECT_STATEMENTS_MEASURED,
                         sum(1 for statement in self.found if statement.kind == "SELECT"),
                         "the scan reads another number of SELECT statements")
        self.assertEqual(WRITTEN_TABLES_MEASURED,
                         len({statement.table for statement in self.found if statement.kind == "INSERT"}),
                         "the scan reads another number of written tables")
        self.assertEqual(READ_TABLES_MEASURED,
                         len({statement.table for statement in self.found if statement.kind == "SELECT"}),
                         "the scan reads another number of read tables")
        self.assertEqual(SKIPPED_MEASURED, len(self.outside),
                         f"the scan leaves out {len(self.outside)} statements, not {SKIPPED_MEASURED}")
        self.assertEqual(NAMED_COLUMNS_MEASURED,
                         len({column for columns in named_columns(self.found).values() for column in columns}),
                         "the statements name another number of distinct columns")


if __name__ == "__main__":
    unittest.main()
