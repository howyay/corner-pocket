"""The id of the built-in recording ``vod30`` has one home: ``src/datasets.py:36``.

Round 111 found the id spelled again and again.  The round walk measured
``git grep -F 'vod30' -- src annotator tools scripts``: 268 lines in 64 files, and 110
quoted literals in 55 files.  The python lane was 11 shipped modules, each carrying the
id as a bare argument: ``src/motion_scan.py`` at 14 sites, ``annotator/unified_server.py``
at 12 sites, and nine modules below them.  A rename of the recording then needed one edit
at each site, and a site that missed the edit opened another folder or another media file.

The home is ``src/datasets.py:36``::

    BUILT_IN_DATASET = "vod30"

The home sits above :data:`STATIC`, because the registry of this module owns every
built-in recording: the module docstring of ``src/datasets.py`` already claims "A
built-in recording therefore has one definition site for its name".  The row below the
home now reads that name and not a second literal::

    src/datasets.py:38: STATIC = {BUILT_IN_DATASET: ("scan30", "vod_30min_260815.mp4"),

The value never moves.  ``out/scan30`` already holds the scans of the recording, the
route paths of the console are ``/api/vod30/...``, and an operator document on disk
carries the word, so a rename of the value is the work of a different round.

Two readers tie the home to the rest of the tree, and this guard pins both of them:

* ``tests/test_datasets.py:206`` measures the corpus ``dataset_id_cases.BUILT_IN``
  (``tests/dataset_id_cases.py:22``) equal to ``datasets.STATIC_OUT``, and the row at
  :38 feeds ``STATIC_OUT``.  A home that moved alone leaves the corpus behind.
* ``tests/test_app_routes_owner.py:39`` holds ``DATASET = 'vod30'`` for the page home.
  A page cannot import a python name, so the console holds its own line
  (``annotator/app.js:64``) and that guard pins the pair; this guard pins the guard.

The walk below reads every python file of ``src/`` and ``annotator/``, skips
``src/sam3/``, drops the string node of a module, class or function docstring, and
answers every code constant equal to ``vod30`` that is not the home.  Measured
2026-10-14, Python 3.14.6: 284 files discovered, 112 parsed, one site -
``src/datasets.py:36``.  Two floors keep a walk that read nothing from passing in
silence.

Run: ``./scripts/pool-test.sh python test_built_in_dataset_owner``
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The shipped id of the built-in recording.  The guard spells it once, so a case can
#: pin it against the home, the row and the two readers.
SHIPPED_ID = "vod30"
#: The home module, the name it holds the id under, and the line of the statement.
HOME = "src/datasets.py"
HOME_NAME = "BUILT_IN_DATASET"
HOME_LINE = 36
HOME_FORM = '%s = "%s"' % (HOME_NAME, SHIPPED_ID)
#: The two comment lines above the home, and the facts they must state.
COMMENT_LINES = (34, 35)
COMMENT_WORDS = ("one home", "built-in", "second copy")
#: The row of the registry that reads the name, pinned by number and text.
ROW_LINE = 38
ROW_FORM = 'STATIC = {%s: ("scan30", "vod_30min_260815.mp4"),' % HOME_NAME
#: The line regex of the definition, for the case that pins the home line.
NAME_RE = re.compile(r"\s*%s\s*=" % HOME_NAME)
#: The python reader of the home, the line that measures the corpus equal to the
#: registry, and the corpus of published names it reads there.
PY_READER = "tests/test_datasets.py"
PY_READER_LINE = 206
PY_READER_FORM = ("self.assertEqual(sorted(dataset_id_cases.BUILT_IN), "
                  "sorted(datasets.STATIC_OUT))")
CORPUS = "tests/dataset_id_cases.py"
CORPUS_NAME = "BUILT_IN"
CORPUS_LINE = 22
#: The page reader of the home: the guard of the console holds the name and the id of
#: the built-in recording, because a page cannot import a python name.
PAGE_READER = "tests/test_app_routes_owner.py"
PAGE_READER_NAME_LINE = 38
PAGE_READER_NAME_FORM = "NAME = '%s'" % HOME_NAME
PAGE_READER_LINE = 39
#: The directories the walk reads, the subtree it skips, and the floors that keep a
#: vacuous walk from passing.
PY_WALKED = ("src/**/*.py", "annotator/*.py", "tools/*.py", "scripts/*.py")
PY_SKIP = ("src/sam3",)
PY_FILE_FLOOR = 200
SCANNED_FLOOR = 100
#: The one site of the id that is no copy: the home itself.
ALLOWED = {HOME: (HOME_LINE,)}
#: The probes, each run in a fresh interpreter of this venv.
BIND_PROBE = "import src.datasets as module; print(repr(module.%s))" % HOME_NAME
ROW_PROBE = ("import src.datasets as module; "
             "print(sorted(module.STATIC_OUT), sorted(module.STATIC))")
#: A planted module of the honesty cases: the copy is a code constant, and the two
#: other mentions are prose and a read of the home name.
PLANTED = "src/planted.py"
PLANTED_LINES = (
    '"""A planted module that names the recording vod30 in its docstring."""',
    "import src.datasets as registry",
    "",
    "",
    "class Row:",
    '    """A planted class docstring that names vod30, and is no constant."""',
    "",
    "    def dataset(self):",
    '        """A planted method docstring that names vod30, and is no constant."""',
    '        return {"dataset": "vod30", "%s": registry.%s}'
    % (HOME_NAME, HOME_NAME),
)
PLANTED_COPY_LINE = 10
PLANTED_TEXT = "\n".join(PLANTED_LINES) + "\n"
#: A planted module that holds no copy of the id: it reads the home name, and its
#: prose names the recording.
QUIET = "src/quiet.py"
QUIET_TEXT = ('"""A planted module that names the recording vod30 in prose only."""\n'
              "import src.datasets as registry\n"
              "\n"
              "\n"
              "def row():\n"
              '    """The docstring names vod30, which is no code constant."""\n'
              "    return {registry.%s: 1}\n" % HOME_NAME)


def source_text(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def line_text(lines: list, number: int) -> str:
    """The text of one line, or the empty text when the file is shorter."""
    return lines[number - 1] if 0 < number <= len(lines) else ""


def report(where: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return "%s:%d: %s  <- %s" % (where, line, (text or "").strip(), why)


def parsed_tree(relative: str, text: str) -> ast.Module:
    """The tree of one file; a file the walk cannot read is a finding of its own."""
    try:
        return ast.parse(text, filename=relative)
    except SyntaxError as error:
        raise AssertionError("%s:%d: the walk cannot parse this file: %s"
                             % (relative, error.lineno or 1, error.msg)) from error


def docstring_nodes(tree: ast.Module) -> set:
    """The identity of every string node that holds a docstring.

    The docstring of a module, a class, a function and an async function is prose.
    A sentence of a docstring may name the recording; it is no code constant.
    """
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            found.add(id(first.value))
    return found


def home_sites() -> list:
    """Every line of the home module that defines the name, with its number."""
    return [(number, text) for number, text in enumerate(source_lines(HOME), start=1)
            if NAME_RE.match(text)]


def home_value() -> str:
    """The value of the home constant, read from the syntax tree of the home.

    The read is a read of the shipped text and not an import, so a case can name the
    value of a home that does not import.  A case below proves the run-time binding in
    a fresh interpreter.
    """
    for node in ast.walk(parsed_tree(HOME, source_text(HOME))):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == HOME_NAME
                for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return ""


def constant_tuple(relative: str, name: str) -> tuple:
    """The tuple a module-level name of one file holds."""
    for node in ast.walk(parsed_tree(relative, source_text(relative))):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets):
            if isinstance(node.value, ast.Tuple):
                return tuple(element.value for element in node.value.elts
                             if isinstance(element, ast.Constant))
    return ()


def literal_sites(relative: str, text: str, allowed_lines=()) -> list:
    """Every ``(path, line, text)`` of one file that spells the id as a code constant.

    A string node of a docstring is no code constant, and a comment is no node at all,
    so prose is out of the count by construction.  A line of ``allowed_lines`` is the
    home of the file, and the home may spell the id.  Every other spelling is a copy.
    """
    tree = parsed_tree(relative, text)
    prose = docstring_nodes(tree)
    lines = text.splitlines()
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value != SHIPPED_ID or id(node) in prose:
            continue
        if node.lineno in allowed_lines:
            continue
        found.append((relative, node.lineno, line_text(lines, node.lineno)))
    return sorted(found)


def copy_reports(sites) -> list:
    """One report per copying site, so every message names ``path:line`` and the text."""
    return [report(where, number, text,
                   "%r is a second copy of the id; read %s of %s"
                   % (SHIPPED_ID, HOME_NAME, HOME))
            for where, number, text in sites]


def py_files(root: Path) -> list:
    """Every python file of the walk scope under one tree, the caches dropped."""
    files = []
    for pattern in PY_WALKED:
        files.extend(sorted(root.glob(pattern)))
    return [path for path in files if "__pycache__" not in path.parts]


def scanned(root: Path) -> list:
    """Every file the walk parses, as ``(relative, path)``.  ``src/sam3`` stays out."""
    found = []
    for path in py_files(root):
        relative = path.relative_to(root).as_posix()
        if any(relative == skip or relative.startswith(skip + "/") for skip in PY_SKIP):
            continue
        found.append((relative, path))
    return found


def walk_sites(root: Path, allowed=ALLOWED) -> list:
    """Every code constant of one tree that spells the id outside the home."""
    found = []
    for relative, path in scanned(root):
        found.extend(literal_sites(
            relative, path.read_text(encoding="utf-8", errors="replace"),
            allowed.get(relative, ())))
    return sorted(found)


def walk_offences(root: Path, allowed=ALLOWED) -> list:
    """The walk of one tree, as one report per copying site."""
    return copy_reports(walk_sites(root, allowed))


def write_tree(root: Path, files: dict) -> Path:
    """Plant one small tree of source files under a temporary folder."""
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def run_probe(code: str) -> str:
    """The stdout of one probe, run in a fresh interpreter of this venv."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise AssertionError("the probe %r failed:\n%s" % (code, done.stderr))
    return done.stdout.strip()


class HomeTests(unittest.TestCase):
    """The one home of the id, and the row that reads it."""

    def test_the_home_names_the_shipped_id(self):
        """The constant of the home is the id of the built-in recording."""
        self.assertEqual(SHIPPED_ID, home_value(),
                         report(HOME, HOME_LINE, source_lines(HOME)[HOME_LINE - 1],
                                "the home holds another id than %r" % SHIPPED_ID))

    def test_the_home_line_carries_the_shipped_id(self):
        """One line defines the name, at the pinned number, with the pinned text."""
        lines = source_lines(HOME)
        found = home_sites()
        offenders = [report(HOME, number, text, "the home line must read %r" % HOME_FORM)
                     for number, text in found if text != HOME_FORM]
        if not found:
            offenders.append(report(HOME, HOME_LINE, lines[HOME_LINE - 1],
                                    "no line of the module defines %s" % HOME_NAME))
        elif [number for number, _ in found] != [HOME_LINE]:
            offenders.append(report(HOME, HOME_LINE, lines[HOME_LINE - 1],
                                    "the home lies at %s, not %d"
                                    % ([number for number, _ in found], HOME_LINE)))
        self.assertEqual([], offenders,
                         "the home of the id moved:\n" + "\n".join(offenders))

    def test_the_comment_above_the_home_names_the_rule(self):
        """The two comment lines state what the id names and that a copy is the defect."""
        lines = source_lines(HOME)
        text = " ".join(line_text(lines, number) for number in COMMENT_LINES)
        offenders = [report(HOME, number, line_text(lines, number),
                            "the comment above the home does not say %r; it says %r"
                            % (word, text))
                     for word in COMMENT_WORDS if word not in text]
        offenders.extend(report(HOME, number, line_text(lines, number),
                                "the line above the home is no comment")
                         for number in COMMENT_LINES
                         if not line_text(lines, number).lstrip().startswith("#"))
        self.assertEqual([], offenders,
                         "the comment above the home does not hold:\n"
                         + "\n".join(offenders))

    def test_the_registry_row_reads_the_name(self):
        """The STATIC row of the registry keys the recording by the home name."""
        lines = source_lines(HOME)
        found = line_text(lines, ROW_LINE).strip()
        self.assertEqual(ROW_FORM, found,
                         report(HOME, ROW_LINE, line_text(lines, ROW_LINE),
                                "the row must read %r, and it reads %r"
                                % (ROW_FORM, found)))

    def test_the_home_binds_the_name_at_run_time(self):
        """A fresh interpreter answers the shipped id of the built-in recording."""
        self.assertEqual(repr(SHIPPED_ID), run_probe(BIND_PROBE),
                         "the import of the home does not bind %s to %r"
                         % (HOME_NAME, SHIPPED_ID))

    def test_the_registry_row_serves_the_shipped_id(self):
        """The registry is keyed by the id of the home, so the row read the name."""
        self.assertEqual("['highlight', %r] ['highlight', %r]" % (SHIPPED_ID, SHIPPED_ID),
                         run_probe(ROW_PROBE).replace('"', "'"),
                         "the registry rows are not keyed by the id of the home")


class WalkTests(unittest.TestCase):
    """The walk of the tree, with its floors and its planted proofs."""

    def test_no_file_spells_the_id_again(self):
        """One home, and every other code constant of the id is an offender."""
        files = py_files(ROOT)
        self.assertGreater(len(files), PY_FILE_FLOOR,
                           "the walk discovered %d python files; it is not the tree"
                           % len(files))
        rows = scanned(ROOT)
        self.assertGreater(len(rows), SCANNED_FLOOR,
                           "the walk parsed %d python files; it is not the tree"
                           % len(rows))
        offenders = walk_offences(ROOT)
        self.assertEqual([], offenders,
                         "a second home of the id stands in the tree:\n"
                         + "\n".join(offenders))

    def test_the_walk_answers_the_home_as_the_one_site(self):
        """The walk of the tree answers one constant, and it is the home line."""
        found = walk_sites(ROOT, allowed={})
        self.assertEqual([(HOME, HOME_LINE, HOME_FORM)], found,
                         "the walk answers %s, not the home alone" % (found,))

    def test_the_walk_names_a_planted_copy(self):
        """Honesty: a copy in another tree becomes an offender, named by line."""
        with tempfile.TemporaryDirectory(prefix="built_in_owner_") as folder:
            root = write_tree(Path(folder), {PLANTED: PLANTED_TEXT})
            offenders = walk_offences(root, allowed={})
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("%s:%d:" % (PLANTED, PLANTED_COPY_LINE), offenders[0])
        self.assertIn('"dataset": "vod30"', offenders[0])

    def test_the_walk_leaves_a_docstring_mention_alone(self):
        """A docstring that names the recording is prose, and no offender."""
        with tempfile.TemporaryDirectory(prefix="built_in_owner_") as folder:
            root = write_tree(Path(folder), {QUIET: QUIET_TEXT})
            offenders = walk_offences(root, allowed={})
        self.assertEqual([], offenders,
                         "the walk counts a docstring as a constant:\n"
                         + "\n".join(offenders))

    def test_the_walk_leaves_a_read_of_the_name_alone(self):
        """A file that reads the home name spells no copy, so the walk is quiet."""
        text = '"""A planted module that names the recording vod30 in prose."""\n' \
               "import src.datasets as registry\n" \
               "VALUE = {registry.%s: 1}\n" % HOME_NAME
        self.assertEqual([], copy_reports(literal_sites(PLANTED, text)),
                         "the walk counts a read of the home name as a copy")


class ReaderTests(unittest.TestCase):
    """The two readers of the home, and the pair each one pins."""

    def test_the_python_suite_compares_the_corpus_with_the_registry(self):
        """The line of the corpus case, the corpus itself, and the value of the home."""
        lines = source_lines(PY_READER)
        value = home_value()
        corpus = constant_tuple(CORPUS, CORPUS_NAME)
        offenders = []
        if line_text(lines, PY_READER_LINE).strip() != PY_READER_FORM:
            offenders.append(report(PY_READER, PY_READER_LINE,
                                    line_text(lines, PY_READER_LINE),
                                    "the case must read %r" % PY_READER_FORM))
        if SHIPPED_ID not in corpus:
            offenders.append(report(CORPUS, CORPUS_LINE, source_lines(CORPUS)[CORPUS_LINE - 1],
                                    "the corpus holds %s, not the id of the home %r"
                                    % (list(corpus), SHIPPED_ID)))
        if value != SHIPPED_ID:
            offenders.append(report(HOME, HOME_LINE, source_lines(HOME)[HOME_LINE - 1],
                                    "the home holds %r, and the corpus still pins %r"
                                    % (value, SHIPPED_ID)))
        self.assertEqual([], offenders,
                         "the corpus and the registry row drifted apart:\n"
                         + "\n".join(offenders))

    def test_the_page_guard_pins_the_id_of_the_console(self):
        """The page guard holds the name of the home and the id the home holds."""
        lines = source_lines(PAGE_READER)
        value = home_value()
        offenders = []
        for number, form in ((PAGE_READER_NAME_LINE, PAGE_READER_NAME_FORM),
                             (PAGE_READER_LINE, "DATASET = '%s'" % value)):
            if line_text(lines, number).strip() != form:
                offenders.append(report(PAGE_READER, number, line_text(lines, number),
                                        "the page guard must read %r" % form))
        if value != SHIPPED_ID:
            offenders.append(report(HOME, HOME_LINE, source_lines(HOME)[HOME_LINE - 1],
                                    "the home holds %r, and the page guard pins %r"
                                    % (value, SHIPPED_ID)))
        self.assertEqual([], offenders,
                         "the page guard and the home drifted apart:\n"
                         + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
