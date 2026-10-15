"""The scan folder name ``scan30`` has one home: ``src/datasets.py:38``.

Round 112 found the folder name of the built-in recording spelled again and again.  An
AST walk of ``src/*.py`` and ``annotator/*.py`` (this file, at the measured commit)
answered 14 code constants equal to ``scan30``: one row of the registry and 13 readers
of the row.  A rename of the folder then needed one edit at each site, and a site that
missed the edit opened another folder -- or read a scan that the tool never wrote.

The home is the ``vod30`` row of :data:`src.datasets.STATIC`::

    src/datasets.py:38: STATIC = {BUILT_IN_DATASET: ("scan30", "vod_30min_260815.mp4"),
          src/datasets.py:40: STATIC_OUT = {key: value[0] for key, value in STATIC.items()}

:data:`src.datasets.STATIC_OUT` already publishes the mapping ``id -> scan folder``, and
``src/datasets.py:40`` reads the row, so ``STATIC_OUT["vod30"] == "scan30"``.  Every
former site now reads that mapping.  A module that fixes the dataset spells the key
(``STATIC_OUT[BUILT_IN_DATASET]``); a module that takes the dataset as a parameter
spells the parameter (``STATIC_OUT[dataset]``).

The 13 former sites of this round::

    src/calib_mapping_audit.py:80        src/motion_scan.py:1261
    src/eval_faces.py:78                 src/motion_scan.py:1541
    src/eval_faces.py:174                src/motion_scan.py:1889
    src/motion_scan.py:323               src/motion_scan.py:2345
    src/motion_scan.py:995               src/rebuild_events_calibrated.py:78
    src/motion_scan.py:1044             src/rebuild_events_v2.py:51
    src/motion_scan.py:1050

Two sites keep the word inside a longer path, and neither one is a copy of the folder
name: ``src/eval_faces.py:95`` holds ``"out/scan30/annotations.json"`` in
:data:`src.eval_faces.PROTECTED`, a frozen list of paths that another owner test pins,
and ``src/motion_scan.py:1556`` holds the word in the text of a report.  This guard
counts a string constant equal to ``scan30``, so those two stay out of the count.

The walk below reads every python file of ``src/**/*.py`` and ``annotator/*.py``, drops
the string node of a module, class or function docstring, and answers every code
constant equal to ``scan30`` that is not the home.  Measured 2026-10-14, Python 3.14.6:
111 files parsed, one site -- ``src/datasets.py:38``.  Two floors keep a walk that read
nothing from passing in silence.

Run: ``./scripts/pool-test.sh python test_scan_folder_owner``
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

#: The shipped name of the scan folder of the built-in recording.  The guard spells it
#: once, so a case can pin the row, the mapping and the 13 readers against it.
SHIPPED_FOLDER = "scan30"
#: The home module, the row that holds the folder, and the line of the statement.
HOME = "src/datasets.py"
HOME_LINE = 38
HOME_FORM = 'STATIC = {BUILT_IN_DATASET: ("%s", "vod_30min_260815.mp4"),' % SHIPPED_FOLDER
#: The mapping the row feeds, the line of its own statement, and the comment above it.
MAP_NAME = "STATIC_OUT"
MAP_LINE = 41
MAP_COMMENT_LINE = 40
MAP_FORM = "{key: value[0] for key, value in STATIC.items()}"
#: The key a module uses when the dataset is fixed.
KEY_NAME = "BUILT_IN_DATASET"
#: The 13 former sites, each pinned by file, line and the exact statement text of the
#: worktree after this round.  The line numbers of the brief predate round 111, which
#: inserted one import line in several files; every number below is a fresh measure.
READERS = {
    "src/calib_mapping_audit.py": [
        (80, 'CANDIDATES = ROOT / "out" / %s[%s] / CANDIDATES_NAME'
         % (MAP_NAME, KEY_NAME))],
    "src/eval_faces.py": [
        (78, '%s: (media_relpath(REPO, %s), %s[%s], 1280),'
         % (KEY_NAME, KEY_NAME, MAP_NAME, KEY_NAME)),
        (174, 'for name in (scan_dir, %s[%s]):' % (MAP_NAME, KEY_NAME))],
    "src/motion_scan.py": [
        (324, '[root / "out" / %s[dataset]] if dataset == %s else []) + ['
         % (MAP_NAME, KEY_NAME)),
        (996, 'for name in ([%s[dataset]] if dataset == %s else []) + [f"scan_{dataset}",'
         % (MAP_NAME, KEY_NAME)),
        (1045, 'raw = root / "out" / %s[dataset] / "raw_candidates.json"'
         % MAP_NAME),
        (1051, 'tv = root / "out" / %s[dataset] / "timing_verify.json"' % MAP_NAME),
        (1262, 'path = Path(root) / "out" / %s[%s] / "timing_verify.json"'
         % (MAP_NAME, KEY_NAME)),
        (1542, 'base = root / "out" / %s[%s] / "frame_results"'
         % (MAP_NAME, KEY_NAME)),
        (1890, 'names = ([%s[dataset]] if dataset == %s else []) + [f"scan_{dataset}"]'
         % (MAP_NAME, KEY_NAME)),
        (2346, 'names = ([%s[dataset]] if dataset == %s else []) + [f"scan_{dataset}",'
         % (MAP_NAME, KEY_NAME))],
    "src/rebuild_events_calibrated.py": [
        (83, 'recs = _j.load(open(ROOT.parent / "out" / %s[%s] / RECORDS_NAME))'
         % (MAP_NAME, KEY_NAME))],
    "src/rebuild_events_v2.py": [
        (51, 'SCAN = ROOT.parent / "out" / %s[%s]' % (MAP_NAME, KEY_NAME))],
}
#: The modules of the 13 sites, so a case can hold the list and the table together.
READER_MODULES = ("src/calib_mapping_audit.py", "src/eval_faces.py", "src/motion_scan.py",
                  "src/rebuild_events_calibrated.py", "src/rebuild_events_v2.py")
#: The import line each reader needs, and the module that publishes the mapping.
IMPORT_FORM = "from src.datasets import"
PUBLISHER = "src/datasets.py"
#: The directories the walk reads, and the floors that keep a vacuous walk from passing.
PY_WALKED = ("src/**/*.py", "annotator/*.py")
PY_FILE_FLOOR = 100
SCANNED_FLOOR = 95
#: The one site of the folder that is no copy: the row of the registry.
ALLOWED = {HOME: (HOME_LINE,)}
#: The probes, each run in a fresh interpreter of this venv.  The first proves that the
#: mapping answers the name, the second that the 13 former sites compute their old paths.
MAP_PROBE = ("import src.datasets as module; "
             "print(repr(module.%s[module.%s]))" % (MAP_NAME, KEY_NAME))
PATH_PROBE = (
    "import src.datasets as ds\n"
    "import src.calib_mapping_audit as cma\n"
    "import src.rebuild_events_v2 as rv2\n"
    "import src.rebuild_events_calibrated as rec\n"
    "import src.motion_scan as ms\n"
    "import src.eval_faces as ef\n"
    "print(ds.%s[ds.%s])\n" % (MAP_NAME, KEY_NAME) +
    "print(cma.CANDIDATES.name)\n"
    "print(rv2.SCAN.name)\n"
    "print(rec.ROOT.parent / 'out' / ds.%s[ds.%s])\n" % (MAP_NAME, KEY_NAME) +
    "print(ms.events_for(ds.%s).name)\n" % KEY_NAME +
    "print(ef.DATASETS[ds.%s][1])\n" % KEY_NAME)
#: A planted module of the honesty case: the copy is a code constant, and the two other
#: mentions are prose and a read of the key.
PLANTED = "src/planted.py"
PLANTED_LINES = (
    '"""A planted module that names the scan folder scan30 in its docstring."""',
    "import src.datasets as registry",
    "",
    "",
    "class Row:",
    '    """A planted class docstring that names scan30, and is no constant."""',
    "",
    "    def folder(self):",
    '        """A planted method docstring that names scan30, and is no constant."""',
    '        return {"scan": "%s", "row": registry.%s[registry.%s]}'
    % (SHIPPED_FOLDER, MAP_NAME, KEY_NAME),
)
PLANTED_COPY_LINE = 10
PLANTED_TEXT = "\n".join(PLANTED_LINES) + "\n"
#: A planted module that holds no copy: it reads the mapping, and its prose names the
#: folder, so the walk must stay quiet.
QUIET = "src/quiet.py"
QUIET_TEXT = ('"""A planted module that names the scan folder scan30 in prose only."""\n'
              "import src.datasets as registry\n"
              "\n"
              "\n"
              "def row():\n"
              '    """The docstring names scan30, which is no code constant."""\n'
              "    return {registry.%s[registry.%s]: 1}\n" % (MAP_NAME, KEY_NAME))


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

    The docstring of a module, a class, a function and an async function is prose.  A
    sentence of a docstring may name the folder; it is no code constant.
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


def literal_sites(relative: str, text: str, allowed_lines=()) -> list:
    """Every ``(path, line, text)`` of one file that spells the folder as a constant.

    A string node of a docstring is no code constant, and a comment is no node at all,
    so prose is out of the count by construction.  A line of ``allowed_lines`` is the
    home of the file, and the home may spell the folder.  Every other spelling equal to
    ``scan30`` is a copy.  A longer string that holds the word -- a path such as
    ``out/scan30/annotations.json`` -- is no copy of the folder name, and stays out.
    """
    tree = parsed_tree(relative, text)
    prose = docstring_nodes(tree)
    lines = text.splitlines()
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value != SHIPPED_FOLDER or id(node) in prose:
            continue
        if node.lineno in allowed_lines:
            continue
        found.append((relative, node.lineno, line_text(lines, node.lineno)))
    return sorted(found)


def copy_reports(sites) -> list:
    """One report per copying site, so every message names ``path:line`` and the text."""
    return [report(where, number, text,
                   "%r is a second home of the scan folder; read %s[%s] of %s"
                   % (SHIPPED_FOLDER, MAP_NAME, KEY_NAME, HOME))
            for where, number, text in sites]


def py_files(root: Path) -> list:
    """Every python file of the walk scope under one tree, the caches dropped."""
    files = []
    for pattern in PY_WALKED:
        files.extend(sorted(root.glob(pattern)))
    return [path for path in files if "__pycache__" not in path.parts]


def scanned(root: Path) -> list:
    """Every file the walk parses, as ``(relative, path)``."""
    return [(path.relative_to(root).as_posix(), path) for path in py_files(root)]


def walk_sites(root: Path, allowed=ALLOWED) -> list:
    """Every code constant of one tree that spells the folder outside the home."""
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
                          capture_output=True, text=True, timeout=600)
    if done.returncode != 0:
        raise AssertionError("the probe %r failed:\n%s" % (code, done.stderr))
    return done.stdout.strip()


def home_row() -> str:
    """The text of the ``vod30`` row of the registry, from the shipped text."""
    for line in source_lines(HOME):
        if line.startswith("STATIC = {"):
            return line.rstrip()
    return ""


def reader_lines(relative: str) -> list:
    """The lines of one reader that read the mapping, with their numbers."""
    found = []
    for number, text in enumerate(source_lines(relative), start=1):
        if MAP_NAME + "[" in text:
            found.append((number, text.strip()))
    return found


class HomeTests(unittest.TestCase):
    """The one home of the scan folder, and the mapping it feeds."""

    def test_the_row_carries_the_shipped_folder(self):
        """The ``vod30`` row of the registry holds the shipped scan folder."""
        found = home_row()
        self.assertEqual(HOME_FORM, found,
                         report(HOME, HOME_LINE, found,
                                "the row must read %r, and it reads %r"
                                % (HOME_FORM, found)))

    def test_the_mapping_reads_the_row(self):
        """``STATIC_OUT`` derives every scan folder from the ``STATIC`` row."""
        lines = source_lines(HOME)
        text = line_text(lines, MAP_LINE)
        self.assertIn(MAP_NAME + " = " + MAP_FORM, text,
                      report(HOME, MAP_LINE, text,
                             "the mapping must read %r, and it reads %r"
                             % (MAP_FORM, text.strip())))
        comment = line_text(lines, MAP_COMMENT_LINE)
        self.assertTrue(comment.lstrip().startswith("#"),
                        report(HOME, MAP_COMMENT_LINE, comment,
                               "the line above the mapping is no comment"))

    def test_the_mapping_binds_the_shipped_folder(self):
        """A fresh interpreter answers ``STATIC_OUT['vod30']`` equal to the folder."""
        self.assertEqual(repr(SHIPPED_FOLDER), run_probe(MAP_PROBE),
                         "the import of the home does not bind %s[%s] to %r"
                         % (MAP_NAME, KEY_NAME, SHIPPED_FOLDER))


class WalkTests(unittest.TestCase):
    """The walk of the tree, with its floors and its planted proofs."""

    def test_no_file_spells_the_folder_again(self):
        """One home, and every other code constant of the folder is an offender."""
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
                         "a second home of the scan folder stands in the tree:\n"
                         + "\n".join(offenders))

    def test_the_walk_answers_the_row_as_the_one_site(self):
        """The walk of the tree answers one constant, and it is the home row."""
        found = walk_sites(ROOT, allowed={})
        self.assertEqual([(HOME, HOME_LINE, HOME_FORM)], found,
                         "the walk answers %s, not the home alone" % (found,))

    def test_the_walk_names_a_planted_copy(self):
        """Honesty: a copy in another tree becomes an offender, named by line."""
        with tempfile.TemporaryDirectory(prefix="scan_folder_owner_") as folder:
            root = write_tree(Path(folder), {PLANTED: PLANTED_TEXT})
            offenders = walk_offences(root, allowed={})
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("%s:%d:" % (PLANTED, PLANTED_COPY_LINE), offenders[0])
        self.assertIn('"scan": "scan30"', offenders[0])

    def test_the_walk_leaves_a_docstring_mention_alone(self):
        """A docstring that names the folder is prose, and no offender."""
        with tempfile.TemporaryDirectory(prefix="scan_folder_owner_") as folder:
            root = write_tree(Path(folder), {QUIET: QUIET_TEXT})
            offenders = walk_offences(root, allowed={})
        self.assertEqual([], offenders,
                         "the walk counts a docstring as a constant:\n"
                         + "\n".join(offenders))

    def test_the_walk_leaves_a_read_of_the_mapping_alone(self):
        """A file that reads the mapping spells no copy, so the walk is quiet."""
        text = '"""A planted module that names the scan folder scan30 in prose."""\n' \
               "import src.datasets as registry\n" \
               "VALUE = {registry.%s[registry.%s]: 1}\n" % (MAP_NAME, KEY_NAME)
        self.assertEqual([], copy_reports(literal_sites(PLANTED, text)),
                         "the walk counts a read of the mapping as a copy")


class ReaderTests(unittest.TestCase):
    """The 13 former sites, each one pinned to a read of the mapping."""

    def test_the_reader_table_names_the_five_modules(self):
        """The table of the former sites covers the five modules, and no other."""
        self.assertEqual(list(READER_MODULES), sorted(READERS),
                         "the table of the former sites drifted from its modules")

    def test_every_former_site_reads_the_mapping(self):
        """Each former site carries the pinned statement, at the pinned line."""
        offenders = []
        for relative, sites in sorted(READERS.items()):
            lines = source_lines(relative)
            for number, form in sites:
                found = line_text(lines, number).strip()
                if found != form:
                    offenders.append(report(relative, number, found,
                                            "the site must read %r" % form))
        self.assertEqual([], offenders,
                         "a former site of the scan folder drifted from the mapping:\n"
                         + "\n".join(offenders))

    def test_every_reader_imports_the_mapping(self):
        """Each reader holds an import of the module that publishes the mapping.

        The edge may be one line (``from src.datasets import ... STATIC_OUT``) or a
        parenthesised list over several lines, so the case reads the whole text of the
        module and not one line of it.
        """
        offenders = []
        for relative in READER_MODULES:
            text = source_text(relative)
            if IMPORT_FORM not in text or not re.search(r"\b%s\b" % MAP_NAME, text):
                offenders.append(report(relative, 1, line_text(source_lines(relative), 1),
                                        "the module holds no %s ... %s edge"
                                        % (IMPORT_FORM, MAP_NAME)))
        self.assertEqual([], offenders,
                         "a reader of the mapping does not import it:\n"
                         + "\n".join(offenders))

    def test_every_reader_reads_the_mapping(self):
        """Every reader reads the mapping at least once, at the pinned count."""
        offenders = []
        for relative, sites in sorted(READERS.items()):
            found = reader_lines(relative)
            if len(found) < len(sites):
                offenders.append(report(relative, 1, "",
                                        "the module reads the mapping at %d lines; the "
                                        "table names %d sites"
                                        % (len(found), len(sites))))
        self.assertEqual([], offenders,
                         "a reader of the mapping reads it nowhere:\n"
                         + "\n".join(offenders))

    def test_the_former_sites_compute_the_shipped_paths(self):
        """A fresh interpreter answers the five old paths through the mapping."""
        expected = "\n".join([
            SHIPPED_FOLDER,
            "candidates_selected.json",
            SHIPPED_FOLDER,
            str(ROOT / "out" / SHIPPED_FOLDER),
            "events.json",
            SHIPPED_FOLDER,
        ])
        self.assertEqual(expected, run_probe(PATH_PROBE),
                         "a former site of the scan folder computes another path: %r"
                         % (run_probe(PATH_PROBE),))


if __name__ == "__main__":
    unittest.main()
