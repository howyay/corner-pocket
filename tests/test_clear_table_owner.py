"""The empty-the-table sentence has one home, ``src/store_import.py``.

Round 110 found three live writers of one SQL sentence, each spelling it again:

* ``src/store_import.py:173`` - ``DataSet.clear`` emptied ``self.tables`` in reverse;
* ``src/store_import.py:202`` - ``OperationsSet.clear`` emptied its own eight names;
* ``src/store_pg.py:158`` - ``PostgresStore._save`` emptied seven of those names
  before it rewrote the row projection.

Those are the lines of the round walk, at the state before this round.
``git grep -F 'DELETE FROM {table}' -- src annotator tools scripts`` answered those
three lines and nothing else, and every other ``DELETE FROM`` line of the shipped
tree carries a ``WHERE``: it empties a named subset, so it is another fact.  No
reader of the sentence lives in the tree.  The two store layers are its writers,
and the database is the reader.

The home is the helper ``src/store_import.py:148``::

    def clear_table(conn, table: str) -> None:
        ...
        conn.execute(f"DELETE FROM {table}")        # the pinned line 155

The helper sits beside ``_count``, the other SQL sentence of this module, and the
second writer already imports from ``src.store_import`` at the top of its own module
(``src/store_pg.py:48``), so the new name closes no cycle and needs no local import.
The table names stay at the three call sites: the helper carries the sentence, and
each set still states the tables it owns.

The change moves no value.  The three sites bind one statement before and after:
``clear_table`` executes the same text through the connection it is handed.

The cases below hold six things:

1. the home states the sentence once, on its pinned line, and the helper is defined
   once, on its own pinned line;
2. the helper runs that sentence through the connection it is given, with the table
   name of the call site: a recording connection keeps the statement;
3. the three call sites sit at their ``path:line`` and hold the call;
4. the live sites of the name are the pinned ones, so a moved or a fourth site fails;
5. the second writer imports the name at the top of its module and nowhere inside a
   function body;
6. a walk of ``src/``, ``tools/`` and ``scripts/`` reports a fourth spelling of the
   sentence as ``path:line`` with the text of that line, and a planted copy becomes
   an offender.

Run: ``./scripts/pool-test.sh python test_clear_table_owner``
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from _shipped import code_strings, shipped_modules  # noqa: E402

#: The home module, the helper that holds the sentence, and its two pinned lines:
#: the definition, and the sentence inside the body.
HOME = "src/store_import.py"
HOME_NAME = "clear_table"
DEF_LINE = 148
HOME_LINE = 155
#: The sentence, as the value of the f-string of the home line, and the text of that
#: line.  The guard spells the sentence once, so a case can pin it.
SENTENCE = "DELETE FROM {table}"
HOME_FORM = 'conn.execute(f"DELETE FROM {table}")'
#: The three call sites, as ``(path, line)``, and the text each one holds.
SITES = ((HOME, 183), (HOME, 212), ("src/store_pg.py", 158))
CALL_FORM = "clear_table(conn, table)"
#: Every live site of the helper name, as ``(line, kind)`` per module: the definition,
#: the import of the second writer, and each call.  A moved, a new or a lost site must
#: restate itself here.
NAME_SITES = {
    HOME: ((DEF_LINE, "def"), (183, "call"), (212, "call")),
    "src/store_pg.py": ((48, "import"), (158, "call")),
}
#: The second writer, its one import of the home and the module it takes it from.
READER = "src/store_pg.py"
IMPORT_LINE = 48
OWNER_MODULE = "src.store_import"
#: The three trees the anti-copy walk reads, and the floor that keeps a vacuous walk
#: from passing.
WALKED = ("src", "tools", "scripts")
FILE_FLOOR = 200
#: A sentence starts with DELETE FROM.  A WHERE makes the line another fact: it
#: empties a named subset, and the walk leaves it alone.
SENTENCE_RE = re.compile(r"\s*DELETE\s+FROM\b", re.IGNORECASE)
WHERE_RE = re.compile(r"\bWHERE\b", re.IGNORECASE)


def source_text(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def line_of(lines, number: int) -> str:
    """The text of one line, or the empty text when the number is outside the file."""
    return lines[number - 1] if 0 < number <= len(lines) else ""


def report(where: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return "%s:%d: %s  <- %s" % (where, line, (text or "").strip(), why)


def fstring_parts(tree: ast.AST) -> set:
    """``(line, text)`` of the constant pieces of every f-string of a tree.

    A piece is a part of a longer sentence, so the walk of the sentence skips it:
    ``f"DELETE FROM {table}"`` is one sentence on one line, not two.
    """
    return {(piece.lineno, piece.value) for node in ast.walk(tree)
            if isinstance(node, ast.JoinedStr) for piece in node.values
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str)}


def field_shape(node: ast.expr) -> str:
    """One format field of an f-string: its name when it is a plain name."""
    return "{%s}" % node.id if isinstance(node, ast.Name) else "{}"


def fstring_shape(node: ast.JoinedStr) -> str:
    """The text of an f-string, with the name of each plain format field."""
    return "".join(piece.value if isinstance(piece, ast.Constant) and isinstance(piece.value, str)
                   else field_shape(piece.value) for piece in node.values)


def bare_sentence(text: str) -> bool:
    """True when one literal text is the empty-the-table sentence."""
    return bool(SENTENCE_RE.match(text)) and not WHERE_RE.search(text)


def sentence_sites(text: str, where: str) -> list:
    """Every spelling of the sentence of one module, as ``(line, text)``.

    A docstring that quotes the sentence is no writer, so the plain literals come
    from ``_shipped.code_strings``.  An f-string is no ``ast.Constant``, so the walk
    reads the shape of each one and adds it: that is the shape of the home line.
    """
    tree = ast.parse(text, filename=where)
    parts = fstring_parts(tree)
    found = {(line, value) for line, value in code_strings(tree)
             if (line, value) not in parts and bare_sentence(value)}
    found.update((node.lineno, fstring_shape(node)) for node in ast.walk(tree)
                 if isinstance(node, ast.JoinedStr) and bare_sentence(fstring_shape(node)))
    return sorted(found)


def offences(relative: str, text: str, allowed_lines=()) -> list:
    """Every second spelling of the sentence of one module, as ``path:line``.

    A line of ``allowed_lines`` is the home of that file, so it may hold the
    sentence.  Every other spelling is a copy, and the answer names it.
    """
    lines = text.splitlines()
    found = []
    for number, sentence in sentence_sites(text, relative):
        if number in allowed_lines:
            continue
        text_of_line = line_of(lines, number)
        found.append(report(relative, number, text_of_line,
                            "%r is a second spelling of the sentence; %s of %s holds it"
                            % (sentence, HOME_NAME, HOME)))
    return found


def name_sites(text: str, where: str) -> list:
    """Every site of the home name of one module, as ``(line, kind)``.

    A site is the definition, an import of the name, a call of it, or any other read
    of the name.  A comment or a docstring that names it is no site.
    """
    tree = ast.parse(text, filename=where)
    callees = {id(node.func) for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == HOME_NAME}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == HOME_NAME:
            found.add((node.lineno, "def"))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == HOME_NAME:
                    found.add((getattr(alias, "lineno", node.lineno), "import"))
        elif isinstance(node, ast.Name) and node.id == HOME_NAME:
            if id(node) in callees:
                found.add((node.lineno, "call"))
            elif isinstance(node.ctx, ast.Load):
                found.add((node.lineno, "read"))
    return sorted(found)


def import_sites(text: str, where: str, module: str) -> list:
    """Every ``from module import ...`` of one module, as ``(line, at_top, names)``."""
    tree = ast.parse(text, filename=where)
    top = {id(node) for node in tree.body}
    return sorted((node.lineno, id(node) in top, tuple(alias.name for alias in node.names))
                  for node in ast.walk(tree)
                  if isinstance(node, ast.ImportFrom) and node.module == module)


def walked(prefixes) -> list:
    """Every shipped ``.py`` file of one set of trees, in the shared order."""
    return [path for path in shipped_modules()
            if path.relative_to(ROOT).parts[0] in prefixes]


def walk_offences(files) -> list:
    """Every second spelling of the sentence of one list of files, as ``path:line``."""
    offenders = []
    for path in files:
        try:
            relative = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            relative = path.name
        allowed = (HOME_LINE,) if relative == HOME else ()
        offenders.extend(offences(relative, path.read_text(encoding="utf-8"), allowed))
    return offenders


class RecordingConnection:
    """A connection double that keeps the one statement it is asked to run."""

    def __init__(self):
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        return None


class HomeTests(unittest.TestCase):
    """The home line, the helper line, and the statement the helper runs."""

    maxDiff = None

    def test_the_home_states_the_sentence_once(self):
        """The case that pins the home at ``path:line`` and its text.

        The offender text names the file, the line and the text of that line, so a
        moved or a changed home reads as ``path:line`` in the red text.
        """
        text = source_text(HOME)
        lines = source_lines(HOME)
        sites = sentence_sites(text, HOME)
        offenders = [report(HOME, number, line_of(lines, number),
                            "%r is a spelling of the sentence; the one home is line %d with %r"
                            % (sentence, HOME_LINE, SENTENCE))
                     for number, sentence in sites
                     if (number, sentence) != (HOME_LINE, SENTENCE)]
        if not sites:
            offenders.append(report(HOME, HOME_LINE, line_of(lines, HOME_LINE),
                                    "the home lost the sentence %r" % SENTENCE))
        self.assertEqual([], offenders,
                         "the home of the sentence is not %s:%d with the text %r:\n%s"
                         % (HOME, HOME_LINE, SENTENCE, "\n".join(offenders)))
        self.assertEqual(HOME_FORM, lines[HOME_LINE - 1].strip(),
                         report(HOME, HOME_LINE, line_of(lines, HOME_LINE),
                                "the home line is not %r" % HOME_FORM))

    def test_the_helper_is_defined_once_on_its_pinned_line(self):
        text = source_text(HOME)
        lines = source_lines(HOME)
        definitions = [(node.lineno, node.name) for node in ast.walk(ast.parse(text, filename=HOME))
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name == HOME_NAME]
        self.assertEqual([(DEF_LINE, HOME_NAME)], definitions,
                         "%s defines %s at %s, not once at line %d"
                         % (HOME, HOME_NAME, definitions, DEF_LINE))
        self.assertTrue(lines[DEF_LINE - 1].startswith("def %s(" % HOME_NAME),
                        report(HOME, DEF_LINE, lines[DEF_LINE - 1],
                               "the line does not define %s" % HOME_NAME))

    def test_the_helper_empties_the_named_table(self):
        """The home runs the sentence through the connection, with the caller's name.

        The table names stay at the call sites, so the case hands one name in and
        reads the statement the connection was asked to run.
        """
        from src.store_import import clear_table
        conn = RecordingConnection()
        clear_table(conn, "ops_meta")
        self.assertEqual([("DELETE FROM ops_meta", None)], conn.statements,
                         "%s did not run the sentence through the connection: %s"
                         % (HOME_NAME, conn.statements))
        self.assertEqual(SENTENCE, "DELETE FROM {table}",
                         "the guard and the sentence of the home drifted apart")


class WriterTests(unittest.TestCase):
    """The three call sites, the live sites of the name, and the reader's import."""

    maxDiff = None

    def test_the_three_call_sites_hold_the_call(self):
        offenders = []
        for relative, number in SITES:
            lines = source_lines(relative)
            text = line_of(lines, number)
            if CALL_FORM not in text:
                offenders.append(report(relative, number, text,
                                        "the site does not call %s" % HOME_NAME))
        self.assertEqual([], offenders,
                         "a writer spells the sentence again instead of calling the home:\n"
                         + "\n".join(offenders))

    def test_the_live_sites_of_the_name_are_the_pinned_ones(self):
        """Six sites in two files.  A move or a fourth site must state itself."""
        offenders = []
        for relative, pinned in sorted(NAME_SITES.items()):
            lines = source_lines(relative)
            found = name_sites(source_text(relative), relative)
            if sorted(pinned) != found:
                number = found[0][0] if found else 1
                offenders.append(report(relative, number, line_of(lines, number),
                                        "the live sites of %s are %s, not the pinned %s"
                                        % (HOME_NAME, found, sorted(pinned))))
        self.assertEqual([], offenders,
                         "the live sites of the home name moved:\n" + "\n".join(offenders))

    def test_the_second_writer_imports_the_home_at_the_top(self):
        """The store takes the name from the home, so no local import is needed."""
        found = [(line, at_top, names)
                 for line, at_top, names in import_sites(source_text(READER), READER, OWNER_MODULE)
                 if HOME_NAME in names]
        self.assertEqual(1, len(found),
                         "%s holds %d imports of %s from %s, not one"
                         % (READER, len(found), HOME_NAME, OWNER_MODULE))
        line, at_top, _names = found[0]
        text = source_lines(READER)[line - 1]
        self.assertTrue(at_top,
                        report(READER, line, text,
                               "the import of %s sits inside a call; the store reads the "
                               "name at the top of its module" % HOME_NAME))
        self.assertEqual(IMPORT_LINE, line,
                         report(READER, line, text,
                                "the import stood at line %d when the home landed; a move "
                                "must restate it here" % IMPORT_LINE))


class WalkTests(unittest.TestCase):
    """The anti-copy walk of the three trees, with its planted proofs."""

    maxDiff = None

    def test_no_shipped_file_spells_the_sentence_again(self):
        files = walked(WALKED)
        self.assertGreater(len(files), FILE_FLOOR,
                           "the walk read %d files; it is not the shipped tree" % len(files))
        offenders = walk_offences(files)
        self.assertEqual([], offenders,
                         "a second home of the sentence stands in the shipped tree:\n"
                         + "\n".join(offenders))

    def test_the_walk_reports_a_planted_copy(self):
        """A planted copy becomes an offender, named as ``path:line`` with its text."""
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted.py"
            planted.write_text('def wipe(conn, name):\n'
                               '    conn.execute(f"DELETE FROM {name}")\n',
                               encoding="utf-8")
            offenders = walk_offences([planted])
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("planted.py:2:"),
                        "the report does not name the file and the line: %s" % offenders[0])
        self.assertIn("DELETE FROM {name}", offenders[0])
        self.assertIn('f"DELETE FROM {name}"', offenders[0])

    def test_the_walk_reports_a_planted_hard_coded_table(self):
        """A copy that writes the table name down is a copy of the sentence too."""
        offenders = offences("src/planted.py",
                             'def wipe(conn):\n'
                             '    conn.execute("DELETE FROM ops_meta")\n')
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("src/planted.py:2:"), offenders[0])
        self.assertIn("DELETE FROM ops_meta", offenders[0])

    def test_the_walk_is_quiet_for_the_home_and_for_the_other_delete_facts(self):
        """The home line is the one home, and a DELETE with a WHERE is another fact."""
        self.assertEqual([], offences(HOME, source_text(HOME), (HOME_LINE,)),
                         "%s spells the sentence outside its home line" % HOME)
        quiet = ('def wipe(conn, pid):\n'
                 '    clear_table(conn, "ops_meta")\n'
                 '    conn.execute("DELETE FROM players WHERE id = %s", (pid,))\n')
        self.assertEqual([], offences("src/planted.py", quiet),
                         "a reader of the home, or a DELETE with a WHERE, was reported")


if __name__ == "__main__":
    unittest.main()
