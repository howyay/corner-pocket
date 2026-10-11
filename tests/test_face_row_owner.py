"""One writer owns the face_embeddings row: src/store_import.py.

Round 74 measured the row.  Two writers held it - the bulk import
(``src/store_import.FacesSet.write``) and the console append
(``src/store_pg.PostgresStore.faces_add``) - and the two already disagreed:

* the column list, the ``::double precision[]`` cast and the seven-parameter
  arity stood twice, once per writer, and no case held the pair;
* the import stored the embedding as the JSON file spells it, and the console
  stored a float32 view, cut to ``EMBEDDING_DIM`` and rounded to four decimals.
  For ``0.1234567890123456`` those are ``0.1234567890123456`` and ``0.1235``.

Round 74 gave the row one home.  ``src.store_import`` holds ``FACE_COLUMNS``,
``FACE_INSERT`` and ``face_row()``; the store imports all three.

This module holds that state in four ways, with no database:

1. one ``ast`` walk of ``src/**.py`` reports every module that spells an INSERT
   of the table and every name it binds that statement to;
2. one case counts the parameters of the one statement against
   ``FACE_COLUMNS``, so a column that moves cannot part from the arity;
3. one case proves the walk finds a copy: a planted statement in a source text
   is reported, so the walk cannot pass because it matches nothing;
4. one case names the two writers and reads their bodies, so the console
   writer cannot keep a second statement or a second embedding rule.

``tests/test_store_import.py`` reads the same names: it runs both writers on one
input with a recording connection and compares the bound values.  Those cases
need no PostgreSQL.

Run: ``./scripts/pool-test.sh python test_face_row_owner``
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

from src.store_import import FACE_COLUMNS, FACE_INSERT  # noqa: E402

#: The module that owns the row: the columns, the statement and the value rule.
OWNER = "src/store_import.py"
#: The module that appends to the same table and must read that owner.
READER = "src/store_pg.py"
#: The marker of one INSERT of the table, as it stands in a source text.
MARKER = "INSERT INTO face_embeddings"


def src_sources() -> list[Path]:
    """Every .py source of the shipped package ``src``, once each."""
    return [path for path in shipped_modules()
            if path.relative_to(ROOT).parts[0] == "src"]


def occurrences(text: str) -> list[tuple[str, str]]:
    """Each INSERT of the table in one source text: the name that text binds the
    statement to (``(inline)`` when it binds none) and the statement text.

    The statement is the string literal that names the table and the statement
    keyword.  A docstring is not a statement, so ``code_strings`` drops it."""
    tree = ast.parse(text)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    found = []
    for line, literal in code_strings(tree):
        if MARKER not in literal or "VALUES" not in literal:
            continue
        node = next((item for item in ast.walk(tree)
                     if isinstance(item, ast.Constant) and item.lineno == line
                     and item.value == literal), None)
        target = "(inline)"
        for parent in (parents.get(node), parents.get(parents.get(node))):
            if isinstance(parent, ast.Assign) and len(parent.targets) == 1 \
                    and isinstance(parent.targets[0], ast.Name):
                target = parent.targets[0].id
            elif isinstance(parent, ast.AnnAssign) and isinstance(parent.target, ast.Name):
                target = parent.target.id
        found.append((target, " ".join(literal.split())))
    return found


def scan(files) -> dict[str, list[tuple[str, str]]]:
    """Source path (from the repository root, when the file is inside it) -> the
    INSERTs it holds, for every file that holds one."""
    found = {}
    for path in files:
        hits = occurrences(path.read_text(encoding="utf-8"))
        if hits:
            try:
                key = path.relative_to(ROOT).as_posix()
            except ValueError:               # a planted file, outside the repository
                key = path.name
            found[key] = hits
    return found


def source_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def function_text(relative: str, name: str) -> str:
    """The source of one function or method, by name, and "" when it is absent."""
    text = source_text(relative)
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    return ""


class OneOwner(unittest.TestCase):
    """The row has one home and the second writer reads it."""

    def test_only_the_owner_spells_an_insert_of_the_table(self):
        found = scan(src_sources())
        self.assertEqual(list(found), [OWNER],
                         f"more than one module under src/ inserts into face_embeddings: "
                         f"{ {name: [t for t, _ in hits] for name, hits in found.items()} }")
        self.assertEqual([target for target, _ in found[OWNER]], ["FACE_INSERT"],
                         f"{OWNER} must bind the one statement to FACE_INSERT")
        self.assertEqual(found[OWNER][0][1], " ".join(FACE_INSERT.split()),
                         "the statement in the source text is not the one the module holds")

    def test_the_statement_names_every_column_and_binds_one_parameter_each(self):
        head = FACE_INSERT.split("VALUES")[0]
        between = head.split("(", 1)[1].rstrip(") ")
        named = [name.strip() for name in between.split(",")]
        self.assertEqual(tuple(named), ("player_id",) + FACE_COLUMNS,
                         "the statement's column list is not player_id plus FACE_COLUMNS")
        self.assertEqual(len(set(named)), len(named),
                         f"the one statement names a column twice: {named}")
        self.assertEqual(FACE_INSERT.count("%s"), len(FACE_COLUMNS) + 1,
                         "the parameter count and the column count disagree")
        self.assertEqual(FACE_INSERT.count("::double precision[]"), 1,
                         "the array column must carry one cast, and only the array column")

    def test_the_walk_reports_a_planted_name(self):
        """A copy that the owner does not bind to FACE_INSERT is reported by its own
        name.  The text of the planted statement is not the owner's text, so the
        walk must name the variable and not the statement."""
        planted = textwrap.dedent('''
            """A planted module, never imported."""
            FACE_INSERT_AGAIN = ("INSERT INTO face_embeddings (player_id, embedding)"
                                 " VALUES (%s, %s)")


            def write(conn):
                conn.execute(FACE_INSERT_AGAIN, ())
        ''')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "planted_name.py"
            path.write_text(planted, encoding="utf-8")
            found = scan([path])
        self.assertEqual(list(found), ["planted_name.py"],
                         "the walk did not report a planted statement")
        self.assertEqual(found["planted_name.py"][0][0], "FACE_INSERT_AGAIN",
                         "the walk did not report the name the copy binds")

    def test_the_walk_reports_a_planted_copy(self):
        planted = textwrap.dedent(f'''
            """A planted module, never imported."""
            def write(conn, row):
                conn.execute({FACE_INSERT!r}, ())
        ''')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "planted_copy.py"
            path.write_text(planted, encoding="utf-8")
            found = scan([path])
        self.assertEqual(list(found), ["planted_copy.py"],
                         "the walk did not report a planted copy of the statement")
        self.assertEqual(found["planted_copy.py"][0][0], "(inline)",
                         "the walk did not report the name the copy binds")

    def test_the_console_writer_reads_the_owner(self):
        text = source_text(READER)
        self.assertIn("FACE_INSERT", text, f"{READER} no longer executes the one statement")
        self.assertIn("face_row", text, f"{READER} no longer calls the one value rule")
        body = function_text(READER, "faces_add")
        self.assertTrue(body, "src/store_pg.py has no faces_add")
        for gone in ("INSERT INTO face_embeddings", "np.asarray", "round(float(v), 4)"):
            self.assertNotIn(gone, body,
                             f"faces_add holds its own copy again: {gone!r}")


if __name__ == "__main__":
    unittest.main()
