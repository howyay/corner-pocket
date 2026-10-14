"""The pot pocket keys ``nearest_pocket`` and ``pocket_dist_mm`` have one home.

The walk of round 109 found twelve live spellings of two keys of a served pot
event, and no case named either of them:

* ``src/scan_events.py`` - the write of the served document (:366 and :367 before
  the home landed);
* ``src/rebuild_events_v2.py`` - the first rebuild tool;
* ``src/rebuild_events_calibrated.py`` - the second rebuild tool;
* ``src/candidate_scan.py`` - the served candidate dict of the census scanner;
* ``src/dense_queue.py`` - the pot row of the dense queue;
* ``src/eval_events.py`` - the queue event of the eval tool;
* ``src/event_gates.py`` - the gate reads ``nearest_pocket`` back from the row;
* ``src/shot_pot_gate.py`` - four rejection reports of the gate;
* ``annotator/index.html`` - the pot line of the served page.

A rename of either key used to stay silent in every reader.  ``git grep -F
pocket_dist_mm -- tests/`` answered four literals of a *candidate* dict and no
case of the served key.

The two homes stand beside ``BALL_TABLE_MM_KEY`` in ``src/scan_events.py``::

    NEAREST_POCKET_KEY = "nearest_pocket"
    POCKET_DIST_MM_KEY = "pocket_dist_mm"

The homes sit in the writer, because that module writes the events document that
``annotator/server.py`` serves at ``/api/events``.  Every file of a row keeps the
value byte-identical: a document on disk already carries both keys, and a reader
must still find them.

The page and the two client scripts.  ``annotator/index.html`` cannot read a
python name, so it holds its own two lines, ``annotator/index.html:87`` and
``:83``, with the same values, and the pot line reads them.  The other client
readers spell the key as an object property (``event.nearest_pocket``), which a
constant cannot replace, so the cases below pin the line of each one and the
property it reads: a renamed key must move those lines too.

Weight.  ``src/dense_queue.py`` reads the home at the top of its module and adds
no heavy root: ``src/scan_events.py`` imports cv2 through ``src.datasets``, which
``src/dense_queue.py`` imports already.  A case measures that answer in a fresh
interpreter instead of asserting it.

Every case reads its copy, and pins the NAME of a home, not only the value: the
import of each writer, the line of each site, and the run-time binding of both
names.

Run: ``./scripts/pool-test.sh python test_pocket_dist_key_owner``

Measured 2026-10-14, Python 3.14.6: the anti-copy walk reads 285 python files
under ``src/`` and ``annotator/``, and 14 pages of ``annotator/``, in about 2 s.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The two shipped values of the two keys.  The guard spells each one once, so a
#: case can pin it.
SHIPPED_KEYS = {"NEAREST_POCKET_KEY": "nearest_pocket",
                "POCKET_DIST_MM_KEY": "pocket_dist_mm"}
#: The home module, and the name of each home.
HOME = "src/scan_events.py"
HOME_NAMES = tuple(sorted(SHIPPED_KEYS))
#: The line of each home statement, at the state the homes landed in.
HOME_LINES = {"NEAREST_POCKET_KEY": 65, "POCKET_DIST_MM_KEY": 66}
#: The line regex of a definition, for the case that pins a home line.
NAME_RE = r"\s*%s\s*="
#: A module-level name in upper case, the shape of a constant of this house.
CONSTANT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: Every live site of a home name, as ``(line, kind)`` per module.  The kind is
#: ``home`` for the definition, ``import`` for the import of a home, ``dict`` for
#: a key of a written row, and ``get`` for a lookup that reads a row back.  A
#: moved, a new or a lost site must restate itself here.
SITES = {
    HOME: ((65, "home"), (66, "home"), (374, "dict"), (375, "dict")),
    "src/rebuild_events_v2.py": ((46, "import"), (46, "import"), (164, "dict"),
                                 (165, "dict"), (197, "lookup")),
    "src/rebuild_events_calibrated.py": ((27, "import"), (27, "import"), (141, "dict"),
                                         (142, "dict")),
    "src/candidate_scan.py": ((59, "import"), (59, "import"), (330, "dict"),
                              (437, "get"), (438, "lookup")),
    "src/dense_queue.py": ((80, "import"), (80, "import"), (329, "dict")),
    "src/eval_events.py": ((862, "import"), (862, "import"), (864, "get"),
                           (1018, "get")),
    "src/event_gates.py": ((99, "import"), (99, "import"), (186, "get")),
    "src/shot_pot_gate.py": ((90, "import"), (1407, "dict"), (1566, "dict"),
                             (1581, "dict"), (1598, "dict")),
    "annotator/unified_server.py": ((469, "import"), (1738, "import"), (1739, "get")),
}
#: The module each writer takes the home names from.  A name of a row that one
#: site needs may sit on the import line of another name of the same row.  The
#: value is the module, the names the writer must hold, and ``True`` when the
#: import must stand at the top of the module body.  ``src/eval_events.py`` reads
#: the home inside its own function instead, because it is the heavier end of the
#: pair and needs the name at one site only.  The site walk holds that read.
IMPORTS = {
    "src/rebuild_events_v2.py": ("src.scan_events", HOME_NAMES, True),
    "src/rebuild_events_calibrated.py": ("scan_events", HOME_NAMES, True),
    "src/candidate_scan.py": ("src.scan_events", HOME_NAMES, True),
    "src/dense_queue.py": ("src.scan_events", HOME_NAMES, True),
    "src/eval_events.py": ("src.scan_events", ("NEAREST_POCKET_KEY",), False),
    "src/event_gates.py": ("src.scan_events", ("NEAREST_POCKET_KEY",), True),
    "src/shot_pot_gate.py": ("src.scan_events", ("NEAREST_POCKET_KEY",), True),
}
#: The module that reads the home at the top of its body, and the heavy roots it
#: must not gain.  The argument of the home: this reader is light already.
TOP_READER = "src/dense_queue.py"
TOP_READER_PROBE = ("import sys, %s; print('cv2' in sys.modules, 'torch' in sys.modules)"
                    % TOP_READER[:-3].replace("/", "."))
#: The names the home module answers at run time, in a fresh interpreter.
BIND_PROBE = "; ".join("import src.scan_events as module; print(module.%s)" % name
                       for name in HOME_NAMES)
#: The served page, its own two lines, and the pot line that reads them.
PAGE = "annotator/index.html"
PAGE_LINES = {"POCKET_DIST_MM_KEY": 82, "NEAREST_POCKET_KEY": 83}
PAGE_POT_LINE = 105
PAGE_POT_READS = ("e[%s]" % "POCKET_DIST_MM_KEY", "e[%s]" % "NEAREST_POCKET_KEY")
#: The bare spellings the pot line must not use again.
PAGE_POT_BANNED = ("e.pocket_dist_mm", "e.nearest_pocket")
#: The client readers that cannot import python.  Each row is the file, the line,
#: and the property the line reads.  A renamed key must move these lines too.
JS_READERS = (
    ("annotator/app.js", 1048, "event.nearest_pocket"),
    ("annotator/app.js", 1263, "event.nearest_pocket"),
    ("annotator/app.js", 2000, "e.nearest_pocket"),
    ("annotator/vision-stage.js", 402, "event?.nearest_pocket"),
)
#: The directories the anti-copy walk reads.
PY_WALKED = ("src/**/*.py", "annotator/**/*.py")
PAGE_WALKED = ("annotator/**/*.html", "annotator/**/*.js", "annotator/**/*.css")
#: The floors that keep a vacuous walk from passing.
PY_FILE_FLOOR = 100
PAGE_FILE_FLOOR = 9


def source_text(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(where: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return "%s:%d: %s  <- %s" % (where, line, (text or "").strip(), why)


def home_sites(name: str) -> list:
    """Every line of the home module that defines one home, with its number."""
    regex = re.compile(NAME_RE % name)
    return [(number, text) for number, text in enumerate(source_lines(HOME), start=1)
            if regex.match(text)]


def home_value(name: str) -> str:
    """The value of one home constant, read from the syntax tree of the home.

    The read is a read of the shipped text and not of an import: the home module
    imports cv2, and this guard must not pull cv2 into its own process to answer
    a string.  A case proves the run-time binding with a fresh interpreter.
    """
    for node in ast.walk(ast.parse(source_text(HOME), filename=HOME)):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return ""


def imported_names(text: str, where: str, module: str) -> list:
    """Every home name one module imports from another, as ``(line, name)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                if alias.name in SHIPPED_KEYS:
                    found.append((node.lineno, alias.name))
    return sorted(found)


def body_imports(text: str, where: str, module: str) -> list:
    """Every module-level import of one module, as a line number."""
    tree = ast.parse(text, filename=where)
    return sorted(node.lineno for node in tree.body
                  if isinstance(node, ast.ImportFrom) and node.module == module)


def name_sites(text: str, where: str) -> list:
    """Every site of either home name of one module, as ``(line, kind)``.

    A site is a definition, an import of a home name, a dict key of a written
    row, a lookup that reads a row back, or a subscript of a row.  A name the
    import line holds twice answers the line twice, because the answer counts the
    names and not the lines.  A comment or a docstring that names a home is no
    site of it, so the walk is the honest count.
    """
    names = set(HOME_NAMES)
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom):
            found.extend((node.lineno, "import") for alias in node.names
                         if alias.name in names)
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id in names
                   for target in node.targets):
                found.append((node.lineno, "home"))
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None and ast.unparse(key) in names:
                    found.append((key.lineno, "dict"))
        elif isinstance(node, ast.Call):
            if node.args and ast.unparse(node.args[0]) in names:
                found.append((node.args[0].lineno, "get"))
        elif isinstance(node, ast.Subscript):
            if ast.unparse(node.slice) in names:
                found.append((node.slice.lineno, "lookup"))
    return sorted(found)


def quoted_offences(relative: str, text: str, allowed_lines=()) -> list:
    """Every line of a file that spells a key as a quoted literal.

    A line of ``allowed_lines`` is the one home of that file, so it may spell the
    key.  Every other line that spells it is a copy, and the answer names it.
    """
    offenders = []
    patterns = ['"%s"' % key for key in SHIPPED_KEYS.values()]
    patterns += ["'%s'" % key for key in SHIPPED_KEYS.values()]
    for number, line in enumerate(text.splitlines(), start=1):
        if number in allowed_lines:
            continue
        for pattern in patterns:
            if pattern in line:
                offenders.append(report(relative, number, line,
                                        "%s is a bare copy of a key of %s; read the home "
                                        "name" % (pattern, HOME)))
    return offenders


def walked(patterns) -> list:
    """Every file of one set of patterns, without the caches."""
    files = []
    for pattern in patterns:
        files.extend(sorted(ROOT.glob(pattern)))
    return [path for path in files if "__pycache__" not in path.parts]


def run_probe(code: str) -> str:
    """The stdout of one probe, run in a fresh interpreter of this venv."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise AssertionError("the probe %r failed:\n%s" % (code, done.stderr))
    return done.stdout.strip()


class HomeTests(unittest.TestCase):
    """The two home names, their values, their lines and their binding."""

    def test_each_home_names_the_shipped_key(self):
        offenders = []
        for name in HOME_NAMES:
            if SHIPPED_KEYS[name] != home_value(name):
                offenders.append("%s:%s answers %r, not %r"
                                 % (HOME, name, home_value(name), SHIPPED_KEYS[name]))
        self.assertEqual([], offenders,
                         "a home value moved; the page and the readers must move with "
                         "it:\n" + "\n".join(offenders))

    def test_the_home_line_of_the_module_carries_the_shipped_key(self):
        """The case that pins each home at ``path:line``."""
        lines = source_lines(HOME)
        for name in HOME_NAMES:
            form = '%s = "%s"' % (name, SHIPPED_KEYS[name])
            sites = home_sites(name)
            self.assertEqual(1, len(sites),
                             "%s holds %d definitions of %s: %s"
                             % (HOME, len(sites), name, [site[0] for site in sites]))
            number, text = sites[0]
            self.assertIn(form, text,
                          report(HOME, number, text,
                                 "the line does not assign %r to %s"
                                 % (SHIPPED_KEYS[name], name)))
            self.assertEqual(HOME_LINES[name], number,
                             report(HOME, number, text,
                                    "%s stood at line %d when the home landed; a move "
                                    "must restate it in the report"
                                    % (name, HOME_LINES[name])))
            self.assertEqual(form, lines[HOME_LINES[name] - 1].strip(),
                             report(HOME, HOME_LINES[name], lines[HOME_LINES[name] - 1],
                                    "the home line is not %r" % form))

    def test_the_homes_bind_both_names_at_run_time(self):
        """The shipped module answers both values when a reader imports it."""
        self.assertEqual("\n".join(SHIPPED_KEYS[name] for name in HOME_NAMES),
                         run_probe(BIND_PROBE),
                         "%s does not answer both home names when a reader imports it"
                         % HOME)

    def test_the_home_names_can_be_the_keys_of_a_row(self):
        """The name of a constant is the key of a JSON row, so it is an identifier."""
        for name in HOME_NAMES:
            self.assertTrue(CONSTANT_NAME_RE.match(name),
                            "%s is not the name of a constant" % name)
            self.assertTrue(home_value(name).isidentifier(),
                            "%r is not a valid key of a JSON row" % home_value(name))


class ReaderTests(unittest.TestCase):
    """Every python writer of the two keys reads the home names."""

    def test_every_writer_imports_the_home(self):
        """Every writer takes each name it needs from the home of the two keys."""
        offenders = []
        for relative, (module, names, at_top) in sorted(IMPORTS.items()):
            lines = source_lines(relative)
            text = source_text(relative)
            found = imported_names(text, relative, module)
            for name in names:
                at = [number for number, written in found if written == name]
                if not at:
                    offenders.append(report(relative, 1, lines[0],
                                            "the file imports no %s from %s"
                                            % (name, module)))
                    continue
                if at_top and not body_imports(text, relative, module):
                    offenders.append(report(relative, at[0], lines[at[0] - 1],
                                            "the import of %s sits inside a call, not at "
                                            "the top of the module" % module))
        self.assertEqual([], offenders,
                         "a writer does not import the home:\n" + "\n".join(offenders))

    def test_every_site_reads_the_key_through_a_home(self):
        """Every site that reads or writes a key names a home constant."""
        offenders = []
        for relative in sorted(SITES):
            lines = source_lines(relative)
            for number, kind in SITES[relative]:
                if kind == "home":
                    continue
                line = lines[number - 1]
                if not any(name in line for name in HOME_NAMES):
                    offenders.append(report(relative, number, line,
                                            "the site does not read the home of %s"
                                            % HOME))
        self.assertEqual([], offenders,
                         "a site of a key does not read the home:\n" + "\n".join(offenders))

    def test_the_live_sites_are_the_ones_the_report_names(self):
        """Sixteen sites in eight files.  A move or a new site must state itself."""
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
                         "the live sites of a key moved:\n" + "\n".join(offenders))

    def test_the_dense_queue_reads_the_home_without_a_heavy_root(self):
        """Why the home may sit in the writer: this reader stays light.

        The answer is measured in a fresh interpreter rather than asserted.  The
        home module imports cv2 through src.datasets, and this writer imports that
        module already, so the home adds no new root to it.
        """
        self.assertEqual("True False", run_probe(TOP_READER_PROBE),
                         "the import of %s answers %r; the weight argument of the "
                         "home reads this module"
                         % (TOP_READER, run_probe(TOP_READER_PROBE)))


class PageTests(unittest.TestCase):
    """The page holds both keys, and the pot line reads the page names."""

    def test_the_page_holds_the_keys_of_the_home(self):
        lines = source_lines(PAGE)
        for name in HOME_NAMES:
            form = 'const %s = "%s";' % (name, SHIPPED_KEYS[name])
            number = PAGE_LINES[name]
            self.assertEqual(form, lines[number - 1].strip(),
                             report(PAGE, number, lines[number - 1],
                                    "the key line is not %r" % form))
        offenders = quoted_offences(PAGE, source_text(PAGE),
                                    allowed_lines=tuple(PAGE_LINES.values()))
        self.assertEqual([], offenders,
                         "the page holds a second spelling of a key:\n"
                         + "\n".join(offenders))

    def test_the_pot_line_reads_the_page_names(self):
        lines = source_lines(PAGE)
        line = lines[PAGE_POT_LINE - 1]
        offenders = []
        for read in PAGE_POT_READS:
            if read not in line:
                offenders.append(report(PAGE, PAGE_POT_LINE, line,
                                        "the pot line does not read %s" % read))
        for banned in PAGE_POT_BANNED:
            if banned in line:
                offenders.append(report(PAGE, PAGE_POT_LINE, line,
                                        "the pot line spells %s instead of the page "
                                        "name" % banned))
        self.assertEqual([], offenders,
                         "the pot line of the page does not read the page names:\n"
                         + "\n".join(offenders))

    def test_a_client_reader_names_the_property_of_the_key(self):
        """The four client readers spell the key as a property, line by line."""
        offenders = []
        for relative, number, reading in JS_READERS:
            lines = source_lines(relative)
            if number > len(lines):
                offenders.append(report(relative, number, "",
                                        "the file holds no line %d" % number))
                continue
            line = lines[number - 1]
            if reading not in line:
                offenders.append(report(relative, number, line,
                                        "the line does not read %s" % reading))
        self.assertEqual([], offenders,
                         "a client reader moved:\n" + "\n".join(offenders))

    def test_no_other_page_spells_a_key_again(self):
        offenders = []
        pages = walked(PAGE_WALKED)
        for path in pages:
            relative = path.relative_to(ROOT).as_posix()
            allowed = tuple(PAGE_LINES.values()) if relative == PAGE else ()
            offenders.extend(quoted_offences(relative, path.read_text(encoding="utf-8"),
                                             allowed))
        self.assertGreater(len(pages), PAGE_FILE_FLOOR,
                           "the walk read %d pages; it is not the served tree"
                           % len(pages))
        self.assertEqual([], offenders,
                         "a page of the served tree spells a key again:\n"
                         + "\n".join(offenders))


class WalkTests(unittest.TestCase):
    """The anti-copy walk of the python tree, with its planted proofs."""

    def test_no_python_file_spells_a_key_again(self):
        offenders = []
        files = walked(PY_WALKED)
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            allowed = tuple(HOME_LINES.values()) if relative == HOME else ()
            offenders.extend(quoted_offences(relative, path.read_text(encoding="utf-8"),
                                             allowed))
        self.assertGreater(len(files), PY_FILE_FLOOR,
                           "the walk read %d files; it is not the tree" % len(files))
        self.assertEqual([], offenders,
                         "a second home of a key stands in the source tree:\n"
                         + "\n".join(offenders))

    def test_the_walk_reports_a_planted_copy(self):
        planted = ('def pot_row(ball):\n'
                   '    return {"nearest_pocket": ball["pocket"], '
                   '"pocket_dist_mm": 12}\n')
        offenders = quoted_offences("src/planted.py", planted)
        self.assertEqual(2, len(offenders), offenders)
        self.assertIn("src/planted.py:2:", offenders[0])
        self.assertIn("nearest_pocket", offenders[0])
        self.assertIn("pocket_dist_mm", offenders[1])

    def test_the_walk_accepts_the_home_spelling(self):
        planted = ('def pot_row(ball):\n'
                   '    return {NEAREST_POCKET_KEY: ball["pocket"], '
                   'POCKET_DIST_MM_KEY: 12}\n')
        self.assertEqual([], quoted_offences("src/planted.py", planted),
                         "the home spelling counts as a bare literal")
        self.assertEqual([(2, "dict"), (2, "dict")],
                         name_sites(planted, "src/planted.py"))


if __name__ == "__main__":
    unittest.main()
