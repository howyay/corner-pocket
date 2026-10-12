"""One writer owns each row statement of the shipped tree: src/store_import.py.

Round 80 measured an ``ast`` walk of every shipped ``.py`` file: 19 tables, and
two of them were written by two modules each.

* ``ops_events``: ``src/store_import.py`` (``OperationsSet.write``) and
  ``src/store_pg.py`` (``PostgresStore._save``) spelled one statement, byte for
  byte - ``INSERT INTO ops_events (revision, id, created_at, action, context)``
  with five parameters.
* ``frame_corrections``: ``src/store_import.py`` (``CorrectionsSet.write``) and
  ``src/store_pg.py`` (``PostgresStore.correction_put``) shared the head, the bind
  list and the value rule; the store added an ``ON CONFLICT ... DO UPDATE`` tail
  that the import does not need.  A column added to one copy alone would leave the
  other writer writing the old shape, and only ``face_embeddings`` had a guard.

``src/store_pg.py`` already said the mapping has one owner ("The document <->
rows mapping is src.store_import.OperationsSet (the import uses the same code)").
Round 80 made the code say it: ``src.store_import`` holds ``OPS_EVENT_INSERT``,
``CORRECTION_INSERT`` and ``CORRECTION_UPSERT``, the store imports the three names,
and the one difference - the tail - stands beside the row it belongs to.

This module holds that state in four ways, with no database:

1. one ``ast`` walk of the shipped tree reports every module that spells an INSERT
   of a table and every name it binds that statement to;
2. one case reads the store: it imports the three names, spells no INSERT of either
   table, and its two writers name the owner;
3. two cases plant a second writer in the guard's own temporary text, so the walk
   cannot pass because it matches nothing;
4. one case holds the two rows themselves: the table, the arity and the tail.

``tests/test_face_row_owner.py`` asks a narrower question about one of the
nineteen tables: the columns of the face row, its ``::double precision[]`` cast and
its value rule, with both writers run over one recording connection.  This module
asks who owns each of the nineteen, so a table that gains a second writer fails
here even when the two statements agree today.

Run: ``./scripts/pool-test.sh python test_row_statement_owner``
"""
from __future__ import annotations

import ast
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from _shipped import code_strings, shipped_modules  # noqa: E402

from src.store_import import (  # noqa: E402
    CORRECTION_INSERT, CORRECTION_UPSERT, OPS_EVENT_INSERT)

#: The tables of the shipped tree, counted by the walk in round 80.
TABLES_MEASURED = 19
#: The two tables of round 80, with the module and the name that own their row.
OWNED_ROW_FOR = {"ops_events": ("src/store_import.py", "OPS_EVENT_INSERT"),
                 "frame_corrections": ("src/store_import.py", "CORRECTION_INSERT")}
#: The module that appends to both tables and must read the owner, not spell it.
READER = "src/store_pg.py"
#: The three owner names the console reads.
READ_NAMES = ("CORRECTION_INSERT", "CORRECTION_UPSERT", "OPS_EVENT_INSERT")


def statement_table(text: str) -> str:
    """The table of one statement text, or "" when the text holds no INSERT."""
    _, found, rest = " ".join(text.split()).partition("INSERT INTO ")
    names = rest.split() if found else []
    return names[0] if names else ""


def statement_name(parent: ast.AST | None) -> str:
    """The name one statement literal is bound to, or ``"(inline)"``.

    Only the direct parent counts: the constant of
    ``OPS_EVENT_INSERT = ("INSERT ..." " VALUES ...")`` is the value of an
    assignment, and the constant of ``conn.execute("INSERT ...")`` is an argument.
    """
    if isinstance(parent, ast.Assign) and len(parent.targets) == 1:
        target = parent.targets[0]
    elif isinstance(parent, ast.AnnAssign):
        target = parent.target
    else:
        return "(inline)"
    return target.id if isinstance(target, ast.Name) else "(inline)"


def module_label(path: Path) -> str:
    """The path of a shipped module from the root, or the bare name of a file
    outside the tree: the planted modules of the cases below live in a temporary
    directory."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def insert_writers(files: list[Path]) -> dict:
    """``{table: {module: [statement name]}}`` for every INSERT of the files.

    The literals come from ``_shipped.code_strings``, so a docstring that quotes a
    statement is not a writer.  Names are sorted, so two walks of one tree answer
    one dictionary.
    """
    writers: dict = {}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        kept = set(code_strings(tree))
        parents = {child: parent for parent in ast.walk(tree)
                   for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if (node.lineno, node.value) not in kept:
                continue
            table = statement_table(node.value)
            if table:
                name = statement_name(parents.get(node))
                writers.setdefault(table, {}).setdefault(module_label(path), set()).add(name)
    return {table: {module: sorted(names) for module, names in sorted(owners.items())}
            for table, owners in sorted(writers.items())}


def source_text(relative: str) -> str:
    """The text of one shipped file, read from the repository root."""
    return (ROOT / relative).read_text(encoding="utf-8")


def function_body(relative: str, name: str) -> str:
    """The source of one function of a shipped file, or "" when it is absent."""
    source = source_text(relative)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    return ""


def imported_from(relative: str, module: str) -> set:
    """The names one shipped file imports from one module."""
    names = set()
    for node in ast.walk(ast.parse(source_text(relative))):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.update(alias.name for alias in node.names)
    return names


class OneWriterPerTable(unittest.TestCase):
    """The walk, over the whole shipped tree."""

    def test_no_table_has_two_writing_modules(self):
        writers = insert_writers(shipped_modules())
        twice = {table: owners for table, owners in writers.items() if len(owners) > 1}
        self.assertEqual(twice, {}, f"more than one module writes a table's rows: {twice}")
        self.assertGreaterEqual(
            len(writers), TABLES_MEASURED,
            f"the walk must see the tables of the shipped tree, not an empty set: {sorted(writers)}")

    def test_the_two_rows_of_the_round_have_one_writer(self):
        writers = insert_writers(shipped_modules())
        for table, (module, name) in sorted(OWNED_ROW_FOR.items()):
            self.assertEqual(writers.get(table), {module: [name]})


class TheConsoleReadsTheOwner(unittest.TestCase):
    """The reader side: the store spells no row statement and names the owner."""

    def test_the_store_imports_the_three_owner_names(self):
        names = imported_from(READER, "src.store_import")
        self.assertTrue(set(READ_NAMES) <= names, f"{READER} imports {sorted(names)}")

    def test_the_store_spells_no_row_statement(self):
        text = source_text(READER)
        for table in sorted(OWNED_ROW_FOR):
            self.assertNotIn(f"INSERT INTO {table}", text)

    def test_the_two_writers_name_the_owner(self):
        save = function_body(READER, "_save")
        self.assertIn("OPS_EVENT_INSERT", save)
        self.assertNotIn("INSERT INTO", save)
        put = function_body(READER, "correction_put")
        for name in ("CORRECTION_INSERT", "CORRECTION_UPSERT"):
            self.assertIn(name, put)
        self.assertNotIn("INSERT INTO", put)


class OnePlantCannotPass(unittest.TestCase):
    """A second writer planted in a temporary text is reported by the walk."""

    def test_a_planted_inline_statement_is_a_second_writer(self):
        planted = textwrap.dedent('''
            """A store that spells the row again; this text is not a shipped file."""

            def save(conn, event):
                conn.execute("INSERT INTO ops_events (revision, id, created_at, action, context) "
                             "VALUES (%s, %s, %s, %s, %s)", event)
            ''')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "planted_store.py"
            path.write_text(planted, encoding="utf-8")
            writers = insert_writers(list(shipped_modules()) + [path])
        self.assertEqual(sorted(writers["ops_events"]),
                         ["planted_store.py", "src/store_import.py"])
        self.assertEqual(writers["ops_events"]["planted_store.py"], ["(inline)"])

    def test_a_planted_named_statement_is_reported_by_its_name(self):
        planted = textwrap.dedent('''
            """A rows module that keeps its own copy; this text is not a shipped file."""

            OPS_EVENT_INSERT = ("INSERT INTO ops_events (revision, id, created_at, action, context)"
                                " VALUES (%s, %s, %s, %s, %s)")
            ''')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "planted_rows.py"
            path.write_text(planted, encoding="utf-8")
            writers = insert_writers(list(shipped_modules()) + [path])
        self.assertEqual(sorted(writers["ops_events"]),
                         ["planted_rows.py", "src/store_import.py"])
        self.assertEqual(writers["ops_events"]["planted_rows.py"], ["OPS_EVENT_INSERT"])


class TheTwoRowsThemselves(unittest.TestCase):
    """The owner's rows: the table, the arity and the one named difference."""

    def test_the_rows_name_their_table_and_their_arity(self):
        for text, table, binds in ((OPS_EVENT_INSERT, "ops_events", 5),
                                   (CORRECTION_INSERT, "frame_corrections", 4)):
            self.assertTrue(text.startswith(f"INSERT INTO {table} "), text)
            self.assertEqual(text.count("%s"), binds, text)

    def test_the_import_row_carries_no_conflict_tail(self):
        for text in (OPS_EVENT_INSERT, CORRECTION_INSERT):
            self.assertNotIn("ON CONFLICT", text)
        self.assertIn("ON CONFLICT (dataset, frame_index) DO UPDATE SET", CORRECTION_UPSERT)
        self.assertIn("payload = EXCLUDED.payload, saved_at = EXCLUDED.saved_at", CORRECTION_UPSERT)
