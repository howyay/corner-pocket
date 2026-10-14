"""The pot coordinate key ``ball_table_mm`` has one home, and four sites read it.

The walk of round 107 found five live spellings of one key of a pot event:

* ``src/scan_events.py:373`` - the write of the served document;
* ``src/rebuild_events_v2.py:163`` - the first rebuild tool;
* ``src/rebuild_events_calibrated.py:140`` - the second rebuild tool;
* ``src/event_gates.py:180`` - the gate reads the row back;
* ``annotator/index.html:100`` - the pot line of the served page.

No case named the key.  ``git grep -F ball_table_mm -- tests/`` answered nothing,
so a rename of the served key stayed silent in every reader.

The home is ``src/scan_events.py:58``::

    BALL_TABLE_MM_KEY = "ball_table_mm"

The home sits in the writer, because that module writes the events document that
``annotator/server.py`` serves at ``/api/events``.  Every file of the row keeps the
value byte-identical: a document on disk already carries the old key, and a reader
must still find it.  One case reads the two shipped documents of ``out/scan30/``
and feeds their pot rows to the gate, so the old bytes prove the identity.

Weight.  The gate reads the home at the top of its module, and the home adds no
library: ``src/event_gates.py:99`` imports ``src.table_refine``, which answers
numpy and cv2 already, so a home in ``src/scan_events.py`` adds no heavy root.  A
case measures that answer in a fresh interpreter instead of asserting it.

The page.  ``annotator/index.html`` cannot read a python name, so it holds its own
line, ``annotator/index.html:78``, with the same value.  Two cases hold the two
lines equal: a value that moves in one file and not in the other reddens this
module, and the failure names ``path:line`` with the text of that line.

Every case reads its copy, and pins the NAME of the home, not only the value: the
import of each reader, the line of each site, and the run-time binding of the name.

Run: ``./scripts/pool-test.sh python test_pot_coordinate_key_owner``

Measured 2026-10-13, Python 3.14.6: the anti-copy walk reads 285 python files
under ``src/`` and ``annotator/``, and 14 pages of ``annotator/``, in about 3 s.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The shipped value of the key.  The guard spells it once, so a case can pin it.
SHIPPED_KEY = "ball_table_mm"
#: The home module, and the name it holds the key under.
HOME = "src/scan_events.py"
HOME_NAME = "BALL_TABLE_MM_KEY"
#: The line of the home statement, at the state the home landed in, and its text.
HOME_LINE = 58
HOME_FORM = '%s = "%s"' % (HOME_NAME, SHIPPED_KEY)
#: The line regex of the definition, for the case that pins the home line.
NAME_RE = re.compile(r"\s*%s\s*=" % HOME_NAME)
#: A module-level name in upper case, the shape of a constant of this house.
CONSTANT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: Every live site of the home name, as ``(line, kind)`` per module.  The kind is
#: ``home`` for the definition, ``import`` for the import of the home, ``dict``
#: for a key of a written row and ``get`` for a lookup that reads a row back.
#: A moved, a new or a lost site must restate itself here.
SITES = {
    HOME: ((58, "home"), (373, "dict")),
    "src/rebuild_events_v2.py": ((46, "import"), (164, "dict")),
    "src/rebuild_events_calibrated.py": ((27, "import"), (141, "dict")),
    "src/event_gates.py": ((99, "import"), (180, "get")),
}
#: The module each reader takes the home from.
IMPORTS = {
    "src/rebuild_events_v2.py": "src.scan_events",
    "src/rebuild_events_calibrated.py": "scan_events",
    "src/event_gates.py": "src.scan_events",
}
#: The pure reader, and the light import of its own module body that makes a heavy
#: home free: numpy and cv2 answer there already.
GATE = "src/event_gates.py"
HEAVY_HOST = "src.table_refine"
#: The served page, its own name for the key, and its two lines.
PAGE = "annotator/index.html"
PAGE_NAME = "BALL_TABLE_MM_KEY"
PAGE_KEY_LINE = 78
PAGE_KEY_FORM = 'const %s = "%s";' % (PAGE_NAME, SHIPPED_KEY)
PAGE_POT_LINE = 105
#: What the pot line must read, and the bare spelling it must not use again.
PAGE_POT_READS = ("e[%s][0]" % PAGE_NAME, "e[%s][1]" % PAGE_NAME)
PAGE_POT_BANNED = "e.%s" % SHIPPED_KEY
#: The directories the anti-copy walk reads.
PY_WALKED = ("src/**/*.py", "annotator/**/*.py")
PAGE_WALKED = ("annotator/**/*.html", "annotator/**/*.js", "annotator/**/*.css")
#: The floors that keep a vacuous walk from passing.
PY_FILE_FLOOR = 100
PAGE_FILE_FLOOR = 9
#: The probes of the two weight facts, run in a fresh interpreter of this venv.
BIND_PROBE = "import src.scan_events as module; print(module.%s)" % HOME_NAME
GATE_PROBE = "import sys, src.event_gates; print('numpy' in sys.modules, 'cv2' in sys.modules)"
HOST_PROBE = "import sys, %s; print('numpy' in sys.modules, 'cv2' in sys.modules)" % HEAVY_HOST
#: The two documents a shipped run wrote.  The new reader must still read the key
#: of their pot rows: they carry the bytes of the spelling before the home landed.
SERVED_DOCUMENTS = ("out/scan30/events_v2.json", "out/scan30/events-legacy.json")


def source_text(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(where: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return "%s:%d: %s  <- %s" % (where, line, (text or "").strip(), why)


def home_sites() -> list:
    """Every line of the home module that defines the name, with its number."""
    return [(number, text) for number, text in enumerate(source_lines(HOME), start=1)
            if NAME_RE.match(text)]


def home_value() -> str:
    """The value of the home constant, read from the syntax tree of the home.

    The read is a read of the shipped text and not of an import: the home module
    imports cv2, and this guard must not pull cv2 into its own process to answer a
    string.  Two cases prove the run-time binding with a fresh interpreter instead.
    """
    for node in ast.walk(ast.parse(source_text(HOME), filename=HOME)):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == HOME_NAME
                for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return ""


def name_sites(text: str, where: str) -> list:
    """Every site of one module that names the home, as ``(line, kind)``.

    A site of the home name is a definition, an import of the name, a dict key of
    a written row, or a lookup that reads a row back.  A comment that names the
    name is no site of it, so the walk is the honest count.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == HOME_NAME or alias.asname == HOME_NAME
                   for alias in node.names):
                found.append((node.lineno, "import"))
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == HOME_NAME
                   for target in node.targets):
                found.append((node.lineno, "home"))
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None and ast.unparse(key) == HOME_NAME:
                    found.append((key.lineno, "dict"))
        elif isinstance(node, ast.Call):
            if node.args and ast.unparse(node.args[0]) == HOME_NAME:
                found.append((node.args[0].lineno, "get"))
        elif isinstance(node, ast.Subscript):
            if ast.unparse(node.slice) == HOME_NAME:
                found.append((node.slice.lineno, "lookup"))
    return sorted(set(found))


def imported_names(text: str, where: str, module: str) -> list:
    """Every local name one module imports from another, as ``(line, name)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                if alias.name == HOME_NAME:
                    found.append((node.lineno, alias.asname or alias.name))
    return sorted(found)


def body_imports(text: str, where: str, module: str) -> list:
    """Every module-level import of one module, as a line number."""
    tree = ast.parse(text, filename=where)
    return sorted(node.lineno for node in tree.body
                  if isinstance(node, ast.ImportFrom) and node.module == module)


def imported_roots(text: str, where: str, body_only: bool = False) -> set:
    """The top-level package of every import of one module."""
    tree = ast.parse(text, filename=where)
    roots = set()
    for node in (tree.body if body_only else ast.walk(tree)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def quoted_offences(relative: str, text: str, allowed_lines=()) -> list:
    """Every line of a file that spells the key as a quoted literal.

    A line of ``allowed_lines`` is the one home of that file, so it may spell the
    key.  Every other line that spells it is a copy, and the answer names it.
    """
    offenders = []
    for number, line in enumerate(text.splitlines(), start=1):
        if number in allowed_lines:
            continue
        if '"%s"' % SHIPPED_KEY in line or "'%s'" % SHIPPED_KEY in line:
            offenders.append(report(relative, number, line,
                                    "%r is a bare copy of the key; read %s of %s"
                                    % (SHIPPED_KEY, HOME_NAME, HOME)))
    return offenders


def page_sites(text: str) -> tuple:
    """The key line and the pot line of a page, as ``(number, line)`` each."""
    key_site = (0, "")
    pot_site = (0, "")
    for number, line in enumerate(text.splitlines(), start=1):
        if "const %s" % PAGE_NAME in line and not key_site[0]:
            key_site = (number, line)
        if "ball potted near" in line and not pot_site[0]:
            pot_site = (number, line)
    return key_site, pot_site


def page_offences(relative: str, text: str, key_line: int, key: str) -> list:
    """The copies of the key of a page, and the value of its key line.

    The page holds the key twice: the constant of its own line, and the pot line
    that reads the constant.  A quoted spelling on any other line is a copy.  The
    key line must carry the value of the home, so a drift on either side reddens.
    """
    offenders = []
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        if number == key_line:
            continue
        if '"%s"' % key in line or "'%s'" % key in line:
            offenders.append(report(relative, number, line,
                                    "%r is a second spelling of the key; the page "
                                    "reads %s of line %d" % (key, PAGE_NAME, key_line)))
    if key_line < 1 or key_line > len(lines):
        offenders.append(report(relative, key_line, "", "the page holds no key line"))
        return offenders
    line = lines[key_line - 1]
    if '"%s"' % key not in line:
        offenders.append(report(relative, key_line, line,
                                "the key line does not hold the key of the home, %r"
                                % key))
    return offenders


def walked(patterns) -> list:
    """Every file of one set of patterns, without the caches."""
    files = []
    for pattern in patterns:
        files.extend(sorted(ROOT.glob(pattern)))
    return [path for path in files if "__pycache__" not in path.parts]


def shipped_documents() -> list:
    """Every served document on disk, as ``(path, rows)``.

    The rows answer the pot rows of a shipped run, so the case that reads them
    proves the identity of the key against bytes and not against source text.
    """
    found = []
    for relative in SERVED_DOCUMENTS:
        path = ROOT / relative
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else (data.get("events") or [])
        found.append((relative, rows))
    return found


def run_probe(code: str) -> str:
    """The stdout of one probe, run in a fresh interpreter of this venv."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise AssertionError("the probe %r failed:\n%s" % (code, done.stderr))
    return done.stdout.strip()


class HomeTests(unittest.TestCase):
    """The home name, its value, its line and its run-time binding."""

    def test_the_home_names_the_shipped_key(self):
        self.assertEqual(SHIPPED_KEY, home_value(),
                         "%s:%s moved; the page and the four sites must move with it"
                         % (HOME, HOME_NAME))

    def test_the_home_line_of_the_module_carries_the_shipped_key(self):
        """The case that pins the home at ``path:line``."""
        sites = home_sites()
        self.assertEqual(1, len(sites),
                         "%s holds %d definitions of %s: %s"
                         % (HOME, len(sites), HOME_NAME, [site[0] for site in sites]))
        number, text = sites[0]
        self.assertIn(HOME_FORM, text,
                      report(HOME, number, text,
                             "the line does not assign %r to %s"
                             % (SHIPPED_KEY, HOME_NAME)))
        self.assertEqual(HOME_LINE, number,
                         report(HOME, number, text,
                                "%s stood at line %d when the home landed; a move "
                                "must restate it in the report" % (HOME_NAME, HOME_LINE)))

    def test_the_home_binds_the_name_at_run_time(self):
        """The shipped module answers the value when a reader imports it."""
        self.assertEqual(SHIPPED_KEY, run_probe(BIND_PROBE),
                         "%s does not answer %s when a reader imports it"
                         % (HOME, HOME_NAME))

    def test_the_home_name_can_be_the_key_of_a_row(self):
        """The name of a constant is the key of a JSON row, so it is an identifier."""
        self.assertTrue(CONSTANT_NAME_RE.match(HOME_NAME),
                        "%s is not the name of a constant" % HOME_NAME)
        self.assertTrue(home_value().isidentifier(),
                        "%r is not a valid key of a JSON row" % home_value())


class ReaderTests(unittest.TestCase):
    """The two rebuild tools and the gate read the name of the home."""

    def test_every_reader_imports_the_home(self):
        """Every reader takes the name from the home, at the top of its module."""
        offenders = []
        for relative, module in sorted(IMPORTS.items()):
            lines = source_lines(relative)
            text = source_text(relative)
            found = imported_names(text, relative, module)
            if not found:
                offenders.append(report(relative, 1, lines[0],
                                        "the file imports no %s from %s"
                                        % (HOME_NAME, module)))
                continue
            for number, name in found:
                if name != HOME_NAME:
                    offenders.append(report(relative, number, lines[number - 1],
                                            "the import is named %s, not %s"
                                            % (name, HOME_NAME)))
            if not body_imports(text, relative, module):
                offenders.append(report(relative, found[0][0], lines[found[0][0] - 1],
                                        "the import of %s sits inside a call, not at "
                                        "the top of the module" % module))
        self.assertEqual([], offenders,
                         "a reader does not import the home:\n" + "\n".join(offenders))

    def test_every_reader_reads_the_key_through_the_home(self):
        """Every site that reads or writes the key names the home."""
        offenders = []
        for relative in sorted(SITES):
            lines = source_lines(relative)
            for number, kind in SITES[relative]:
                if kind not in ("dict", "get", "lookup"):
                    continue
                if HOME_NAME not in lines[number - 1]:
                    offenders.append(report(relative, number, lines[number - 1],
                                            "the site does not read %s of %s"
                                            % (HOME_NAME, HOME)))
        self.assertEqual([], offenders,
                         "a site of the key does not read the home:\n"
                         + "\n".join(offenders))

    def test_the_live_sites_are_the_ones_the_report_names(self):
        """Eight sites in four files.  A move or a new site must state itself."""
        offenders = []
        for relative, pinned in sorted(SITES.items()):
            lines = source_lines(relative)
            found = name_sites(source_text(relative), relative)
            if sorted(pinned) != found:
                number = found[0][0] if found else 1
                offenders.append(report(relative, number, lines[number - 1],
                                        "the live sites are %s, not the pinned %s"
                                        % (found, sorted(pinned))))
        self.assertEqual([], offenders,
                         "the live sites of the key moved:\n" + "\n".join(offenders))

    def test_the_gate_reads_the_row_key_of_the_home(self):
        """The gate reads a pot row whose key is the value of the home.

        The row carries the value and not the name, because the document on disk
        carries the value.  A row whose key is the name of the home answers None,
        and a reader of this case sees which of the two the gate reads.
        """
        from src.event_gates import normalize
        coordinate = [1200.0, 800.0]
        row = {"type": "pot", home_value(): coordinate, "window_s": [1.0, 2.0]}
        self.assertEqual(coordinate, normalize(row)["last_mm"],
                         "%s does not read the row key %s" % (GATE, home_value()))
        self.assertIsNone(normalize({"type": "pot", HOME_NAME: coordinate})["last_mm"],
                          "%s reads the name %s instead of the value %s"
                          % (GATE, HOME_NAME, home_value()))

    def test_the_home_adds_no_library_to_the_gate(self):
        """Why the home may sit in the writer: the gate is heavy already.

        The answer is measured in two fresh interpreters, one for the gate and one
        for the light import of its own body that brings the heavy pair in.  A
        reader of this case sees the reason, and not only the claim.
        """
        self.assertEqual("True True", run_probe(GATE_PROBE),
                         "the import of %s answers %r, and this case states the "
                         "weight argument of the home"
                         % (GATE, run_probe(GATE_PROBE)))
        self.assertEqual("True True", run_probe(HOST_PROBE),
                         "the import of %s answers %r; the argument of the home is "
                         "that this module brings numpy and cv2 into the gate"
                         % (HEAVY_HOST, run_probe(HOST_PROBE)))
        roots = imported_roots(source_text(GATE), GATE, body_only=True)
        heavy = sorted(roots & {"numpy", "cv2", "torch"})
        self.assertEqual([], heavy,
                         "%s spells %s in a top-level import; the weight argument "
                         "reads the hosts of the heavy pair" % (GATE, heavy))

    def test_the_shipped_documents_still_answer_the_reader(self):
        """The documents on disk carry the old spelling, and the gate still reads.

        This case reads the artifacts of a shipped run, so the identity of the key
        is measured against bytes on disk and not against the text of the source.
        """
        from src.event_gates import normalize
        documents = shipped_documents()
        self.assertTrue(documents,
                        "no served document of %s is on disk" % (SERVED_DOCUMENTS,))
        rows_read = 0
        for relative, rows in documents:
            pot_rows = [row for row in rows
                        if isinstance(row, dict) and SHIPPED_KEY in row]
            self.assertTrue(pot_rows, "%s carries no pot row of %r" % (relative, SHIPPED_KEY))
            for row in pot_rows:
                rows_read += 1
                expected = row.get("last_mm") or row[SHIPPED_KEY]
                self.assertEqual(expected, normalize(row)["last_mm"],
                                 "%s does not read the pot key of %s"
                                 % (GATE, relative))
        self.assertGreater(rows_read, 5,
                           "the case read %d pot rows; it is not the shipped set"
                           % rows_read)


class PageTests(unittest.TestCase):
    """The page holds the key of the home, and the pot line reads the page name."""

    def test_the_page_holds_the_key_of_the_home(self):
        text = source_text(PAGE)
        (number, line), _pot = page_sites(text)
        self.assertEqual(PAGE_KEY_LINE, number,
                         report(PAGE, number or 1, line,
                                "the key line stood at %d when the page landed; a "
                                "move must restate it here" % PAGE_KEY_LINE))
        self.assertEqual(PAGE_KEY_FORM, line.strip(),
                         report(PAGE, number, line,
                                "the key line is not %r" % PAGE_KEY_FORM))
        self.assertEqual([], page_offences(PAGE, text, number, home_value()),
                         "the page holds a second spelling of the key")

    def test_the_pot_line_reads_the_page_name(self):
        text = source_text(PAGE)
        _key, (number, line) = page_sites(text)
        self.assertEqual(PAGE_POT_LINE, number,
                         report(PAGE, number or 1, line,
                                "the pot line stood at %d when the page landed; a "
                                "move must restate it here" % PAGE_POT_LINE))
        for read in PAGE_POT_READS:
            self.assertIn(read, line,
                          report(PAGE, number, line,
                                 "the pot line does not read %s" % read))
        self.assertNotIn(PAGE_POT_BANNED, line,
                         report(PAGE, number, line,
                                "the pot line spells %s instead of %s"
                                % (PAGE_POT_BANNED, PAGE_NAME)))

    def test_the_page_bites_when_the_key_moves(self):
        """A page whose key line drifted is reported as ``path:line: <text>``."""
        text = source_text(PAGE)
        drifted = text.replace('const %s = "%s";' % (PAGE_NAME, SHIPPED_KEY),
                               'const %s = "ball_table_mm_x";' % PAGE_NAME, 1)
        self.assertNotEqual(text, drifted, "the planted drift changed nothing")
        offenders = page_offences(PAGE, drifted, PAGE_KEY_LINE, home_value())
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("%s:%d:" % (PAGE, PAGE_KEY_LINE), offenders[0])
        self.assertIn("ball_table_mm_x", offenders[0])

    def test_no_other_page_spells_the_key_again(self):
        offenders = []
        pages = walked(PAGE_WALKED)
        for path in pages:
            relative = path.relative_to(ROOT).as_posix()
            allowed = (PAGE_KEY_LINE,) if relative == PAGE else ()
            offenders.extend(quoted_offences(relative, path.read_text(encoding="utf-8"),
                                             allowed))
        self.assertGreater(len(pages), PAGE_FILE_FLOOR,
                           "the walk read %d pages; it is not the served tree"
                           % len(pages))
        self.assertEqual([], offenders,
                         "a page of the served tree spells the key again:\n"
                         + "\n".join(offenders))


class WalkTests(unittest.TestCase):
    """The anti-copy walk of the python tree, with its planted proofs."""

    def test_no_python_file_spells_the_key_again(self):
        offenders = []
        files = walked(PY_WALKED)
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            allowed = (HOME_LINE,) if relative == HOME else ()
            offenders.extend(quoted_offences(relative, path.read_text(encoding="utf-8"),
                                             allowed))
        self.assertGreater(len(files), PY_FILE_FLOOR,
                           "the walk read %d files; it is not the tree" % len(files))
        self.assertEqual([], offenders,
                         "a second home of the key stands in the source tree:\n"
                         + "\n".join(offenders))

    def test_the_walk_reports_a_planted_copy(self):
        planted = ('def pot_row(ball):\n'
                   '    return {"ball_table_mm": ball["table_mm"]}\n')
        offenders = quoted_offences("src/planted.py", planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("src/planted.py:2:", offenders[0])
        self.assertIn("ball_table_mm", offenders[0])
        self.assertIn('ball["table_mm"]', offenders[0])

    def test_the_walk_accepts_the_home_spelling(self):
        planted = ('def pot_row(ball):\n'
                   '    return {BALL_TABLE_MM_KEY: ball["table_mm"]}\n')
        self.assertEqual([], quoted_offences("src/planted.py", planted),
                         "the home spelling counts as a bare literal")
        self.assertEqual([(2, "dict")], name_sites(planted, "src/planted.py"))


if __name__ == "__main__":
    unittest.main()
